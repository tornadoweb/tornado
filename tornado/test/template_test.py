from tornado.template import Template
from tornado.testing import LogTrapTestCase

class TemplateTest(LogTrapTestCase):
    def test_simple(self):
        template = Template("Hello {{ name }}!")
        self.assertEqual(template.generate(name="Ben"),
                         "Hello Ben!")
