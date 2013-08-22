#-*- coding: utf-8 -*-
import tornado.web
import os.path
import tornado.ioloop
import mako.lookup
import tornado.httpserver
import mako.template
from tornado.options import options, define

define('port', default=3000, help='running on the given port', type=int)


class BaseHandler(tornado.web.RequestHandler):


    def initialize(self):
        template_path = self.get_template_path()
        self.lookup = mako.lookup.TemplateLookup(directories=[template_path], input_encoding='utf-8', output_encoding='utf-8')

    def render_string(self, template_path, **kwargs):
        template = self.lookup.get_template(template_path)
        namespace = self.get_template_namespace()
        namespace.update(kwargs)
        return template.render(**namespace)

    def render(self, template_path, **kwargs):
        self.finish(self.render_string(template_path, **kwargs))


class IndexHandler(BaseHandler):
    def get(self):
        self.render('index.html',title='Tornado with Mako',body='This is a body')

class Application(tornado.web.Application):
    def __init__(self):
        handlers = [
                (r'/',IndexHandler),
                ]
        settings = {
                'template_path' : os.path.join(os.path.dirname(__file__),'templates')
                }
        tornado.web.Application.__init__(self, handlers,**settings)


def main():
    tornado.options.parse_command_line()
    http_server = tornado.httpserver.HTTPServer(Application())
    http_server.listen(options.port)
    tornado.ioloop.IOLoop.instance().start()


if __name__ == '__main__':
    main()
