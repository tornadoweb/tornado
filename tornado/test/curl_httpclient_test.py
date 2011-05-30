from tornado.test.httpclient_test import HTTPClientCommonTestCase

try:
    import pycurl
except ImportError:
    pycurl = None

if pycurl is not None:
    from tornado.curl_httpclient import CurlAsyncHTTPClient

class CurlHTTPClientCommonTestCase(HTTPClientCommonTestCase):
    def get_http_client(self):
        return CurlAsyncHTTPClient(io_loop=self.io_loop)

# Remove the base class from our namespace so the unittest module doesn't
# try to run it again.
del HTTPClientCommonTestCase

if pycurl is None:
    del CurlHTTPClientCommonTestCase
