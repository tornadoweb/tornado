#!/usr/bin/env python
import unittest

TEST_MODULES = [
    'tornado.httputil.doctests',
    'tornado.test.httpserver_test',
    'tornado.test.ioloop_test',
    'tornado.test.stack_context_test',
    'tornado.test.testing_test',
    'tornado.test.web_test',
]

def all():
    return unittest.defaultTestLoader.loadTestsFromNames(TEST_MODULES)

if __name__ == '__main__':
    import tornado.testing
    tornado.testing.main()
