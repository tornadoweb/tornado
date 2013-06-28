#!/usr/bin/env python
# -*- coding:utf-8 -*- 
"""
    demo for tornado handler router
    author comger@gmail.com
"""
import tornado.ioloop
import tornado.web

from action import index
from tornado.router import load_handlers

if __name__ == "__main__":

    handlers = load_handlers()
    for h in handlers:
        print h


    app = tornado.web.Application(handlers)
    app.listen(8888)
    tornado.ioloop.IOLoop.instance().start()



