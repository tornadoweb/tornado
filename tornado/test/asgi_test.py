import unittest

try:
    import async_asgi_testclient  # type: ignore
except ImportError:
    async_asgi_testclient = None

from tornado.asgi import ASGIAdapter
from tornado.web import Application, RequestHandler
from tornado.testing import AsyncTestCase, gen_test


class BasicHandler(RequestHandler):
    def get(self):
        name = self.get_argument("name", "world")
        self.write(f"Hello, {name}")


class InspectHandler(RequestHandler):
    def make_response(self, path_var):
        # Send the response as JSON
        self.finish(
            {
                "method": self.request.method,
                "path": self.request.path,
                "path_var": path_var,
                "query_params": {
                    k: self.get_query_arguments(k) for k in self.request.query_arguments
                },
                "body": self.request.body.decode("latin1"),
            }
        )

    def get(self, path_var):
        return self.make_response(path_var)

    def post(self, path_var):
        return self.make_response(path_var)


@unittest.skipIf(
    async_asgi_testclient is None, "async_asgi_testclient module not present"
)
class AsyncASGITestCase(AsyncTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.asgi_app = ASGIAdapter(
            Application([(r"/", BasicHandler), (r"/inspect(/.*)", InspectHandler)])
        )
        self.client = async_asgi_testclient.TestClient(self.asgi_app)

    @gen_test
    async def test_basic_request(self):
        resp = await self.client.get("/?name=foo")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.text, "Hello, foo")

    @gen_test
    async def test_get_request_details(self):
        resp = await self.client.get("/inspect/foo/?bar=baz")
        d = resp.json()
        self.assertEqual(d["method"], "GET")
        self.assertEqual(d["path"], "/inspect/foo/")
        self.assertEqual(d["query_params"], {"bar": ["baz"]})
        self.assertEqual(d["body"], "")

    @gen_test
    async def test_post_request_details(self):
        resp = await self.client.post("/inspect/foo/?bar=baz", data=b"123")
        d = resp.json()
        self.assertEqual(d["method"], "POST")
        self.assertEqual(d["path"], "/inspect/foo/")
        self.assertEqual(d["query_params"], {"bar": ["baz"]})
        self.assertEqual(d["body"], "123")
