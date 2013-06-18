``tornado.websocket`` --- Bidirectional communication to the browser
====================================================================

.. automodule:: tornado.websocket

   .. autoclass:: WebSocketHandler

   Event handlers
   --------------

   .. automethod:: WebSocketHandler.open
   .. automethod:: WebSocketHandler.on_message
   .. automethod:: WebSocketHandler.on_close
   .. automethod:: WebSocketHandler.select_subprotocol

   Output
   ------

   .. automethod:: WebSocketHandler.write_message
   .. automethod:: WebSocketHandler.close

   Configuration
   -------------

   .. automethod:: WebSocketHandler.allow_draft76
   .. automethod:: WebSocketHandler.get_websocket_scheme
   .. automethod:: WebSocketHandler.set_nodelay

   Other
   -----

   .. automethod:: WebSocketHandler.async_callback
   .. automethod:: WebSocketHandler.ping
   .. automethod:: WebSocketHandler.on_pong


   Client-side support
   -------------------

   .. autofunction:: websocket_connect
   .. autoclass:: WebSocketClientConnection
       :members:
