#!/usr/bin/env python

import unittest
import time

from tornado import ioloop


class TestIOLoop(unittest.TestCase):
    def setUp(self):
        self.loop = ioloop.IOLoop()

    def tearDown(self):
        pass

    def _callback(self):
        self.called = True
        self.loop.stop()

    def _schedule_callback(self):
        self.loop.add_callback(self._callback)
        # Scroll away the time so we can check if we woke up immediately
        self._start_time = time.time()
        self.called = False

    def test_add_callback(self):
        self.loop.add_timeout(time.time(), self._schedule_callback)
        self.loop.start() # Set some long poll timeout so we can check wakeup
        self.assertAlmostEqual(time.time(), self._start_time, places=2)
        self.assertTrue(self.called)


if __name__ == "__main__":
    import logging

    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s:%(msecs)03d %(levelname)-8s %(name)-8s %(message)s', datefmt='%H:%M:%S')

    unittest.main()
