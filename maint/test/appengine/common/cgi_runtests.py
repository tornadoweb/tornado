#!/usr/bin/env python
import sys
import unittest

# Most of our tests depend on IOLoop, which is not importable on app engine.
# Run the tests that work, and check that forbidden imports don't sneak
# in to modules that are supposed to work on app engine.
TEST_MODULES = [
    'tornado.httputil.doctests',
    #'tornado.iostream.doctests',
    'tornado.util.doctests',
    #'tornado.test.auth_test',
    #'tornado.test.curl_httpclient_test',
    'tornado.test.escape_test',
    #'tornado.test.gen_test',
    #'tornado.test.httpclient_test',
    #'tornado.test.httpserver_test',
    'tornado.test.httputil_test',
    #'tornado.test.import_test',
    #'tornado.test.ioloop_test',
    #'tornado.test.iostream_test',
    #'tornado.test.process_test',
    #'tornado.test.simple_httpclient_test',
    #'tornado.test.stack_context_test',
    'tornado.test.template_test',
    #'tornado.test.testing_test',
    #'tornado.test.twisted_test',
    #'tornado.test.web_test',
    #'tornado.test.wsgi_test',
]

def import_everything():
    # import tornado.auth
    # import tornado.autoreload
    # import tornado.curl_httpclient  # depends on pycurl
    import tornado.escape
    # import tornado.httpclient
    # import tornado.httpserver
    import tornado.httputil
    # import tornado.ioloop
    # import tornado.iostream
    import tornado.locale
    import tornado.options
    # import tornado.netutil
    # import tornado.platform.twisted # depends on twisted
    # import tornado.process
    # import tornado.simple_httpclient
    import tornado.stack_context
    import tornado.template
    import tornado.testing
    import tornado.util
    import tornado.web
    # import tornado.websocket
    import tornado.wsgi

def all():
    return unittest.defaultTestLoader.loadTestsFromNames(TEST_MODULES)

def main():
    print "Content-Type: text/plain\r\n\r\n",

    import_everything()

    try:
        unittest.main(defaultTest="all", argv=sys.argv)
    except SystemExit, e:
        if e.code == 0:
            print "PASS"
        else:
            raise

if __name__ == '__main__':
    main()
