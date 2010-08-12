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

import markdown
import os
import os.path
import time
import tornado.web
import tornado.wsgi
import wsgiref.handlers


class ContentHandler(tornado.web.RequestHandler):
    def get(self, path):
        paths = ("documentation", "index")
        if not path: path = "index"
        if path not in paths:
            raise tornado.web.HTTPError(404)
        self.render(path + ".html", markdown=self.markdown)

    def markdown(self, path, toc=False):
        if not hasattr(ContentHandler, "_md") or self.settings.get("debug"):
            ContentHandler._md = {}
        if path not in ContentHandler._md:
            full_path = os.path.join(self.settings["template_path"], path)
            f = open(full_path, "r")
            contents = f.read().decode("utf-8")
            f.close()
            if toc: contents = u"[TOC]\n\n" + contents
            md = markdown.Markdown(extensions=["toc"] if toc else [])
            ContentHandler._md[path] = md.convert(contents).encode("utf-8")
        return ContentHandler._md[path]


settings = {
    "template_path": os.path.join(os.path.dirname(__file__), "templates"),
    "xsrf_cookies": True,
    "debug": os.environ.get("SERVER_SOFTWARE", "").startswith("Development/"),
}
application = tornado.wsgi.WSGIApplication([
    (r"/([a-z]*)", ContentHandler),
    (r"/static/tornado-0.1.tar.gz", tornado.web.RedirectHandler,
     dict(url="http://github.com/downloads/facebook/tornado/tornado-0.1.tar.gz")),
    (r"/static/tornado-0.2.tar.gz", tornado.web.RedirectHandler,
     dict(url="http://github.com/downloads/facebook/tornado/tornado-0.2.tar.gz")),

], **settings)


def main():
    wsgiref.handlers.CGIHandler().run(application)


if __name__ == "__main__":
    main()
