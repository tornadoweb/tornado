# app.py
import os
import tornado.ioloop
import tornado.web
from tornado.webmiddleware import RequestParsingMiddleware


class MainHandler(tornado.web.RequestHandler):
    async def prepare(self):
        self.parsed_body = None
        await self._apply_middlewares()  # Await middleware processing

    async def _apply_middlewares(self):
        middlewares = [RequestParsingMiddleware()]
        for middleware in middlewares:
            await middleware.process_request(self)  # Await middleware

    async def get(self):
        # Render the HTML form for user input
        self.write("""
            <html>
                <body>
                    <h1>Submit Your Information</h1>
                    <form action="/parse" method="post" enctype="multipart/form-data">
                        <label for="name">Name:</label><br>
                        <input type="text" id="name" name="name"><br><br>
                        <label for="file">Upload File:</label><br>
                        <input type="file" id="file" name="file"><br><br>
                        <input type="submit" value="Submit">
                    </form>
                </body>
            </html>
        """)

    async def post(self):
        # Access parsed body data
        name = self.parsed_body["arguments"].get("name", [""])[0]  # Getting the name field
        files = self.parsed_body["files"].get("file", [])  # Getting uploaded files
        
        # Prepare response HTML
        response_html = "<h1>Submitted Information</h1>"
        response_html += f"<p>Name: {name}</p>"
        
        if files:
            response_html += "<h2>Uploaded Files:</h2><ul>"
            for file_info in files:
                response_html += f"<li>{file_info['filename']}</li>"
                # Save the file to the server
                await self.save_file(file_info)  # Await the file saving process
            response_html += "</ul>"

        self.write(response_html)

    async def save_file(self, file_info):
        # Define the upload directory
        upload_dir = 'uploads'
        if not os.path.exists(upload_dir):
            os.makedirs(upload_dir)  # Create the directory if it doesn't exist
        
        # Save the uploaded file asynchronously
        file_path = os.path.join(upload_dir, file_info['filename'])
        with open(file_path, 'wb') as f:
            f.write(file_info['body'])  # Write the raw file body to disk

class HomeHandler(tornado.web.RequestHandler):
    async def get(self):
        self.redirect("/parse")  # Redirect to the /parse route

def make_app():
    return tornado.web.Application([
        (r"/", HomeHandler),  # Add root route
        (r"/parse", MainHandler),
    ])

if __name__ == "__main__":
    app = make_app()
    app.listen(8888)
    print("Server is running on http://localhost:8888")
    tornado.ioloop.IOLoop.current().start()
