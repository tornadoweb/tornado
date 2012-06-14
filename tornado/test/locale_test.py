from __future__ import absolute_import, division, with_statement

import os
import tornado.locale
import unittest

class TranslationLoaderTest(unittest.TestCase):
    # TODO: less hacky way to get isolated tests
    SAVE_VARS = ['_translations', '_supported_locales', '_use_gettext']

    def setUp(self):
        self.saved = {}
        for var in TranslationLoaderTest.SAVE_VARS:
            self.saved[var] = getattr(tornado.locale, var)

    def tearDown(self):
        for k, v in self.saved.items():
            setattr(tornado.locale, k, v)

    def test_csv(self):
        tornado.locale.load_translations(
            os.path.join(os.path.dirname(__file__), 'csv_translations'))
        locale = tornado.locale.get("fr_FR")
        self.assertEqual(locale.translate("school"), u"\u00e9cole")
