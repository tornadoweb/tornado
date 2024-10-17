import json
from tornado.testing import AsyncHTTPTestCase
from tornado.web import Application, RequestHandler
from tornado.httputil import HTTPServerRequest
from tornado.web import RequestHandler
from tornado.webmiddleware import RequestParsingMiddleware

class TestHandler(RequestHandler):
    def prepare(self):
        self.parsed_body = None
        self._apply_middlewares()

    def _apply_middlewares(self):
        middlewares = [RequestParsingMiddleware()]
        for middleware in middlewares:
            middleware.process_request(self)

    def post(self):
        self.write(self.parsed_body)

class MiddlewareTest(AsyncHTTPTestCase):
    def get_app(self):
        return Application([
            (r"/test", TestHandler),
        ])

    def test_json_parsing(self):
        response = self.fetch("/test", method="POST", body=json.dumps({"key": "value"}), headers={"Content-Type": "application/json"})
        self.assertEqual(response.code, 200)
        self.assertEqual(json.loads(response.body), {"key": "value"})

    def test_form_parsing(self):
        body = "key=value"
        response = self.fetch("/test", method="POST", body=body, headers={"Content-Type": "application/x-www-form-urlencoded"})
        self.assertEqual(response.code, 200)
        self.assertEqual(json.loads(response.body), {"key": ["value"]})

    def test_multipart_parsing_with_file(self):
        # Create a mock file content
        file_content = b"This is a test file."
        file_name = "test_file.txt"
        
        # Define the boundary
        boundary = "----WebKitFormBoundary7MA4YWxkTrZu0gW"
        
        # Create the multipart body
        body = (
            f"--{boundary}\r\n"
            f"Content-Disposition: form-data; name=\"key\"\r\n\r\n"
            "value\r\n"
            f"--{boundary}\r\n"
            f"Content-Disposition: form-data; name=\"file\"; filename=\"{file_name}\"\r\n"
            f"Content-Type: text/plain\r\n\r\n"
        )
        body += file_content.decode('utf-8') + f"\r\n--{boundary}--\r\n"
        
        headers = {
            "Content-Type": f"multipart/form-data; boundary={boundary}"
        }

        # Send the request
        response = self.fetch("/test", method="POST", body=body.encode('utf-8'), headers=headers)

        # Assert response code
        self.assertEqual(response.code, 200)

        # Load the parsed response body
        parsed_body = json.loads(response.body)

        # Assert the file data and form data
        self.assertEqual(parsed_body["arguments"], {"key": ["value"]})
        self.assertEqual(len(parsed_body["files"]["file"]), 1)

        uploaded_file = parsed_body["files"]["file"][0]
        self.assertEqual(uploaded_file["filename"], file_name)
        self.assertEqual(uploaded_file["body"], file_content.decode('utf-8'))
        self.assertEqual(uploaded_file["content_type"], "text/plain")

        
if __name__ == "__main__":
    import unittest
    unittest.main()