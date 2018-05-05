#!/usr/bin/env python
#
# Copyright 2009 Facebook
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

import logging, os.path
import tornado.httpserver
import tornado.ioloop
import tornado.options
import tornado.web
import tornado.locale

from tornado.options import define, options

class Application(tornado.web.Application):
    def __init__(self):
        handlers = [
            (r"/", HomeHandler),
            (r"/in-handler", TranslationInHandler),
            (r"/in-template", TranslationInTemplate),
        ]
        settings = dict(
            template_path=os.path.join(os.path.dirname(__file__), "templates"),
            cookie_secret="__TODO:_GENERATE_YOUR_OWN_RANDOM_VALUE_HERE__",
            debug=True,
        )
        super(Application, self).__init__(handlers, **settings)

class BaseHandler(tornado.web.RequestHandler):
    def get_current_user(self):
        user = self.get_secure_cookie("user")
        if not user: return None
        return tornado.escape.xhtml_escape(user)

    def get_user_locale(self):
        """
        TODO : get user lang value from DB or browser heads and set like this.
        If None is returned, Tornado fall back to get_browser_locale()
        check this : http://tornado.readthedocs.org/en/latest/web.html#tornado.web.RequestHandler.get_user_locale
        """
        return tornado.locale.get("tr_TR")


class HomeHandler(BaseHandler):
    def get(self):
        body =  '<ul>' \
                '<li><a href="/in-handler">Translation in the Handler</a></li>' \
                '<li><a href="/in-template">Translation in the Template</a></li>' \
                '</ul>'
        self.write(body)

class TranslationInHandler(BaseHandler):
    def get(self):
        message = "Hello, everyone!"
        message_tr = tornado.locale.get('tr_TR').translate(message)
        body = "English: <strong>%s</strong>, "\
                "Translation : <strong>%s</strong>" % (message,message_tr)
        self.write(body)

class TranslationInTemplate(BaseHandler):
    def get(self):
        message = "Hello, everyone!"
        self.render("hello.html", message=message)

def main():
    tornado.options.parse_command_line()
    translationsPath = os.path.join(os.path.dirname(__file__), "translations")
    tornado.locale.load_translations(translationsPath)
    # Also, you can set default lang value
    #tornado.locale.set_default_locale("tr_TR")
    http_server = tornado.httpserver.HTTPServer(Application())
    http_server.listen(8888)
    tornado.ioloop.IOLoop.current().start()

if __name__ == "__main__":
    main()
