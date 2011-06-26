#!/usr/bin/env python
#
# Copyright 2009 Bret Taylor
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

import os
import os.path
import tornado.web
import tornado.wsgi
import wsgiref.handlers


class ContentHandler(tornado.web.RequestHandler):
    def get(self, path="index"):
        paths = ("index",)
        if path not in paths:
            raise tornado.web.HTTPError(404)
        self.render(path + ".html", version=tornado.version)


settings = {
    "template_path": os.path.join(os.path.dirname(__file__), "templates"),
    "xsrf_cookies": True,
    "debug": os.environ.get("SERVER_SOFTWARE", "").startswith("Development/"),
}
application = tornado.wsgi.WSGIApplication([
    (r"/", ContentHandler),
    (r"/(index)", ContentHandler),
    (r"/static/tornado-0.1.tar.gz", tornado.web.RedirectHandler,
     dict(url="http://github.com/downloads/facebook/tornado/tornado-0.1.tar.gz")),
    (r"/static/tornado-0.2.tar.gz", tornado.web.RedirectHandler,
     dict(url="http://github.com/downloads/facebook/tornado/tornado-0.2.tar.gz")),

    (r"/documentation/?", tornado.web.RedirectHandler,
     dict(url="/documentation/index.html")),

], **settings)


def main():
    wsgiref.handlers.CGIHandler().run(application)


if __name__ == "__main__":
    main()
