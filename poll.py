#!/usr/bin/python3

import os
import re
import subprocess
import sys

class SshConnection(object):

  def __init__(self, addr):
    self._addr = addr

  def Run(self, cmd, callback=None):
    command = ['/usr/bin/ssh',
               '-o', 'NumberOfPasswordPrompts=0',  # never prompt for a password when ssh with key fails.
               '-n', self._addr]
    command.extend(cmd)
    h = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.DEVNULL)
    if callback:
      callback(h.pid)
    out, err = h.communicate()
#    if err:
#      print('===== begin stderr =====')
#      print(err.decode('utf-8'))
#      print('===== end stderr =====')
    return out, err


class LoadBalance(object):

  def __init__(self):
    self._groups = []

  def __str__(self):
    out = []
    for g in self._groups:
      out.append(str(g))
    return '\n'.join(out)


def truefalse(b):
  if b:
    return 'true'
  return 'false'

class LoadBalanceGroup(object):

  def __init__(self, name):
    self._name = name
    self._balanceLocal = None
    self._lockLocalDNS = None
    self._conntrackFlush = None
    self._stickyBits = None
    self._interfaces = []

  def __str__(self):
    out = [
        'Group %s' % self._name,
        '    Balance Local  : %s' % self._balanceLocal,
        '    Local Lock DNS : %s' % self._lockLocalDNS,
        '    Conntrack Flush: %s' % self._conntrackFlush,
        '    Sticky Bits    : %s' % self._stickyBits,
        ''
      ]
    for i in self._interfaces:
      out.append(str(i))
    return '\n'.join(out)


class LoadBalanceGroupInterface(object):

  def __init__(self, name):
    self._name = name
    self._reachable = None
    self._status = None
    self._gateway = None
    self._routeTable = None
    self._weight = None
    self._foPriority = None
    self._flows = []

  def __str__(self):
    out = [
        '  interface   : %s' % self._name,
        '  reachable   : %s' % self._reachable,
        '  status      : %s' % self._status,
        '  gateway     : %s' % self._gateway,
        '  route table : %s' % self._routeTable,
        '  weight      : %s' % self._weight,
        '  fo_priority : %s' % self._foPriority,
      ]
    out.append(str(self._flows))
    return '\n'.join(out)


class LoadBalanceGroupInterfaceFlows(object):

  def __init__(self):
    self._wanOut = None
    self._wanIn = None
    self._localIcmp = None
    self._localDns = None
    self._localData = None

  def __str__(self):
    out = [
        '  flows',
        '      WAN Out   : %s' % self._wanOut,
        '      WAN In    : %s' % self._wanIn,
        '      Local ICMP: %s' % self._localIcmp,
        '      Local DNS : %s' % self._localDns,
        '      Local Data: %s' % self._localData,
        ''
      ]
    return '\n'.join(out)


class ShowLoadBalanceStatus(object):

  def __init__(self, conn):
    self._conn = conn
    self._d = LoadBalance()

  def Run(self, callback=None):
    out, err = self._conn.Run(
        ['/usr/sbin/ubnt-hal', 'wlbGetStatus'], callback=callback)
    current_group = None
    current_interface = None
    current_flows = None
    for line in out.decode('utf-8').split('\n'):
      m = re.match(r'^Group (.*)', line)
      if m:
        n = LoadBalanceGroup(m.group(1))
        self._d._groups.append(n)
        current_group = n
        current_interface = None
        current_flows = None
        continue
      if current_group:
        m = re.match(r'^    Balance Local  : (true|false)', line)
        if m:
          current_group._balanceLocal = m.group(1)
          continue
        m = re.match(r'^    Lock Local DNS : (true|false)', line)
        if m:
          current_group._lockLocalDNS = m.group(1)
          continue
        m = re.match(r'^    Conntrack Flush: (true|false)', line)
        if m:
          current_group._conntrackFlush = m.group(1)
          continue
        m = re.match(r'^    Sticky Bits    : (0x[0-9]*)', line)
        if m:
          current_group._stickyBits = m.group(1)
          continue
        m = re.match(r'^  interface   : (.*)', line)
        if m:
          n = LoadBalanceGroupInterface(m.group(1))
          current_group._interfaces.append(n)
          current_interface = n
        # else logging.error()
      if current_interface:
        m = re.match(r'^  reachable   : (true|false)', line)
        if m:
          current_interface._reachable = m.group(1)
          continue
        m = re.match(r'^  status      : (.*)', line)
        if m:
          current_interface._status = m.group(1)
          continue
        m = re.match(r'^  gateway     : (.*)', line)
        if m:
          current_interface._gateway = m.group(1)
          continue
        m = re.match(r'^  route table : (.*)', line)
        if m:
          current_interface._routeTable = m.group(1)
          continue
        m = re.match(r'^  weight      : (.*)', line)
        if m:
          current_interface._weight = m.group(1)
          continue
        m = re.match(r'^  fo_priority : (.*)', line)
        if m:
          current_interface._foPriority = m.group(1)
          continue
        m = re.match(r'^  flows$', line)
        if m:
          current_interface._flows = LoadBalanceGroupInterfaceFlows()
          current_flows = current_interface._flows
        # else logging.error()
      if current_flows:
        m = re.match(r'^      WAN Out   : (.*)', line)
        if m:
          current_flows._wanOut = m.group(1)
          continue
        m = re.match(r'^      WAN In    : (.*)', line)
        if m:
          current_flows._wanIn = m.group(1)
          continue
        m = re.match(r'^      Local ICMP: (.*)', line)
        if m:
          current_flows._localIcmp = m.group(1)
          continue
        m = re.match(r'^      Local DNS : (.*)', line)
        if m:
          current_flows._localDns = m.group(1)
          continue
        m = re.match(r'^      Local Data: (.*)', line)
        if m:
          current_flows._localData = m.group(1)
          continue
        # else logging.error()

class ShowConfig(object):

  def __init__(self, conn):
    self._conn = conn
    self._d = LoadBalance()
    self._config = []

  def Run(self, callback=None):
    START = '==========starto=========='
    END = '==========endo=========='
    out, err = self._conn.Run(
        ['echo', START, ';',
         'cat', '/config/config.boot', ';',
         'echo', END], callback=callback)

    mode = 0
    for line in out.decode('utf-8').split('\n'):
      if mode == 0 and line == START:
        mode = 1
        continue
      if mode == 1:
        if line == END:
          break
        self._config.append(line)

  def __str__(self):
    return('\n'.join(self._config))


if __name__ == '__main__':
  c = SshConnection('EdgeRouterScraper')
  lb = ShowLoadBalanceStatus(c)
  lb.Run()
  print(str(lb._d))

  conf = ShowConfig(c)
  conf.Run()
  if len(str(conf)) != 0:
    with open('/tmp/conf', 'w') as fh:
      fh.write(str(conf))
    print('less /tmp/conf')
