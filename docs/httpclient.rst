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
   .. autoexception:: HTTPError
      :members:

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
   :members:

.. module:: tornado.curl_httpclient

.. class:: CurlAsyncHTTPClient(io_loop, max_clients=10, defaults=None)

   ``libcurl``-based HTTP client.
   
   ``max_clients`` is the number of concurrent requests that can be in progress; when this limit is reached additional requests will be queued. Note that unlike ``SimpleAsyncHTTPClient``, time spent waiting in this queue **does not** count against the request_timeout.

Example Code
~~~~~~~~~~~~

* `A simple webspider <https://github.com/tornadoweb/tornado/blob/master/demos/webspider/webspider.py>`_
  shows how to fetch URLs concurrently.
* `The file uploader demo <https://github.com/tornadoweb/tornado/tree/master/demos/file_upload/>`_
  uses either HTTP POST or HTTP PUT to upload files to a server.
