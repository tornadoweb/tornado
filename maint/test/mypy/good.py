from asyncio import Future
from concurrent.futures import ThreadPoolExecutor

from tornado import gen
from tornado.concurrent import run_on_executor
from tornado.gen import TimeoutError, WaitIterator
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


def fetch_sync(url: str) -> bytes:
    # run_sync returns the type of the awaitable's result.
    return IOLoop.current().run_sync(lambda: fetch(url))


def make_app() -> Application:
    return Application([URLSpec("/", MyHandler)])


if __name__ == "__main__":
    make_app().listen(8888)
    IOLoop.current().start()


async def first_result(futures: list[Future[int]]) -> int:
    # WaitIterator yields futures of the type it was given.
    async for result in WaitIterator(*futures):
        return result
    return 0


class Worker:
    executor = ThreadPoolExecutor(1)

    @run_on_executor
    def compute(self, x: int) -> str:
        return str(x)


async def use_worker(w: Worker) -> str:
    # run_on_executor keeps the signature and wraps the result in a Future.
    return await w.compute(1)
