.. currentmodule:: tornado.web

Structure of a Tornado web application
======================================

Request handlers and request arguments
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

A Tornado web application maps URLs or URL patterns to subclasses of
`tornado.web.RequestHandler`. Those classes define ``get()`` or
``post()`` methods to handle HTTP ``GET`` or ``POST`` requests to that
URL.

This code maps the root URL ``/`` to ``MainHandler`` and the URL pattern
``/story/([0-9]+)`` to ``StoryHandler``. Regular expression groups are
passed as arguments to the ``RequestHandler`` methods:

::

    class MainHandler(tornado.web.RequestHandler):
        def get(self):
            self.write("You requested the main page")

    class StoryHandler(tornado.web.RequestHandler):
        def get(self, story_id):
            self.write("You requested the story " + story_id)

    application = tornado.web.Application([
        (r"/", MainHandler),
        (r"/story/([0-9]+)", StoryHandler),
    ])

You can get query string arguments and parse ``POST`` bodies with the
``get_argument()`` method:

::

    class MyFormHandler(tornado.web.RequestHandler):
        def get(self):
            self.write('<html><body><form action="/myform" method="post">'
                       '<input type="text" name="message">'
                       '<input type="submit" value="Submit">'
                       '</form></body></html>')

        def post(self):
            self.set_header("Content-Type", "text/plain")
            self.write("You wrote " + self.get_argument("message"))

Uploaded files are available in ``self.request.files``, which maps names
(the name of the HTML ``<input type="file">`` element) to a list of
files. Each file is a dictionary of the form
``{"filename":..., "content_type":..., "body":...}``.

If you want to send an error response to the client, e.g., 403
Unauthorized, you can just raise a ``tornado.web.HTTPError`` exception:

::

    if not self.user_is_logged_in():
        raise tornado.web.HTTPError(403)

The request handler can access the object representing the current
request with ``self.request``. The ``HTTPRequest`` object includes a
number of useful attributes, including:

-  ``arguments`` - all of the ``GET`` and ``POST`` arguments
-  ``files`` - all of the uploaded files (via ``multipart/form-data``
   POST requests)
-  ``path`` - the request path (everything before the ``?``)
-  ``headers`` - the request headers

See the class definition for `tornado.httputil.HTTPServerRequest` for a
complete list of attributes.

Overriding RequestHandler methods
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

In addition to ``get()``/``post()``/etc, certain other methods in
``RequestHandler`` are designed to be overridden by subclasses when
necessary. On every request, the following sequence of calls takes
place:

1. A new RequestHandler object is created on each request
2. ``initialize()`` is called with keyword arguments from the
   ``Application`` configuration. (the ``initialize`` method is new in
   Tornado 1.1; in older versions subclasses would override ``__init__``
   instead). ``initialize`` should typically just save the arguments
   passed into member variables; it may not produce any output or call
   methods like ``send_error``.
3. ``prepare()`` is called. This is most useful in a base class shared
   by all of your handler subclasses, as ``prepare`` is called no matter
   which HTTP method is used. ``prepare`` may produce output; if it
   calls ``finish`` (or ``send_error``, etc), processing stops here.
4. One of the HTTP methods is called: ``get()``, ``post()``, ``put()``,
   etc. If the URL regular expression contains capturing groups, they
   are passed as arguments to this method.
5. When the request is finished, ``on_finish()`` is called.  For synchronous
   handlers this is immediately after ``get()`` (etc) return; for
   asynchronous handlers it is after the call to ``finish()``.

Here is an example demonstrating the ``initialize()`` method:

::

    class ProfileHandler(RequestHandler):
        def initialize(self, database):
            self.database = database

        def get(self, username):
            ...

    app = Application([
        (r'/user/(.*)', ProfileHandler, dict(database=database)),
        ])

Other methods designed for overriding include:

-  ``write_error(self, status_code, exc_info=None, **kwargs)`` -
   outputs HTML for use on error pages.
-  ``get_current_user(self)`` - see `User
   Authentication <#user-authentication>`_ below
-  ``get_user_locale(self)`` - returns ``locale`` object to use for the
   current user
-  ``get_login_url(self)`` - returns login url to be used by the
   ``@authenticated`` decorator (default is in ``Application`` settings)
-  ``get_template_path(self)`` - returns location of template files
   (default is in ``Application`` settings)
-  ``set_default_headers(self)`` - may be used to set additional headers
   on the response (such as a custom ``Server`` header)

Error Handling
~~~~~~~~~~~~~~

There are three ways to return an error from a `RequestHandler`:

1. Manually call `~tornado.web.RequestHandler.set_status` and output the
   response body normally.
2. Call `~RequestHandler.send_error`.  This discards
   any pending unflushed output and calls `~RequestHandler.write_error` to
   generate an error page.
3. Raise an exception.  `tornado.web.HTTPError` can be used to generate
   a specified status code; all other exceptions return a 500 status.
   The exception handler uses `~RequestHandler.send_error` and
   `~RequestHandler.write_error` to generate the error page.

The default error page includes a stack trace in debug mode and a one-line
description of the error (e.g. "500: Internal Server Error") otherwise.
To produce a custom error page, override `RequestHandler.write_error`.
This method may produce output normally via methods such as
`~RequestHandler.write` and `~RequestHandler.render`.  If the error was
caused by an exception, an ``exc_info`` triple will be passed as a keyword
argument (note that this exception is not guaranteed to be the current
exception in ``sys.exc_info``, so ``write_error`` must use e.g.
`traceback.format_exception` instead of `traceback.format_exc`).

Redirection
~~~~~~~~~~~

There are two main ways you can redirect requests in Tornado:
``self.redirect`` and with the ``RedirectHandler``.

You can use ``self.redirect`` within a ``RequestHandler`` method (like
``get``) to redirect users elsewhere. There is also an optional
parameter ``permanent`` which you can use to indicate that the
redirection is considered permanent.

This triggers a ``301 Moved Permanently`` HTTP status, which is useful
for e.g. redirecting to a canonical URL for a page in an SEO-friendly
manner.

The default value of ``permanent`` is ``False``, which is apt for things
like redirecting users on successful POST requests.

::

    self.redirect('/some-canonical-page', permanent=True)

``RedirectHandler`` is available for your use when you initialize
``Application``.

For example, notice how we redirect to a longer download URL on this
website:

::

    application = tornado.wsgi.WSGIApplication([
        (r"/([a-z]*)", ContentHandler),
        (r"/static/tornado-0.2.tar.gz", tornado.web.RedirectHandler,
         dict(url="https://github.com/downloads/facebook/tornado/tornado-0.2.tar.gz")),
    ], **settings)

The default ``RedirectHandler`` status code is
``301 Moved Permanently``, but to use ``302 Found`` instead, set
``permanent`` to ``False``.

::

    application = tornado.wsgi.WSGIApplication([
        (r"/foo", tornado.web.RedirectHandler, {"url":"/bar", "permanent":False}),
    ], **settings)

Note that the default value of ``permanent`` is different in
``self.redirect`` than in ``RedirectHandler``. This should make some
sense if you consider that ``self.redirect`` is used in your methods and
is probably invoked by logic involving environment, authentication, or
form submission, but ``RedirectHandler`` patterns are going to fire 100%
of the time they match the request URL.

Non-blocking, asynchronous requests
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

When a request handler is executed, the request is automatically
finished. Since Tornado uses a non-blocking I/O style, you can override
this default behavior if you want a request to remain open after the
main request handler method returns using the
``tornado.web.asynchronous`` decorator.

When you use this decorator, it is your responsibility to call
``self.finish()`` to finish the HTTP request, or the user's browser will
simply hang:

::

    class MainHandler(tornado.web.RequestHandler):
        @tornado.web.asynchronous
        def get(self):
            self.write("Hello, world")
            self.finish()

Here is a real example that makes a call to the FriendFeed API using
Tornado's built-in asynchronous HTTP client:

::

    class MainHandler(tornado.web.RequestHandler):
        @tornado.web.asynchronous
        def get(self):
            http = tornado.httpclient.AsyncHTTPClient()
            http.fetch("http://friendfeed-api.com/v2/feed/bret",
                       callback=self.on_response)

        def on_response(self, response):
            if response.error: raise tornado.web.HTTPError(500)
            json = tornado.escape.json_decode(response.body)
            self.write("Fetched " + str(len(json["entries"])) + " entries "
                       "from the FriendFeed API")
            self.finish()

When ``get()`` returns, the request has not finished. When the HTTP
client eventually calls ``on_response()``, the request is still open,
and the response is finally flushed to the client with the call to
``self.finish()``.

For a more advanced asynchronous example, take a look at the `chat
example application
<https://github.com/tornadoweb/tornado/tree/stable/demos/chat>`_, which
implements an AJAX chat room using `long polling
<http://en.wikipedia.org/wiki/Push_technology#Long_polling>`_.  Users
of long polling may want to override ``on_connection_close()`` to
clean up after the client closes the connection (but see that method's
docstring for caveats).

Asynchronous HTTP clients
~~~~~~~~~~~~~~~~~~~~~~~~~

Tornado includes two non-blocking HTTP client implementations:
``SimpleAsyncHTTPClient`` and ``CurlAsyncHTTPClient``. The simple client
has no external dependencies because it is implemented directly on top
of Tornado's ``IOLoop``. The Curl client requires that ``libcurl`` and
``pycurl`` be installed (and a recent version of each is highly
recommended to avoid bugs in older version's asynchronous interfaces),
but is more likely to be compatible with sites that exercise little-used
parts of the HTTP specification.

Each of these clients is available in its own module
(``tornado.simple_httpclient`` and ``tornado.curl_httpclient``), as well
as via a configurable alias in ``tornado.httpclient``.
``SimpleAsyncHTTPClient`` is the default, but to use a different
implementation call the ``AsyncHTTPClient.configure`` method at startup:

::

    AsyncHTTPClient.configure('tornado.curl_httpclient.CurlAsyncHTTPClient')
