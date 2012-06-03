#!/usr/bin/env python
#
# Copyright 2012 Alek Storm
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

"""Data structures representing SPDY frames, serialization/deserialization
routines, and miscellaneous utilities.
"""

from __future__ import absolute_import, division, with_statement

from tornado.escape import to_unicode


class SPDYParseException(Exception):
    pass


class SPDYStreamParseException(SPDYParseException):
    def __init__(self, stream_id, msg):
        SPDYParseException.__init__(self, stream_id, msg)
        self.stream_id = stream_id


def to_spdy_headers(headers):
    spdy_headers = {}
    for key, values in headers:
        for value in to_unicode(values).split(','):
            spdy_headers.setdefault(key.lower(), []).append(value.strip())
    return spdy_headers
