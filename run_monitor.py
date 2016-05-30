#!/usr/bin/python2.7

# Copyright 2015 SICS Swedish ICT AB
# 
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
# 
#     http://www.apache.org/licenses/LICENSE-2.0
# 
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import argparse
#import pdb
from version import __version__
from monitor import Monitor

# NOTE: For some options, if the option is None, we set a default
# value explicitly after parsing the arguments instead of setting
# defaults here. This is to be able to detect if an option was given
# on the command line or not even if it should have a default value.

parser = argparse.ArgumentParser(description="Monitor")
parser.add_argument('-b',"--meter_port", help='Port to send metering data to. This will inhibit storing metering data in Ceilometer',dest='meter_port',action='store',nargs='?',const=None,default=None, type=int)
parser.add_argument('-g',"--meter_host", help='Host to send metering data to if the --meter-port argument is given; default is localhost. This will inhibit storing metering data in Ceilometer',dest='meter_host',action='store',nargs='?',const=None,default=None)
parser.add_argument('-f',"--meter_file", help='Name of a file to append metering data to. This will inhibit storing metering data in Ceilometer',dest='meter_file',action='store',nargs='?',const=None,default=None)
parser.add_argument('-i',"--interface", help='Interface to monitor; default "eth0"', nargs='?', default='eth0')
parser.add_argument('-s',"--sample_rate", help='How often to sample; default 1000 samples per second',nargs='?', default='1000', type=int)
parser.add_argument('-e',"--estimation_interval", help='How often to estimate; default every 10 seconds',nargs='?', default='10.0', type=float)
parser.add_argument('-m',"--meter_interval", help='How often to meter; default every 30 seconds',nargs='?', default='30.0', type=float)
parser.add_argument('-k',"--link_speed", help='Set the link speed value for the monitored interface (in Mbits per second)', type=int)
parser.add_argument('-a',"--alarm_trigger", help='The overload risk which will trigger an alarm; default 95%%', type=int, default=95)
parser.add_argument('-o',"--cutoff", help='A percentage of the link speed to use in the overload risk calculation; default 99%%', type=int, default="99")
parser.add_argument('-q',"--confport", help='Port number for configuration messages (see also monconf.py); default 54736', type=int, default='54736')
parser.add_argument('-n',"--meter_name", help='The name of this meter in Ceilometer')
parser.add_argument('-r',"--resource_ID", help='Resource identifier for the resource to associate with the meter',nargs='?')
parser.add_argument('-p',"--project_ID", help='Project identifier for the resource to associate with the meter',nargs='?')
parser.add_argument('-c',"--controller", help="The IP adress of the controller running Ceilometer; default 10.0.0.11",nargs='?')
parser.add_argument('-u',"--username", help='User name; default "admin"',nargs='?')
parser.add_argument('-w',"--password", help='Password',nargs='?')
parser.add_argument('-t',"--tenantname", help='Tenant name; default "admin"',nargs='?')
parser.add_argument('-d',"--debug", help='Debug flag',action='store_true')
parser.add_argument('-l',"--log", help='Log debug messages to a file of the form monitor_<meter_name>_%%Y-%%m-%%dT%%H.%%M.%%S.log',action='store_true')
parser.add_argument('-v',"--version", help='Show version and exit',action='store_true')

args = parser.parse_args()

# Mode 1: output to file and/or port
# valid options:
# -i, -s, -e, -m, -k, -a, -o, -q, -d, -l, -f, -b, -v
# mandatory options:
# -f or -b (obviously, since it triggers mode 1 behavior)
# invalid options:
# -n, -r, -p, -c, -u, -w, -t
# 
# Mode 2: output to ceilometer
# valid options:
# -n, -i, -s, -e, -m, -k, -a, -o, -q, -r, -p, -c, -d, -l, -u, -w, -t, -v
# mandatory options:
# -n, -r, -p, -w
# invalid option:
# -f, -b
# 
# The presence of the -f or -b option determines the mode.
# if -f or -b is present:
#     we are running in mode 1
# else:
#     we are running in mode 2
#     invalid switches for mode 2 will be ignored

if args.version is True:
    print(__version__)
    exit(0)

if args.meter_file is None and args.meter_port is None:     # mode 2
    mode = 2
else:                           # mode 1
    mode = 1
    invalid_opt_found = False
    for option in  ['meter_name',
                    'resource_ID',
                    'project_ID',
                    'controller',
                    'username',
                    'password',
                    'tenantname']:
        optval = getattr(args,option)
        if not optval is None:
            print("Ignoring invalid option in Mode 1: --" + option + " " + optval)
            setattr(args,option,None) # Make sure the option is ignored.
            invalid_opt_found |=  True
    if invalid_opt_found:
        try:
            input = raw_input("\nPress Enter to continue")
        except NameError: pass
    
if mode == 2:
    # All options without default values (i.e. if the option was not given
    # on the command line) must have a value set here, before we
    # instantiate a Monitor.
    missing_option = False
    for option in ['meter_name',
                   'resource_ID',
                   'project_ID',
                   'password']:
        optval = getattr(args,option)
        if optval is None:
            print("Option --" + option + " must be set in mode 2.")
            missing_option |= True
    if missing_option:
        exit(1)
    # All options that _should_ have default values will get them here.
    for optpair in [('controller','10.0.0.11'),
                    ('username','admin'),
                    ('tenantname','admin')]:
        optval = getattr(args,optpair[0])
        if optval is None:
            setattr(args,optpair[0],optpair[1])
else:
    # There are no mandatory options in mode 1, except for -f which of
    # course already is present if we are in mode 1.
    if args.meter_host is None:
        args.meter_host = '127.0.0.1'

mon = Monitor(meter_name=args.meter_name,
              sample_rate=args.sample_rate,
              interface=args.interface,
              estimation_interval=args.estimation_interval,
              meter_interval=args.meter_interval,
              link_speed=args.link_speed,
              alarm_trigger_value=args.alarm_trigger,
              cutoff=args.cutoff,
              confport=args.confport,
              resid=args.resource_ID,
              projid=args.project_ID,
              controller_IP=args.controller,
              debug=args.debug,
              log=args.log,
              meter_file_name=args.meter_file,
#              meter_host_and_port=args.meter_port,
              meter_host_and_port=(args.meter_host,args.meter_port),
              username=args.username,
              password=args.password,
              tenantname=args.tenantname,
              mode=mode)

mon.main()
