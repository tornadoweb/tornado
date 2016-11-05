#!/usr/bin/env python

"""Usage: python file_uploader.py [--put] file1.txt file2.png ...

Demonstrates uploading files to a server, without concurrency. It can either
POST a multipart-form-encoded request containing one or more files, or PUT a
single file without encoding.

See also file_receiver.py in this directory, a server that receives uploads.
"""

import mimetypes
import os
import sys
from functools import partial
from uuid import uuid4

try:
    from urllib.parse import quote
except ImportError:
    # Python 2.
    from urllib import quote

from tornado import gen, httpclient, ioloop
from tornado.options import define, options


# Using HTTP POST, upload one or more files in a single multipart-form-encoded
# request.
@gen.coroutine
def multipart_producer(boundary, filenames, write):
    boundary_bytes = boundary.encode()

    for filename in filenames:
        filename_bytes = filename.encode()
        write(b'--%s\r\n' % (boundary_bytes,))
        write(b'Content-Disposition: form-data; name="%s"; filename="%s"\r\n' %
              (filename_bytes, filename_bytes))

        mtype = mimetypes.guess_type(filename)[0] or 'application/octet-stream'
        write(b'Content-Type: %s\r\n' % (mtype.encode(),))
        write(b'\r\n')
        with open(filename, 'rb') as f:
            while True:
                # 16k at a time.
                chunk = f.read(16 * 1024)
                if not chunk:
                    break
                write(chunk)

                # Let the IOLoop process its event queue.
                yield gen.moment

        write(b'\r\n')
        yield gen.moment

    write(b'--%s--\r\n' % (boundary_bytes,))


# Using HTTP PUT, upload one raw file. This is preferred for large files since
# the server can stream the data instead of buffering it entirely in memory.
@gen.coroutine
def post(filenames):
    client = httpclient.AsyncHTTPClient()
    boundary = uuid4().hex
    headers = {'Content-Type': 'multipart/form-data; boundary=%s' % boundary}
    producer = partial(multipart_producer, boundary, filenames)
    response = yield client.fetch('http://localhost:8888/post',
                                  method='POST',
                                  headers=headers,
                                  body_producer=producer)

    print(response)


@gen.coroutine
def raw_producer(filename, write):
    with open(filename, 'rb') as f:
        while True:
            # 16K at a time.
            chunk = f.read(16 * 1024)
            if not chunk:
                # Complete.
                break

            write(chunk)


@gen.coroutine
def put(filenames):
    client = httpclient.AsyncHTTPClient()
    for filename in filenames:
        mtype = mimetypes.guess_type(filename)[0] or 'application/octet-stream'
        headers = {'Content-Type': mtype}
        producer = partial(raw_producer, filename)
        url_path = quote(os.path.basename(filename))
        response = yield client.fetch('http://localhost:8888/%s' % url_path,
                                      method='PUT',
                                      headers=headers,
                                      body_producer=producer)
    
        print(response)


define("put", type=bool, help="Use PUT instead of POST", group="file uploader")

# Tornado configures logging from command line opts and returns remaining args.
filenames = options.parse_command_line()
if not filenames:
    print("Provide a list of filenames to upload.", file=sys.stderr)
    sys.exit(1)

method = put if options.put else post
ioloop.IOLoop.current().run_sync(lambda: method(filenames))
