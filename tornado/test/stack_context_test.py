#!/usr/bin/env python

from tornado.testing import AsyncHTTPTestCase, LogTrapTestCase
from tornado.web import asynchronous, Application, RequestHandler
import logging
import unittest

class TestRequestHandler(RequestHandler):
  def __init__(self, app, request, io_loop):
    super(TestRequestHandler, self).__init__(app, request)
    self.io_loop = io_loop

  @asynchronous
  def get(self):
    logging.info('in get()')
    # call self.part2 without a self.async_callback wrapper.  Its
    # exception should still get thrown
    self.io_loop.add_callback(self.part2)

  def part2(self):
    logging.info('in part2()')
    # Go through a third layer to make sure that contexts once restored
    # are again passed on to future callbacks
    self.io_loop.add_callback(self.part3)

  def part3(self):
    logging.info('in part3()')
    raise Exception('test exception')

  def get_error_html(self, status_code, **kwargs):
    if 'exception' in kwargs and str(kwargs['exception']) == 'test exception':
      return 'got expected exception'
    else:
      return 'unexpected failure'

class StackContextTest(AsyncHTTPTestCase, LogTrapTestCase):
  def get_app(self):
    return Application([('/', TestRequestHandler,
                         dict(io_loop=self.io_loop))])

  def test_stack_context(self):
    self.http_client.fetch(self.get_url('/'), self.handle_response)
    self.wait()
    self.assertEquals(self.response.code, 500)
    self.assertTrue('got expected exception' in self.response.body)

  def handle_response(self, response):
    self.response = response
    self.stop()

if __name__ == '__main__':
  unittest.main()
