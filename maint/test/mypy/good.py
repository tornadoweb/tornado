from tornado import gen
from tornado.gen import TimeoutError
from tornado.httpclient import AsyncHTTPClient, HTTPResponse
from tornado.ioloop import IOLoop
from tornado.web import Application, RequestHandler, URLSpec


class MyHandler(RequestHandler):
    def get(self) -> None:
        self.write("foo")

    async def post(self) -> None:
        await gen.sleep(1)
        self.write("foo")


async def fetch(url: str) -> bytes:
    response: HTTPResponse = await AsyncHTTPClient().fetch(url)
    return response.body


async def fetch_with_timeout(url: str) -> bytes | None:
    # Names that modules re-export must be usable under --strict.
    try:
        body: bytes = await gen.with_timeout(1, fetch(url))
        return body
    except TimeoutError:
        return None


def make_app() -> Application:
    return Application([URLSpec("/", MyHandler)])


if __name__ == "__main__":
    make_app().listen(8888)
    IOLoop.current().start()
