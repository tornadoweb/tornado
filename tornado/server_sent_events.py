import time
import tornado.web
import tornado.escape
import tornado.ioloop
import tornado.web
import hashlib

class SSEHandler(tornado.web.RequestHandler):
    _closing_timeout = False
    _live_connections = [] # Yes, this list is declared here because it is used by the class methods

    def __init__(self, application, request, **kwargs):
        super(SSEHandler, self).__init__(application, request, **kwargs)
        self.stream = request.connection.stream
        self._closed = False

    def initialize(self):
        self.set_header('Content-Type','text/event-stream; charset=utf-8')
        self.set_header('Cache-Control','no-cache')
        self.set_header('Connection','keep-alive')

    def generate_id(self):
        return hashlib.md5('%s-%s-%s'%(
            self.request.connection.address[0],
            self.request.connection.address[1],
            time.time(),
            )).hexdigest()

    @tornado.web.asynchronous
    def get(self):
        # Sending the standard headers
        headers = self._generate_headers()
        self.write(headers); self.flush()

        # Adding the current client instance to the live handlers pool
        self.connection_id = self.generate_id()
        SSEHandler._live_connections.append(self)

        # Calling the open event
        self.on_open()

    def on_open(self, *args, **kwargs):
        """Invoked for a new connection opened."""
        pass

    def on_close(self):
        """Invoked when the connection for this instance is closed."""
        pass

    def close(self):
        """Closes the connection for this instance"""
        if not self._closed and not getattr(self, '_closing_timeout', None):
            self._closed = True
            self._closing_timeout = tornado.ioloop.IOLoop.instance().add_timeout(time.time() + 5, self._abort)
        else:
            tornado.ioloop.IOLoop.instance().remove_timeout(self._closing_timeout)
            self.on_close() # Calling the closing event
            self.stream.close()

    def _abort(self):
        """Instantly aborts the connection by closing the socket"""
        self._closed = True
        self.stream.close()

    @classmethod
    def write_message_to_all(cls, event_id, data):
        """Sends a message to all live connections"""
        for conn in cls._live_connections:
            conn.write_message(event_id, data)

    @tornado.web.asynchronous
    def write_message(self, event_id, data):
        message = tornado.escape.utf8(('id: %s\n'%event_id if event_id else '') + 'data: %s\n\n'%data)
        self.write(message)
        self.flush()

    def remove_connection(self):
        if self in SSEHandler._live_connections:
            SSEHandler._live_connections.remove(self)

