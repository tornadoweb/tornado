from tornado.testing import AsyncHTTPTestCase, gen_test
from tornado.web import Application
from tornado.websocket import WebSocketHandler, WebSocketConnect


class EchoHandler(WebSocketHandler):
    def on_message(self, message):
        self.write_message(message, isinstance(message, bytes))


class WebSocketTest(AsyncHTTPTestCase):
    def get_app(self):
        return Application([
            ('/echo', EchoHandler),
        ])

    @gen_test
    def test_websocket_gen(self):
        ws = yield WebSocketConnect(
            'ws://localhost:%d/echo' % self.get_http_port(),
            io_loop=self.io_loop)
        ws.write_message('hello')
        response = yield ws.read_message()
        self.assertEqual(response, 'hello')

    def test_websocket_callbacks(self):
        WebSocketConnect(
            'ws://localhost:%d/echo' % self.get_http_port(),
            io_loop=self.io_loop, callback=self.stop)
        ws = self.wait().result()
        ws.write_message('hello')
        ws.read_message(self.stop)
        response = self.wait().result()
        self.assertEqual(response, 'hello')
