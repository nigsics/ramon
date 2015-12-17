# -*- coding: latin-1 -*-

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

import time
from threading import Thread, Event
from sh import netstat,ErrorReturnCode
import re
#import pdb
from monitor import OS_type, OS

#
# Partly based on code from the UNIFY FP7 Demo for the Y1 review 2015,
# by Pontus Sköldström, Acreo Swedish ICT AB / Per Kreuger, SICS Swedish ICT AB.
#

class Sampler(Thread):
    def __init__(self, inq, outq, sample_rate, monitor, interface='eth0', name='Sampler', debug=False):
        Thread.__init__(self, name=name)
        self.inq = inq
        self.outq = outq
        self.request_event = Event()
        self.set_sample_rate(sample_rate)
        self.monitor = monitor
        self.interface = interface
        self.debug = debug
        self.keep_running = True
        self.tx_agg = self.rx_agg = 0.0
        self.txb2 = self.rxb2 = 0.0
        self.tx_file = None
        self.rx_file = None
        self.samples = 0
        self.last_data = self.get_interface_data(self.interface)
        # FIXME: These two should be inferred by checking the word
        #        length of the computer we're running on.
        #        Perhaps with platform.architecture() or sys.maxsize
        #        For now assume 32-bit architecture.
        self.tx_byte_counter_wrap_adjustment = (2 ** 32) - 1
        self.rx_byte_counter_wrap_adjustment = (2 ** 32) - 1


    def run(self):
        if (self.debug):
            self.monitor.debugPrint("sampler.py: starting run()")
        self.last_data = self.get_interface_data(self.interface)
        while self.keep_running:
            timestamp = self.sample()

            while not self.inq.empty():
                request = self.inq.get()
                if request == 'rate_data':
                    self.inq.task_done()
                    self.outq.put({'ts': timestamp, 'samples': self.samples, 'txb2': self.txb2, 'rxb2': self.rxb2, 'tx_agg': self.tx_agg, 'rx_agg': self.rx_agg})
#                    self.samples = 0 # Don't do this!
                elif request == 'stop':
                    self.inq.task_done()
                    self.keep_running = False
                else:
                    self.inq.task_done()
                    pass # unknown request, FIXME: perhaps report an error?
            #
#            time.sleep(self.sleep_time)
            self.request_event.wait(self.sleep_time)
            self.request_event.clear()
        if (self.debug):
            # Race conditions can cause things to be pulled from under
            # our feet, so catch all exceptions here.
            try:
                self.monitor.debugPrint("sampler.py: exit from run()")
            except BaseException:
                pass


    # Read the traffic flow data from the network interface and accumulate the rate
    def sample(self):
        self.samples += 1
        curr = self.get_interface_data(self.interface)

        if curr[1] < self.last_data[1]:
            # tx counter has wrapped
            self.monitor.debugPrint("sampler.py: self.last_data[1] before wrap adjustment: " + str(self.last_data[1]))
            self.last_data[1] -= self.tx_byte_counter_wrap_adjustment
       
        tx_bytes = curr[1] - self.last_data[1]

        if curr[2] < self.last_data[2]:
            # rx counter has wrapped
            self.monitor.debugPrint("sampler.py: self.last_data[2] before wrap adjustment: " + str(self.last_data[2]))
            self.last_data[2] -= self.rx_byte_counter_wrap_adjustment

        rx_bytes = curr[2] - self.last_data[2]

        timestamp = curr[0] #- self.last_data[0]
        obs_time = timestamp - self.last_data[0]

        if self.debug:
            self.monitor.debugPrint("sampler.py: curr: " + str(curr) + ", self.last_data: " + str(self.last_data))
            self.monitor.debugPrint("sampler.py: tx_bytes: " + str(tx_bytes) + ", rx_bytes: " + str(rx_bytes))
            self.monitor.debugPrint("sampler.py: obs_time: " + str(obs_time))

#        self.last_data = curr
        self.last_data = list(curr) # copy curr

        tx_byte_rate  = tx_bytes / obs_time
        rx_byte_rate  = rx_bytes / obs_time
        self.tx_agg = self.tx_agg + tx_byte_rate
        self.rx_agg = self.rx_agg + rx_byte_rate
        self.txb2 = self.txb2 + (tx_byte_rate*tx_byte_rate)
        self.rxb2 = self.rxb2 + (rx_byte_rate*rx_byte_rate)

        if self.debug:
            self.monitor.debugPrint("sampler.py: tx_byte_rate: " + str(tx_byte_rate) + ", rx_byte_rate: " + str(rx_byte_rate) + ", self.tx_agg: " + str(self.tx_agg) + ". self.rx_agg: " + str(self.rx_agg) + ", self.txb2: " + str(self.txb2) + ", self.rxb2: " + str(self.rxb2))

        return timestamp
            

    # Read the number of bytes received and sent to/from the network interface
    def get_interface_data(self,interface):
        if OS == OS_type.darwin: # OS X does not have /sys/class/net/...
            # This is only for testing on OS X. Running netstat takes
            # way to much time to be a practical method for reading
            # the byte counters of an interface.
            netstat_output = netstat("-i", "-b", "-I", interface)
            for line in netstat_output:
                if line.startswith(interface):
                    words = line.split()
                    rx_bytes = int(words[6])
                    tx_bytes = int(words[9])
                    return time.time(),rx_bytes,tx_bytes
            return  time.time(),0,0
        else:
            # FIXME: Perhaps open the tx_file and the rx_file in the
            #        __init__ method instead. Is there really a good
            #        reason for doing it this way?
            tx_fn = "/sys/class/net/%s/statistics/tx_bytes" % interface
            rx_fn = "/sys/class/net/%s/statistics/rx_bytes" % interface
            if self.tx_file is None:
                self.tx_file = open(tx_fn)
                tx_bytes = int(self.tx_file.read())
            else:
                self.tx_file.seek(0)
                tx_bytes = int(self.tx_file.read())

            if self.rx_file is None:
                self.rx_file = open(rx_fn)
                rx_bytes = int(self.rx_file.read())
            else:
                self.rx_file.seek(0)
                rx_bytes = int(self.rx_file.read())

#            return time.time(), tx_bytes, rx_bytes
            return [time.time(), tx_bytes, rx_bytes]


    # 
    def set_sample_rate(self,sample_rate):
        self.sample_rate = sample_rate
        self.sleep_time = 1.0 / sample_rate

    def get_sample_rate(self):
        return self.sample_rate

    def set_interface(self,interface):
        self.interface = interface

    def get_interface(self):
        return self.interface

    def running(self):
        return self.keep_running

    def stopped(self):
        return not self.keep_running
