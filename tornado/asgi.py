import inspect
from asyncio import create_task, Future, Task, wait
from collections.abc import AsyncGenerator, Awaitable, Callable
from dataclasses import dataclass
from typing import Optional, Union

from tornado.httputil import (
    HTTPConnection,
    HTTPHeaders,
    RequestStartLine,
    ResponseStartLine,
)
from tornado.web import Application

ReceiveCallable = Callable[[], Awaitable[dict]]
SendCallable = Callable[[dict], Awaitable[None]]
ApplicationGen = Callable[[], AsyncGenerator]


@dataclass
class ASGIHTTPRequestContext:
    """To convey connection details to the HTTPServerRequest object"""

    protocol: str
    address: Optional[tuple] = None
    remote_ip: str = "0.0.0.0"


class ASGIHTTPConnection(HTTPConnection):
    """Represents the connection for 1 request/response pair

    This provides the API for sending the response.
    """

    def __init__(self, send_cb: SendCallable, context: ASGIHTTPRequestContext):
        self.send_cb = send_cb
        self.context = context
        self.task_holder: set[Task] = set()
        self._close_callback: Callable[[], None] | None = None
        self._request_finished: Future[None] = Future()

    # Various tornado APIs (e.g. RequestHandler.flush()) return a Future which
    # application code does not need to await. The operations these represent
    # are expected to complete even if the Future is not awaited. We hold onto
    # these on the connection so they are not destroyed, and so that we can
    # wait for them at the end of the ASGI connections scope.
    def _bg_task(self, coro) -> Future:  # type: ignore
        task = create_task(coro)
        self.task_holder.add(task)
        task.add_done_callback(self.task_holder.discard)
        return task

    async def _write_headers(
        self,
        start_line: Union["RequestStartLine", "ResponseStartLine"],
        headers: HTTPHeaders,
        chunk: Optional[bytes] = None,
    ) -> None:
        assert isinstance(start_line, ResponseStartLine)
        await self.send_cb(
            {
                "type": "http.response.start",
                "status": start_line.code,
                "headers": [
                    [k.lower().encode("latin1"), v.encode("latin1")]
                    for k, v in headers.get_all()
                ],
            }
        )
        if chunk is not None:
            await self._write(chunk)

    def write_headers(
        self,
        start_line: Union["RequestStartLine", "ResponseStartLine"],
        headers: HTTPHeaders,
        chunk: Optional[bytes] = None,
    ) -> "Future[None]":
        return self._bg_task(self._write_headers(start_line, headers, chunk))

    async def _write(self, chunk: bytes) -> None:
        await self.send_cb(
            {"type": "http.response.body", "body": chunk, "more_body": True}
        )

    def write(self, chunk: bytes) -> "Future[None]":
        return self._bg_task(self._write(chunk))

    def finish(self) -> None:
        self._bg_task(
            self.send_cb(
                {
                    "type": "http.response.body",
                    "body": b"",
                    "more_body": False,
                }
            )
        )
        self._request_finished.set_result(None)

    def set_close_callback(self, callback: Optional[Callable[[], None]]) -> None:
        self._close_callback = callback

    def _on_connection_close(self) -> None:
        if self._close_callback is not None:
            callback = self._close_callback
            self._close_callback = None
            callback()
        self._request_finished.set_result(None)

    async def wait_finish(self) -> None:
        """For the ASGI interface: wait for all input & output to finish"""
        await self._request_finished
        await wait(self.task_holder)


class ASGIAdapter:
    """Wrap a tornado application object to use with an ASGI server"""

    application: Optional[Application]

    def __init__(self, application: Application | ApplicationGen):
        if isinstance(application, Application):
            self.application_gen = None
            self.application = application
        elif inspect.isasyncgenfunction(application):
            self.application_gen = application()
            self.application = None
        else:
            raise TypeError(f"ASGIAdapter does not recognise {application!r}")

    async def __call__(
        self, scope: dict, receive: ReceiveCallable, send: SendCallable
    ) -> None:
        if scope["type"] == "lifespan":
            return await self.lifespan_scope(scope, receive, send)
        if scope["type"] == "http":
            return await self.http_scope(scope, receive, send)
        raise KeyError(scope["type"])

    async def _initialise_application(self) -> None:
        # Ideally triggered by a lifespan startup message, but if the server
        # doesn't support that, we'll do the setup on the first request.
        if self.application is None:
            assert self.application_gen is not None
            self.application = await anext(self.application_gen)

    async def lifespan_scope(
        self, scope: dict, receive: ReceiveCallable, send: SendCallable
    ) -> None:
        while True:
            event = await receive()
            if event["type"] == "lifespan.startup":
                try:
                    await self._initialise_application()
                except Exception as e:
                    await send({"type": "lifespan.startup.failed", "message": str(e)})
                else:
                    await send({"type": "lifespan.startup.complete"})

            elif event["type"] == "lifespan.shutdown":
                try:
                    if self.application_gen is not None:
                        await anext(self.application_gen)
                except StopAsyncIteration:
                    await send({"type": "lifespan.shutdown.complete"})
                except Exception as e:
                    await send({"type": "lifespan.shutdown.failed", "message": str(e)})
                else:
                    await send(
                        {
                            "type": "lifespan.shutdown.failed",
                            "message": "Async generator did not exit as expected",
                        }
                    )

    async def http_scope(
        self, scope: dict, receive: ReceiveCallable, send: SendCallable
    ) -> None:
        """Handles one HTTP request"""
        await self._initialise_application()
        assert self.application is not None

        ctx = ASGIHTTPRequestContext(scope["scheme"])
        if client_addr := scope.get("client", None):
            ctx.address = tuple(client_addr)
            ctx.remote_ip = client_addr[0]

        conn = ASGIHTTPConnection(send, ctx)
        msg_delegate = self.application.start_request(None, conn)
        start_line, req_headers = self._http_convert_req(scope)
        if (fut := msg_delegate.headers_received(start_line, req_headers)) is not None:
            await fut

        while True:
            event = await receive()
            if event["type"] == "http.request":
                if chunk := event.get("body", b""):
                    if (fut := msg_delegate.data_received(chunk)) is not None:
                        await fut
                if not event.get("more_body", False):
                    msg_delegate.finish()
                    break
            elif event["type"] == "http.disconnect":
                msg_delegate.on_connection_close()
                conn._on_connection_close()
                break

        await conn.wait_finish()

    @staticmethod
    def _http_convert_req(scope: dict) -> tuple[RequestStartLine, HTTPHeaders]:
        req_target = scope["path"]
        if qs := scope["query_string"]:
            req_target += "?" + qs.decode("latin1")
        req_start_line = RequestStartLine(
            scope["method"], req_target, scope["http_version"]
        )
        req_headers = HTTPHeaders()
        for k, v in scope["headers"]:
            req_headers.add(k.decode("latin1"), v.decode("latin1"))

        return req_start_line, req_headers
