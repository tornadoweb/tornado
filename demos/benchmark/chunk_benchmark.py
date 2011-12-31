#!/usr/bin/env python
#
# Downloads a large file in chunked encoding with both curl and simple clients

import logging
from tornado.curl_httpclient import CurlAsyncHTTPClient
from tornado.simple_httpclient import SimpleAsyncHTTPClient
from tornado.ioloop import IOLoop
from tornado.options import define, options, parse_command_line
from tornado.web import RequestHandler, Application

define('port', default=8888)
define('num_chunks', default=1000)
define('chunk_size', default=2048)

class ChunkHandler(RequestHandler):
    def get(self):
        for i in xrange(options.num_chunks):
            self.write('A' * options.chunk_size)
            self.flush()
        self.finish()

def main():
    parse_command_line()
    app = Application([('/', ChunkHandler)])
    app.listen(options.port, address='127.0.0.1')
    def callback(response):
        response.rethrow()
        assert len(response.body) == (options.num_chunks * options.chunk_size)
        logging.warning("fetch completed in %s seconds", response.request_time)
        IOLoop.instance().stop()

    logging.warning("Starting fetch with curl client")
    curl_client = CurlAsyncHTTPClient()
    curl_client.fetch('http://localhost:%d/' % options.port,
                      callback=callback)
    IOLoop.instance().start()

    logging.warning("Starting fetch with simple client")
    simple_client = SimpleAsyncHTTPClient()
    simple_client.fetch('http://localhost:%d/' % options.port,
                        callback=callback)
    IOLoop.instance().start()
    

if __name__ == '__main__':
    main()
