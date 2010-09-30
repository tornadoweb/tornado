#!/usr/bin/env python
#
# Copyright 2009 Facebook
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

"""Escaping/unescaping methods for HTML, JSON, URLs, and others."""

import htmlentitydefs
import re
import xml.sax.saxutils
import urllib

# json module is in the standard library as of python 2.6; fall back to
# simplejson if present for older versions.
try:
    import json
    assert hasattr(json, "loads") and hasattr(json, "dumps")
    _json_decode = json.loads
    _json_encode = json.dumps
except:
    try:
        import simplejson
        _json_decode = lambda s: simplejson.loads(_unicode(s))
        _json_encode = lambda v: simplejson.dumps(v)
    except ImportError:
        try:
            # For Google AppEngine
            from django.utils import simplejson
            _json_decode = lambda s: simplejson.loads(_unicode(s))
            _json_encode = lambda v: simplejson.dumps(v)
        except ImportError:
            def _json_decode(s):
                raise NotImplementedError(
                    "A JSON parser is required, e.g., simplejson at "
                    "http://pypi.python.org/pypi/simplejson/")
            _json_encode = _json_decode


def xhtml_escape(value):
    """Escapes a string so it is valid within XML or XHTML."""
    return xml.sax.saxutils.escape(value, {'"': "&quot;"})


def xhtml_unescape(value):
    """Un-escapes an XML-escaped string."""
    return re.sub(r"&(#?)(\w+?);", _convert_entity, _unicode(value))


def json_encode(value):
    """JSON-encodes the given Python object."""
    # JSON permits but does not require forward slashes to be escaped.
    # This is useful when json data is emitted in a <script> tag
    # in HTML, as it prevents </script> tags from prematurely terminating
    # the javscript.  Some json libraries do this escaping by default,
    # although python's standard library does not, so we do it here.
    # http://stackoverflow.com/questions/1580647/json-why-are-forward-slashes-escaped
    return _json_encode(value).replace("</", "<\\/")


def json_decode(value):
    """Returns Python objects for the given JSON string."""
    return _json_decode(value)


def squeeze(value):
    """Replace all sequences of whitespace chars with a single space."""
    return re.sub(r"[\x00-\x20]+", " ", value).strip()


def url_escape(value):
    """Returns a valid URL-encoded version of the given value."""
    return urllib.quote_plus(utf8(value))


def url_unescape(value):
    """Decodes the given value from a URL."""
    return _unicode(urllib.unquote_plus(value))


def utf8(value):
    if isinstance(value, unicode):
        return value.encode("utf-8")
    assert isinstance(value, str)
    return value


# Regex from http://daringfireball.net/2010/07/improved_regex_for_matching_urls
# Modified to capture protocol and to avoid HTML character entities other than &amp;
_URL_RE = re.compile(ur"""(?i)\b((?:([a-z][\w-]+):(?:(/{1,3})|[a-z0-9%])|www\d{0,3}[.]|[a-z0-9.\-]+[.][a-z]{2,4}/)(?:[^\s()<>&]+|&amp;|\(([^\s()<>&]+|(\([^\s()<>&]+\)))*\))+(?:\(([^\s()<>&]+|(\([^\s()<>&]+\)))*\)|[^\s`!()\[\]{};:'".,<>?\xab\xbb\u201c\u201d\u2018\u2019&]))""")


def linkify(text, shorten=False, extra_params="",
            require_protocol=False, permitted_protocols=["http", "https"]):
    """Converts plain text into HTML with links.

    For example: linkify("Hello http://tornadoweb.org!") would return
    Hello <a href="http://tornadoweb.org">http://tornadoweb.org</a>!

    Parameters:
    shorten: Long urls will be shortened for display.
    extra_params: Extra text to include in the link tag,
        e.g. linkify(text, extra_params='rel="nofollow" class="external"')
    require_protocol: Only linkify urls which include a protocol. If this is
        False, urls such as www.facebook.com will also be linkified.
    permitted_protocols: List (or set) of protocols which should be linkified,
        e.g. linkify(text, permitted_protocols=["http", "ftp", "mailto"]).
        It is very unsafe to include protocols such as "javascript".
    """
    if extra_params:
        extra_params = " " + extra_params.strip()

    def make_link(m):
        url = m.group(1)
        proto = m.group(2)
        if require_protocol and not proto:
            return url  # not protocol, no linkify

        if proto and proto not in permitted_protocols:
            return url  # bad protocol, no linkify

        href = m.group(1)
        if not proto:
            href = "http://" + href   # no proto specified, use http

        params = extra_params

        # clip long urls. max_len is just an approximation
        max_len = 30
        if shorten and len(url) > max_len:
            before_clip = url
            if proto:
                proto_len = len(proto) + 1 + len(m.group(3) or "")  # +1 for :
            else:
                proto_len = 0

            parts = url[proto_len:].split("/")
            if len(parts) > 1:
                # Grab the whole host part plus the first bit of the path
                # The path is usually not that interesting once shortened
                # (no more slug, etc), so it really just provides a little
                # extra indication of shortening.
                url = url[:proto_len] + parts[0] + "/" + \
                        parts[1][:8].split('?')[0].split('.')[0]

            if len(url) > max_len * 1.5:  # still too long
                url = url[:max_len]

            if url != before_clip:
                amp = url.rfind('&')
                # avoid splitting html char entities
                if amp > max_len - 5:
                    url = url[:amp]
                url += "..."

                if len(url) >= len(before_clip):
                    url = before_clip
                else:
                    # full url is visible on mouse-over (for those who don't
                    # have a status bar, such as Safari by default)
                    params += ' title="%s"' % href

        return u'<a href="%s"%s>%s</a>' % (href, params, url)

    # First HTML-escape so that our strings are all safe.
    # The regex is modified to avoid character entites other than &amp; so
    # that we won't pick up &quot;, etc.
    text = _unicode(xhtml_escape(text))
    return _URL_RE.sub(make_link, text)


def _unicode(value):
    if isinstance(value, str):
        return value.decode("utf-8")
    assert isinstance(value, unicode)
    return value


def _convert_entity(m):
    if m.group(1) == "#":
        try:
            return unichr(int(m.group(2)))
        except ValueError:
            return "&#%s;" % m.group(2)
    try:
        return _HTML_UNICODE_MAP[m.group(2)]
    except KeyError:
        return "&%s;" % m.group(2)


def _build_unicode_map():
    unicode_map = {}
    for name, value in htmlentitydefs.name2codepoint.iteritems():
        unicode_map[name] = unichr(value)
    return unicode_map

_HTML_UNICODE_MAP = _build_unicode_map()
