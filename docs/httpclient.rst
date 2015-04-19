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
