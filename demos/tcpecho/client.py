from __future__ import print_function
from tornado.ioloop import IOLoop
from tornado import gen
from tornado.tcpclient import TCPClient
from tornado.options import options, define

define("host", default="localhost", help="TCP server host")
define("port", default=9888, help="TCP port to connect to")
define("message", default="ping", help="Message to send")


@gen.coroutine
def send_message():
    stream = yield TCPClient().connect(options.host, options.port)
    yield stream.write((options.message + "\n").encode())
    print("Sent to server:", options.message)
    reply = yield stream.read_until(b"\n")
    print("Response from server:", reply.decode().strip())


if __name__ == "__main__":
    options.parse_command_line()
    IOLoop.current().run_sync(send_message)
