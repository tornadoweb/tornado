#!/usr/bin/env python
import unittest

try:
    import coverage
    use_coverage = True
except ImportError:
    use_coverage = False
    import sys
    print >> sys.stderr, "Test coverage disabled. To enable install ``coverage`` package"

TEST_MODULES = [
    'tornado.httputil.doctests',
    'tornado.iostream.doctests',
    'tornado.util.doctests',
    'tornado.test.auth_test',
    'tornado.test.curl_httpclient_test',
    'tornado.test.escape_test',
    'tornado.test.gen_test',
    'tornado.test.httpclient_test',
    'tornado.test.httpserver_test',
    'tornado.test.httputil_test',
    'tornado.test.import_test',
    'tornado.test.ioloop_test',
    'tornado.test.iostream_test',
    'tornado.test.process_test',
    'tornado.test.simple_httpclient_test',
    'tornado.test.stack_context_test',
    'tornado.test.template_test',
    'tornado.test.testing_test',
    'tornado.test.twisted_test',
    'tornado.test.web_test',
    'tornado.test.wsgi_test',
]

def all():
    return unittest.defaultTestLoader.loadTestsFromNames(TEST_MODULES)

def run_with_coverage(runtests):
    cov = coverage.coverage(config_file=True)
    cov.start()
    try:
        runtests()
    except SystemExit, e:
        cov.stop()
        cov.save()
        cov.report()
        raise e

if __name__ == '__main__':
    import tornado.testing

    if use_coverage:
        run_with_coverage(tornado.testing.main)
    else:
        tornado.testing.main()
