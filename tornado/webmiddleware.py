import json
from typing import Any, Dict, List, Optional
from tornado.httputil import HTTPServerRequest
from tornado.escape import json_decode
from tornado.httputil import parse_body_arguments
import base64

class Middleware:
    def process_request(self, handler: Any) -> None:  # Update type hint
        raise NotImplementedError

class RequestParsingMiddleware(Middleware):
    """ 
    Middleware to parse the request body based on the Content-Type header.

    This middleware class processes incoming HTTP requests to extract and 
    parse the body content according to the specified Content-Type. 
    It supports multiple formats, including:

    - JSON: Parses the body as a JSON object when the Content-Type is 
      'application/json'. The resulting data structure is made accessible 
      via the `parsed_body` attribute of the request handler.

    - Form Data: Handles URL-encoded form data when the Content-Type is 
      'application/x-www-form-urlencoded'. It converts the body into a 
      dictionary format where each key corresponds to form fields and 
      the values are lists of field values.

    - Multipart Data: Processes multipart form data (e.g., file uploads) 
      when the Content-Type is 'multipart/form-data'. This is particularly 
      useful for handling file uploads alongside other form fields. The 
      parsed data will contain both regular arguments and files.

    Attributes:
        None

    Methods:
        process_request(handler): Analyzes the Content-Type of the incoming 
        request and calls the appropriate parsing method to populate the 
        `parsed_body` attribute of the request handler.

    Example Usage:
        In a Tornado application, you can use the `RequestParsingMiddleware` 
        to simplify handling different types of request bodies. Below is an 
        example implementation:

        ```python
        import tornado.ioloop
        import tornado.web
        import json
        from tornado.webmiddleware import RequestParsingMiddleware

        class MainHandler(tornado.web.RequestHandler):
            def prepare(self):
                self.parsed_body = None
                self._apply_middlewares()

            def _apply_middlewares(self):
                middlewares = [RequestParsingMiddleware()]
                for middleware in middlewares:
                    middleware.process_request(self)

            def post(self):
                # Respond with the parsed body as JSON
                self.set_header("Content-Type", "application/json")
                self.write(json.dumps(self.parsed_body))

        def make_app():
            return tornado.web.Application([
                (r"/", MainHandler),
            ])

        if __name__ == "__main__":
            app = make_app()
            app.listen(8888)
            tornado.ioloop.IOLoop.current().start()
        ```

        In this example, the `MainHandler` prepares for requests by applying the 
        `RequestParsingMiddleware`, allowing it to handle JSON, form data, 
        and multipart data seamlessly. When a POST request is made to the root 
        endpoint, the parsed body is returned as a JSON response.

    Note: This middleware is intended to be used in conjunction with 
    request handlers in a Tornado web application. It assumes that 
    the request body will be available for parsing.
    """

    def process_request(self, handler: Any) -> None:

        content_type = handler.request.headers.get("Content-Type", "")
        if content_type.startswith("application/json"):
            handler.parsed_body = self._parse_json(handler.request)
        elif content_type.startswith("application/x-www-form-urlencoded") or content_type.startswith("multipart/form-data"):
            handler.parsed_body = self._parse_form_or_multipart(handler.request)
        else:
            handler.parsed_body = None

    def _parse_json(self, request: HTTPServerRequest) -> Any:
        try:
            return json_decode(request.body)
        except json.JSONDecodeError:
            return None

    def _parse_form_or_multipart(self, request: HTTPServerRequest) -> Dict[str, Any]:
        arguments = {}
        files = {}

        # Use Tornado's built-in function to parse body arguments and files
        parse_body_arguments(
            request.headers.get("Content-Type", ""), 
            request.body, 
            arguments, 
            files, 
            headers=request.headers
        )

        parsed_data = {
            "arguments": {
                k: [v.decode('utf-8') if isinstance(v, bytes) else v for v in values]
                for k, values in arguments.items()
            },
            "files": {
                k: [{
                    "filename": f.filename,
                    "body": base64.b64encode(f.body).decode('utf-8') if f.body else None,  # Encode file body to base64
                    "content_type": f.content_type
                } for f in file_list]
                for k, file_list in files.items()
            }
        }
        return parsed_data
    
    

