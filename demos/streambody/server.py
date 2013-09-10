'''Demo code of the functionality in the Tornado "streambody" branch,
providing support for streaming request body data in POST and PUT requests.

The streambody branch is available at:
https://github.com/nephics/tornado

Run the demo by first starting the server and then the client.
'''

import os.path
import sys
# use the local version of tornado
sys.path.insert(0, os.path.abspath('../..'))

import hashlib
import logging

logging.basicConfig(level=logging.DEBUG,
        format='%(asctime)-6s: %(levelname)s - %(message)s')


import tornado.ioloop
import tornado.web


class MainHandler(tornado.web.RequestHandler):
    def put(self):
        md5 = hashlib.md5(self.request.body)
        self.write('Default body handler: received %d bytes\n%s'
                % (len(self.request.body), md5.hexdigest()))


@tornado.web.stream_body
class StreamHandler(tornado.web.RequestHandler):

    def put(self):
        self.read_bytes = 0
        self.request.request_continue()
        self.read_chunks()
        self.md5 = hashlib.md5()

    def read_chunks(self, chunk=''):
        self.read_bytes += len(chunk)
        if chunk:
            logging.info('Received {} bytes'.format(len(chunk)))
            self.md5.update(chunk)
        chunk_length = min(100000,
                self.request.content_length - self.read_bytes)
        if chunk_length > 0:
            self.request.connection.stream.read_bytes(
                    chunk_length, self.read_chunks)
        else:
            self.uploaded()

    def uploaded(self):
        self.write('Stream body handler: received %d bytes\n%s'
                % (self.read_bytes, self.md5.hexdigest()))
        self.finish()


if __name__ == "__main__":
    application = tornado.web.Application([
        (r"/", MainHandler),
        (r"/stream", StreamHandler),
    ])
    application.listen(8888)
    tornado.ioloop.IOLoop.instance().start()
