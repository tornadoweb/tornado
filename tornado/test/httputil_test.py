#!/usr/bin/env python

from tornado.httputil import url_concat
import unittest


class TestUrlConcat(unittest.TestCase):

    def test_url_concat_no_query_params(self):
        url = url_concat(
                "https://localhost/path",
                {'y':'y', 'z':'z'},
                )
        self.assertEqual(url, "https://localhost/path?y=y&z=z")

    def test_url_concat_encode_args(self):
        url = url_concat(
                "https://localhost/path",
                {'y':'/y', 'z':'z'},
                )
        self.assertEqual(url, "https://localhost/path?y=%2Fy&z=z")

    def test_url_concat_trailing_q(self):
        url = url_concat(
                "https://localhost/path?",
                {'y':'y', 'z':'z'},
                )
        self.assertEqual(url, "https://localhost/path?y=y&z=z")

    def test_url_concat_q_with_no_trailing_amp(self):
        url = url_concat(
                "https://localhost/path?x",
                {'y':'y', 'z':'z'},
                )
        self.assertEqual(url, "https://localhost/path?x&y=y&z=z")

    def test_url_concat_trailing_amp(self):
        url = url_concat(
                "https://localhost/path?x&",
                {'y':'y', 'z':'z'},
                )
        self.assertEqual(url, "https://localhost/path?x&y=y&z=z")

    def test_url_concat_mult_params(self):
        url = url_concat(
                "https://localhost/path?a=1&b=2",
                {'y':'y', 'z':'z'},
                )
        self.assertEqual(url, "https://localhost/path?a=1&b=2&y=y&z=z")

    def test_url_concat_no_params(self):
        url = url_concat(
            "https://localhost/path?r=1&t=2",
            {},
            )
        self.assertEqual(url, "https://localhost/path?r=1&t=2")
