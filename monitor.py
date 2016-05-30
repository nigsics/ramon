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

from __future__ import print_function

import time
import math
import json
import sys
import traceback
import SocketServer

from threading import Thread, Event
import logging
#import pdb
import re

class OS_type:
    darwin, other = range(2)

if sys.platform == 'darwin':
    OS = OS_type.darwin
else:
    OS = OS_type.other

if OS != OS_type.darwin:
    try:
        from sh import iwconfig,ErrorReturnCode
    except Exception as ex:
        print("WARNING: import from sh failed - " + str(ex))

from scipy.stats import lognorm
from datetime import datetime, timedelta, tzinfo

from Queue import Queue,Empty

from ceilocomm import CeiloComm
from sampler import Sampler
from confserver import createConfServer

from utc import UTC

class InterfaceType:
    Ethernet, Wireless = range(2)

class SamplerStatus:
    stopped, running, unknown = range(3)


#
# Partly based on code from the UNIFY FP7 Demo for the Y1 review 2015,
# by Pontus Sköldström, Acreo Swedish ICT AB / Per Kreuger, SICS Swedish ICT AB.
#

class Monitor():
    def __init__(self,name="mon0", sample_rate=1000,
                 estimation_interval=1.0,
                 meter_name=None,
                 meter_interval=30.0,
                 link_speed=10,
                 alarm_trigger_value=None,
                 cutoff=99,
                 interface="eth0",
                 controller_IP='10.0.0.11',
                 conflistener_IP='0.0.0.0',
                 confport=54736,
                 meter_file_name=None, # if not None, write metering
                                       # data to a file instead of to Ceilometer
                 meter_host_and_port=None, # if not None, write metering
                                       # data to a local port instead of to Ceilometer
                 debug=False,
                 log=False,
                 resid=None,
                 projid=None,
                 username='admin',
                 password=None,
                 tenantname='admin',
                 mode=None):
        self.exit_flag = False
        self.mode = mode
        self.debug = debug
        self.log = log
#        self.meter_name = 'sdn_at_edge'
        self.meter_name = meter_name

        if alarm_trigger_value is None:
            raise RuntimeError('missing alarm_trigger_value in Monitor.__init__')
        else:
            self.set_alarm_trigger(alarm_trigger_value)

        self.set_cutoff(cutoff)

        if self.debug and self.log:
            self.logger = logging.getLogger(__name__)
            now = datetime.now()
            nowstr = now.strftime('%Y-%m-%dT%H.%M.%S')
            logging.basicConfig(filename='monitor_' + (meter_file_name if meter_name is None else meter_name) + '_' + nowstr + '.log',
                                level=logging.DEBUG,
                                format='%(asctime)s %(levelname)s %(message)s')
            # make the 'sh' module be quiet
            logging.getLogger("sh").setLevel(logging.CRITICAL + 1)
        self.conflistener_IP=conflistener_IP
        self.conflistenerport=confport
        self.name = name
        #
        self.config_queue = Queue()
        self.config_reply = Queue()
        self.reset(sample_rate,interface)
        #
        self.conf_event = Event()
        #
        if link_speed is None:
            self.interface_type,self.linerate = self.get_linerate(interface)
            if self.linerate is None:
                raise(ValueError("Cannot determine the linerate of " + interface))
        else:
            self.set_linerate(link_speed)
            self.interface_type = InterfaceType.Ethernet
        self.link_speed = self.linerate_to_link_speed(self.linerate)
        self.est_interval = estimation_interval
        self.meter_interval = meter_interval
        self.resource_ID = resid
        self.project_ID = projid
        self.username = username
        self.tenantname = tenantname
        if self.debug:
            self.ceilocomm = None
        else:
            self.ceilocomm = CeiloComm(resid,projid,controller=controller_IP,
                                       file_name=meter_file_name,
                                       host_and_port=meter_host_and_port)
        self.authpassword = password
        if not self.debug:
            self.get_auth_token()


    # Print some trace outout on the terminal, or if self.log is
    # True log the trace output in a log file.
    def debugPrint(self,tracestring):
        if self.log:
            self.logger.debug(tracestring)
        else:
            print(tracestring)


    def reset(self,sample_rate,interface):
        self.time_of_last_meter = self.time_of_last_calc = time.time()
        self.last_samples = 0
        self.last_tx_agg = self.last_rx_agg = 0.0
        self.last_txb2 = self.last_rxb2 = 0.0
        self.mean_tx = self.mean_rx = 0.0
        self.var_tx = self.var_rx = 0.0
        self.mu_tx = self.mu_rx = 0.0
        self.sigma2_tx = self.sigma2_rx = 0.0
        self.request_queue = Queue()
        self.sample_queue = Queue()
        self.sampler = Sampler(self.request_queue,self.sample_queue,
                               sample_rate,self,interface=interface,
                               debug=self.debug)
        if self.debug:
            print("\33[H",end="")   # move cursor home
            print("\33[J",end="")   # clear screen


    def clear_queue(self,q):
        while not q.empty():
            try:
                q.get(False)
            except Empty:
                continue
            q.task_done()


    # Start a new sampler
    def start_sampler(self):
        self.clear_queue(self.request_queue)
        self.clear_queue(self.sample_queue)
        self.reset(self.sampler.get_sample_rate(),
                   self.sampler.get_interface())
        self.sampler.setDaemon(True)
        self.sampler.start()


    # Stop the running sampler
    def stop_sampler(self):
        self.request_queue.put('stop');
        self.sampler.request_event.set()


    # Return status of the sampler
    def status_sampler(self,sampler):
        if sampler is None:
#            return 'stopped'
            return SamplerStatus.stopped
        elif sampler.stopped():
#            return 'stopped'
            return SamplerStatus.stopped
        elif sampler.running():
#            return 'running'
            return SamplerStatus.running
        else:
#            return 'unknown'
            return SamplerStatus.unknown


    # Set sample rate (in samples per second)
    def set_sample_rate(self, sampler, sample_rate):
        sampler.set_sample_rate(sample_rate)


    # Set estimation interval (in seconds)
    def set_estimation_interval(self,interval):
        self.est_interval = interval


    # Set meter interval (in seconds)
    def set_meter_interval(self,interval):
        self.meter_interval = interval


    # Set linerate (link_speed is given in Mbits/s)
    def set_linerate(self,link_speed):
#        self.linerate = link_speed * 1024 * 1024 / 8 # convert from Mbit/s to bytes/s
        self.linerate = link_speed * 1000 * 1000 / 8 # convert from Mbit/s to bytes/s
        
    # Convert back from linerate in bytes/s to link speed in Mbit/s
    def linerate_to_link_speed(self,linerate):
        return linerate * 8 / 1000 / 1000

    # Set alarm trigger value (overload risk which will trigger an alarm; percentage)
    def set_alarm_trigger(self,alarm_trigger_value):
        self.alarm_trigger_value = alarm_trigger_value        

    # Set the cutoff for the overload risk calculation
    def set_cutoff(self,cutoff):
        self.cutoff = cutoff / 100.0


    def listen_for_configuration(self):
        server = createConfServer(self.conflistener_IP,self.conflistenerport,self)
        server.serve_forever()


    def handle_configuration(self,sampler,config_queue,config_reply):
        reply = {}
        if self.debug:
            self.debugPrint('handle_configuration: config_queue.get()')
        data = config_queue.get()
        config_queue.task_done()
        #
        resume = data.get('resume')
        if not resume is None and sampler.keep_running == False:
            # resume is implemented by starting a new sampler thread.
            self.start_sampler();
## The start request is sent to the sampler asynchronously, so we
## can't ask it if it has stopped simply by calling a method on the
## sampler object
#            reply['started'] = sampler.running()
            reply['resumed'] = 'ok'
        #
        stop = data.get('pause')
        if not stop is None and sampler.keep_running == True:
            # pause is implemented by telling the sampler thread to exit.
            self.stop_sampler();
## The stop request is sent to the sampler asynchronously, so we
## can't ask it if it has stopped simply by calling a method on the
## sampler object
#            reply['stopped'] = sampler.stopped()
            reply['paused'] = 'ok'
        #
        status = data.get('status')
        if not status is None:
            pstatus = self.status_sampler(sampler)
            if pstatus == SamplerStatus.stopped:
                reply['status'] = 'paused'
            elif pstatus == SamplerStatus.running:
                reply['status'] = 'running'
            else:
                reply['status'] = 'unknown'
        #
        exit_cmd = data.get('exit')
        if not exit_cmd is None and sampler.keep_running == True:
            reply['exit'] = 'ok'
            self.exit();
        #
        interface = data.get('interface')
        if not interface is None:
            sampler.set_interface(interface)
            reply['interface'] = sampler.get_interface()
        #
        sample_rate = data.get('sample_rate')
        if not sample_rate is None:
            self.set_sample_rate(sampler,sample_rate)
            reply['sample_rate'] = sampler.get_sample_rate()
        #
        estimation_interval = data.get('estimation_interval')
        if not estimation_interval is None:
            self.set_estimation_interval(estimation_interval)
            reply['estimation_interval'] = self.est_interval
        #
        meter_interval = data.get('meter_interval')
        if not meter_interval is None:
            self.set_meter_interval(meter_interval)
            reply['meter_interval'] = self.meter_interval
        #
        link_speed = data.get('link_speed')
        if not link_speed is None:
            self.set_linerate(link_speed)
            reply['linerate'] = self.linerate
        #
        alarm_trigger = data.get('alarm_trigger')
        if not alarm_trigger is None:
            self.set_alarm_trigger(alarm_trigger)
            reply['alarm_trigger'] = self.alarm_trigger_value
        #
        cutoff = data.get('cutoff')
        if not cutoff is None:
            self.set_cutoff(cutoff)
            reply['cutoff'] = self.cutoff
        #
        if self.debug:
            self.debugPrint('handle_configuration: ' + repr(self.config_reply) + '.put(' + repr(reply) + ')')
#        pdb.set_trace()
        if reply == {}:
            reply['unknown option(s)'] = data
        self.config_reply.put(reply)
        if self.debug:
            self.debugPrint('handle_configuration: qsize==' + repr(self.config_reply.qsize()))


    # Get and save an authorization token and its expiration date/time
    # from Keystone.
    # The authorization token is used later when communicating with Ceilometer.
    def get_auth_token(self):
        if self.debug:
            return
        authtokenpair = self.ceilocomm.getAuthToken(tenantname=self.tenantname,username=self.username,password=self.authpassword)
        self.authtoken = authtokenpair.get('tok')
        authexpstr = authtokenpair.get('exp')
        if authexpstr[-1] == 'Z':
            expstrUTC = authexpstr[0:-1] # remove the Z
            local_authexptime = datetime.strptime(expstrUTC,'%Y-%m-%dT%H:%M:%S')
            local_tz_offset = datetime.fromtimestamp(time.mktime(time.localtime())) - datetime.fromtimestamp(time.mktime(time.gmtime()))
            authexptime_no_tz = local_authexptime - local_tz_offset # Convert local time to UTC
            self.authexptime = authexptime_no_tz.replace(tzinfo=UTC())
        else:
            self.authexptime = datetime.strptime(authexpstr,'%Y-%m-%dT%H:%M:%S')


    def estimate(self, sampler):

        # A wireless interface can increase or decrease its line rate
        # so the line rate is checked regularly for WiFi.
        if (self.interface_type == InterfaceType.Wireless):
            dummy,self.linerate = self.get_linerate_wireless(sampler.get_interface())

        t = time.time()
        est_timer = t - self.time_of_last_calc
        self.time_of_last_calc =  t

#        self.request_queue.put('r')
        self.request_queue.put('rate_data')
        rate_data = self.sample_queue.get()
        self.sample_queue.task_done()
        tx_agg = rate_data['tx_agg']
        rx_agg = rate_data['rx_agg']
        samples = rate_data['samples']
        txb2 = rate_data['txb2']
        rxb2 = rate_data['rxb2']

        n = samples - self.last_samples

        # Approximately kbytes/sec, but not really since we have a
        # measurement jitter of the number of samples recorded in each
        # sampling period. (Usually, by default ms). (The sampling
        # often cannot keep up).
        self.mean_tx = (tx_agg - self.last_tx_agg) / n
        self.mean_rx = (rx_agg - self.last_rx_agg) / n

        mean_square_tx = self.mean_tx*self.mean_tx
        mean_square_rx = self.mean_rx*self.mean_rx

        sum_square_tx = (txb2 - self.last_txb2) / n
        sum_square_rx = (rxb2 - self.last_rxb2) / n

        # NOTE: Rounding to 5 decimals is perhaps correct if we get
        # negative variance due to the measurement jitter.
        # It is not clear why we get a measurement jitter, so why this
        # is necessary is a somewhat of a mystery.
        self.var_tx = sum_square_tx - mean_square_tx
        if self.var_tx < 0:
            print("\33[9;1H")  # 
            print("\33[0JWARNING: self.var_tx == " + str(self.var_tx))
            self.var_tx = round(sum_square_tx - mean_square_tx,5) # round to avoid negative value
        self.var_rx = sum_square_rx - mean_square_rx
        if self.var_rx < 0:
            print("\33[10;1H")  # 
            print("\33[0JWARNING: self.var_rx == " + str(self.var_rx))
            self.var_rx = round(sum_square_rx - mean_square_rx,5) # round to avoid negative value

        if self.debug and False:
            print("\33[12;1H")
            print("\33[0J################### DEBUG ##################")
            print("\33[0Jest_timer:      %f"%est_timer)
            print("\33[0Jself.mean_tx:   %f        self.mean_rx:  %f"%(self.mean_tx,self.mean_rx))
            print("\33[0Jtxb2:           %f        rxb2           %f"%(txb2,rxb2))
            print("\33[0Jself.last_txb2  %f        self.last_rxb2 %f"%(self.last_txb2,self.last_rxb2))
            print("\33[0Jmean_square_tx  %f        mean_square_rx %f"%((mean_square_tx),(mean_square_rx)))
            print("\33[0Jsum_square_tx   %f        sum_square_rx  %f"%(sum_square_tx,sum_square_rx))
            print("\33[0Jself.var tx:         %f        self.var_rx:        %f"%(self.var_tx,self.var_rx))


        self.last_samples = samples

        self.last_tx_agg = tx_agg
        self.last_rx_agg = rx_agg

        self.last_txb2 = txb2
        self.last_rxb2 = rxb2

        # Estimate the moments
        try:
            if self.mean_tx != 0.0:
                self.sigma2_tx = math.log(1.0+(self.var_tx/mean_square_tx))
                self.mu_tx = math.log(self.mean_tx) - (self.sigma2_tx/2.0)
            else:
#                self.sigma2_tx = float('nan')
                self.sigma2_tx = 0.0
                self.mu_tx = 0.0

            if self.mean_rx != 0.0:
                self.sigma2_rx = math.log(1.0+(self.var_rx/(mean_square_rx)))
                self.mu_rx = math.log(self.mean_rx) - (self.sigma2_rx/2.0)
            else:
#                self.sigma2_rx = float('nan')
                self.sigma2_rx = 0.0
                self.mu_rx = 0.0

        # Calculate the overload risk

## Based on the original code, using the CDF (Cumulative Distribution Function).
#            self.overload_risk_tx = (1-lognorm.cdf(self.linerate * self.cutoff,math.sqrt(self.sigma2_tx),0,math.exp(self.mu_tx)))*100
#            self.overload_risk_rx = (1-lognorm.cdf(self.linerate * self.cutoff,math.sqrt(self.sigma2_rx),0,math.exp(self.mu_rx)))*100

## Using the survival function (1 - cdf). See http://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.lognorm.html for a motivation).
            self.overload_risk_tx = (lognorm.sf(self.linerate * self.cutoff,math.sqrt(self.sigma2_tx),0,math.exp(self.mu_tx)))*100
            self.overload_risk_rx = (lognorm.sf(self.linerate * self.cutoff,math.sqrt(self.sigma2_rx),0,math.exp(self.mu_rx)))*100

### According to our dicussion, using the PPF (Percentile Point Function (or Quantile function).
#            self.cutoff_rate_tx = (1-lognorm.ppf( self.cutoff,math.sqrt(self.sigma2_tx),0,math.exp(self.mu_tx)))
#            self.cutoff_rate_rx = (1-lognorm.ppf( self.cutoff,math.sqrt(self.sigma2_rx),0,math.exp(self.mu_rx)))
            # To estimate a risk: compare the calculated cutoff rate with the nominal line rate.

        except ValueError as ve:
            print("\33[2KError in estimation: ({}):".format(ve))
            traceback.print_exc()
            print("\33[2Kmean_tx: %.2e, mean_rx: %.2e "%(self.mean_tx,self.mean_rx))
            print("\33[2Kvar_tx: %.2e, var_rx: %.2e "%(self.var_tx,self.var_rx))
            print("\33[2Kmean_square_tx: %.2e, mean_square_rx: %.2e "%(mean_square_tx,mean_square_rx))
            print("\33[2Krate_data: %s"%(rate_data,))
            exit(1)

        try:
            print("\33[H",end="") # move cursor home
# [PD] 2016-05-23, The calculation of "actual" seems to be buggy.
#            print("\33[2KEstimate (sample_rate: {:d} actual({:d}), interface: {}, linerate: {:d}".format(sampler.get_sample_rate(), n, sampler.get_interface(),self.linerate))
            print("\33[2Ksample_rate (/s): {:d}, interface: {}, linerate (bytes/s): {:d}, link speed (Mbit/s): {:d}".format(sampler.get_sample_rate(), sampler.get_interface(),self.linerate,self.link_speed))
            print("\33[2KTX(mean: %.2e b/s std: %.2e mu: %.2e s2: %.2e, ol-risk: %.2e) "%(self.mean_tx,math.sqrt(self.var_tx),self.mu_tx,self.sigma2_tx, self.overload_risk_tx))
            print("\33[2KRX(mean: %.2e b/s std: %.2e mu: %.2e s2: %.2e, ol-risk: %.2e) "%(self.mean_rx,math.sqrt(self.var_rx),self.mu_rx,self.sigma2_rx, self.overload_risk_rx))
            print("\33[2Kestimation timer: {:.4f}".format(est_timer))
            print("\33[2Kestimation interval: {:.2f}".format(self.est_interval))
            print("\33[2Kmeter interval: %d"%(self.meter_interval))
            print("\33[2Kmode: %d"%(self.mode))
            if self.debug:
                print("\33[2Kdebug: %s"%str(self.debug))
                print("\33[2Ksample_queue size: %s"%str(self.sample_queue.qsize()))
        except ValueError as ve:
            print("\33[2KError in display ({}):".format(ve))
            traceback.print_exc()
            print("\33[2Kvar_tx: %.2e, var_rx: %.2e "%(self.var_tx,self.var_rx))
            print("\33[2Krate_data: %s"%(rate_data,))
            exit(1)
        # FIXME: It should not be necessary to empty the queue here
        # anymore, since the monitor code only puts stuff in the Queue
        # on request.
        # Verify this before remove this while loop!
        while not self.sample_queue.empty():
            self.sample_queue.get()
            self.sample_queue.task_done()

    # Return a tuple with interface type and linerate
    def get_linerate(self,interface):
        if OS == OS_type.darwin:      # Fake it on OS X
            # 1 Gbit/s in bytes/s (NOTE: 1000, not 1024; see IEEE 802.3-2008)
            lr = (InterfaceType.Ethernet,(1000*1000*1000)/8)
        else:
            lr = self.get_linerate_ethernet(interface)
            if lr is None:
                lr = self.get_linerate_wireless(interface)
        return lr

    def get_linerate_ethernet(self,interface):
        try:
            # The link speed in Mbits/sec.
            with open("/sys/class/net/{interface}/speed".format(interface=interface)) as f:
                speed = int(f.read()) * 1000 * 1000 / 8 # convert to bytes/s (NOTE: 1000, not 1024; see IEEE 802.3-2008)
        except IOError:
            speed = None
        finally:
            return InterfaceType.Ethernet,speed

    def get_linerate_wireless(self,interface):
        try:
            iwres = iwconfig(interface,_ok_code=[0,1])
            rx = re.compile("Bit Rate=([0-9]+)\s*Mb/s", re.MULTILINE | re.IGNORECASE)
            lrg = rx.search(iwres)
            if lrg.groups() != ():
                bit_rate = int(lrg.group(1)) # Mbits/s
                lr = (InterfaceType.Wireless,bit_rate * 1000 * 1000 / 8) # convert Mbit/s to bytes/s (NOTE: 1000, not 1024; see IEEE 802.3-2008)
                return lr
            else:
                return None,None
        except ErrorReturnCode:
            return None,None


    # Store metered data in Ceilometer
    def meter(self):
        t = time.time()
        self.time_of_last_meter = t

        alarm_value_tx = self.overload_risk_tx > self.alarm_trigger_value
        alarm_value_rx = self.overload_risk_rx > self.alarm_trigger_value

        now = datetime.now(tz=UTC())
        nowstr = now.strftime('%Y-%m-%dT%H.%M.%S')
        data = {'timestamp': nowstr,
                'interface': repr(self.sampler.get_interface()),
                'linerate': repr(self.linerate),
                'alarm_trigger_value': repr(self.alarm_trigger_value),
                'cutoff': repr(self.cutoff),
                'tx': repr(self.mean_tx),
                'var_tx': repr(self.var_tx),
                'mu_tx': repr(self.mu_tx),
                'sigma2_tx': repr(self.sigma2_tx),
                'overload_risk_tx': repr(self.overload_risk_tx),
                'alarm_tx': repr(alarm_value_tx),
                'rx': repr(self.mean_rx),
                'var_rx': repr(self.var_rx),
                'mu_rx': repr(self.mu_rx),
                'sigma2_rx': repr(self.sigma2_rx),
                'overload_risk_rx': repr(self.overload_risk_rx),
                'alarm_rx': repr(alarm_value_rx),
                'sample_rate': repr(self.sampler.get_sample_rate()),
                'estimation_interval': repr(self.est_interval),
                'meter_interval': repr(self.meter_interval)}
        self.ceilorecord(now,data)


    def ceilomessage(self,message):
        now = datetime.now(tz=UTC())
        nowstr = now.strftime('%Y-%m-%dT%H:%M:%S')
        data = {message: repr(nowstr)}
        self.ceilorecord(now,data)


    def ceilorecord(self,now,data):
        if not self.debug:
            # Check if the authorization token has expired.
            # Add one minute margin for possible bad time sync.
            delta = timedelta(minutes=1)
            if now + delta > self.authexptime:
                self.get_auth_token()
        print("\33[15;1H")
        print("\33[0J")      # clear rest of screen
        if self.debug:
            print("\33[0J" + str(data))
        else:
            rjson = self.ceilocomm.putMeter(self.meter_name,data,self.authtoken,
                                            username=self.username,
                                            project_id=self.project_ID,
                                            resource_id=self.resource_ID)
            print(json.dumps(rjson,indent=4))
#            print(str(rjson))


    def main(self):
        self.time_of_last_meter = self.time_of_last_calc = time.time()
        # Sampling is done in a separate thread to avoid
        # introducing a delay jitter in our measurements.
#        self.sampler.setDaemon(True)
        self.sampler.start()
        sleep_time = min(self.est_interval,self.meter_interval)

        # Start the thread listening for configuration messages
        conflistener = Thread(target=self.listen_for_configuration)
        conflistener.setDaemon(True)
        conflistener.start()

### FIXME:
#   The conflistener may not be completely initialized when ceilocomm
#   starts sending messages on the local port (in mode 1).
#   We should wait for the conflistener to initialize before
#   proceeding here.

        print("\33[2J")         # clear screen
        self.ceilomessage('initialized')

        try:
            while not self.exit_flag:
                if not self.config_queue.empty():
                    if self.debug:
                        self.debugPrint('main loop: handle_configuration()')
                    self.handle_configuration(self.sampler,self.config_queue,self.config_reply)
                    continue
                    
#                if self.status_sampler(self.sampler) == 'stopped':
                if self.status_sampler(self.sampler) == SamplerStatus.stopped:
                    self.conf_event.wait()
                    continue

                timestamp = time.time()
                # time to do an estimation?
                if timestamp >= (self.time_of_last_calc  + self.est_interval):
                    self.estimate(self.sampler)
                # time to store a meter value?
                if timestamp >= (self.time_of_last_meter  + self.meter_interval):
                    self.meter()        
                self.conf_event.wait(sleep_time)
                self.conf_event.clear()
            print('exit')

        except KeyboardInterrupt:
            self.exit()


    def exit(self):
        self.stop_sampler() # make sure the sampler thread is stopped in an
                            # orderly manner 
        self.ceilomessage('exited')
        self.exit_flag = True
