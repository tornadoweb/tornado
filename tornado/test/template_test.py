from tornado.escape import utf8
from tornado.template import Template, DictLoader
from tornado.testing import LogTrapTestCase
from tornado.util import b

class TemplateTest(LogTrapTestCase):
    def test_simple(self):
        template = Template("Hello {{ name }}!")
        self.assertEqual(template.generate(name="Ben"),
                         b("Hello Ben!"))

    def test_bytes(self):
        template = Template("Hello {{ name }}!")
        self.assertEqual(template.generate(name=utf8("Ben")),
                         b("Hello Ben!"))

    def test_expressions(self):
        template = Template("2 + 2 = {{ 2 + 2 }}")
        self.assertEqual(template.generate(), b("2 + 2 = 4"))

    def test_include(self):
        loader = DictLoader({
                "index.html": '{% include "header.html" %}\nbody text',
                "header.html": "header text",
                })
        self.assertEqual(loader.load("index.html").generate(),
                         b("header text\nbody text"))

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
                         b("<title>page title</title>\n<body>page body</body>\n"))

    def test_relative_load(self):
        loader = DictLoader({
                "a/1.html": "{% include '2.html' %}",
                "a/2.html": "{% include '../b/3.html' %}",
                "b/3.html": "ok",
                })
        self.assertEqual(loader.load("a/1.html").generate(),
                         b("ok"))
