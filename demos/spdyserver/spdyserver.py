#!/usr/bin/env python
#
# Copyright 2009 Facebook
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

import os.path

import tornado.spdy
import tornado.ioloop
import tornado.options
import tornado.web

from tornado.options import define, options

define("port", default=8888, help="run on the given port", type=int)

class MainHandler(tornado.web.RequestHandler):
    def get(self):
        self.write("Hello, world")

def main():
    tornado.options.parse_command_line()

    application = tornado.web.Application([
        (r"/", MainHandler),
        ])

    ssl_options = {}

    base_dir = os.path.dirname(__file__)

    cert_file = os.path.join(base_dir, 'certificate.pem')
    key_file = os.path.join(base_dir, 'privatekey.pem')

    if os.path.exists(cert_file) and os.path.exists(key_file):
        """
        openssl genrsa -out privatekey.pem 1024
        openssl req -new -key privatekey.pem -out certrequest.csr
        openssl x509 -req -in certrequest.csr -signkey privatekey.pem -out certificate.pem
        """
        ssl_options.update(certfile=cert_file, keyfile=key_file)

    spdy_options = {}

    http_server = tornado.spdy.SPDYServer(application, ssl_options=ssl_options, spdy_options=spdy_options)
    http_server.listen(options.port)

    tornado.ioloop.IOLoop.instance().start()

if __name__ == "__main__":
    main()
