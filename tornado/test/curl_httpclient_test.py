from tornado.test.httpclient_test import HTTPClientCommonTestCase

try:
    import pycurl
except ImportError:
    pycurl = None

if pycurl is not None:
    from tornado.curl_httpclient import CurlAsyncHTTPClient

class CurlHTTPClientCommonTestCase(HTTPClientCommonTestCase):
    def get_http_client(self):
        client = CurlAsyncHTTPClient(io_loop=self.io_loop)
        # make sure AsyncHTTPClient magic doesn't give us the wrong class
        self.assertTrue(isinstance(client, CurlAsyncHTTPClient))
        return client

# Remove the base class from our namespace so the unittest module doesn't
# try to run it again.
del HTTPClientCommonTestCase

if pycurl is None:
    del CurlHTTPClientCommonTestCase
