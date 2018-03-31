# -*- coding: utf-8 -*-
"""
    tornado.blueprints
    ~~~~~~~~~~~~~~~~

    Blueprints are the recommended way to implement larger or more
    pluggable applications in Tornado.
"""
from __future__ import absolute_import

from tornado.web import RequestHandler

__all__ = ["Blueprint", "RouteRuleDuplicate"]


class RouteRuleDuplicate(Exception):
    """Exception class for register duplicate handlers with the same url.
    """

    def __init__(self, url, handler):
        error = "Url {!r} already registerd with handler {!r}".format(url, handler.__name__)
        super(RouteRuleDuplicate, self).__init__(error)


class Blueprint(object):
    """Represents a blueprint.  A blueprint is an object that records
    handlers that will be registered with the web application.
    """

    def __init__(self, name, verbose=True):
        self.name = name
        self.verbose = verbose
        self.router = {}

    def route(self, url, host_pattern=None):
        def wrapper(handler):
            assert issubclass(handler, RequestHandler)
            _rules = self.router.get(url)
            if _rules and self.verbose:
                raise RouteRuleDuplicate(url, _rules[0])
            self.router[url] = (handler, host_pattern or ".*$")
            return handler
        return wrapper

    def register(self, app, url_prefix=None):
        for url, rule in self.router.items():
            handler, host_pattern = rule
            if url_prefix:
                _prefix = url_prefix.rstrip("/").split("/")
                _suffix = url.strip("/").split("/")
                url = "/".join(_prefix + _suffix)
            app.add_handlers(host_pattern, [(url, handler)])