#!/usr/bin/python3

import time

import tornado.ioloop
import tornado.web
import tornado.websocket
from tornado import gen

MSG = memoryview(b'qwe') # [b'x' * (30 * 1024)] * 100 + [memoryview(b'qwe')]

if isinstance(MSG, list):
    totlen = sum(len(i) for i in MSG)
else:
    totlen = len(MSG)

class ChatSocketHandler(tornado.websocket.WebSocketHandler):
    def get_compression_options(self):
        # Non-None enables compression with default options.
        return None

    @gen.coroutine
    def on_message(self, message):
        iterations = 100
        start = time.monotonic()
        for _ in range(iterations):
            yield self.write_message(MSG)  # yielding here changes from 319 to 265 MB/s
        stop = time.monotonic()
        print('Speed: {:0.02f} MB/s'.format(iterations * totlen / ((stop - start) * 1000000)))
        self.close()


class MainHandler(tornado.web.RequestHandler):
    def get(self):
        self.set_header('content-type', 'text/html')
        self.write('''
        <body>
            <script>
                var ws = new WebSocket("ws://localhost:1234/test");
                ws.onopen = function() {
                   ws.send("start!");
                };
                ws.onmessage = function (evt) {
                   // alert(evt.data);
                };
            </script>
        </body>
        ''')


def main():
    app = tornado.web.Application(handlers=[
        (r'/', MainHandler),
        (r"/test", ChatSocketHandler)
    ])
    app.listen(1234)
    print('Go to http://localhost:1234 and see results in console.')
    tornado.ioloop.IOLoop.current().start()


if __name__ == "__main__":
    main()
