import unittest

from tornado import testing
from app import create_app

class SimpleTest(testing.AsyncHTTPTestCase):

    def get_app(self):
        application, ioloop = create_app()
        return application

    def get_new_ioloop(self):
        application, ioloop = create_app()
        return ioloop

    @testing.gen_test
    def test_endpoint_status_code(self):
        response = yield self.http_client.fetch(self.get_url("/"), method='GET')
        self.assertEqual(response.code, 200)

if __name__ == "__main__":
    unittest.main(verbosity=2)
