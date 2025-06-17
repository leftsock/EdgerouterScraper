#!/usr/bin/python3
"""Scrape edgerouter via ssh commands

Archive config once a minute into Logs/YYYY/YYYYmmdd-HHMMSS

Publish prometheus metrics on port 8000:
  reachable{group= interface=eth[0-4] is={true,false}}
  status{group= interface=eth[0-4] is={failover,active,inactive}}
The metrics are split out into every permutation to make boolean graphs
and alerts easier to understand.
"""

import argparse
import datetime
import logging
import os
import signal
import threading
import time

import prometheus_client
import poll


METRICS = {
  'reachable': prometheus_client.Gauge('reachable', 'is the interface reachable?', ['group', 'interface', 'is']),
  'status': prometheus_client.Gauge('status', 'is the interface active?', ['group', 'interface', 'is']),
}

# TODO: Create a prometheus metric to track time spent and requests made.
##REQUEST_TIME = prometheus_client.Summary('request_processing_seconds', 'Time spent processing request')
##
### Decorate function with metric.
##@REQUEST_TIME.time()
##def process_request(t):
##  """A dummy function that takes some time."""
##  time.sleep(t)


class Processor(threading.Thread):

  def __init__(self, ip, **kwargs):
    super().__init__(**kwargs)
    self._ip = ip
    self._pid = None
    self.load_balance = None

  def run(self):
    logging.debug('Processor.run')
    c = poll.SshConnection(self._ip)
    self.load_balance = poll.ShowLoadBalanceStatus(c)
    self.load_balance.Run(callback=self.setPid)
    logging.debug('Processor.run end')

  def setPid(self, pid):
    self._pid = pid

  def kill(self):
    try:
      os.kill(self._pid, signal.SIGINT)
    except ProcessLookupError:
      pass
    time.sleep(3)
    try:
      os.kill(self._pid, signal.SIGKILL)
    except ProcessLookupError:
      pass
    

class Archiver(threading.Thread):
  """Archive the config if different."""

  # TODO: push config into rcs, publish the version #

  def __init__(self, ip, logdir, **kwargs):
    super().__init__(**kwargs)
    self._ip = ip
    self._logdir = logdir

  def run(self):
    logging.debug('Archiver.run')
    c = poll.SshConnection(self._ip)
    # download the config
    conf = poll.ShowConfig(c)
    conf.Run()
    now = time.time()
    dt = datetime.datetime.fromtimestamp(now)
    latest_fn = os.path.join(self._logdir, 'latest')
    try:
      with open(latest_fn, 'r') as fh:
        old_config = fh.read()
    except FileNotFoundError:
      old_config = ''
    new_config = str(conf)
    if old_config == new_config:
      return
    new_fn = '%04d%02d%02d-%02d%02d%02d' % (dt.year, dt.month, dt.day, dt.hour, dt.minute, dt.second)
    new_dir = os.path.join(self._logdir, '%04d' % dt.year)
    try:
      os.mkdir(new_dir)
    except FileExistsError:
      pass  # dir already exists
    if not new_config:  # don't write 0 byte files
      return
    new_dirfn = os.path.join(self._logdir, '%04d' % dt.year, new_fn)
    with open(new_dirfn, 'w') as fh:
      fh.write(new_config)
    new_yearfn = os.path.join('%04d' % dt.year, new_fn)
    try:
      os.symlink(new_yearfn, latest_fn)
    except FileExistsError:
      os.unlink(latest_fn)
      os.symlink(new_yearfn, latest_fn)
    logging.debug('Archiver.run end')


def _publishMetrics(name, labels, allowed, status, uninitializedMetrics):
  if uninitializedMetrics:
    for state in allowed:
      labels['is'] = state
      METRICS[name].labels(**labels).set(-2)
  if status not in allowed:
    logging.error('ERR: unknown status=%s on %s', status, labels)
    for state in allowed:
      labels['is'] = state
      METRICS[name].labels(**labels).set(-1)  # is there a undefined instead? or publish nothing?
  else:
    for state in allowed:
      labels['is'] = state
      if status == state:
        METRICS[name].labels(**labels).set(1)
      else:
        METRICS[name].labels(**labels).set(0)
  logging.debug('publish %s %s', name, labels)


if __name__ == '__main__':
  logging.basicConfig(filename='log', level=logging.INFO)

  # TODO: use gateway as default router
  # e.g. netstat -nr | egrep '^0.0.0.0 ' -> "0.0.0.0         10.0.0.1     0.0.0.0         UG        0 0          0 en0"
  # new hotness: ip route show default -> "default via 10.0.0.1 dev en0 proto static\n"
  # N.B.: multiple network interfaces (i.e. ethernet and wifi) causes multiple lines returned
  parser = argparse.ArgumentParser(description='Extract edgerouter status')
  parser.add_argument('--ip', default='EdgeRouterScraper', help='IP address of the router; default=EdgeRouterScraper')
  args = parser.parse_args()

  # check the config at intervals
  config_t = 0  # check config right away

  # Start up the server to expose the metrics.
  uninitializedMetrics = True
  prometheus_client.start_http_server(8000)
  logging.debug('Started prometheus stats publishing on :8000')
  # Generate some requests.
  while True:
    t = Processor(args.ip)
    t.start()
    now = time.time()
    if now - config_t > 3600:
      tc = Archiver(args.ip, 'Logs/')
      tc.start()
      tc.join(timeout=30)
      if tc.is_alive():
        tc.kill()
      else:
        logging.debug('Archiver success')
      config_t = now
    t.join(timeout=50)
    if t.is_alive():
      t.kill()
    else:
      # TODO: productionize _d; stop being a private
      #print(t.load_balance._d)
      logging.debug('Processor success, harvesting data')
      for g in t.load_balance._d._groups:
        for interface in g._interfaces:
          labels = {'group':g._name, 'interface':interface._name}
          _publishMetrics(
              'reachable', labels,
              ('true', 'false'), interface._reachable,
              uninitializedMetrics)
          labels = {'group':g._name, 'interface':interface._name}
          _publishMetrics(
              'status', labels,
              ('active', 'inactive', 'failover'), interface._status,
              uninitializedMetrics)
          uninitializedMetrics = False

    remainder = 60 - (time.time() % 60)
    logging.debug('sleep(%s)', int(remainder))
    #time.sleep(5)
    time.sleep(remainder)
