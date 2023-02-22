#!/usr/bin/env python

import asyncio
import tornado.httpserver
import tornado.options
import tornado.web

from tornado.options import define, options

define("port", default=8888, help="run on the given port", type=int)


async def do_slow_task(task, param1, param2):
    await asyncio.sleep(3)
    print('Task is Done: ', task)
    print('Param1: ', param1)
    print('Param2: ', param2)

class MainHandler(tornado.web.RequestHandler):
    def get(self):
        task = self.get_query_argument('task')
        self.add_background_task(do_slow_task, task, 'param1', 'param2')
        self.write(f"Hello {task}")


async def main():
    tornado.options.parse_command_line()
    application = tornado.web.Application([(r"/", MainHandler)])
    http_server = tornado.httpserver.HTTPServer(application)
    http_server.listen(options.port)
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
