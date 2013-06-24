#!/usr/bin/env python
# -*- coding:utf-8 -*- 
"""
    Request router for tornado
    author comger@gmail.com
"""
import os
import tornado.web

from fnmatch import fnmatch
from inspect import getmembers


def url(pattern, order = 0):
    """
        设置路径匹配模式和排序序号
        支持多次设置及排序
        
        Demo:
        @url('/blog/info/{0}')
        class ActionHandler(tornado.web.RequestHandler):
            def get(self,blogid):
                pass
    """
    def actual(handler):
        assert(issubclass(handler, tornado.web.RequestHandler))
        if not hasattr(handler, "__urls__") or not handler.__urls__: handler.__urls__ = []
        handler.__urls__.append((pattern, order))

        return handler

    return actual

def load_handlers(handler_dir = 'action'):
    '''
        加载指定目录的RequestHandler
        Load handler_dir's Handler
        Demo:
        handlers = load_handlers():
        app = tornado.web.Application(handlers)
    '''
    path = os.path.join(os.getcwd(), handler_dir)
    py_filter = lambda f:fnmatch(f, '*.py') and not f.startswith('__')
    member_filter = lambda m:isinstance(m, type) and issubclass(m, tornado.web.RequestHandler) and hasattr(m, '__urls__') and m.__urls__

    names = [os.path.splitext(n)[0] for n in os.listdir(path) if py_filter(n)]
    modules = [__import__("{0}.{1}".format(handler_dir, n)).__dict__[n] for n in names]

    ret = {}
    for m in modules:
        members = dict(("{0}.{1}".format(v.__module__, k), v) for k, v in getmembers(m, member_filter))
        ret.update(members)
    
    handlers = [(pattern, order, h) for h in ret.values() for pattern, order in h.__urls__]
    handlers.sort(cmp = cmp, key = lambda x: x[1])

    return [(pattern, handler) for pattern, _, handler in handlers]
