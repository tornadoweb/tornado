from tornado.template import Template, DictLoader
from tornado.testing import LogTrapTestCase

class TemplateTest(LogTrapTestCase):
    def test_simple(self):
        template = Template("Hello {{ name }}!")
        self.assertEqual(template.generate(name="Ben"),
                         "Hello Ben!")

    def test_include(self):
        loader = DictLoader({
                "index.html": '{% include "header.html" %}\nbody text',
                "header.html": "header text",
                })
        self.assertEqual(loader.load("index.html").generate(),
                         "header text\nbody text")

    def test_extends(self):
        loader = DictLoader({
                "base.html": """\
<title>{% block title %}default title{% end %}</title>
<body>{% block body %}default body{% end %}</body>
""",
                "page.html": """\
{% extends "base.html" %}
{% block title %}page title{% end %}
{% block body %}page body{% end %}
""",
                })
        self.assertEqual(loader.load("page.html").generate(),
                         "<title>page title</title>\n<body>page body</body>\n")
