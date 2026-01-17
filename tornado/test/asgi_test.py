from async_asgi_testclient import TestClient

from tornado.asgi import ASGIAdapter
from tornado.web import Application, RequestHandler
from tornado.testing import AsyncTestCase, gen_test


class BasicHandler(RequestHandler):
    def get(self):
        name = self.get_argument("name", "world")
        self.write(f"Hello, {name}")


class AsyncASGITestCase(AsyncTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.asgi_app = ASGIAdapter(
            Application(
                [
                    (r"/", BasicHandler),
                ]
            )
        )

    @gen_test(timeout=None)
    async def test_basic_request(self):
        client = TestClient(self.asgi_app)
        resp = await client.get("/?name=foo")
        assert resp.status_code == 200
        assert resp.text == "Hello, foo"
