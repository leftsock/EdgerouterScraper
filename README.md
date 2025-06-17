# Edgerouter Scraper

## What is this

This daemon ssh'es into an Edgerouter once a minute.

It 1- watches for config changes (i.e. backup!) and 2- captures the state
of the load balancer (i.e. multiple uplinks to the outside world) and
publishes its state via Prometheus.

There is an incomplete config parser (configdiff.py) meant to provide
real diffs instead of using diff -u which is sensitive to lines being
in a different order.

## About

Wrote this for myself, so it has only been tested against an Edgerouter
X running v2.0.9-hotfix.7

The install instructions in 00Readme.txt are for running on Ubuntu Server.
Do not blindly copy and paste the commands. read them line-by-line and
make sure you know what they're doing first!

Good luck!
