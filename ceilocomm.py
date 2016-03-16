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

import requests
import json
import socket
from datetime import datetime
from utc import UTC
#import pdb

class CeiloComm():
    def __init__(self,
                 resource_id,
                 project_id,
                 controller='10.0.0.11',
                 authURL=None,
                 meterURL=None,
                 file_name=None, # if this is not None meter data will be
                                 # written to a file instead of to Ceilometer
#                 port_number=None  # if this is not None meter data will be
#		                 # written to a port instead of to Ceilometer
                 host_and_port=None  # if this is not None meter data will be
		                 # written to a port instead of to Ceilometer
                 ):
        self.resource_id=resource_id
        self.project_id=project_id
        self.controller = controller
        if file_name is None and host_and_port is None and authURL is None:
            self.authURL = 'http://' + controller + ':5000/v2.0/tokens'
        else:
            self.authURL=authURL
        if file_name is None and host_and_port is None and meterURL is None:
            self.meterURL = 'http://' + controller + ':8777/v2/meters'
        self.file_name = file_name
        self.host_and_port = host_and_port


    # Get authorization token data from Keystone and return the token together with its expiration date/time
    # If self.file_name is not None, return a dummy token and an
    # expiration date far, far in the future.
    def getAuthToken(self,tenantname='admin',username='admin',password=''):
# curl -s -X POST http://10.0.0.11:5000/v2.0/tokens -H "Content-Type: application/json" -d '{"auth": {"tenantName": "'"admin"'", "passwordCredentials": {"username": "'"admin"'", "password": "'"bar"'"}}}' | python -m json.tool
        if self.file_name is not None or self.host_and_port is not None:
            return {'tok': 'dummy',
                    'exp': datetime.strftime(datetime.max.replace(tzinfo=UTC()),'%Y-%m-%dT%H:%M:%SZ')}
        else:
            headers = {'Content-Type': 'application/json'}
            payload = {'auth': {'tenantName': tenantname, 'passwordCredentials': {'username': username, 'password': password}}}
            response = requests.post(self.authURL, data=json.dumps(payload), headers=headers)
            if response.status_code == requests.codes.ok:
                return {'tok': response.json().get('access').get('token').get('id'),
                        'exp': response.json().get('access').get('token').get('expires')}
            else:
                response.raise_for_status()

    # Get metering data from Ceilometer.
    def getMeter(self,metername,timestart,authtoken):
#curl -X GET -H "X-Auth-Token: 806f3ea653324082ac0d2bca2ab34ae5" -H "Content-Type: application/json" -d '{"q": [{"field": "timestamp", "op": "ge", "value": "2014-04-01T13:34:17"}]}' http://10.0.0.11:8777/v2/meters/test
        headers = {'X-Auth-Token': authtoken, 'Content-Type': 'application/json'}
        payload = {'q': [{'field': 'timestamp', 'op': 'ge', 'value': timestart}]}
        url = self.meterURL + '/' + metername
        response = requests.get(url, data = json.dumps(payload), headers=headers)
        if response.status_code == requests.codes.ok:
            return response.json()
        else:
            response.raise_for_status()

# To print some meter data from Ceilometer, call printMeter()
# something like this; replacing 'bar' with the relevant password, and
# the timestamp with the time of the first record you want to print:
# cel = CeiloComm()
# cel.printMeter('sdn_at_edge','2015-09-21T10:15:15',cel.getAuthToken(password='bar').get('tok'))

    # Print metering data from Ceilometer. 
    def printMeter(self,metername,timestart,authtoken):
        print(json.dumps(self.getMeter(metername,timestart,authtoken),indent=4))

    # Store metering data in Ceilometer.
    # If self.file_name is not None, append the metering data to a
    # file with that name instead of storing it in Ceilometer.
    # If self.port_number is not None, write the metering data to a
    # port with that number instead of storing it in Ceilometer.
    def putMeter(self,metername,data,authtoken,username='admin',project_id=None,resource_id=None):
#curl -X POST -H 'X-Auth-Token: TOKEN' -H 'Content-Type: application/json'   -d '[{"counter_name": "test","user_id": "admin","resource_id": "76799085-e0ff-4620-9b7f-120d3c51cc49","resource_metadata": {"display_name": "my_test","my_custom_metadata_1": "value1","my_custom_metadata_2": "value2"},"counter_unit": "b/s","counter_volume": 117,"project_id": "855f014353ec48d98ef7b887fc6980e1","counter_type": "gauge"}]'  http://controller:8777/v2/meters/test
        if self.file_name is not None: # Append to file
            with open(self.file_name, "a") as meterfile:
                meterfile.write(json.dumps(data) + '\n')
            return data
        if self.host_and_port is not None: # write to port
            self.meter_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.meter_socket.connect(self.host_and_port)
            self.meter_socket.send(bytes(json.dumps(data) + '\n'))
            return data
        if self.file_name is None and self.port_number is None: # Write to ceilometer
            if project_id is None:
                project_id = self.project_id
            if resource_id is None:
                resource_id = self.resource_id
            headers = {'X-Auth-Token': authtoken, 'Content-Type': 'application/json'}
            datad = {
                'project_id': project_id,
                'counter_type': 'gauge',
                'counter_volume': 4711, # Just some random value. All relevant data is in the resource_metadata field.
                'resource_id': resource_id,
                'counter_unit': 'b/s',
                'user_id': username,
                'resource_metadata': data,
                'counter_name': metername # Should be the same as the meter name at the end of the URL
            }
            payload = [ datad ]
            url = self.meterURL + '/' + metername
            response = requests.post(url, data = json.dumps(payload), headers=headers)
            if response.status_code == requests.codes.ok:
                return response.json()
            else:
                print(json.dumps(response.json(),indent=4))
                response.raise_for_status()
