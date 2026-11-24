import copy
import datetime
import logging
import pickle
import sys
import time
import urllib.parse

from tornado.escape import native_str, utf8
from tornado.httputil import (
    HTTPFile,
    HTTPHeaders,
    HTTPInputError,
    HTTPServerRequest,
    ParseMultipartConfig,
    ParseUrlEncodedConfig,
    RequestStartLine,
    _DEFAULT_PARSE_BODY_CONFIG,
    _parse_header,
    format_timestamp,
    parse_body_arguments,
    parse_cookie,
    parse_multipart_form_data,
    parse_request_start_line,
    qs_to_qsl,
    split_host_and_port,
    url_concat,
    _url_to_ascii,
)
from tornado.log import gen_log
from tornado.test.util import (
    TestCase,
    assert_linear_scaling,
    assert_memory_budget,
    ignore_deprecation,
    skipNotCPython,
)


def form_data_args() -> tuple[dict[str, list[bytes]], dict[str, list[HTTPFile]]]:
    """Return two empty dicts suitable for use with parse_multipart_form_data.

    mypy insists on type annotations for dict literals, so this lets us avoid
    the verbose types throughout this test.
    """
    return {}, {}


class TestUrlConcat(TestCase):
    def test_url_concat_no_query_params(self):
        url = url_concat("https://localhost/path", [("y", "y"), ("z", "z")])
        self.assertEqual(url, "https://localhost/path?y=y&z=z")

    def test_url_concat_encode_args(self):
        url = url_concat("https://localhost/path", [("y", "/y"), ("z", "z")])
        self.assertEqual(url, "https://localhost/path?y=%2Fy&z=z")

    def test_url_concat_trailing_q(self):
        url = url_concat("https://localhost/path?", [("y", "y"), ("z", "z")])
        self.assertEqual(url, "https://localhost/path?y=y&z=z")

    def test_url_concat_q_with_no_trailing_amp(self):
        url = url_concat("https://localhost/path?x", [("y", "y"), ("z", "z")])
        self.assertEqual(url, "https://localhost/path?x=&y=y&z=z")

    def test_url_concat_trailing_amp(self):
        url = url_concat("https://localhost/path?x&", [("y", "y"), ("z", "z")])
        self.assertEqual(url, "https://localhost/path?x=&y=y&z=z")

    def test_url_concat_mult_params(self):
        url = url_concat("https://localhost/path?a=1&b=2", [("y", "y"), ("z", "z")])
        self.assertEqual(url, "https://localhost/path?a=1&b=2&y=y&z=z")

    def test_url_concat_no_params(self):
        url = url_concat("https://localhost/path?r=1&t=2", [])
        self.assertEqual(url, "https://localhost/path?r=1&t=2")

    def test_url_concat_none_params(self):
        url = url_concat("https://localhost/path?r=1&t=2", None)
        self.assertEqual(url, "https://localhost/path?r=1&t=2")

    def test_url_concat_with_frag(self):
        url = url_concat("https://localhost/path#tab", [("y", "y")])
        self.assertEqual(url, "https://localhost/path?y=y#tab")

    def test_url_concat_multi_same_params(self):
        url = url_concat("https://localhost/path", [("y", "y1"), ("y", "y2")])
        self.assertEqual(url, "https://localhost/path?y=y1&y=y2")

    def test_url_concat_multi_same_query_params(self):
        url = url_concat("https://localhost/path?r=1&r=2", [("y", "y")])
        self.assertEqual(url, "https://localhost/path?r=1&r=2&y=y")

    def test_url_concat_dict_params(self):
        url = url_concat("https://localhost/path", dict(y="y"))
        self.assertEqual(url, "https://localhost/path?y=y")


class QsParseTest(TestCase):
    def test_parsing(self):
        qsstring = "a=1&b=2&a=3"
        qs = urllib.parse.parse_qs(qsstring)
        qsl = list(qs_to_qsl(qs))
        self.assertIn(("a", "1"), qsl)
        self.assertIn(("a", "3"), qsl)
        self.assertIn(("b", "2"), qsl)


class UrlEncodedDataTest(TestCase):
    def test_content_type_case(self):
        for content_type in (
            "application/x-www-form-urlencoded",
            "Application/X-WWW-Form-Urlencoded",
            "APPLICATION/X-WWW-FORM-URLENCODED; charset=UTF-8",
        ):
            with self.subTest(content_type=content_type):
                args, files = form_data_args()
                parse_body_arguments(
                    content_type, b"Name=Value&Name=Other", args, files
                )
                self.assertEqual(args, {"Name": [b"Value", b"Other"]})
                self.assertEqual(files, {})

    def test_urlencoded_data(self):
        data = b"a=1&b=2&a=3"
        args, files = form_data_args()
        parse_body_arguments("application/x-www-form-urlencoded", data, args, files)
        self.assertEqual(args["a"], [b"1", b"3"])
        self.assertEqual(args["b"], [b"2"])
        self.assertEqual(files, {})

    def test_max_arguments(self):
        data = b"".join(b"a=1&" for _ in range(1001))
        args, files = form_data_args()
        with self.assertRaises(HTTPInputError) as cm:
            parse_body_arguments("application/x-www-form-urlencoded", data, args, files)
        self.assertIn("Max number of fields exceeded", str(cm.exception))

    def test_urlencoded_prefix_not_matched(self):
        # A media type that merely shares the urlencoded prefix must not be
        # parsed as form data.
        data = b"a=1&b=2"
        for content_type in (
            "application/x-www-form-urlencoded-garbage",
            "application/x-www-form-urlencoded2",
        ):
            args, files = form_data_args()
            parse_body_arguments(content_type, data, args, files)
            self.assertEqual(args, {})
            self.assertEqual(files, {})
        # The real media type, with and without parameters, still parses.
        for content_type in (
            "application/x-www-form-urlencoded",
            "application/x-www-form-urlencoded; charset=utf-8",
        ):
            args, files = form_data_args()
            parse_body_arguments(content_type, data, args, files)
            self.assertEqual(args["a"], [b"1"])
            self.assertEqual(args["b"], [b"2"])

    @skipNotCPython
    def test_memory_budget(self):
        # Large bodies use a few bytes of memory per input byte: up to about
        # 8 for lone % signs (see EscapeTestCase.test_unquote_memory_budget)
        # and about 2 for many long fields, as of 2026-11.
        n = ParseUrlEncodedConfig().max_arguments - 1
        for name, body in [
            ("lone %", b"a=" + b"%" * 900_000),
            (
                "escaped keys",
                b"&".join(b"%d" % i + b"%41" * 333 + b"=" for i in range(n)),
            ),
            ("long values", b"&".join(b"a=" + b"x" * 1000 for i in range(n))),
        ]:
            with self.subTest(name):
                args, files = form_data_args()
                with assert_memory_budget(
                    len(body),
                    max_ratio=12,
                    msg="urlencoded body parsing uses too much memory",
                ):
                    parse_body_arguments(
                        "application/x-www-form-urlencoded", body, args, files
                    )

    @skipNotCPython
    def test_memory_budget_many_fields(self):
        # Each field costs a fixed amount (about 250 bytes as of 2026-11), so
        # many short fields use about 50 bytes per input byte. max_arguments
        # bounds the total, so the budget is per field rather than per byte.
        max_arguments = ParseUrlEncodedConfig().max_arguments
        body = b"".join(b"%d=&" % i for i in range(max_arguments - 1))
        args, files = form_data_args()
        with assert_memory_budget(
            max_arguments,
            max_ratio=500,
            msg="urlencoded body parsing uses too much memory per field",
        ):
            parse_body_arguments("application/x-www-form-urlencoded", body, args, files)
        self.assertEqual(len(args), max_arguments - 1)


class MultipartFormDataTest(TestCase):
    def test_content_type_case(self):
        data = (
            b"--AaB03x\r\n"
            b'Content-Disposition: form-data; name="Files"; filename="Report.TXT"\r\n'
            b"\r\nHello\r\n--AaB03x--\r\n"
        )
        for media_type in ("multipart/form-data", "Multipart/Form-Data"):
            for parameter in ("boundary", "Boundary", "BOUNDARY"):
                for boundary in ("AaB03x", '"AaB03x"'):
                    content_type = f"{media_type}; {parameter}={boundary}"
                    with self.subTest(content_type=content_type):
                        args, files = form_data_args()
                        parse_body_arguments(content_type, data, args, files)
                        self.assertEqual(args, {})
                        self.assertEqual(files["Files"][0].filename, "Report.TXT")
                        self.assertEqual(files["Files"][0].body, b"Hello")

    def test_multipart_prefix_not_matched(self):
        # A media type that merely shares the multipart/form-data prefix
        # must be ignored (not parsed, and no error), consistent with how
        # unrecognized urlencoded-like media types are treated.
        data = (
            b"--AaB03x\r\n"
            b'Content-Disposition: form-data; name="a"\r\n'
            b"\r\n1\r\n--AaB03x--\r\n"
        )
        for content_type in (
            "multipart/form-dataxyz",
            "multipart/form-data-garbage; boundary=AaB03x",
        ):
            args, files = form_data_args()
            parse_body_arguments(content_type, data, args, files)
            self.assertEqual(args, {})
            self.assertEqual(files, {})

    def test_multipart_malformed_rfc2231_params(self):
        # A parameter given both with and without an RFC 2231
        # continuation number ("name*=a; name*1=b") makes
        # _parse_header raise ValueError on Python < 3.13.5. That
        # error must not escape parse_body_arguments; the media type
        # is recovered from the header prefix and nothing is parsed
        # out of the (empty) body.
        args, files = form_data_args()
        parse_body_arguments(
            "multipart/form-data; boundary=AaB03x; name*=a; name*1=b",
            b"--AaB03x--\r\n",
            args,
            files,
        )
        self.assertEqual(args, {})
        self.assertEqual(files, {})

    def test_multiple_boundaries(self):
        data = (
            b"--1234\r\n"
            b'Content-Disposition: form-data; name="Name"\r\n'
            b"\r\nValue\r\n--1234--\r\n"
        )
        for content_type in (
            "multipart/form-data; boundary=1234; boundary=5678",
            "multipart/form-data; boundary=5678; BOUNDARY=1234",
            "multipart/form-data; boundary=1234; boundary=1234",
            "multipart/form-data; boundary=; boundary=1234",
        ):
            with self.subTest(content_type=content_type):
                args, files = form_data_args()
                with self.assertRaisesRegex(HTTPInputError, "multiple"):
                    parse_body_arguments(content_type, data, args, files)

    def test_boundary_value_is_case_sensitive(self):
        data = (
            b"--AaB03x\r\n"
            b'Content-Disposition: form-data; name="Name"\r\n'
            b"\r\nValue\r\n--AaB03x--\r\n"
        )
        args, files = form_data_args()
        with self.assertRaisesRegex(HTTPInputError, "no final boundary found"):
            parse_body_arguments(
                "multipart/form-data; boundary=aab03x", data, args, files
            )

    def test_file_upload(self):
        data = b"""\
--1234
Content-Disposition: form-data; name="files"; filename="ab.txt"

Foo
--1234--""".replace(b"\n", b"\r\n")
        args, files = form_data_args()
        parse_multipart_form_data(b"1234", data, args, files)
        file = files["files"][0]
        self.assertEqual(file["filename"], "ab.txt")
        self.assertEqual(file["body"], b"Foo")

    def test_unquoted_names(self):
        # quotes are optional unless special characters are present
        data = b"""\
--1234
Content-Disposition: form-data; name=files; filename=ab.txt

Foo
--1234--""".replace(b"\n", b"\r\n")
        args, files = form_data_args()
        parse_multipart_form_data(b"1234", data, args, files)
        file = files["files"][0]
        self.assertEqual(file["filename"], "ab.txt")
        self.assertEqual(file["body"], b"Foo")

    def test_special_filenames(self):
        filenames = [
            "a;b.txt",
            'a"b.txt',
            'a";b.txt',
            'a;"b.txt',
            'a";";.txt',
            'a\\"b.txt',
            "a\\b.txt",
            "a b.txt",
            "a\tb.txt",
        ]
        for filename in filenames:
            logging.debug("trying filename %r", filename)
            str_data = """\
--1234
Content-Disposition: form-data; name="files"; filename="%s"

Foo
--1234--""" % filename.replace("\\", "\\\\").replace('"', '\\"')
            data = utf8(str_data.replace("\n", "\r\n"))
            args, files = form_data_args()
            parse_multipart_form_data(b"1234", data, args, files)
            file = files["files"][0]
            self.assertEqual(file["filename"], filename)
            self.assertEqual(file["body"], b"Foo")

    def test_invalid_chars(self):
        filenames = [
            "a\rb.txt",
            "a\0b.txt",
            "a\x08b.txt",
        ]
        for filename in filenames:
            str_data = """\
--1234
Content-Disposition: form-data; name="files"; filename="%s"

Foo
--1234--""" % filename.replace("\\", "\\\\").replace('"', '\\"')
            data = utf8(str_data.replace("\n", "\r\n"))
            args, files = form_data_args()
            with self.assertRaises(HTTPInputError) as cm:
                parse_multipart_form_data(b"1234", data, args, files)
            self.assertIn("Invalid header value", str(cm.exception))

    def test_non_ascii_filename_rfc5987(self):
        data = b"""\
--1234
Content-Disposition: form-data; name="files"; filename="ab.txt"; filename*=UTF-8''%C3%A1b.txt

Foo
--1234--""".replace(b"\n", b"\r\n")
        args, files = form_data_args()
        parse_multipart_form_data(b"1234", data, args, files)
        file = files["files"][0]
        self.assertEqual(file["filename"], "áb.txt")
        self.assertEqual(file["body"], b"Foo")

    def test_non_ascii_filename_raw(self):
        data = """\
--1234
Content-Disposition: form-data; name="files"; filename="测试.txt"

Foo
--1234--""".encode().replace(b"\n", b"\r\n")
        args, files = form_data_args()
        parse_multipart_form_data(b"1234", data, args, files)
        file = files["files"][0]
        self.assertEqual(file["filename"], "测试.txt")
        self.assertEqual(file["body"], b"Foo")

    def test_boundary_starts_and_ends_with_quotes(self):
        data = b"""\
--1234
Content-Disposition: form-data; name="files"; filename="ab.txt"

Foo
--1234--""".replace(b"\n", b"\r\n")
        args, files = form_data_args()
        parse_multipart_form_data(b'"1234"', data, args, files)
        file = files["files"][0]
        self.assertEqual(file["filename"], "ab.txt")
        self.assertEqual(file["body"], b"Foo")

    def test_missing_headers(self):
        data = b"""\
--1234

Foo
--1234--""".replace(b"\n", b"\r\n")
        args, files = form_data_args()
        with self.assertRaises(
            HTTPInputError, msg="multipart/form-data missing headers"
        ):
            parse_multipart_form_data(b"1234", data, args, files)
        self.assertEqual(files, {})

    def test_invalid_content_disposition(self):
        data = b"""\
--1234
Content-Disposition: invalid; name="files"; filename="ab.txt"

Foo
--1234--""".replace(b"\n", b"\r\n")
        args, files = form_data_args()
        with self.assertRaises(HTTPInputError, msg="Invalid multipart/form-data"):
            parse_multipart_form_data(b"1234", data, args, files)
        self.assertEqual(files, {})

    def test_line_does_not_end_with_correct_line_break(self):
        data = b"""\
--1234
Content-Disposition: form-data; name="files"; filename="ab.txt"

Foo--1234--""".replace(b"\n", b"\r\n")
        args, files = form_data_args()
        with self.assertRaises(HTTPInputError, msg="Invalid multipart/form-data"):
            parse_multipart_form_data(b"1234", data, args, files)
        self.assertEqual(files, {})

    def test_content_disposition_header_without_name_parameter(self):
        data = b"""\
--1234
Content-Disposition: form-data; filename="ab.txt"

Foo
--1234--""".replace(b"\n", b"\r\n")
        args, files = form_data_args()
        with self.assertRaises(
            HTTPInputError, msg="multipart/form-data value missing name"
        ):
            parse_multipart_form_data(b"1234", data, args, files)
        self.assertEqual(files, {})

    def test_data_after_final_boundary(self):
        # The spec requires that data after the final boundary be ignored.
        # http://www.w3.org/Protocols/rfc1341/7_2_Multipart.html
        # In practice, some libraries include an extra CRLF after the boundary.
        data = b"""\
--1234
Content-Disposition: form-data; name="files"; filename="ab.txt"

Foo
--1234--
""".replace(b"\n", b"\r\n")
        args, files = form_data_args()
        parse_multipart_form_data(b"1234", data, args, files)
        file = files["files"][0]
        self.assertEqual(file["filename"], "ab.txt")
        self.assertEqual(file["body"], b"Foo")

    def test_mixed_rfc2231_continuations(self):
        # A parameter given both with and without a continuation number
        # made email.utils.decode_params raise TypeError before Python
        # 3.13.5. It must be reported as bad input.
        data = (
            b"--1234\r\nContent-Disposition: form-data; name*=a; name*1=b\r\n"
            b"\r\nFoo\r\n--1234--\r\n"
        )
        args, files = form_data_args()
        if sys.version_info >= (3, 13, 5):
            parse_multipart_form_data(b"1234", data, args, files)
            self.assertEqual(args, {"ab": [b"Foo"]})
        else:
            with self.assertRaises(HTTPInputError):
                parse_multipart_form_data(b"1234", data, args, files)

    def test_undecodable_rfc2231_parameter(self):
        # _parse_header raises ValueError (UnicodeError) for a charset that
        # can't decode with errors="replace".
        data = (
            b"--1234\r\nContent-Disposition: form-data; name*=idna''%ff\r\n"
            b"\r\nFoo\r\n--1234--\r\n"
        )
        args, files = form_data_args()
        with self.assertRaises(HTTPInputError):
            parse_multipart_form_data(b"1234", data, args, files)

    def test_rfc2231_continuations(self):
        # Correctly numbered continuations, alone or with an encoded first
        # section, are joined.
        for disposition, name in [
            (b"name*0=a; name*1=b", "ab"),
            (b"name*0*=utf-8''%C3%A4; name*1=b", "\u00e4b"),
            (b"name*=utf-8''%C3%A4b", "\u00e4b"),
        ]:
            with self.subTest(disposition):
                data = (
                    b"--1234\r\nContent-Disposition: form-data; "
                    + disposition
                    + b"\r\n\r\nFoo\r\n--1234--\r\n"
                )
                args, files = form_data_args()
                parse_multipart_form_data(b"1234", data, args, files)
                self.assertEqual(args, {name: [b"Foo"]})

    def test_disposition_param_linear_performance(self):
        # This is a regression test for performance of parsing parameters
        # to the content-disposition header, specifically for semicolons within
        # quoted strings.
        def f(n):
            message = (
                b"--1234\r\nContent-Disposition: form-data; "
                + b'x="'
                + b";" * n
                + b'"; '
                + b'name="files"; filename="a.txt"\r\n\r\nFoo\r\n--1234--\r\n'
            )
            args: dict[str, list[bytes]] = {}
            files: dict[str, list[HTTPFile]] = {}
            parse_multipart_form_data(b"1234", message, args, files)

        # Note that headers larger than 10_000 are blocked by the default
        # configuration.
        assert_linear_scaling(
            f,
            1_000,
            10_000,
            max_ratio=20,
            msg="Disposition param parsing is not linear",
        )

    @skipNotCPython
    def test_parse_header_memory_budget(self):
        # Many tiny parameters are the worst case for memory in
        # _parse_header (about 45 bytes per input byte as of 2026-10).
        header = "form-data" + "; a=b" * 10_000
        with assert_memory_budget(
            len(header), max_ratio=60, msg="_parse_header uses too much memory"
        ):
            _parse_header(header)

    @skipNotCPython
    def test_multipart_memory_budget(self):
        # Many empty parts are the worst case for memory, since each part
        # costs a fixed amount (about 5 bytes per input byte as of 2026-10
        # with the default max_parts). Larger parts are close to 2: the
        # body and one copy of each part's data.
        part = (
            b"--1234\r\n"
            b'Content-Disposition: form-data; name="a"; filename="b"\r\n'
            b"Content-Type: text/plain\r\n\r\n\r\n"
        )
        body = part * (ParseMultipartConfig().max_parts - 1) + b"--1234--\r\n"
        args, files = form_data_args()
        with assert_memory_budget(
            len(body), max_ratio=10, msg="multipart parsing uses too much memory"
        ):
            parse_multipart_form_data(b"1234", body, args, files)
        self.assertEqual(len(files["a"]), 99)

    def test_multipart_config(self):
        boundary = b"1234"
        body = b"""--1234
Content-Disposition: form-data; name="files"; filename="ab.txt"

--1234--""".replace(b"\n", b"\r\n")
        config = ParseMultipartConfig()
        args, files = form_data_args()
        parse_multipart_form_data(boundary, body, args, files, config=config)
        self.assertEqual(files["files"][0]["filename"], "ab.txt")

        config_no_parts = ParseMultipartConfig(max_parts=0)
        with self.assertRaises(HTTPInputError) as cm:
            parse_multipart_form_data(
                boundary, body, args, files, config=config_no_parts
            )
        self.assertIn("too many parts", str(cm.exception))

        config_small_headers = ParseMultipartConfig(max_part_header_size=10)
        with self.assertRaises(HTTPInputError) as cm:
            parse_multipart_form_data(
                boundary, body, args, files, config=config_small_headers
            )
        self.assertIn("header too large", str(cm.exception))

        config_disabled = ParseMultipartConfig(enabled=False)
        with self.assertRaises(HTTPInputError) as cm:
            parse_multipart_form_data(
                boundary, body, args, files, config=config_disabled
            )
        self.assertIn("multipart/form-data parsing is disabled", str(cm.exception))


class ParseHeaderTest(TestCase):
    def test_content_type_is_case_insensitive(self):
        self.assertEqual(
            _parse_header("TEXT/PLAIN; charset=UTF-8"),
            ("text/plain", {"charset": "UTF-8"}),
        )

    def test_mixed_rfc2231_continuations(self):
        # See MultipartFormDataTest.test_mixed_rfc2231_continuations.
        for header in [
            "form-data; name*=a; name*1=b",
            "form-data; name*1=b; name*=a",
            "permessage-deflate; a*=1; a*1=2",
        ]:
            with self.subTest(header):
                if sys.version_info >= (3, 13, 5):
                    _parse_header(header)
                else:
                    with self.assertRaises(ValueError):
                        _parse_header(header)

    def test_undecodable_rfc2231_parameter(self):
        with self.assertRaises(ValueError):
            _parse_header("form-data; name*=idna''%ff")

    def test_valid_parameters(self):
        # The parameter forms closest to the one above still work.
        self.assertEqual(
            _parse_header("form-data; name*0=a; name*1=b; filename*=utf-8''x%20y"),
            ("form-data", {"name": "ab", "filename": "x y"}),
        )
        self.assertEqual(
            _parse_header("form-data; name*0*=utf-8''%C3%A4; name*1=b"),
            ("form-data", {"name": "\u00e4b"}),
        )
        self.assertEqual(
            _parse_header("permessage-deflate; client_max_window_bits=10; x"),
            ("permessage-deflate", {"client_max_window_bits": "10", "x": None}),
        )


class HTTPHeadersTest(TestCase):
    def test_bytes_parse_default_latin1_and_repeated_order(self):
        headers = HTTPHeaders.parse(b"X: \xff\r\nX: second\r\n")
        self.assertEqual(list(headers.get_all()), [("X", "\xff"), ("X", "second")])
        self.assertEqual(headers["X"], "\xff,second")

    def test_bytes_parse_line_and_explicit_encoding(self):
        headers = HTTPHeaders()
        headers.parse_line("X: 名\r\n".encode(), encoding="utf8", strict_http=False)
        self.assertEqual(headers["X"], "名")
        headers.parse_line(b"X: \xff\n")
        self.assertEqual(headers.get_list("X"), ["名", "\xff"])
        self.assertEqual(headers["X"], "名,\xff")

    def test_encoding_does_not_choose_validation(self):
        for operation in (HTTPHeaders.parse, HTTPHeaders().parse_line):
            with self.subTest(operation=operation):
                with self.assertRaises(HTTPInputError):
                    operation("X: 名".encode(), encoding="utf8")
                operation("X: 名".encode(), encoding="utf8", strict_http=False)
                with self.assertRaises(HTTPInputError):
                    operation(b"X: left\x00right", strict_http=False)
                with self.assertRaises(HTTPInputError):
                    operation("名: value".encode(), encoding="utf8", strict_http=False)

    def test_byte_decode_errors_remain_strict(self):
        for operation in (HTTPHeaders.parse, HTTPHeaders().parse_line):
            with self.subTest(operation=operation):
                with self.assertRaises(UnicodeDecodeError):
                    operation(b"X: \xff", encoding="utf8", strict_http=False)
                with self.assertRaises(LookupError):
                    operation(b"X: value", encoding="not-a-codec")

    def test_text_input_is_not_reencoded(self):
        headers = HTTPHeaders.parse("X: 名", encoding="ascii", strict_http=False)
        self.assertEqual(headers["X"], "名")
        headers.parse_line("Y: 名", encoding="ascii", strict_http=False)
        self.assertEqual(headers["Y"], "名")

    def test_explicit_validation_overrides_compatibility_alias(self):
        headers = HTTPHeaders.parse("X: 名", strict_http=False, _chars_are_bytes=True)
        self.assertEqual(headers["X"], "名")
        with self.assertRaises(HTTPInputError):
            HTTPHeaders.parse("X: 名", strict_http=True, _chars_are_bytes=False)
        headers = HTTPHeaders()
        headers.add("X", "名", strict_http=False)
        self.assertEqual(headers["X"], "名")
        with self.assertRaises(HTTPInputError):
            headers.add("Y", "名", strict_http=True, _chars_are_bytes=False)

    def test_http_and_multipart_value_validation(self):
        # Decoding and validation are separate: multipart permits Unicode
        # outside the HTTP obs-text range but must still reject controls.
        for chars_are_bytes in (True, False):
            for codepoint in range(256):
                value = "left" + chr(codepoint) + "right"
                with self.subTest(chars_are_bytes=chars_are_bytes, codepoint=codepoint):
                    if codepoint == 9 or (codepoint >= 32 and codepoint != 127):
                        headers = HTTPHeaders.parse(
                            "X: " + value, _chars_are_bytes=chars_are_bytes
                        )
                        self.assertEqual(headers["X"], value)
                    else:
                        with self.assertRaises(HTTPInputError):
                            HTTPHeaders.parse(
                                "X: " + value, _chars_are_bytes=chars_are_bytes
                            )

    def test_multipart_unicode_values_keep_separators_and_whitespace(self):
        for char in ("名", "\u20ac", "\u2028", "\u2029", "\u0085", "\u00a0"):
            with self.subTest(char=char):
                value = char + "body" + char
                headers = HTTPHeaders.parse("X: " + value, _chars_are_bytes=False)
                self.assertEqual(list(headers.get_all()), [("X", value)])
        for char in ("名", "\u20ac", "\u2028", "\u2029"):
            with self.subTest(http_char=char):
                with self.assertRaises(HTTPInputError):
                    HTTPHeaders.parse("X: " + char)

    def test_multipart_names_remain_http_tokens(self):
        for name in ("bad name", "名", "", "x\x00"):
            with self.subTest(name=name):
                with self.assertRaises(HTTPInputError):
                    HTTPHeaders.parse(name + ": value", _chars_are_bytes=False)

    def test_http_utf8_octets_remain_latin1_not_unicode(self):
        raw = "X: 名".encode("utf8")
        headers = HTTPHeaders.parse(raw.decode("latin1"))
        self.assertEqual(headers["X"].encode("latin1"), "名".encode("utf8"))
        self.assertNotEqual(headers["X"], "名")

    def test_multipart_line_structure_and_order(self):
        headers = HTTPHeaders.parse("X: a\nX: b\r\n", _chars_are_bytes=False)
        self.assertEqual(list(headers.get_all()), [("X", "a"), ("X", "b")])
        self.assertEqual(headers["X"], "a,b")
        for text in ("X: a\rY: b", " X: a", "X: a\r\n\tb", "no colon"):
            with self.subTest(text=text):
                with self.assertRaises(HTTPInputError):
                    HTTPHeaders.parse(text, _chars_are_bytes=False)

    def test_folding_rejected(self):
        data = "Foo: bar\r\n\tasdf"
        with self.assertRaises(HTTPInputError):
            # Folded continuation lines are not supported.
            HTTPHeaders.parse(data)

    def test_forbidden_ascii_characters(self):
        # Control characters and ASCII whitespace other than space, tab, and CRLF are not allowed in
        # headers.
        for c in range(0xFF):
            data = f"Foo: bar{chr(c)}baz\r\n"
            if c == 0x09 or (c >= 0x20 and c != 0x7F):
                headers = HTTPHeaders.parse(data)
                self.assertEqual(headers["Foo"], f"bar{chr(c)}baz")
            else:
                self.assertRaises(HTTPInputError, HTTPHeaders.parse, data)

    def test_setitem_validates_name_and_value(self):
        headers = HTTPHeaders()
        with self.assertRaises(ValueError):
            headers["Foo Bar"] = "baz"
        with self.assertRaises(ValueError):
            headers["Foo"] = "bar\rbaz"
        with self.assertRaises(ValueError):
            headers["Foo"] = "bar\x00baz"
        # obs-text is allowed in a header value.
        headers["Foo"] = "b\u00e1r"
        self.assertEqual(headers["Foo"], "b\u00e1r")

    def test_update_and_initialization_validate(self):
        with self.assertRaises(ValueError):
            HTTPHeaders({"Foo": "bar\rbaz"})
        headers = HTTPHeaders()
        with self.assertRaises(ValueError):
            headers.update({"Foo": "bar\rbaz"})
        self.assertEqual(list(headers.get_all()), [])

    def test_surrounding_whitespace_allowed(self):
        # Leading and trailing whitespace is optional whitespace around the
        # field value (RFC 9110 section 5.5), not part of it, so it is
        # accepted when building headers. (#3902 briefly rejected it.)
        for value in [" lead", "trail ", "  both  ", "\tlead", "trail\t", " ", "\t"]:
            with self.subTest(value=value):
                headers = HTTPHeaders({"X-Foo": value})
                self.assertEqual(headers["X-Foo"], value)
                headers = HTTPHeaders()
                headers["X-Foo"] = value
                self.assertEqual(headers["X-Foo"], value)
                headers = HTTPHeaders()
                headers.add("X-Foo", value)
                headers.add("X-Foo", value)
                self.assertEqual(headers.get_list("X-Foo"), [value, value])
        # Whitespace doesn't hide invalid characters.
        for value in [" \r\n", "\t\x00", " a\rb ", "\n ", " \x7f"]:
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    HTTPHeaders({"X-Foo": value})
                with self.assertRaises(ValueError):
                    HTTPHeaders().add("X-Foo", value)

    def test_loose_multipart_validation_is_not_reapplied(self):
        headers = HTTPHeaders()
        headers.add("X-Filename", "\u20ac", _chars_are_bytes=False)
        self.assertEqual(headers["X-Filename"], "\u20ac")

    def test_unicode_newlines(self):
        # Ensure that only \r\n is recognized as a header separator, and not
        # the other newline-like unicode characters.
        # Characters that are likely to be problematic can be found in
        # http://unicode.org/standard/reports/tr13/tr13-5.html
        # and cpython's unicodeobject.c (which defines the implementation
        # of unicode_type.splitlines(), and uses a different list than TR13).
        newlines = [
            # The following ascii characters are sometimes treated as newline-like,
            # but they're disallowed in HTTP headers. This test covers unicode
            # characters that are permitted in headers (under the obs-text rule).
            # "\u001b",  # VERTICAL TAB
            # "\u001c",  # FILE SEPARATOR
            # "\u001d",  # GROUP SEPARATOR
            # "\u001e",  # RECORD SEPARATOR
            "\u0085",  # NEXT LINE
            "\u2028",  # LINE SEPARATOR
            "\u2029",  # PARAGRAPH SEPARATOR
        ]
        for newline in newlines:
            # Try the utf8 and latin1 representations of each newline
            for encoding in ["utf8", "latin1"]:
                try:
                    try:
                        encoded = newline.encode(encoding)
                    except UnicodeEncodeError:
                        # Some chars cannot be represented in latin1
                        continue
                    data = b"Cookie: foo=" + encoded + b"bar"
                    # parse() wants a native_str, so decode through latin1
                    # in the same way the real parser does.
                    headers = HTTPHeaders.parse(native_str(data.decode("latin1")))
                    expected = [
                        (
                            "Cookie",
                            "foo=" + native_str(encoded.decode("latin1")) + "bar",
                        )
                    ]
                    self.assertEqual(expected, list(headers.get_all()))
                except Exception:
                    gen_log.warning("failed while trying %r in %s", newline, encoding)
                    raise

    def test_unicode_whitespace(self):
        # Only tabs and spaces are to be stripped according to the HTTP standard.
        # Other unicode whitespace is to be left as-is. In the context of headers,
        # this specifically means the whitespace characters falling within the
        # latin1 charset.
        whitespace = [
            (" ", True),  # SPACE
            ("\t", True),  # TAB
            ("\u00a0", False),  # NON-BREAKING SPACE
            ("\u0085", False),  # NEXT LINE
        ]
        for c, stripped in whitespace:
            headers = HTTPHeaders.parse("Transfer-Encoding: %schunked" % c)
            if stripped:
                expected = [("Transfer-Encoding", "chunked")]
            else:
                expected = [("Transfer-Encoding", "%schunked" % c)]
            self.assertEqual(expected, list(headers.get_all()))

    def test_optional_cr(self):
        # Bare CR is  not a valid line separator
        with self.assertRaises(HTTPInputError):
            HTTPHeaders.parse("CRLF: crlf\r\nLF: lf\nCR: cr\rMore: more\r\n")

        # Both CRLF and LF should be accepted as separators. CR should not be
        # part of the data when followed by LF.
        headers = HTTPHeaders.parse("CRLF: crlf\r\nLF: lf\nMore: more\r\n")
        self.assertEqual(
            sorted(headers.get_all()),
            [("Crlf", "crlf"), ("Lf", "lf"), ("More", "more")],
        )

    def test_copy(self):
        all_pairs = [("A", "1"), ("A", "2"), ("B", "c")]
        h1 = HTTPHeaders()
        for k, v in all_pairs:
            h1.add(k, v)
        h2 = h1.copy()
        h3 = copy.copy(h1)
        h4 = copy.deepcopy(h1)
        for headers in [h1, h2, h3, h4]:
            # All the copies are identical, no matter how they were
            # constructed.
            self.assertEqual(list(sorted(headers.get_all())), all_pairs)
        for headers in [h2, h3, h4]:
            # Neither the dict or its member lists are reused.
            self.assertIsNot(headers, h1)
            self.assertIsNot(headers.get_list("A"), h1.get_list("A"))

    def test_pickle_roundtrip(self):
        headers = HTTPHeaders()
        headers.add("Set-Cookie", "a=b")
        headers.add("Set-Cookie", "c=d")
        headers.add("Content-Type", "text/html")
        pickled = pickle.dumps(headers)
        unpickled = pickle.loads(pickled)
        self.assertEqual(sorted(headers.get_all()), sorted(unpickled.get_all()))
        self.assertEqual(sorted(headers.items()), sorted(unpickled.items()))

    def test_setdefault(self):
        headers = HTTPHeaders()
        headers["foo"] = "bar"
        # If a value is present, setdefault returns it without changes.
        self.assertEqual(headers.setdefault("foo", "baz"), "bar")
        self.assertEqual(headers["foo"], "bar")
        # If a value is not present, setdefault sets it for future use.
        self.assertEqual(headers.setdefault("quux", "xyzzy"), "xyzzy")
        self.assertEqual(headers["quux"], "xyzzy")
        self.assertEqual(sorted(headers.get_all()), [("Foo", "bar"), ("Quux", "xyzzy")])

    def test_delitem(self):
        # Deleting a header must not depend on whether the combined-value
        # cache happens to be populated for it. The cache is invalidated by
        # add(), so a multi-valued header that was never read through
        # __getitem__ has no cache entry.
        headers = HTTPHeaders()
        headers["foo"] = "bar"
        del headers["foo"]
        self.assertEqual(sorted(headers.get_all()), [])
        with self.assertRaises(KeyError):
            del headers["foo"]

        headers = HTTPHeaders()
        headers.add("Set-Cookie", "a=b")
        headers.add("Set-Cookie", "c=d")
        del headers["set-cookie"]
        self.assertEqual(sorted(headers.get_all()), [])

    def test_string(self):
        headers = HTTPHeaders()
        headers.add("Foo", "1")
        headers.add("Foo", "2")
        headers.add("Foo", "3")
        headers2 = HTTPHeaders.parse(str(headers))
        self.assertEqual(headers, headers2)

    def test_invalid_header_names(self):
        invalid_names = [
            "",
            "foo bar",
            "foo\tbar",
            "foo\nbar",
            "foo\x00bar",
            "foo ",
            " foo",
            "é",
        ]
        for name in invalid_names:
            headers = HTTPHeaders()
            with self.assertRaises(ValueError):
                headers.add(name, "bar")
            # The same name in a parsed header line is an input error.
            with self.assertRaises(HTTPInputError):
                HTTPHeaders.parse(f"{name}: bar\r\n")

    def test_linear_performance(self):
        def f(n):
            headers = HTTPHeaders()
            for i in range(n):
                headers.add("X-Foo", "bar")

        # This runs under 50ms on my laptop as of 2025-12-09. The ratio
        # between the two sizes should be about 10x, but allow a wide margin
        # for variability.
        assert_linear_scaling(
            f,
            10_000,
            100_000,
            max_ratio=20,
            msg="HTTPHeaders.add() does not scale linearly",
        )

    def test_parse_repeated_linear_performance(self):
        # Regression test for CVE-2025-67725, through the parsing path that
        # HTTP1Connection uses rather than HTTPHeaders.add() directly. Before
        # Tornado 6.5.3 this measured a ratio of about 30; the per-line
        # parsing costs hide some of the quadratic part at these sizes.
        def f(n):
            HTTPHeaders.parse("X: a\r\n" * n)

        assert_linear_scaling(
            f,
            10_000,
            100_000,
            max_ratio=20,
            msg="HTTPHeaders.parse() of a repeated header is not linear",
        )

    @skipNotCPython
    def test_parse_memory_budget(self):
        # Many short, distinct headers are the worst case for memory (about
        # 18 bytes per input byte as of 2026-10). The default max_header_size
        # is 64KB, so this is about as large as a server will parse.
        data = "".join(f"X{i}: b\r\n" for i in range(8_000))
        with assert_memory_budget(
            len(data), max_ratio=30, msg="HTTPHeaders.parse() uses too much memory"
        ):
            HTTPHeaders.parse(data)


class FormatTimestampTest(TestCase):
    # Make sure that all the input types are supported.
    TIMESTAMP = 1359312200.503611
    EXPECTED = "Sun, 27 Jan 2013 18:43:20 GMT"

    def check(self, value):
        self.assertEqual(format_timestamp(value), self.EXPECTED)

    def test_unix_time_float(self):
        self.check(self.TIMESTAMP)

    def test_unix_time_int(self):
        self.check(int(self.TIMESTAMP))

    def test_struct_time(self):
        self.check(time.gmtime(self.TIMESTAMP))

    def test_time_tuple(self):
        tup = tuple(time.gmtime(self.TIMESTAMP))
        self.assertEqual(9, len(tup))
        self.check(tup)

    def test_utc_naive_datetime(self):
        self.check(
            datetime.datetime.fromtimestamp(self.TIMESTAMP, datetime.UTC).replace(
                tzinfo=None
            )
        )

    def test_utc_naive_datetime_deprecated(self):
        with ignore_deprecation():
            self.check(datetime.datetime.utcfromtimestamp(self.TIMESTAMP))

    def test_utc_aware_datetime(self):
        self.check(datetime.datetime.fromtimestamp(self.TIMESTAMP, datetime.UTC))

    def test_other_aware_datetime(self):
        # Other timezones are ignored; the timezone is always printed as GMT
        self.check(
            datetime.datetime.fromtimestamp(
                self.TIMESTAMP, datetime.timezone(datetime.timedelta(hours=-4))
            )
        )


# HTTPServerRequest is mainly tested incidentally to the server itself,
# but this tests the parts of the class that can be tested in isolation.
class HTTPServerRequestTest(TestCase):
    def test_default_constructor(self):
        # All parameters are formally optional, but uri is required
        # (and has been for some time).  This test ensures that no
        # more required parameters slip in.
        with ignore_deprecation():
            HTTPServerRequest(method="GET", uri="/")
        # The new minimal construction uses the start_line parameter.
        HTTPServerRequest(start_line=RequestStartLine("GET", "/", "HTTP/1.0"))

    def test_body_is_a_byte_string(self):
        request = HTTPServerRequest(start_line=RequestStartLine("GET", "/", "HTTP/1.0"))
        self.assertIsInstance(request.body, bytes)

    def test_repr_does_not_contain_headers(self):
        request = HTTPServerRequest(
            start_line=RequestStartLine("GET", "/", "HTTP/1.0"),
            headers=HTTPHeaders({"Canary": "Coal Mine"}),
        )
        self.assertNotIn("Canary", repr(request))

    def test_query_arguments_within_limit(self):
        n = _DEFAULT_PARSE_BODY_CONFIG.urlencoded.max_arguments
        uri = "/?" + "&".join("a=%d" % i for i in range(n))
        request = HTTPServerRequest(start_line=RequestStartLine("GET", uri, "HTTP/1.0"))
        self.assertEqual(len(request.arguments["a"]), n)

    def test_max_query_arguments(self):
        # The query string is subject to the same limit on the number of
        # arguments as a urlencoded body: parsing is superlinear enough in
        # the number of fields to be worth bounding.
        n = _DEFAULT_PARSE_BODY_CONFIG.urlencoded.max_arguments + 1
        uri = "/?" + "&".join("a=%d" % i for i in range(n))
        with self.assertRaises(HTTPInputError) as cm:
            HTTPServerRequest(start_line=RequestStartLine("GET", uri, "HTTP/1.0"))
        self.assertIn("Max number of fields exceeded", str(cm.exception))


class ParseRequestStartLineTest(TestCase):
    METHOD = "GET"
    PATH = "/foo"
    VERSION = "HTTP/1.1"

    def test_parse_request_start_line(self):
        start_line = " ".join([self.METHOD, self.PATH, self.VERSION])
        parsed_start_line = parse_request_start_line(start_line)
        self.assertEqual(parsed_start_line.method, self.METHOD)
        self.assertEqual(parsed_start_line.path, self.PATH)
        self.assertEqual(parsed_start_line.version, self.VERSION)

    def test_fragment_rejected(self):
        # A fragment is never sent as part of a request target.
        for path in ["/foo#bar", "/foo?a=b#c", "#"]:
            with self.subTest(path=path):
                with self.assertRaises(HTTPInputError):
                    parse_request_start_line(f"GET {path} HTTP/1.1")


class SplitHostAndPortTest(TestCase):
    def test_split_host_and_port(self):
        self.assertEqual(split_host_and_port("example.com"), ("example.com", None))
        self.assertEqual(split_host_and_port("example.com:80"), ("example.com", 80))
        self.assertEqual(split_host_and_port("[::1]:80"), ("[::1]", 80))

    def test_non_ascii_digits(self):
        # Only ASCII digits make a port. "\u0668\u0660" is "80" in Arabic-Indic
        # digits, which int() would accept.
        self.assertEqual(
            split_host_and_port("example.com:\u0668\u0660"),
            ("example.com:\u0668\u0660", None),
        )


class URLToASCIITest(TestCase):
    def test_url_to_ascii(self):
        for url, expected in [
            # ASCII URLs are unchanged, even if they are unusual.
            ("http://example.com/a b%41?#", "http://example.com/a b%41?#"),
            ("http://caf\u00e9.example/", "http://xn--caf-dma.example/"),
            (
                "https://u\u00e9:p\u00e9@caf\u00e9.example:8080/\u00e9?\u00e9=1#\u00e9",
                "https://u%C3%A9:p%C3%A9@xn--caf-dma.example:8080/%C3%A9?%C3%A9=1#%C3%A9",
            ),
            # Empty queries and fragments are kept.
            ("http://caf\u00e9.example/?", "http://xn--caf-dma.example/?"),
            ("http://caf\u00e9.example#", "http://xn--caf-dma.example#"),
            ("http://[::1]:80/\u00e9", "http://[::1]:80/%C3%A9"),
            ("//caf\u00e9.example/x", "//xn--caf-dma.example/x"),
            ("/\u00e9", "/%C3%A9"),
            (
                "http://\uff4c\uff4f\uff43\uff41\uff4c\uff48\uff4f\uff53\uff54/",
                "http://localhost/",
            ),
        ]:
            with self.subTest(url=url):
                self.assertEqual(_url_to_ascii(url), expected)

    def test_invalid_hostname(self):
        for url in ["http://a..b\u00e9/", "http://" + "\u00e9" * 64 + ".example/"]:
            with self.subTest(url=url):
                with self.assertRaises(ValueError):
                    _url_to_ascii(url)


class ParseCookieTest(TestCase):
    # These tests copied from Django:
    # https://github.com/django/django/pull/6277/commits/da810901ada1cae9fc1f018f879f11a7fb467b28
    def test_python_cookies(self):
        """
        Test cases copied from Python's Lib/test/test_http_cookies.py
        """
        self.assertEqual(
            parse_cookie("chips=ahoy; vienna=finger"),
            {"chips": "ahoy", "vienna": "finger"},
        )
        # Here parse_cookie() differs from Python's cookie parsing in that it
        # treats all semicolons as delimiters, even within quotes.
        self.assertEqual(
            parse_cookie('keebler="E=mc2; L=\\"Loves\\"; fudge=\\012;"'),
            {"keebler": '"E=mc2', "L": '\\"Loves\\"', "fudge": "\\012", "": '"'},
        )
        # Illegal cookies that have an '=' char in an unquoted value.
        self.assertEqual(parse_cookie("keebler=E=mc2"), {"keebler": "E=mc2"})
        # Cookies with ':' character in their name.
        self.assertEqual(
            parse_cookie("key:term=value:term"), {"key:term": "value:term"}
        )
        # Cookies with '[' and ']'.
        self.assertEqual(
            parse_cookie("a=b; c=[; d=r; f=h"), {"a": "b", "c": "[", "d": "r", "f": "h"}
        )

    def test_cookie_edgecases(self):
        # Cookies that RFC6265 allows.
        self.assertEqual(
            parse_cookie("a=b; Domain=example.com"), {"a": "b", "Domain": "example.com"}
        )
        # parse_cookie() has historically kept only the last cookie with the
        # same name.
        self.assertEqual(parse_cookie("a=b; h=i; a=c"), {"a": "c", "h": "i"})

    def test_invalid_cookies(self):
        """
        Cookie strings that go against RFC6265 but browsers will send if set
        via document.cookie.
        """
        # Chunks without an equals sign appear as unnamed values per
        # https://bugzilla.mozilla.org/show_bug.cgi?id=169091
        self.assertIn(
            "django_language",
            parse_cookie("abc=def; unnamed; django_language=en").keys(),
        )
        # Even a double quote may be an unnamed value.
        self.assertEqual(parse_cookie('a=b; "; c=d'), {"a": "b", "": '"', "c": "d"})
        # Spaces in names and values, and an equals sign in values.
        self.assertEqual(
            parse_cookie("a b c=d e = f; gh=i"), {"a b c": "d e = f", "gh": "i"}
        )
        # More characters the spec forbids.
        self.assertEqual(
            parse_cookie('a   b,c<>@:/[]?{}=d  "  =e,f g'),
            {"a   b,c<>@:/[]?{}": 'd  "  =e,f g'},
        )
        # Unicode characters. The spec only allows ASCII.
        self.assertEqual(
            parse_cookie("saint=André Bessette"),
            {"saint": native_str("André Bessette")},
        )
        # Browsers don't send extra whitespace or semicolons in Cookie headers,
        # but parse_cookie() should parse whitespace the same way
        # document.cookie parses whitespace.
        self.assertEqual(
            parse_cookie("  =  b  ;  ;  =  ;   c  =  ;  "), {"": "b", "c": ""}
        )

    def test_unquote(self):
        # Copied from
        # https://github.com/python/cpython/blob/dc7a2b6522ec7af41282bc34f405bee9b306d611/Lib/test/test_http_cookies.py#L62
        cases = [
            (r'a="b=\""', 'b="'),
            (r'a="b=\\"', "b=\\"),
            (r'a="b=\="', "b=="),
            (r'a="b=\n"', "b=n"),
            (r'a="b=\042"', 'b="'),
            (r'a="b=\134"', "b=\\"),
            (r'a="b=\377"', "b=\xff"),
            (r'a="b=\400"', "b=400"),
            (r'a="b=\42"', "b=42"),
            (r'a="b=\\042"', "b=\\042"),
            (r'a="b=\\134"', "b=\\134"),
            (r'a="b=\\\""', 'b=\\"'),
            (r'a="b=\\\042"', 'b=\\"'),
            (r'a="b=\134\""', 'b=\\"'),
            (r'a="b=\134\042"', 'b=\\"'),
        ]
        for encoded, decoded in cases:
            with self.subTest(encoded):
                c = parse_cookie(encoded)
                self.assertEqual(c["a"], decoded)

    def test_unquote_large(self):
        # Adapted from
        # https://github.com/python/cpython/blob/dc7a2b6522ec7af41282bc34f405bee9b306d611/Lib/test/test_http_cookies.py#L87
        # Modified from that test because we handle semicolons differently from the stdlib.
        n = 100000
        for encoded in r"\\", r"\134":
            with self.subTest(encoded):
                data = 'a="b=' + encoded * n + '"'
                value = parse_cookie(data)["a"]
                self.assertEqual(value[:3], "b=\\")
                self.assertEqual(value[-3:], "\\\\\\")
                self.assertEqual(len(value), n + 2)

    def test_unquote_linear_performance(self):
        # Regression test for CVE-2024-7592: before Tornado 6.4.2, unquoting
        # escape sequences in a cookie value was quadratic. (Only the r"\\"
        # case reproduces it on 6.4.1; r"\134" is here for symmetry with
        # test_unquote_large.)
        #
        # 6.4.1 measures a ratio of about 100 on CPython and 60-100 on PyPy.
        # The fixed version measures about 10 on CPython, but this test
        # allocates heavily for each byte of input, and PyPy's ratio depends
        # on how that compares to its nursery and CPU caches: as of 2026-10
        # it measures 11-24 depending on PYPY_GC_NURSERY, so the usual limit
        # of 20 is too tight.
        for encoded in r"\\", r"\134":
            with self.subTest(encoded):
                assert_linear_scaling(
                    lambda n: parse_cookie('a="b=' + encoded * n + '"'),
                    1_000,
                    10_000,
                    max_ratio=40,
                    msg="Cookie unquoting is not linear",
                )

    @skipNotCPython
    def test_parse_memory_budget(self):
        # Many short cookies with empty values are the worst case for memory
        # (about 20 bytes per input byte as of 2026-10). Cookies arrive in a
        # header, so the default max_header_size of 64KB bounds the input.
        data = "".join(f"{i}=;" for i in range(10_000))
        with assert_memory_budget(
            len(data), max_ratio=30, msg="parse_cookie() uses too much memory"
        ):
            parse_cookie(data)
