#!/usr/bin/env python
#
# Copyright 2012 Facebook
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
from __future__ import absolute_import, division, with_statement

import logging

# Per-request logging for Tornado's HTTP servers (and potentially other servers
# in the future)
access_log = logging.getLogger("tornado.access")

# Logging of errors from application code (i.e. uncaught exceptions from
# callbacks
app_log = logging.getLogger("tornado.application")

# General logging, i.e. everything else
gen_log = logging.getLogger("tornado.general")
