What's new in the next version of Tornado
=========================================

In Progress
-----------

* `.WSGIContainer` now calls the iterable's ``close()`` method even if
  an error is raised, in compliance with the spec.
* Fixed an incorrect error message when handler methods return a value
  other than None or a Future.
* `.xhtml_escape` now escapes apostrophes as well.
* `.Subprocess` no longer leaks file descriptors if `subprocess.Popen` fails.
* `.IOLoop` now frees callback objects earlier, reducing memory usage
  while idle.
* `.FacebookGraphMixin` has been updated to use the current Facebook login
  URL, which saves a redirect.
* `.IOStream` now recognizes ``ECONNABORTED`` error codes in more places
  (which was mainly an issue on Windows).
* `.IOStream` now frees memory earlier if a connection is closed while
  there is data in the write buffer.
* `.StaticFileHandler` no longer fails if the client requests a ``Range`` that
  is larger than the entire file (Facebook has a crawler that does this).
* `.PipeIOStream` now handles ``EAGAIN`` error codes correctly.
* `.SSLIOStream` now initiates the SSL handshake automatically without
  waiting for the application to try and read or write to the connection.
* `.IOLoop` now uses `~.IOLoop.handle_callback_exception` consistently for
  error logging.
* `.RequestHandler.on_connection_close` now works correctly on subsequent
  requests of a keep-alive connection.
* `.RequestHandler.clear_all_cookies` now accepts ``domain`` and ``path``
  arguments, just like `~.RequestHandler.clear_cookie`.
* The embedded ``ca-certificats.crt`` file has been updated with the current
  Mozilla CA list.
