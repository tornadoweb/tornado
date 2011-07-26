from tornado.escape import utf8, native_str
from tornado.template import Template, DictLoader, ParseError
from tornado.testing import LogTrapTestCase
from tornado.util import b, bytes_type

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

    def test_escaping(self):
        self.assertRaises(ParseError, lambda: Template("{{"))
        self.assertRaises(ParseError, lambda: Template("{%"))
        self.assertEqual(Template("{{!").generate(), b("{{"))
        self.assertEqual(Template("{%!").generate(), b("{%"))
        self.assertEqual(Template("{{ 'expr' }} {{!jquery expr}}").generate(),
                         b("expr {{jquery expr}}"))

    def test_unicode_template(self):
        template = Template(utf8(u"\u00e9"))
        self.assertEqual(template.generate(), utf8(u"\u00e9"))

    def test_unicode_literal_expression(self):
        # Unicode literals should be usable in templates.  Note that this
        # test simulates unicode characters appearing directly in the
        # template file (with utf8 encoding), i.e. \u escapes would not
        # be used in the template file itself.
        if str is unicode:
            # python 3 needs a different version of this test since
            # 2to3 doesn't run on template internals
            template = Template(utf8(u'{{ "\u00e9" }}'))
        else:
            template = Template(utf8(u'{{ u"\u00e9" }}'))
        self.assertEqual(template.generate(), utf8(u"\u00e9"))
        

class AutoEscapeTest(LogTrapTestCase):
    def setUp(self):
        self.templates = {
            "escaped.html": "{% autoescape xhtml_escape %}{{ name }}",
            "unescaped.html": "{% autoescape None %}{{ name }}",
            "default.html": "{{ name }}",

            "include.html": """\
escaped: {% include 'escaped.html' %}
unescaped: {% include 'unescaped.html' %}
default: {% include 'default.html' %}
""",

            "escaped_block.html": """\
{% autoescape xhtml_escape %}\
{% block name %}base: {{ name }}{% end %}""",
            "unescaped_block.html": """\
{% autoescape None %}\
{% block name %}base: {{ name }}{% end %}""",

            # Extend a base template with different autoescape policy,
            # with and without overriding the base's blocks
            "escaped_extends_unescaped.html": """\
{% autoescape xhtml_escape %}\
{% extends "unescaped_block.html" %}""",
            "escaped_overrides_unescaped.html": """\
{% autoescape xhtml_escape %}\
{% extends "unescaped_block.html" %}\
{% block name %}extended: {{ name }}{% end %}""",
            "unescaped_extends_escaped.html": """\
{% autoescape None %}\
{% extends "escaped_block.html" %}""",
            "unescaped_overrides_escaped.html": """\
{% autoescape None %}\
{% extends "escaped_block.html" %}\
{% block name %}extended: {{ name }}{% end %}""",

            "raw_expression.html": """\
{% autoescape xhtml_escape %}\
expr: {{ name }}
raw: {% raw name %}""",
            }
    
    def test_default_off(self):
        loader = DictLoader(self.templates, autoescape=None)
        name = "Bobby <table>s"
        self.assertEqual(loader.load("escaped.html").generate(name=name),
                         b("Bobby &lt;table&gt;s"))
        self.assertEqual(loader.load("unescaped.html").generate(name=name),
                         b("Bobby <table>s"))
        self.assertEqual(loader.load("default.html").generate(name=name),
                         b("Bobby <table>s"))

        self.assertEqual(loader.load("include.html").generate(name=name),
                         b("escaped: Bobby &lt;table&gt;s\n"
                           "unescaped: Bobby <table>s\n"
                           "default: Bobby <table>s\n"))
        
    def test_default_on(self):
        loader = DictLoader(self.templates, autoescape="xhtml_escape")
        name = "Bobby <table>s"
        self.assertEqual(loader.load("escaped.html").generate(name=name),
                         b("Bobby &lt;table&gt;s"))
        self.assertEqual(loader.load("unescaped.html").generate(name=name),
                         b("Bobby <table>s"))
        self.assertEqual(loader.load("default.html").generate(name=name),
                         b("Bobby &lt;table&gt;s"))
        
        self.assertEqual(loader.load("include.html").generate(name=name),
                         b("escaped: Bobby &lt;table&gt;s\n"
                           "unescaped: Bobby <table>s\n"
                           "default: Bobby &lt;table&gt;s\n"))

    def test_unextended_block(self):
        loader = DictLoader(self.templates)
        name = "<script>"
        self.assertEqual(loader.load("escaped_block.html").generate(name=name),
                         b("base: &lt;script&gt;"))
        self.assertEqual(loader.load("unescaped_block.html").generate(name=name),
                         b("base: <script>"))

    def test_extended_block(self):
        loader = DictLoader(self.templates)
        def render(name): return loader.load(name).generate(name="<script>")
        self.assertEqual(render("escaped_extends_unescaped.html"),
                         b("base: <script>"))
        self.assertEqual(render("escaped_overrides_unescaped.html"),
                         b("extended: &lt;script&gt;"))

        self.assertEqual(render("unescaped_extends_escaped.html"),
                         b("base: &lt;script&gt;"))
        self.assertEqual(render("unescaped_overrides_escaped.html"),
                         b("extended: <script>"))

    def test_raw_expression(self):
        loader = DictLoader(self.templates)
        def render(name): return loader.load(name).generate(name='<>&"')
        self.assertEqual(render("raw_expression.html"),
                         b("expr: &lt;&gt;&amp;&quot;\n"
                           "raw: <>&\""))

    def test_custom_escape(self):
        loader = DictLoader({"foo.py": 
                             "{% autoescape py_escape %}s = {{ name }}\n"})
        def py_escape(s):
            self.assertEqual(type(s), bytes_type)
            return repr(native_str(s))
        def render(template, name):
            return loader.load(template).generate(py_escape=py_escape, 
                                                  name=name)
        self.assertEqual(render("foo.py", "<html>"),
                         b("s = '<html>'\n"))
        self.assertEqual(render("foo.py", "';sys.exit()"),
                         b("""s = "';sys.exit()"\n"""))
        self.assertEqual(render("foo.py", ["not a string"]),
                         b("""s = "['not a string']"\n"""))
