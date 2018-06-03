"""
Simple demo for Server-Sent Event protocol
"""

import time
import logging
import tornado.escape
import tornado.ioloop
import tornado.options
import tornado.web
import tornado.server_sent_events
import os.path

from tornado.options import define, options

define("port", default=8888, help="run on the given port", type=int)


class Application(tornado.web.Application):
    def __init__(self):
        handlers = [
            (r"/", MainHandler),
            (r"/sse-handler", MessageSourceHandler),
        ]
        settings = dict(
            cookie_secret="43oETzKXQAGaYdkL5gEmGeJJFuYh7EQnp2XdTP1o/Vo=",
            template_path=os.path.join(os.path.dirname(__file__), "templates"),
            xsrf_cookies=True,
            autoescape=None,
        )
        tornado.web.Application.__init__(self, handlers, **settings)


class MainHandler(tornado.web.RequestHandler):
    def get(self):
        self.render("index.html")

class MessageSourceHandler(tornado.server_sent_events.SSEHandler):
    _msg_timeout = None
    counter = 0

    def on_open(self):
        print 'connection %s opened'%self.connection_id

        self.write_message('connection_id', self.connection_id)

        if not MessageSourceHandler._msg_timeout:
            self.send_message()

    def on_close(self):
        print 'connection %s closed'%self.connection_id

    def send_message(self):
        logging.info("sending new message")
        MessageSourceHandler.counter += 1
        MessageSourceHandler.write_message_to_all('message', {
            'waiters': len(MessageSourceHandler._live_connections),
            'counter': MessageSourceHandler.counter,
            })

        MessageSourceHandler._msg_timeout = tornado.ioloop.IOLoop.instance().add_timeout(time.time() + 5, self.send_message)


def main():
    tornado.options.parse_command_line()
    app = Application()
    app.listen(options.port)
    tornado.ioloop.IOLoop.instance().start()


if __name__ == "__main__":
    main()
