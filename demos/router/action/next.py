#!/usr/bin/env python
# -*- coding:utf-8 -*- 
"""
    author comger@gmail.com
"""
import tornado.web
from tornado.router import url

@url(r'/next')
class NextHandler(tornado.web.RequestHandler):
    def get(self):
        self.write('next')



