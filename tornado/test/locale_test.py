from __future__ import absolute_import, division, print_function, with_statement

import datetime
import os
import tornado.locale
from tornado.escape import utf8
from tornado.test.util import unittest
from tornado.util import u, unicode_type


class TranslationLoaderTest(unittest.TestCase):
    # TODO: less hacky way to get isolated tests
    SAVE_VARS = ['_translations', '_supported_locales', '_use_gettext']

    def clear_locale_cache(self):
        if hasattr(tornado.locale.Locale, '_cache'):
            del tornado.locale.Locale._cache

    def setUp(self):
        self.saved = {}
        for var in TranslationLoaderTest.SAVE_VARS:
            self.saved[var] = getattr(tornado.locale, var)
        self.clear_locale_cache()

    def tearDown(self):
        for k, v in self.saved.items():
            setattr(tornado.locale, k, v)
        self.clear_locale_cache()

    def test_csv(self):
        tornado.locale.load_translations(
            os.path.join(os.path.dirname(__file__), 'csv_translations'))
        locale = tornado.locale.get("fr_FR")
        self.assertTrue(isinstance(locale, tornado.locale.CSVLocale))
        self.assertEqual(locale.translate("school"), u("\u00e9cole"))

    def test_gettext(self):
        tornado.locale.load_gettext_translations(
            os.path.join(os.path.dirname(__file__), 'gettext_translations'),
            "tornado_test")
        locale = tornado.locale.get("fr_FR")
        self.assertTrue(isinstance(locale, tornado.locale.GettextLocale))
        self.assertEqual(locale.translate("school"), u("\u00e9cole"))


class LocaleDataTest(unittest.TestCase):
    def test_non_ascii_name(self):
        name = tornado.locale.LOCALE_NAMES['es_LA']['name']
        self.assertTrue(isinstance(name, unicode_type))
        self.assertEqual(name, u('Espa\u00f1ol'))
        self.assertEqual(utf8(name), b'Espa\xc3\xb1ol')


class EnglishTest(unittest.TestCase):
    def test_format_date(self):
        locale = tornado.locale.get('en_US')
        date = datetime.datetime(2013, 4, 28, 18, 35)
        self.assertEqual(locale.format_date(date, full_format=True),
                         'April 28, 2013 at 6:35 pm')
