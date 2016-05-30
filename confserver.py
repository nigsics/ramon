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

import json
import sys, os
import SocketServer

class ConfTCPServer(SocketServer.ThreadingMixIn, SocketServer.TCPServer):
    def __init__(self, (host, port), handler):
        SocketServer.TCPServer.__init__(self, (host, port), handler, bind_and_activate=False)
        self.allow_reuse_address = True
        self.server_bind()
        self.server_activate()

BaseRequestHandler = SocketServer.BaseRequestHandler

def createConfServer(Host,Port,handler):
    class ConfTCPServerHandler(BaseRequestHandler):
        def handle(self):
            try:
                data = json.loads(self.request.recv(1024).decode('UTF-8').strip())
                if handler.debug:
                    handler.debugPrint('ConfTCPServerHandler.handle(): handler.config_queue.put(' + repr(data))
                handler.config_queue.put(data)
                handler.conf_event.set()
                handler.config_queue.join()
                if handler.debug:
                    handler.debugPrint('ConfTCPServerHandler.handle: ' + repr(handler.config_reply) + '.get()')
                    handler.debugPrint('ConfTCPServerHandler.handle: qsize==' + repr(handler.config_reply.qsize()))
                reply = handler.config_reply.get()
                handler.config_reply.task_done()
                if handler.debug:
                    handler.debugPrint('ConfTCPServerHandler.handle: self.request.sendall(bytes(json.dumps({\'return\': reply})))')
                self.request.sendall(bytes(json.dumps({'return': reply})))

            except Exception as e:
                print("ConfTCPServerHandler.handle(): Exception while receiving message: ", e)
                exc_type, exc_obj, exc_tb = sys.exc_info()
                fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
                print("                              ", exc_type, fname, exc_tb.tb_lineno)
                self.request.sendall(bytes(json.dumps({'return': str(e)})))

    confserver = ConfTCPServer((Host,Port),ConfTCPServerHandler)
    return confserver
