from tornado import gen
from tornado.web import RequestHandler


class MyHandler(RequestHandler):
    def get(self) -> None:
        self.write("foo")

    async def post(self) -> None:
        await gen.sleep(1)
        self.write("foo")
