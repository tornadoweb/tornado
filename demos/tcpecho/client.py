#!/usr/bin/env python

import asyncio
from tornado.tcpclient import TCPClient
from tornado.options import options, define

define("host", default="localhost", help="TCP server host")
define("port", default=9888, help="TCP port to connect to")
define("message", default="ping", help="Message to send")


async def send_message():
    stream = await TCPClient().connect(options.host, options.port)
    await stream.write((options.message + "\n").encode())
    print("Sent to server:", options.message)
    reply = await stream.read_until(b"\n")
    print("Response from server:", reply.decode().strip())


if __name__ == "__main__":
    options.parse_command_line()
    asyncio.run(send_message())
