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
import socket
import json
#import pdb
from version import __version__

parser = argparse.ArgumentParser(description="Monitor Configuration")
parser.add_argument("--pause", help='Pause the rate monitor', action='store_true')
parser.add_argument("--resume", help='Resume the rate monitor', action='store_true')
parser.add_argument("--status", help='Show the status of the rate monitor', action='store_true')
parser.add_argument("--exit", help='Tell the rate monitor to exit. Setting this option will cause all other options to be ignored', action='store_true')
parser.add_argument('-i', "--interface", help='Interface to monitor')
parser.add_argument('-s', "--sample_rate", help='Sample rate in samples per second', type=int)
parser.add_argument('-e', "--estimation_interval", help='Estimation interval in seconds', type=int)
parser.add_argument('-m', "--meter_interval", help='Meter interval in seconds', type=int)
parser.add_argument('-k', "--link_speed", help='Set the link speed value for the monitored interface (in Mbits per second)', type=int)
parser.add_argument('-a', "--alarm_trigger", help='The overload risk which will trigger an alarm (a percentage)', type=int)
parser.add_argument('-o', "--cutoff", help='A percentage of the link speed to use in the overload risk calculation', type=int)
# The following are "local" arguments, and will not be sent to the monitor.
parser.add_argument("--host", help='IP or name of the computer running the rate monitor; default 127.0.0.1', nargs='?', default="127.0.0.1")
parser.add_argument("--port", help='Port of the computer running the rate monitor; default 54736', nargs='?', default="54736", type=int)
parser.add_argument('-v',"--version", help='Show version and exit',action='store_true')

args = parser.parse_args()

if args.version is True:
    print(__version__)
    exit(0)

# # DEBUG
# print("#")
# print("print(args):")
# print(args)
# # END DEBUG

#pdb.set_trace()
if args.exit:
    message = {'exit': True}
else:
    if args.resume and args.pause:
        print("You cannot resume and pause the monitor simultaneously")
        exit(1)
    else:
        args.resume = True if args.resume else None
        args.pause = True if args.pause else None

    if args.status and (args.resume or args.pause):
        print("status cannot be queried when resuming or pausing")
        exit(1)
    else:
        args.status = True if args.status else None

    sample_rate = args.sample_rate
    estimation_interval = args.estimation_interval
    meter_interval = args.meter_interval

    message = {}
    for confparam in ['resume','pause','status','interface','sample_rate','estimation_interval','meter_interval','link_speed','alarm_trigger','cutoff']:
        confval = getattr(args,confparam)
        if not confval is None:
            message[confparam] = getattr(args,confparam)

# # DEBUG
# print("#")
# print("print(message)")
# print(message)
# print("#")
# # END DEBUG

if message:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((args.host, args.port))
        s.send(bytes(json.dumps(message)))

        reply = s.recv(1024)
        result = json.loads(reply.decode('UTF-8'))
        print(result)
    except socket.error as (errno, string):
        print("Error " + repr(errno) + ": " + string)
    except Exception as e:
        print(e)
        print(reply)
else:
    print('unimplemented or empty option')
