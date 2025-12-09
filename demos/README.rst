Tornado Demo Apps
-----------------

This directory contains several example apps that illustrate the usage of
various Tornado features. If you're not sure where to start, try the ``chat``,
``blog``, or ``websocket`` demos.

Web Applications
~~~~~~~~~~~~~~~~

- ``blog``: A simple database-backed blogging platform, including
  HTML templates and authentication.
- ``chat``: A chat room demonstrating live updates via long polling.
- ``websocket``: Similar to ``chat`` but with WebSockets instead of
  long polling.
- ``helloworld``: The simplest possible Tornado web page.

Feature demos
~~~~~~~~~~~~~

- ``facebook``: Authentication with the Facebook Graph API.
- ``file_upload``: Client and server support for streaming HTTP request 
  payloads.
- ``tcpecho``: Using the lower-level ``IOStream`` interfaces for non-HTTP
  networking.
- ``webspider``: Concurrent usage of ``AsyncHTTPClient``, using queues and
  semaphores.

