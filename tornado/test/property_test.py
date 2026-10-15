"""Property-based tests using Hypothesis.

These tests generate many inputs and check invariants (round-trips, agreement with a
simple model, or "fails only in the documented way") rather than specific examples.
They require the ``hypothesis`` package, which is installed in the ``-full`` tox
configurations; without it, they are skipped.

When a test fails, Hypothesis prints the smallest failing input it found along with a
``@reproduce_failure`` decorator that can be pasted onto the test to replay it. Once
the bug is fixed, add that input as a regular example-based test (or an ``@example``
here) so it stays covered regardless of what Hypothesis generates.
"""

import gzip
import os
import unittest
import unittest.mock
import zlib

from tornado.test.util import TestCase

try:
    import hypothesis
    from hypothesis import given, settings, strategies as st
except ImportError:
    # Stand-ins so that this module still imports without hypothesis and its
    # tests are reported as skipped. Strategies are built at import time, so
    # `st` and `settings` must accept any attribute access, call or subscript.
    hypothesis = settings = st = unittest.mock.MagicMock()  # type: ignore

    def given(*args, **kwargs):  # type: ignore
        return unittest.skip("hypothesis module not present")


from tornado.escape import (
    parse_qs_bytes,
    url_escape,
    url_unescape,
    xhtml_escape,
    xhtml_unescape,
)
from tornado.httputil import (
    HTTPFile,
    HTTPHeaders,
    HTTPInputError,
    _ABNF,
    parse_body_arguments,
    parse_cookie,
    parse_request_start_line,
    parse_response_start_line,
)
from tornado.util import GzipDecompressor, _websocket_mask_python
from tornado.websocket import (
    _DecompressTooLargeError,
    _PerMessageDeflateCompressor,
    _PerMessageDeflateDecompressor,
)

try:
    from tornado import speedups
except ImportError:
    speedups = None  # type: ignore

# The default per-example deadline (200ms) is too tight for CI machines and
# coverage runs; these tests are about correctness, not speed.
settings.register_profile("tornado", deadline=None, print_blob=True)
# For runs that only need these tests to execute, not to search hard for
# bugs (the coverage env in tox.ini).
settings.register_profile(
    "tornado-quick", parent=settings.get_profile("tornado"), max_examples=10
)
settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "tornado"))

# Strategies for syntactically valid HTTP elements, built from the same ABNF
# patterns httputil uses to validate them.
header_names = st.from_regex(_ABNF.field_name, fullmatch=True)
header_values = st.from_regex(_ABNF.field_value, fullmatch=True)
tokens = st.from_regex(_ABNF.token, fullmatch=True)
request_targets = st.from_regex(_ABNF.request_target, fullmatch=True)
http1_versions = st.sampled_from(["HTTP/1.0", "HTTP/1.1"])
reason_phrases = st.from_regex(_ABNF.reason_phrase, fullmatch=True)


def case_variants(name: str) -> st.SearchStrategy[str]:
    """Strategy producing ``name`` with each letter in random case."""
    return st.lists(st.booleans(), min_size=len(name), max_size=len(name)).map(
        lambda flips: "".join(
            c.upper() if f else c.lower() for c, f in zip(name, flips)
        )
    )


# Random names rarely collide, so mix in a few names in several cases to
# exercise repeated and case-insensitive keys.
op_names = st.one_of(
    header_names,
    st.sampled_from(["set-cookie", "Set-Cookie", "SET-COOKIE", "x-a", "X-A"]),
)

# Operations applied to both an HTTPHeaders and a simple model of it.
header_ops = st.lists(
    st.one_of(
        st.tuples(st.just("add"), op_names, header_values),
        st.tuples(st.just("set"), op_names, header_values),
        st.tuples(st.just("del"), op_names),
    ),
    max_size=20,
)


class HTTPHeadersPropertyTest(TestCase):
    """HTTPHeaders must behave like a case-insensitive ordered multidict."""

    def apply(self, ops):
        headers = HTTPHeaders()
        # Model: lowercased name -> list of values, in first-insertion order.
        model: dict[str, list[str]] = {}
        for op in ops:
            if op[0] == "add":
                _, name, value = op
                headers.add(name, value)
                model.setdefault(name.lower(), []).append(value)
            elif op[0] == "set":
                _, name, value = op
                headers[name] = value
                # Replaces all values but keeps the name's position.
                model[name.lower()] = [value]
            else:
                _, name = op
                if name.lower() in model:
                    del headers[name]
                    del model[name.lower()]
                else:
                    with self.assertRaises(KeyError):
                        del headers[name]
        return headers, model

    def check(self, headers, model):
        self.assertEqual(len(headers), len(model))
        self.assertEqual([k.lower() for k in headers], list(model))
        self.assertEqual(
            [(k.lower(), v) for k, v in headers.get_all()],
            [(k, v) for k, values in model.items() for v in values],
        )
        for name, values in model.items():
            self.assertIn(name, headers)
            self.assertIn(name.upper(), headers)
            self.assertEqual(headers.get_list(name.upper()), values)
            self.assertEqual(headers[name.upper()], ",".join(values))

    @given(header_ops)
    def test_model(self, ops):
        headers, model = self.apply(ops)
        self.check(headers, model)

    @given(header_ops, st.data())
    def test_lookup_any_case(self, ops, data):
        headers, model = self.apply(ops)
        for name in model:
            variant = data.draw(case_variants(name))
            self.assertIn(variant, headers)
            self.assertEqual(headers.get_list(variant), model[name])
            self.assertEqual(headers.get(variant), ",".join(model[name]))

    @given(header_names, header_ops)
    def test_absent_names(self, name, ops):
        headers, model = self.apply(ops)
        if name.lower() not in model:
            self.assertNotIn(name, headers)
            self.assertEqual(headers.get_list(name), [])
            self.assertIsNone(headers.get(name))
            with self.assertRaises(KeyError):
                headers[name]

    @given(header_ops)
    def test_copy_is_independent(self, ops):
        headers, model = self.apply(ops)
        copied = headers.copy()
        self.check(copied, model)
        copied.add("X-Extra", "1")
        self.check(headers, model)

    @given(header_ops)
    def test_str_parse_round_trip(self, ops):
        headers, model = self.apply(ops)
        parsed = HTTPHeaders.parse(str(headers))
        self.check(parsed, model)
        # CRLF line endings, as used on the wire, parse the same way.
        parsed = HTTPHeaders.parse(str(headers).replace("\n", "\r\n"))
        self.check(parsed, model)

    @given(st.text())
    def test_parse_arbitrary_text(self, text):
        # Malformed input must be reported as HTTPInputError and nothing else.
        try:
            headers = HTTPHeaders.parse(text)
        except HTTPInputError:
            return
        for name, value in headers.get_all():
            self.assertTrue(_ABNF.field_name.fullmatch(name), name)
            self.assertTrue(_ABNF.field_value.fullmatch(value), value)


class StartLinePropertyTest(TestCase):
    @given(tokens, request_targets, http1_versions)
    def test_request_line_round_trip(self, method, target, version):
        line = f"{method} {target} {version}"
        self.assertEqual(
            tuple(parse_request_start_line(line)), (method, target, version)
        )

    @given(st.text())
    def test_request_line_arbitrary_text(self, line):
        try:
            parsed = parse_request_start_line(line)
        except HTTPInputError:
            return
        self.assertEqual(" ".join(parsed), line)

    @given(
        http1_versions,
        st.integers(min_value=0, max_value=999),
        st.one_of(st.just(""), reason_phrases),
    )
    def test_response_line_round_trip(self, version, code, reason):
        line = f"{version} {code:03d} {reason}"
        parsed = parse_response_start_line(line)
        self.assertEqual(parsed.version, version)
        self.assertEqual(parsed.code, code)
        self.assertEqual(parsed.reason or "", reason)

    @given(st.text())
    def test_response_line_arbitrary_text(self, line):
        try:
            parsed = parse_response_start_line(line)
        except HTTPInputError:
            return
        self.assertEqual(
            f"{parsed.version} {parsed.code:03d} {parsed.reason or ''}", line
        )


class EscapePropertyTest(TestCase):
    @given(st.text(), st.booleans())
    def test_url_escape_round_trip(self, s, plus):
        escaped = url_escape(s, plus=plus)
        self.assertTrue(escaped.isascii())
        self.assertEqual(url_unescape(escaped, plus=plus), s)

    @given(st.binary(), st.booleans())
    def test_url_escape_bytes_round_trip(self, b, plus):
        self.assertEqual(url_unescape(url_escape(b, plus=plus), None, plus=plus), b)

    @given(st.text())
    def test_xhtml_escape_round_trip(self, s):
        escaped = xhtml_escape(s)
        for c in "<>\"'":
            self.assertNotIn(c, escaped)
        self.assertEqual(xhtml_unescape(escaped), s)

    @given(st.lists(st.tuples(st.text(min_size=1), st.text()), max_size=10))
    def test_parse_qs_bytes_round_trip(self, pairs):
        qs = "&".join(f"{url_escape(k)}={url_escape(v)}" for k, v in pairs)
        expected: dict[str, list[bytes]] = {}
        for k, v in pairs:
            # Keys are decoded as latin1 and values are left as bytes.
            expected.setdefault(k.encode("utf-8").decode("latin1"), []).append(
                v.encode("utf-8")
            )
        self.assertEqual(parse_qs_bytes(qs, keep_blank_values=True), expected)


# Cookie names and values that browsers send unquoted: no whitespace at
# the ends, and no separators.
cookie_names = st.from_regex(r"[!#$%&'*+\-.^_`|~0-9A-Za-z]+", fullmatch=True)
cookie_values = st.from_regex(
    r"[!#$%&'()*+\-./0-9:<>?@A-Z\[\]^_`a-z{|}~]*", fullmatch=True
)


class CookiePropertyTest(TestCase):
    @given(st.lists(st.tuples(cookie_names, cookie_values), max_size=10))
    def test_parse_cookie_round_trip(self, pairs):
        header = "; ".join(f"{k}={v}" for k, v in pairs)
        # Later values win, as in browsers.
        self.assertEqual(parse_cookie(header), dict(pairs))

    @given(st.text())
    def test_parse_cookie_arbitrary_text(self, header):
        # Never raises, and always returns str keys and values.
        for k, v in parse_cookie(header).items():
            self.assertIsInstance(k, str)
            self.assertIsInstance(v, str)


# Field names and filenames that can appear in a quoted Content-Disposition
# parameter without escaping.
form_names = st.text(
    st.characters(blacklist_categories=("Cc", "Cs"), blacklist_characters='"\\;'),
    min_size=1,
).filter(lambda s: s == s.strip())
boundaries = st.from_regex(
    r"[0-9A-Za-z'()+_,\-./:=?]{1,69}[0-9A-Za-z'()+_,\-./=?]", fullmatch=True
)
form_parts = st.lists(
    st.tuples(form_names, st.binary(), st.one_of(st.none(), form_names)),
    max_size=10,
)


def encode_multipart(boundary: str, parts) -> bytes:
    body = []
    for name, value, filename in parts:
        disposition = f'form-data; name="{name}"'
        if filename is not None:
            disposition += f'; filename="{filename}"'
        body.append(f"--{boundary}\r\n".encode())
        body.append(f"Content-Disposition: {disposition}\r\n\r\n".encode("utf-8"))
        body.append(value + b"\r\n")
    body.append(f"--{boundary}--\r\n".encode())
    return b"".join(body)


class MultipartPropertyTest(TestCase):
    @given(boundaries, form_parts)
    def test_multipart_round_trip(self, boundary, parts):
        delimiter = b"--" + boundary.encode()
        hypothesis.assume(not any(delimiter in value for _, value, _ in parts))
        body = encode_multipart(boundary, parts)
        arguments: dict[str, list[bytes]] = {}
        files: dict[str, list[HTTPFile]] = {}
        parse_body_arguments(
            f"multipart/form-data; boundary={boundary}", body, arguments, files
        )
        expected_args: dict[str, list[bytes]] = {}
        expected_files: dict[str, list[tuple[str, bytes]]] = {}
        for name, value, filename in parts:
            if filename:
                expected_files.setdefault(name, []).append((filename, value))
            else:
                expected_args.setdefault(name, []).append(value)
        self.assertEqual(arguments, expected_args)
        self.assertEqual(
            {k: [(f.filename, f.body) for f in v] for k, v in files.items()},
            expected_files,
        )

    @given(boundaries, st.binary())
    def test_multipart_arbitrary_body(self, boundary, body):
        # Malformed bodies must be reported as HTTPInputError and nothing else.
        try:
            parse_body_arguments(
                f"multipart/form-data; boundary={boundary}", body, {}, {}
            )
        except HTTPInputError:
            pass


class WebSocketPropertyTest(TestCase):
    @given(st.binary(min_size=4, max_size=4), st.binary())
    def test_mask_is_involution(self, mask, data):
        masked = _websocket_mask_python(mask, data)
        self.assertEqual(len(masked), len(data))
        self.assertEqual(_websocket_mask_python(mask, masked), data)

    @unittest.skipIf(speedups is None, "tornado.speedups module not present")
    @given(st.binary(min_size=4, max_size=4), st.binary(max_size=1000))
    def test_mask_c_matches_python(self, mask, data):
        self.assertEqual(
            speedups.websocket_mask(mask, data), _websocket_mask_python(mask, data)
        )

    @given(
        st.booleans(),
        st.integers(min_value=9, max_value=zlib.MAX_WBITS),
        st.lists(st.binary(max_size=2000), max_size=5),
    )
    def test_deflate_round_trip(self, persistent, wbits, messages):
        compressor = _PerMessageDeflateCompressor(persistent, wbits)
        decompressor = _PerMessageDeflateDecompressor(
            persistent, wbits, max_message_size=1 << 20
        )
        for message in messages:
            self.assertEqual(
                decompressor.decompress(compressor.compress(message)), message
            )

    @given(
        st.binary(max_size=2000),
        st.integers(min_value=1, max_value=2000),
    )
    def test_deflate_max_message_size(self, message, max_size):
        compressed = _PerMessageDeflateCompressor(False, None).compress(message)
        decompressor = _PerMessageDeflateDecompressor(False, None, max_size)
        if len(message) <= max_size:
            self.assertEqual(decompressor.decompress(compressed), message)
        else:
            with self.assertRaises(_DecompressTooLargeError):
                decompressor.decompress(compressed)


# A gzip stream: zero or more members, each compressed separately.
gzip_members = st.lists(
    st.tuples(st.binary(max_size=5000), st.integers(min_value=0, max_value=9)),
    max_size=4,
).map(
    lambda members: [
        (data, gzip.compress(data, compresslevel=level, mtime=0))
        for data, level in members
    ]
)


def split_at(data: bytes, points: list[int]) -> list[bytes]:
    """Split ``data`` into chunks at the given offsets."""
    bounds = [0] + sorted(points) + [len(data)]
    return [data[a:b] for a, b in zip(bounds, bounds[1:])]


class GzipDecompressorPropertyTest(TestCase):
    def feed(self, chunks: list[bytes], max_length: int) -> bytes:
        """Decompress ``chunks`` the way http1connection does.

        Checks the documented interface along the way: no call returns more
        than ``max_length``, and every call either returns output or
        consumes input.
        """
        decompressor = GzipDecompressor()
        output = []
        for data in chunks:
            while data:
                result = decompressor.decompress(data, max_length)
                self.assertLessEqual(len(result), max_length)
                tail = decompressor.unconsumed_tail
                self.assertTrue(result or len(tail) < len(data))
                output.append(result)
                data = tail
        self.assertEqual(decompressor.flush(), b"")
        return b"".join(output)

    @given(gzip_members, st.integers(min_value=1, max_value=4096), st.data())
    def test_round_trip(self, members, max_length, data):
        stream = b"".join(compressed for _, compressed in members)
        points = data.draw(st.lists(st.integers(0, len(stream)), max_size=5))
        self.assertEqual(
            self.feed(split_at(stream, points), max_length),
            b"".join(original for original, _ in members),
        )

    @given(gzip_members, st.integers(min_value=1, max_value=4096), st.data())
    def test_truncated(self, members, max_length, data):
        stream = b"".join(compressed for _, compressed in members)
        hypothesis.assume(stream)
        cut = data.draw(st.integers(0, len(stream) - 1))
        # Cutting the stream between members leaves a valid stream of the
        # members before the cut; cutting anywhere else is an error.
        complete = []
        offset = 0
        for original, compressed in members:
            offset += len(compressed)
            if offset > cut:
                break
            complete.append((original, offset))
        if cut == 0 or (complete and complete[-1][1] == cut):
            self.assertEqual(
                self.feed([stream[:cut]], max_length),
                b"".join(original for original, _ in complete),
            )
        else:
            with self.assertRaises(zlib.error):
                self.feed([stream[:cut]], max_length)

    @given(gzip_members, st.binary(min_size=1), st.integers(1, 4096))
    def test_trailing_garbage(self, members, garbage, max_length):
        try:
            gzip.decompress(garbage)
        except Exception:
            pass
        else:
            # The "garbage" is itself a valid gzip stream.
            hypothesis.assume(False)
        stream = b"".join(compressed for _, compressed in members)
        with self.assertRaises(zlib.error):
            self.feed([stream + garbage], max_length)

    @given(st.binary(), st.integers(1, 4096))
    def test_arbitrary_input(self, data, max_length):
        # Invalid input must be reported as zlib.error and nothing else.
        try:
            self.feed([data], max_length)
        except zlib.error:
            pass


if __name__ == "__main__":
    unittest.main()
