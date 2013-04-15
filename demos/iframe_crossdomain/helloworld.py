#!/usr/bin/env python
#
# Copyright 2009 Facebook
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

"""Implementation with iframe cross domain using postmessage

"""
import tornado.httpserver
import tornado.ioloop
import tornado.options
import tornado.web
import os
from time import sleep
from tornado.options import define, options
from simplejson import dumps

define("port", default=8888, help="run on the given port", type=int)


class MainHandler(tornado.web.RequestHandler):
    @tornado.web.asynchronous
    def get(self):

        self.write(u"""<script src="http://postmessage.freebaseapps.com/postmessage.js"></script>""")
        self.flush()

        for i in range(10):
            sleep(1)
            item = 'pos %s' % i
            code = u"""<script>pm({
              target: window.parent,
              type:"Update",
              data: %s
            });</script>""" % dumps(item)
            self.write(code)
            self.flush()

        print 'finish'
        self.finish()


def main():
    tornado.options.parse_command_line()
    application = tornado.web.Application([
        (r"/keepalive.js", MainHandler),
    ],
        static_path=os.path.join(os.path.dirname(__file__), "static"),
    )
    http_server = tornado.httpserver.HTTPServer(application)
    http_server.listen(options.port)
    tornado.ioloop.IOLoop.instance().start()


if __name__ == "__main__":
    main()
