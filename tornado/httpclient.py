import httplib
import time

from tornado.escape import utf8
from tornado import httputil

class HTTPRequest(object):
    def __init__(self, url, method="GET", headers=None, body=None,
                 auth_username=None, auth_password=None,
                 connect_timeout=20.0, request_timeout=20.0,
                 if_modified_since=None, follow_redirects=True,
                 max_redirects=5, user_agent=None, use_gzip=True,
                 network_interface=None, streaming_callback=None,
                 header_callback=None, prepare_curl_callback=None,
                 proxy_host=None, proxy_port=None, proxy_username=None,
                 proxy_password='', allow_nonstandard_methods=False,
                 validate_cert=True, ca_certs=None):
        if headers is None:
            headers = httputil.HTTPHeaders()
        if if_modified_since:
            timestamp = calendar.timegm(if_modified_since.utctimetuple())
            headers["If-Modified-Since"] = email.utils.formatdate(
                timestamp, localtime=False, usegmt=True)
        if "Pragma" not in headers:
            headers["Pragma"] = ""
        # Proxy support: proxy_host and proxy_port must be set to connect via
        # proxy.  The username and password credentials are optional.
        self.proxy_host = proxy_host
        self.proxy_port = proxy_port
        self.proxy_username = proxy_username
        self.proxy_password = proxy_password
        # libcurl's magic "Expect: 100-continue" behavior causes delays
        # with servers that don't support it (which include, among others,
        # Google's OpenID endpoint).  Additionally, this behavior has
        # a bug in conjunction with the curl_multi_socket_action API
        # (https://sourceforge.net/tracker/?func=detail&atid=100976&aid=3039744&group_id=976),
        # which increases the delays.  It's more trouble than it's worth,
        # so just turn off the feature (yes, setting Expect: to an empty
        # value is the official way to disable this)
        if "Expect" not in headers:
            headers["Expect"] = ""
        self.url = utf8(url)
        self.method = method
        self.headers = headers
        self.body = body
        self.auth_username = utf8(auth_username)
        self.auth_password = utf8(auth_password)
        self.connect_timeout = connect_timeout
        self.request_timeout = request_timeout
        self.follow_redirects = follow_redirects
        self.max_redirects = max_redirects
        self.user_agent = user_agent
        self.use_gzip = use_gzip
        self.network_interface = network_interface
        self.streaming_callback = streaming_callback
        self.header_callback = header_callback
        self.prepare_curl_callback = prepare_curl_callback
        self.allow_nonstandard_methods = allow_nonstandard_methods
        # SSL certificate validation:
        # validate_cert: boolean, set to False to disable validation
        # ca_certs: filename of CA certificates in PEM format, or
        #     None to use defaults
        # Note that in the curl-based HTTP client, if any request
        # uses a custom ca_certs file, they all must (they don't have to
        # all use the same ca_certs, but it's not possible to mix requests
        # with ca_certs and requests that use the defaults).
        # SimpleAsyncHTTPClient does not have this limitation.
        self.validate_cert = validate_cert
        self.ca_certs = ca_certs
        self.start_time = time.time()


class HTTPResponse(object):
    """HTTP Response object.

    Attributes:
    * request: HTTPRequest object
    * code: numeric HTTP status code, e.g. 200 or 404
    * headers: httputil.HTTPHeaders object
    * buffer: cStringIO object for response body
    * body: respose body as string (created on demand from self.buffer)
    * error: Exception object, if any
    * request_time: seconds from request start to finish
    * time_info: dictionary of diagnostic timing information from the request.
        Available data are subject to change, but currently uses timings
        available from http://curl.haxx.se/libcurl/c/curl_easy_getinfo.html,
        plus 'queue', which is the delay (if any) introduced by waiting for
        a slot under AsyncHTTPClient's max_clients setting.
    """
    def __init__(self, request, code, headers={}, buffer=None,
                 effective_url=None, error=None, request_time=None,
                 time_info={}):
        self.request = request
        self.code = code
        self.headers = headers
        self.buffer = buffer
        self._body = None
        if effective_url is None:
            self.effective_url = request.url
        else:
            self.effective_url = effective_url
        if error is None:
            if self.code < 200 or self.code >= 300:
                self.error = HTTPError(self.code, response=self)
            else:
                self.error = None
        else:
            self.error = error
        self.request_time = request_time
        self.time_info = time_info

    def _get_body(self):
        if self.buffer is None:
            return None
        elif self._body is None:
            self._body = self.buffer.getvalue()

        return self._body

    body = property(_get_body)

    def rethrow(self):
        if self.error:
            raise self.error

    def __repr__(self):
        args = ",".join("%s=%r" % i for i in self.__dict__.iteritems())
        return "%s(%s)" % (self.__class__.__name__, args)


class HTTPError(Exception):
    """Exception thrown for an unsuccessful HTTP request.

    Attributes:
    code - HTTP error integer error code, e.g. 404.  Error code 599 is
           used when no HTTP response was received, e.g. for a timeout.
    response - HTTPResponse object, if any.

    Note that if follow_redirects is False, redirects become HTTPErrors,
    and you can look at error.response.headers['Location'] to see the
    destination of the redirect.
    """
    def __init__(self, code, message=None, response=None):
        self.code = code
        message = message or httplib.responses.get(code, "Unknown")
        self.response = response
        Exception.__init__(self, "HTTP %d: %s" % (self.code, message))


from tornado.curl_httpclient import AsyncHTTPClient, HTTPClient
