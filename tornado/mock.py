"""
Mocks for mocking-out asynchronous functions. Works the same way as
`unittest.mock.Mock` from Python standard library.

Note when you are using older Python than 3.3 you have to install
module ``mock``.
"""
from __future__ import absolute_import

try:
    from unittest import mock
except ImportError:
    import mock

from tornado import gen


class AsyncMock(mock.Mock):
    """
    Mock allowing to mock-out code returning `tornado.concurrent.Future`
    instance. For example functions decorated by `tornado.gen.coroutine`
    or by `tornado.gen.Task`.

    Note you can use everything as with standard ``mock.Mock``.

    Example usage:

    .. code-block:: python

        class Handler(tornado.web.RequestHandler):
            @tornado.gen.coroutine
            def post(self):
                value = yield self.method()

            @tornado.gen.coroutine
            def method(self):
                yield tornado.gen.Task(self.inner_method)

            def inner_method(self):
                return 'whatever'

        def test_method():
            with mock.patch.object(Handler, 'method', AsyncMock(return_value=42)):
                assert 42 == Handler().method()

        def test_inner_method():
            with mock.patch.object(Handler, 'inner_method', AsyncMock(return_value=42)):
                assert 42 == Handler().method()
    """
    def __call__(self, *args, **kwds):
        future = gen.Future()
        callback = kwds.get('callback', lambda val: None)
        try:
            res = super(AsyncMock, self).__call__(*args, **kwds)
        except Exception as exc:
            future.set_exception(exc)
            callback(exc)
        else:
            future.set_result(res)
            callback(res)
        return future
