from tornado.web import RequestHandler


class MyHandler(RequestHandler):
    def get(self) -> str:  # Deliberate type error
        return "foo"
