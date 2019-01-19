``tornado.httpserver`` --- Non-blocking HTTP server
===================================================

.. automodule:: tornado.httpserver

   HTTP Server
   -----------
   .. autoclass:: HTTPServer(request_callback: Union[httputil.HTTPServerConnectionDelegate, Callable[[httputil.HTTPServerRequest], None]], no_keep_alive: bool = False, xheaders: bool = False, ssl_options: Union[Dict[str, Any], ssl.SSLContext] = None, protocol: str = None, decompress_request: bool = False, chunk_size: int = None, max_header_size: int = None, idle_connection_timeout: float = None, body_timeout: float = None, max_body_size: int = None, max_buffer_size: int = None, trusted_downstream: List[str] = None)
      :members:

      The public interface of this class is mostly inherited from
      `.TCPServer` and is documented under that class.
