#!/usr/bin/env python

"""Usage: python file_receiver.py

Demonstrates a server that receives a multipart-form-encoded set of files in an
HTTP POST, or streams in the raw data of a single file in an HTTP PUT.

See file_uploader.py in this directory for code that uploads files in this format.
"""

import logging

try:
    from urllib.parse import unquote
except ImportError:
    # Python 2.
    from urllib import unquote

import tornado.ioloop
import tornado.web
from tornado import options


class POSTHandler(tornado.web.RequestHandler):
    def post(self):
        for field_name, files in self.request.files.items():
            for info in files:
                filename, content_type = info['filename'], info['content_type']
                body = info['body']
                logging.info('POST "%s" "%s" %d bytes',
                             filename, content_type, len(body))

        self.write('OK')


@tornado.web.stream_request_body
class PUTHandler(tornado.web.RequestHandler):
    def initialize(self):
        self.bytes_read = 0

    def data_received(self, chunk):
        self.bytes_read += len(chunk)

    def put(self, filename):
        filename = unquote(filename)
        mtype = self.request.headers.get('Content-Type')
        logging.info('PUT "%s" "%s" %d bytes', filename, mtype, self.bytes_read)
        self.write('OK')


def make_app():
    return tornado.web.Application([
        (r"/post", POSTHandler),
        (r"/(.*)", PUTHandler),
    ])


if __name__ == "__main__":
    # Tornado configures logging.
    options.parse_command_line()
    app = make_app()
    app.listen(8888)
    tornado.ioloop.IOLoop.current().start()
