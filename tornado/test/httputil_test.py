#!/usr/bin/env python


from __future__ import absolute_import, division, with_statement
from tornado.httputil import url_concat, parse_multipart_form_data, HTTPHeaders
from tornado.escape import utf8
from tornado.testing import LogTrapTestCase
from tornado.util import b
import logging
import unittest


class TestUrlConcat(unittest.TestCase):

    def test_url_concat_no_query_params(self):
        url = url_concat(
                "https://localhost/path",
                [('y', 'y'), ('z', 'z')],
                )
        self.assertEqual(url, "https://localhost/path?y=y&z=z")

    def test_url_concat_encode_args(self):
        url = url_concat(
                "https://localhost/path",
                [('y', '/y'), ('z', 'z')],
                )
        self.assertEqual(url, "https://localhost/path?y=%2Fy&z=z")

    def test_url_concat_trailing_q(self):
        url = url_concat(
                "https://localhost/path?",
                [('y', 'y'), ('z', 'z')],
                )
        self.assertEqual(url, "https://localhost/path?y=y&z=z")

    def test_url_concat_q_with_no_trailing_amp(self):
        url = url_concat(
                "https://localhost/path?x",
                [('y', 'y'), ('z', 'z')],
                )
        self.assertEqual(url, "https://localhost/path?x&y=y&z=z")

    def test_url_concat_trailing_amp(self):
        url = url_concat(
                "https://localhost/path?x&",
                [('y', 'y'), ('z', 'z')],
                )
        self.assertEqual(url, "https://localhost/path?x&y=y&z=z")

    def test_url_concat_mult_params(self):
        url = url_concat(
                "https://localhost/path?a=1&b=2",
                [('y', 'y'), ('z', 'z')],
                )
        self.assertEqual(url, "https://localhost/path?a=1&b=2&y=y&z=z")

    def test_url_concat_no_params(self):
        url = url_concat(
            "https://localhost/path?r=1&t=2",
            [],
            )
        self.assertEqual(url, "https://localhost/path?r=1&t=2")


class MultipartFormDataTest(LogTrapTestCase):
    def test_file_upload(self):
        data = b("""\
--1234
Content-Disposition: form-data; name="files"; filename="ab.txt"

Foo
--1234--""").replace(b("\n"), b("\r\n"))
        args = {}
        files = {}
        parse_multipart_form_data(b("1234"), data, args, files)
        file = files["files"][0]
        self.assertEqual(file["filename"], "ab.txt")
        self.assertEqual(file["body"], b("Foo"))

    def test_unquoted_names(self):
        # quotes are optional unless special characters are present
        data = b("""\
--1234
Content-Disposition: form-data; name=files; filename=ab.txt

Foo
--1234--""").replace(b("\n"), b("\r\n"))
        args = {}
        files = {}
        parse_multipart_form_data(b("1234"), data, args, files)
        file = files["files"][0]
        self.assertEqual(file["filename"], "ab.txt")
        self.assertEqual(file["body"], b("Foo"))

    def test_special_filenames(self):
        filenames = ['a;b.txt',
                     'a"b.txt',
                     'a";b.txt',
                     'a;"b.txt',
                     'a";";.txt',
                     'a\\"b.txt',
                     'a\\b.txt',
                     ]
        for filename in filenames:
            logging.info("trying filename %r", filename)
            data = """\
--1234
Content-Disposition: form-data; name="files"; filename="%s"

Foo
--1234--""" % filename.replace('\\', '\\\\').replace('"', '\\"')
            data = utf8(data.replace("\n", "\r\n"))
            args = {}
            files = {}
            parse_multipart_form_data(b("1234"), data, args, files)
            file = files["files"][0]
            self.assertEqual(file["filename"], filename)
            self.assertEqual(file["body"], b("Foo"))

    def test_boundary_starts_and_ends_with_quotes(self):
        data = b('''\
--1234
Content-Disposition: form-data; name="files"; filename="ab.txt"

Foo
--1234--''').replace(b("\n"), b("\r\n"))
        args = {}
        files = {}
        parse_multipart_form_data(b('"1234"'), data, args, files)
        file = files["files"][0]
        self.assertEqual(file["filename"], "ab.txt")
        self.assertEqual(file["body"], b("Foo"))

    def test_missing_headers(self):
        data = b('''\
--1234

Foo
--1234--''').replace(b("\n"), b("\r\n"))
        args = {}
        files = {}
        parse_multipart_form_data(b("1234"), data, args, files)
        self.assertEqual(files, {})

    def test_invalid_content_disposition(self):
        data = b('''\
--1234
Content-Disposition: invalid; name="files"; filename="ab.txt"

Foo
--1234--''').replace(b("\n"), b("\r\n"))
        args = {}
        files = {}
        parse_multipart_form_data(b("1234"), data, args, files)
        self.assertEqual(files, {})

    def test_line_does_not_end_with_correct_line_break(self):
        data = b('''\
--1234
Content-Disposition: form-data; name="files"; filename="ab.txt"

Foo--1234--''').replace(b("\n"), b("\r\n"))
        args = {}
        files = {}
        parse_multipart_form_data(b("1234"), data, args, files)
        self.assertEqual(files, {})

    def test_content_disposition_header_without_name_parameter(self):
        data = b("""\
--1234
Content-Disposition: form-data; filename="ab.txt"

Foo
--1234--""").replace(b("\n"), b("\r\n"))
        args = {}
        files = {}
        parse_multipart_form_data(b("1234"), data, args, files)
        self.assertEqual(files, {})

    def test_data_after_final_boundary(self):
        # The spec requires that data after the final boundary be ignored.
        # http://www.w3.org/Protocols/rfc1341/7_2_Multipart.html
        # In practice, some libraries include an extra CRLF after the boundary.
        data = b("""\
--1234
Content-Disposition: form-data; name="files"; filename="ab.txt"

Foo
--1234--
""").replace(b("\n"), b("\r\n"))
        args = {}
        files = {}
        parse_multipart_form_data(b("1234"), data, args, files)
        file = files["files"][0]
        self.assertEqual(file["filename"], "ab.txt")
        self.assertEqual(file["body"], b("Foo"))


class HTTPHeadersTest(unittest.TestCase):
    def test_multi_line(self):
        # Lines beginning with whitespace are appended to the previous line
        # with any leading whitespace replaced by a single space.
        # Note that while multi-line headers are a part of the HTTP spec,
        # their use is strongly discouraged.
        data = """\
Foo: bar
 baz
Asdf: qwer
\tzxcv
Foo: even
     more
     lines
""".replace("\n", "\r\n")
        headers = HTTPHeaders.parse(data)
        self.assertEqual(headers["asdf"], "qwer zxcv")
        self.assertEqual(headers.get_list("asdf"), ["qwer zxcv"])
        self.assertEqual(headers["Foo"], "bar baz,even more lines")
        self.assertEqual(headers.get_list("foo"), ["bar baz", "even more lines"])
        self.assertEqual(sorted(list(headers.get_all())),
                         [("Asdf", "qwer zxcv"),
                          ("Foo", "bar baz"),
                          ("Foo", "even more lines")])
