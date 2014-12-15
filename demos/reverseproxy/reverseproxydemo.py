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

import tornado.escape
import tornado.httpserver
import tornado.ioloop
import tornado.web
from tornado.httpclient import AsyncHTTPClient
from tornado.concurrent import Future
from tornado import gen
from tornado.options import define, options, parse_command_line

define("port", default=8888, help="run on the given port", type=int)

# This is a substandard reverse proxy to illustrate asynchronous non blocking IO, 
# coroutines, use of futures, yield, and chaining of coroutines.
#
# It also demonstrates passing arguments to handlers.
#
# There are three different "fetchers" which provide information to be presented
# to the caller.  One uses a coroutine to produce a future, another uses a callback,
# and the third does not produce a future, but rather returns a response object.

class Application(tornado.web.Application):
    def __init__(self):
        handlers = [
            (r"/", MainHandler, {"url":"http://www.example.com/"}),
            (r"/coroutine", MainHandler, {"fetcher":"CoroutineFetcher"}),
            (r"/err", MainHandler, {"url":"asdf://this.is.broken/"}),
            (r"/spiffy", MainHandler, {"subst":"Spiffy"}),
            (r"/hello", MainHandler, {"fetcher":"HelloFetcher"})
        ]
        tornado.web.Application.__init__(self, handlers,dict())

class MainHandler(tornado.web.RequestHandler):
    def initialize(self,url="http://www.example.com/",subst=None,fetcher="CoroutineFetcher"):
        """This handler accepts named parameters.  After __init__ is called, 
        the application calls initialize() with the parameters contained
        in the dictionary passed in each handler's entry."""
        self.url=url
        self.subst=subst
        self.fetcher=fetcher

    @gen.coroutine
    def get(self):
        # construct the appropriate fetcher
        fetcher=eval(self.fetcher + "()")
 
        # maybe_future makes yield work whether or not the fetcher returns a future
        response=yield gen.maybe_future(fetcher.go_fetch(self.url))
        body=response.body

        # If a substitution was requested, perform it (post-processing)
        if self.subst:
            body=body.replace(bytearray("Example","utf8"),bytearray(self.subst,"utf8"))

        # write out the result
        self.write(body)

class CoroutineFetcher():
    """This is an ordinary async IO invocation with coroutine"""
    @gen.coroutine
    def go_fetch(self,url):
        http_client=AsyncHTTPClient()
        response=yield http_client.fetch(url)
        return response

class FetcherWithCallback():
    """If http_client required a callback, it would look more like this.
    Since this code does not include a "yield", it also does not require 
    the @gen.coroutine annotation."""
    def go_fetch(self,url):
        http_client=AsyncHTTPClient()
        future=Future()
        def callback(response):
            if response.error:
               future.set_exception(response.error)
            else:
               future.set_result(response)

        http_client.fetch(url,callback)
        return future

class MockResponse():
    def __init__(self,body):
       self.body=body

class HelloFetcher():
    """This returns a "response" without leaving the server.  Since it is not a future, 
       it requires special handling by the caller."""
    def go_fetch(self,url):
       return MockResponse("Hello, world!")

def main():
    parse_command_line()
    http_server = tornado.httpserver.HTTPServer(Application())
    http_server.listen(options.port)
    tornado.ioloop.IOLoop.instance().start()

if __name__ == "__main__":
    main()
