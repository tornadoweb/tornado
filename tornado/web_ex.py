from __future__ import absolute_import, division, with_statement

import Cookie
import base64
import binascii
import calendar
import datetime
import email.utils
import functools
import gzip
import hashlib
import hmac
import httplib
import itertools
import logging
import mimetypes
import os.path
import re
import stat
import sys
import threading
import time
import tornado
import traceback
import types
import urllib
import urlparse
import uuid

from tornado import escape
from tornado import locale
from tornado import stack_context
from tornado import template
from tornado.escape import utf8, _unicode
from tornado.util import b, bytes_type, import_object, ObjectDict, raise_exc_info
from tornado.web import RequestHandler

class StaticFileExHandler(RequestHandler):
    """A simple handler that can serve static content from a directory.

    To map a path to this handler for a static data directory /var/www,
    you would add a line to your application like::

        application = web.Application([
            (r"/static/(.*)", web.StaticFileHandler, 
                {"path": "/var/www", "dir_explore": True}),
        ])

    The local root directory of the content should be passed as the "path"
    argument to the handler.

    To support aggressive browser caching, if the argument "v" is given
    with the path, we set an infinite HTTP expiration header. So, if you
    want browsers to cache a file indefinitely, send them to, e.g.,
    /static/images/myimage.png?v=xxx. Override ``get_cache_time`` method for
    more fine-grained cache control.
    """
    CACHE_MAX_AGE = 86400 * 365 * 10  # 10 years

    _static_hashes = {}
    _lock = threading.Lock()  # protects _static_hashes

    def initialize(self, path, default_filename=None, dir_explore=False):
        self.root = os.path.abspath(path) + os.path.sep
        self.default_filename = default_filename
        self.dir_explore = dir_explore

    @classmethod
    def reset(cls):
        with cls._lock:
            cls._static_hashes = {}

    def head(self, path):
        self.get(path, include_body=False)

    def get(self, path, include_body=True):
        path = self.parse_url_path(path)
        abspath = os.path.abspath(os.path.join(self.root, path))
        # os.path.abspath strips a trailing /
        # it needs to be temporarily added back for requests to root/
        if not (abspath + os.path.sep).startswith(self.root):
            raise HTTPError(403, "%s is not in root static directory", path)
        if os.path.isdir(abspath) and self.default_filename is not None:
            # need to look at the request.path here for when path is empty
            # but there is some prefix to the path that was already
            # trimmed by the routing
            if not self.request.path.endswith("/"):
                self.redirect(self.request.path + "/")
                return
            abspath = os.path.join(abspath, self.default_filename)
        if not os.path.exists(abspath):
            raise HTTPError(404)
        if not os.path.isfile(abspath):
            if(not self.dir_explore):
                raise HTTPError(403, "%s is not a file", path)
            else:
                file_list = []
                for root, dirs, files in os.walk(dir): 
                    for file in files:
                        file_list.append(root + file)
                self.write("<br/>".join(file_list))
                return

        stat_result = os.stat(abspath)
        modified = datetime.datetime.fromtimestamp(stat_result[stat.ST_MTIME])

        self.set_header("Last-Modified", modified)

        mime_type, encoding = mimetypes.guess_type(abspath)
        if mime_type:
            self.set_header("Content-Type", mime_type)

        cache_time = self.get_cache_time(path, modified, mime_type)

        if cache_time > 0:
            self.set_header("Expires", datetime.datetime.utcnow() + \
                                       datetime.timedelta(seconds=cache_time))
            self.set_header("Cache-Control", "max-age=" + str(cache_time))
        else:
            self.set_header("Cache-Control", "public")

        self.set_extra_headers(path)

        # Check the If-Modified-Since, and don't send the result if the
        # content has not been modified
        ims_value = self.request.headers.get("If-Modified-Since")
        if ims_value is not None:
            date_tuple = email.utils.parsedate(ims_value)
            if_since = datetime.datetime.fromtimestamp(time.mktime(date_tuple))
            if if_since >= modified:
                self.set_status(304)
                return

        with open(abspath, "rb") as file:
            data = file.read()
            hasher = hashlib.sha1()
            hasher.update(data)
            self.set_header("Etag", '"%s"' % hasher.hexdigest())
            if include_body:
                self.write(data)
            else:
                assert self.request.method == "HEAD"
                self.set_header("Content-Length", len(data))

    def set_extra_headers(self, path):
        """For subclass to add extra headers to the response"""
        pass

    def get_cache_time(self, path, modified, mime_type):
        """Override to customize cache control behavior.

        Return a positive number of seconds to trigger aggressive caching or 0
        to mark resource as cacheable, only.

        By default returns cache expiry of 10 years for resources requested
        with "v" argument.
        """
        return self.CACHE_MAX_AGE if "v" in self.request.arguments else 0

    @classmethod
    def make_static_url(cls, settings, path):
        """Constructs a versioned url for the given path.

        This method may be overridden in subclasses (but note that it is
        a class method rather than an instance method).

        ``settings`` is the `Application.settings` dictionary.  ``path``
        is the static path being requested.  The url returned should be
        relative to the current host.
        """
        static_url_prefix = settings.get('static_url_prefix', '/static/')
        version_hash = cls.get_version(settings, path)
        if version_hash:
            return static_url_prefix + path + "?v=" + version_hash
        return static_url_prefix + path

    @classmethod
    def get_version(cls, settings, path):
        """Generate the version string to be used in static URLs.

        This method may be overridden in subclasses (but note that it
        is a class method rather than a static method).  The default
        implementation uses a hash of the file's contents.

        ``settings`` is the `Application.settings` dictionary and ``path``
        is the relative location of the requested asset on the filesystem.
        The returned value should be a string, or ``None`` if no version
        could be determined.
        """
        abs_path = os.path.join(settings["static_path"], path)
        with cls._lock:
            hashes = cls._static_hashes
            if abs_path not in hashes:
                try:
                    f = open(abs_path, "rb")
                    hashes[abs_path] = hashlib.md5(f.read()).hexdigest()
                    f.close()
                except Exception:
                    logging.error("Could not open static file %r", path)
                    hashes[abs_path] = None
            hsh = hashes.get(abs_path)
            if hsh:
                return hsh[:5]
        return None

    def parse_url_path(self, url_path):
        """Converts a static URL path into a filesystem path.

        ``url_path`` is the path component of the URL with
        ``static_url_prefix`` removed.  The return value should be
        filesystem path relative to ``static_path``.
        """
        if os.path.sep != "/":
            url_path = url_path.replace("/", os.path.sep)
        return url_path