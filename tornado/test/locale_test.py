from __future__ import absolute_import, division, with_statement

import os
from .. import locale as tornado_locale
import unittest


class TranslationLoaderTest(unittest.TestCase):
    # TODO: less hacky way to get isolated tests
    SAVE_VARS = ['_translations', '_supported_locales', '_use_gettext']

    def clear_locale_cache(self):
        if hasattr(tornado_locale.Locale, '_cache'):
            del tornado_locale.Locale._cache

    def setUp(self):
        self.saved = {}
        for var in TranslationLoaderTest.SAVE_VARS:
            self.saved[var] = getattr(tornado_locale, var)
        self.clear_locale_cache()

    def tearDown(self):
        for k, v in self.saved.items():
            setattr(tornado_locale, k, v)
        self.clear_locale_cache()

    def test_csv(self):
        tornado_locale.load_translations(
            os.path.join(os.path.dirname(__file__), 'csv_translations'))
        locale = tornado_locale.get("fr_FR")
        self.assertTrue(isinstance(locale, tornado_locale.CSVLocale))
        self.assertEqual(locale.translate("school"), u"\u00e9cole")

    def test_gettext(self):
        tornado_locale.load_gettext_translations(
            os.path.join(os.path.dirname(__file__), 'gettext_translations'),
            "tornado_test")
        locale = tornado_locale.get("fr_FR")
        self.assertTrue(isinstance(locale, tornado_locale.GettextLocale))
        self.assertEqual(locale.translate("school"), u"\u00e9cole")
