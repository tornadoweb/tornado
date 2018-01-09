#!/usr/bin/env python
from __future__ import absolute_import, division, print_function

import sys
import unittest

# Most of our tests depend on IOLoop, which is not usable on app engine.
# Run the tests that work, and check that everything else is at least
# importable (via tornado.test.import_test)
TEST_MODULES = [
    'tornado.httputil.doctests',
    'tornado.iostream.doctests',
    'tornado.util.doctests',
    #'tornado.test.auth_test',
    #'tornado.test.concurrent_test',
    #'tornado.test.curl_httpclient_test',
    'tornado.test.escape_test',
    #'tornado.test.gen_test',
    #'tornado.test.httpclient_test',
    #'tornado.test.httpserver_test',
    'tornado.test.httputil_test',
    'tornado.test.import_test',
    #'tornado.test.ioloop_test',
    #'tornado.test.iostream_test',
    'tornado.test.locale_test',
    #'tornado.test.netutil_test',
    #'tornado.test.log_test',
    'tornado.test.options_test',
    #'tornado.test.process_test',
    #'tornado.test.simple_httpclient_test',
    #'tornado.test.stack_context_test',
    'tornado.test.template_test',
    #'tornado.test.testing_test',
    #'tornado.test.twisted_test',
    'tornado.test.util_test',
    #'tornado.test.web_test',
    #'tornado.test.websocket_test',
    #'tornado.test.wsgi_test',
]


def all():
    return unittest.defaultTestLoader.loadTestsFromNames(TEST_MODULES)


def main():
    print("Content-Type: text/plain\r\n\r\n", end="")

    try:
        unittest.main(defaultTest='all', argv=sys.argv[:1])
    except SystemExit as e:
        if e.code == 0:
            print("PASS")
        else:
            raise


if __name__ == '__main__':
    main()
