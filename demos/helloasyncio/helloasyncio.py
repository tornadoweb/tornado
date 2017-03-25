import asyncio
import tornado.httpserver
import tornado.ioloop
import tornado.gen
import tornado.options
import tornado.web

from tornado.options import define, options

define("port", default=8888, help="run on the given port", type=int)

from tornado.ioloop import IOLoop

IOLoop.configure('tornado.platform.asyncio.AsyncIOLoop')


class MainHandler(tornado.web.RequestHandler):
    @tornado.gen.coroutine
    def get(self):
        # Read some data asynchronously, note that 'yield from' is used
        output = yield from self.quick_async()
        self.write(output)

        # Run long running task and don't wait for result, i.e. send email.
        # Total execution time is about 5 seconds, but server is
        # not blocked here. Just refresh the page to make sure.
        self.loop().create_task(self.long_task())

    def loop(self):
        """Get current asyncio event loop.
        """
        return tornado.ioloop.IOLoop.current().asyncio_loop

    @asyncio.coroutine
    def quick_async(self):
        """Some "quick" asynchronous operation. We just fake it with async sleep.
        Please note, that we have to perform async calls on current loop!
        """
        # We MUST explicitly provide asyncio loop instance, because
        # the application may run on its own loop, not the default one!
        yield from asyncio.sleep(0.5, loop=self.loop())
        return "Hello, world"

    @asyncio.coroutine
    def long_task(self):
        """Some "long" asynchronous operation. We just fake it with repeated
        async sleep.
        """
        for n in range(5):
            yield from asyncio.sleep(1.0, loop=self.loop())
            print("long_task is running:", n)


def main():
    tornado.options.parse_command_line()
    application = tornado.web.Application([
        (r"/", MainHandler),
    ], debug=True)
    http_server = tornado.httpserver.HTTPServer(application)
    http_server.listen(options.port)

    # Note how we can get access to asyncio loop instance
    loop = tornado.ioloop.IOLoop.current().asyncio_loop
    loop.run_forever()


if __name__ == "__main__":
    main()