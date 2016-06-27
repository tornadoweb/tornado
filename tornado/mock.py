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


class TaskMock(mock.Mock):
    """
    Mock allowing to mock-out code wrapped in `tornado.gen.Task`. Function
    ``Task`` passes param ``callback`` which has to be called to resolve
    `Future <tornado.concurrent.Future>` instance.

    Suitable for mocking ``call_some_sync_api`` from following example:

    .. code-block:: python

        @tornado.gen.coroutine
        def post():
            value = yield self.method()

        @tornado.gen.coroutine
        def method():
            yield tornado.gen.Task(call_some_sync_api)
    """
    def _mock_call(self, *args, **kwds):
        res = super(TaskMock, self)._mock_call(*args, **kwds)
        callback = kwds.get('callback')
        if callback:
            callback(res)
        return res


class FutureMock(mock.Mock):
    """
    Mock allowing to mock-out code which should return
    `Future <tornado.concurrent.Future>` instance. For example
    code decorated by `tornado.gen.coroutine`.

    Suitable for mocking ``method`` from following example:

    .. code-block:: python

        @tornado.gen.coroutine
        def post():
            value = yield self.method()

        @tornado.gen.coroutine
        def method():
            yield tornado.gen.Task(call_some_sync_api)
    """
    def _mock_call(self, *args, **kwds):
        res = super(FutureMock, self)._mock_call(*args, **kwds)
        future = gen.Future()
        future.set_result(res)
        return future
