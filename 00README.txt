# Fetching load balance status and exports it to Prometheus
# based on     ssh $router /usr/sbin/ubnt-hal wlbGetStatus
# use systemd to keep server running on port 8000


#
# These manual installation instructions expect you to copy and paste
# lines into a shell running as yourself. This is not a script, and
# may throw errors or stop and expect you to enter a password (i.e. sudo). You are the one responsible for detecting errors and
# correcting them.
#


# assumes: ssh ${ER_USER}@router-ip
ER_USER=$USER
ER_USER=root

# requires: localhost /home/${LOCAL_USER}/Src/EdgeRouter/
LOCAL_USER=$USER
[ -d /home/${LOCAL_USER}/Src/EdgeRouter ] || printf 'ERROR!\n ERROR!\nHALT!\nFIX LOCAL_USER= setting before proceeding\n'

# Write your own distribution script. Mine contains rsync commands to
# copy from my laptop to my servers.
./distribute.sh

## ONETIME SETUP
# Install Prometheus locally; don't use snap.
sudo apt -y install prometheus
sudo systemctl restart prometheus  # I think?
# next, leverage python prometheus_client to export the info to prometheus
#pip install prometheus-client
# Ubuntu 24
sudo apt -y install python3-prometheus-client

## assume default route is the Edgerouter
IP=
if which netstat >/dev/null 2>/dev/null ; then
  IP=$(netstat -nr | egrep '^0\.0\.0\.0 ' | awk '{print $2}')
else
  IP=$(ip route | egrep '^default ' | awk '{print $3}')
fi
echo default route: ${IP?}

# create dedicated ssh key
if [ ! -f $HOME/.ssh/router ] ; then
  # 2025-09 upgrade from rsa to ed25519; verified working with 2.0.9-hotfix.7
  #ssh-keygen -N '' -f $HOME/.ssh/router -t rsa
  ssh-keygen -N '' -f $HOME/.ssh/router -t ed25519
  scp $HOME/.ssh/router.pub ${ER_USER?}@${IP?}:/tmp/id.pub
fi
if ! grep EdgeRouterScraper $HOME/.ssh/config >/dev/null 2>/dev/null ; then
  cat >>$HOME/.ssh/config <<__EOF__
Host EdgeRouterScraper
	Hostname ${IP?}
        ForwardX11 no
        ForwardAgent no
        IdentityFile ~/.ssh/router
__EOF__
fi

# install key on router
ssh ${ER_USER?}@${IP?}
configure
loadkey ${ER_USER?} /tmp/id.pub
save
exit
exit

# verify key install succeeded
ssh EdgeRouterScraper date

# back on machine running EdgeRouter scripts
# test "show load-balance status" command
ssh EdgeRouterScraper /usr/sbin/ubnt-hal wlbGetStatus

# for starters, just run daemon.py in screen
# verify it's outputting data
screen
cd $HOME/Src/EdgeRouter/. && ./daemon.py &
# verify publication works. assuming ssh'ed in:
printf 'GET /\r\n\r\n' | nc localhost 8000 | fgrep G
# expect something like:
# reachable{group="G",interface="eth0",is="true"} 1.0
# reachable{group="G",interface="eth0",is="false"} 0.0
# reachable{group="G",interface="eth1",is="true"} 0.0
# reachable{group="G",interface="eth1",is="false"} 1.0
# status{group="G",interface="eth0",is="active"} 1.0
# status{group="G",interface="eth0",is="inactive"} 0.0
# status{group="G",interface="eth0",is="failover"} 0.0
# status{group="G",interface="eth1",is="active"} 0.0
# status{group="G",interface="eth1",is="inactive"} 1.0
# status{group="G",interface="eth1",is="failover"} 0.0

# verify config snapshots are created
cat Logs/latest

# configure metric collection
# this assumes scrape_configs: is at the end of the file
sudo date
cat | sudo tee -a /etc/prometheus/prometheus.yml <<'__EOF__'

  - job_name: 'edgerouter'
    scrape_interval: 60s
    scrape_timeout: 50s
    static_configs:
      - targets: ['localhost:8000']
__EOF__
sudo /etc/init.d/prometheus reload

# test by graphing:
reachable{group="G"}
status{group="G"}
google-chrome 'http://10.0.0.5:9090/classic/graph?g0.range_input=15m&g0.stacked=0&g0.moment_input=2020-12-08%2022%3A29%3A55&g0.expr=reachable%7Bgroup%3D%22G%22%7D&g0.tab=0&g1.range_input=15m&g1.expr=status%7Bgroup%3D%22G%22%7D&g1.tab=0'
sleep 61  # reload tab after 60s scrape interval

# test complete
kill %1
exit  # screen -> shell

# install as a service
sudo date
sudo install -d -m 0700 /root/systemd
cat | sudo tee /root/systemd/edgerouter.sh <<__EOF__
#!/bin/sh
cd /home/${LOCAL_USER?}/Src/EdgeRouter
su ${LOCAL_USER?} -c './daemon.py'
sleep 5
__EOF__
sudo chmod +x /root/systemd/edgerouter.sh
cat | sudo tee /etc/systemd/system/edgerouter.service <<'__EOF__'
[Unit]
Description=edgerouter monitor

[Service]
Type=simple
Restart=always
RestartSec=5
ExecStart=/root/systemd/edgerouter.sh

[Install]
WantedBy=multi-user.target
__EOF__
sudo systemd-analyze verify edgerouter.service
sudo systemctl daemon-reload
sudo systemctl enable edgerouter  # new for ubuntu 20.04
sudo systemctl start edgerouter

# 1- verify daemon start
ps -ef | fgrep "su ${LOCAL_USER?} -c ./daemon.py"
# 2- and listening
#netstat -nap | fgrep :8000
ss -ltn | fgrep :8000
# 3- repeat prometheus graph in browser, make sure systemd wrapped daemon works.
google-chrome 'http://10.0.0.5:9090/classic/graph?g0.range_input=15m&g0.stacked=0&g0.moment_input=2020-12-08%2022%3A29%3A55&g0.expr=reachable%7Bgroup%3D%22G%22%7D&g0.tab=0&g1.range_input=15m&g1.expr=status%7Bgroup%3D%22G%22%7D&g1.tab=0'
# 4- config scraping
cat $HOME/Src/EdgeRouter/Logs/latest
ls -al $HOME/Src/EdgeRouter/Logs/latest

# done!

# incremental software update
./distribute.sh
systemctl reload edgerouter

# repeat 4 verifications above


# DISASTER RECOVERY INSTRUCTIONS
## In case of disaster recovery, just scp the latest config to
## /config/config.boot and reboot your (replacement) router!
