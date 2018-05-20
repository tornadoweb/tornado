import unittest

from app import create_app

from tornado.testing import AsyncHTTPTestCase


class TestApp(AsyncHTTPTestCase):
    def get_app(self):
        return create_app()

    def test_homepage(self):
        response = self.fetch('/')
        self.assertEqual(self.get_protocol(), 'http')
        self.assertEqual(response.code, 200)
        # For python 2
        #self.assertEqual(response.body, 'Hello, world')
        # For python3
        #self.assertEqual(response.body, b'Hello, world')

if __name__ == "__main__":
    unittest.main()
