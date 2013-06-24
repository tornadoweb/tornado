#!/usr/bin/env python
# -*- coding:utf-8 -*- 
"""
    author comger@gmail.com
"""
import tornado.web
from tornado.router import url

@url(r'/')
class IndexHandler(tornado.web.RequestHandler):
    def get(self):
        self.write('index ok')


@url(r'/about')
class AboutHandler(tornado.web.RequestHandler):
    def get(self):
        self.write('about')

