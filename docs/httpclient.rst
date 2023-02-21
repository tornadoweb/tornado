``tornado.httpclient`` --- Asynchronous HTTP client
===================================================

.. automodule:: tornado.httpclient

   HTTP client interfaces
   ----------------------

   .. autoclass:: HTTPClient
      :members:

   .. autoclass:: AsyncHTTPClient
      :members:

   Request objects
   ---------------
   .. autoclass:: HTTPRequest
      :members:
   
   Response objects
   ----------------
   .. autoclass:: HTTPResponse
      :members:

   Exceptions
   ----------
   .. autoexception:: HTTPClientError
      :members:

   .. exception:: HTTPError

      Alias for `HTTPClientError`.

   Command-line interface
   ----------------------

   This module provides a simple command-line interface to fetch a url
   using Tornado's HTTP client.  Example usage::

      # Fetch the url and print its body
      python -m tornado.httpclient http://www.google.com

      # Just print the headers
      python -m tornado.httpclient --print_headers --print_body=false http://www.google.com

Implementations
~~~~~~~~~~~~~~~

.. automodule:: tornado.simple_httpclient
   
   .. autoclass:: SimpleAsyncHTTPClient
      :members:

.. module:: tornado.curl_httpclient

.. class:: CurlAsyncHTTPClient(max_clients=10, defaults=None)

   ``libcurl``-based HTTP client.

   This implementation supports the following arguments, which can be passed
   to ``configure()`` to control the global singleton, or to the constructor
   when ``force_instance=True``.

   ``max_clients`` is the number of concurrent requests that can be in progress;
   when this limit is reached additional requests will be queued.

   ``defaults`` is a dict of parameters that will be used as defaults on all
   `.HTTPRequest` objects submitted to this client.

Example Code
~~~~~~~~~~~~

* `A simple webspider <https://github.com/tornadoweb/tornado/blob/stable/demos/webspider/webspider.py>`_
  shows how to fetch URLs concurrently.
* `The file uploader demo <https://github.com/tornadoweb/tornado/tree/stable/demos/file_upload/>`_
  uses either HTTP POST or HTTP PUT to upload files to a server.
