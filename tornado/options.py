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

"""A command line parsing module that lets modules define their own options.

Each module defines its own options, e.g.::

    from tornado.options import define, options

    define("mysql_host", default="127.0.0.1:3306", help="Main user DB")
    define("memcache_hosts", default="127.0.0.1:11011", multiple=True,
           help="Main user memcache servers")

    def connect():
        db = database.Connection(options.mysql_host)
        ...

The main() method of your application does not need to be aware of all of
the options used throughout your program; they are all automatically loaded
when the modules are loaded. Your main() method can parse the command line
or parse a config file with::

    import tornado.options
    tornado.options.parse_config_file("/etc/server.conf")
    tornado.options.parse_command_line()

Command line formats are what you would expect ("--myoption=myvalue").
Config files are just Python files. Global names become options, e.g.::

    myoption = "myvalue"
    myotheroption = "myothervalue"

We support datetimes, timedeltas, ints, and floats (just pass a 'type'
kwarg to define). We also accept multi-value options. See the documentation
for define() below.
"""

import datetime
import logging
import logging.handlers
import re
import sys
import time

from tornado.escape import _unicode

# For pretty log messages, if available
try:
    import curses
except ImportError:
    curses = None


def define(name, default=None, type=None, help=None, metavar=None,
           multiple=False, group=None):
    """Defines a new command line option.

    If type is given (one of str, float, int, datetime, or timedelta)
    or can be inferred from the default, we parse the command line
    arguments based on the given type. If multiple is True, we accept
    comma-separated values, and the option value is always a list.

    For multi-value integers, we also accept the syntax x:y, which
    turns into range(x, y) - very useful for long integer ranges.

    help and metavar are used to construct the automatically generated
    command line help string. The help message is formatted like::

       --name=METAVAR      help string

    group is used to group the defined options in logical groups. By default,
    command line options are grouped by the defined file.

    Command line option names must be unique globally. They can be parsed
    from the command line with parse_command_line() or parsed from a
    config file with parse_config_file.
    """
    if name in options:
        raise Error("Option %r already defined in %s", name,
                    options[name].file_name)
    frame = sys._getframe(0)
    options_file = frame.f_code.co_filename
    file_name = frame.f_back.f_code.co_filename
    if file_name == options_file: file_name = ""
    if type is None:
        if not multiple and default is not None:
            type = default.__class__
        else:
            type = str
    if group:
        group_name = group
    else:
        group_name = file_name
    options[name] = _Option(name, file_name=file_name, default=default,
                            type=type, help=help, metavar=metavar,
                            multiple=multiple, group_name=group_name)


def parse_command_line(args=None):
    """Parses all options given on the command line.

    We return all command line arguments that are not options as a list.
    """
    if args is None: args = sys.argv
    remaining = []
    for i in xrange(1, len(args)):
        # All things after the last option are command line arguments
        if not args[i].startswith("-"):
            remaining = args[i:]
            break
        if args[i] == "--":
            remaining = args[i+1:]
            break
        arg = args[i].lstrip("-")
        name, equals, value = arg.partition("=")
        name = name.replace('-', '_')
        if not name in options:
            print_help()
            raise Error('Unrecognized command line option: %r' % name)
        option = options[name]
        if not equals:
            if option.type == bool:
                value = "true"
            else:
                raise Error('Option %r requires a value' % name)
        option.parse(value)
    if options.help:
        print_help()
        sys.exit(0)

    # Set up log level and pretty console logging by default
    if options.logging != 'none':
        logging.getLogger().setLevel(getattr(logging, options.logging.upper()))
        enable_pretty_logging()

    return remaining


def parse_config_file(path):
    """Parses and loads the Python config file at the given path."""
    config = {}
    execfile(path, config, config)
    for name in config:
        if name in options:
            options[name].set(config[name])


def print_help(file=sys.stdout):
    """Prints all the command line options to stdout."""
    print >> file, "Usage: %s [OPTIONS]" % sys.argv[0]
    print >> file, ""
    print >> file, "Options:"
    by_group = {}
    for option in options.itervalues():
        by_group.setdefault(option.group_name, []).append(option)

    for filename, o in sorted(by_group.items()):
        if filename: print >> file, filename
        o.sort(key=lambda option: option.name)
        for option in o:
            prefix = option.name
            if option.metavar:
                prefix += "=" + option.metavar
            print >> file, "  --%-30s %s" % (prefix, option.help or "")
    print >> file


class _Options(dict):
    """Our global program options, an dictionary with object-like access."""
    @classmethod
    def instance(cls):
        if not hasattr(cls, "_instance"):
            cls._instance = cls()
        return cls._instance

    def __getattr__(self, name):
        if isinstance(self.get(name), _Option):
            return self[name].value()
        raise AttributeError("Unrecognized option %r" % name)


class _Option(object):
    def __init__(self, name, default=None, type=str, help=None, metavar=None,
                 multiple=False, file_name=None, group_name=None):
        if default is None and multiple:
            default = []
        self.name = name
        self.type = type
        self.help = help
        self.metavar = metavar
        self.multiple = multiple
        self.file_name = file_name
        self.group_name = group_name
        self.default = default
        self._value = None

    def value(self):
        return self.default if self._value is None else self._value

    def parse(self, value):
        _parse = {
            datetime.datetime: self._parse_datetime,
            datetime.timedelta: self._parse_timedelta,
            bool: self._parse_bool,
            str: self._parse_string,
        }.get(self.type, self.type)
        if self.multiple:
            if self._value is None:
                self._value = []
            for part in value.split(","):
                if self.type in (int, long):
                    # allow ranges of the form X:Y (inclusive at both ends)
                    lo, _, hi = part.partition(":")
                    lo = _parse(lo)
                    hi = _parse(hi) if hi else lo
                    self._value.extend(range(lo, hi+1))
                else:
                    self._value.append(_parse(part))
        else:
            self._value = _parse(value)
        return self.value()

    def set(self, value):
        if self.multiple:
            if not isinstance(value, list):
                raise Error("Option %r is required to be a list of %s" %
                            (self.name, self.type.__name__))
            for item in value:
                if item != None and not isinstance(item, self.type):
                    raise Error("Option %r is required to be a list of %s" %
                                (self.name, self.type.__name__))
        else:
            if value != None and not isinstance(value, self.type):
                raise Error("Option %r is required to be a %s" %
                            (self.name, self.type.__name__))
        self._value = value

    # Supported date/time formats in our options
    _DATETIME_FORMATS = [
        "%a %b %d %H:%M:%S %Y",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%dT%H:%M",
        "%Y%m%d %H:%M:%S",
        "%Y%m%d %H:%M",
        "%Y-%m-%d",
        "%Y%m%d",
        "%H:%M:%S",
        "%H:%M",
    ]

    def _parse_datetime(self, value):
        for format in self._DATETIME_FORMATS:
            try:
                return datetime.datetime.strptime(value, format)
            except ValueError:
                pass
        raise Error('Unrecognized date/time format: %r' % value)

    _TIMEDELTA_ABBREVS = [
        ('hours', ['h']),
        ('minutes', ['m', 'min']),
        ('seconds', ['s', 'sec']),
        ('milliseconds', ['ms']),
        ('microseconds', ['us']),
        ('days', ['d']),
        ('weeks', ['w']),
    ]

    _TIMEDELTA_ABBREV_DICT = dict(
        (abbrev, full) for full, abbrevs in _TIMEDELTA_ABBREVS
        for abbrev in abbrevs)

    _FLOAT_PATTERN = r'[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?'

    _TIMEDELTA_PATTERN = re.compile(
        r'\s*(%s)\s*(\w*)\s*' % _FLOAT_PATTERN, re.IGNORECASE)

    def _parse_timedelta(self, value):
        try:
            sum = datetime.timedelta()
            start = 0
            while start < len(value):
                m = self._TIMEDELTA_PATTERN.match(value, start)
                if not m:
                    raise Exception()
                num = float(m.group(1))
                units = m.group(2) or 'seconds'
                units = self._TIMEDELTA_ABBREV_DICT.get(units, units)
                sum += datetime.timedelta(**{units: num})
                start = m.end()
            return sum
        except Exception:
            raise

    def _parse_bool(self, value):
        return value.lower() not in ("false", "0", "f")

    def _parse_string(self, value):
        return _unicode(value)


class Error(Exception):
    """Exception raised by errors in the options module."""
    pass


def enable_pretty_logging():
    """Turns on formatted logging output as configured.
    
    This is called automatically by `parse_command_line`.
    """
    root_logger = logging.getLogger()
    if options.log_file_prefix:
        channel = logging.handlers.RotatingFileHandler(
            filename=options.log_file_prefix,
            maxBytes=options.log_file_max_size,
            backupCount=options.log_file_num_backups)
        channel.setFormatter(_LogFormatter(color=False))
        root_logger.addHandler(channel)

    if (options.log_to_stderr or
        (options.log_to_stderr is None and not root_logger.handlers)):
        # Set up color if we are in a tty and curses is installed
        color = False
        if curses and sys.stderr.isatty():
            try:
                curses.setupterm()
                if curses.tigetnum("colors") > 0:
                    color = True
            except Exception:
                pass
        channel = logging.StreamHandler()
        channel.setFormatter(_LogFormatter(color=color))
        root_logger.addHandler(channel)



class _LogFormatter(logging.Formatter):
    def __init__(self, color, *args, **kwargs):
        logging.Formatter.__init__(self, *args, **kwargs)
        self._color = color
        if color:
            # The curses module has some str/bytes confusion in python3.
            # Most methods return bytes, but only accept strings.
            # The explict calls to unicode() below are harmless in python2,
            # but will do the right conversion in python3.
            fg_color = unicode(curses.tigetstr("setaf") or 
                               curses.tigetstr("setf") or "", "ascii")
            self._colors = {
                logging.DEBUG: unicode(curses.tparm(fg_color, 4), # Blue
                                       "ascii"),
                logging.INFO: unicode(curses.tparm(fg_color, 2), # Green
                                      "ascii"),
                logging.WARNING: unicode(curses.tparm(fg_color, 3), # Yellow
                                         "ascii"),
                logging.ERROR: unicode(curses.tparm(fg_color, 1), # Red
                                       "ascii"),
            }
            self._normal = unicode(curses.tigetstr("sgr0"), "ascii")

    def format(self, record):
        try:
            record.message = record.getMessage()
        except Exception, e:
            record.message = "Bad message (%r): %r" % (e, record.__dict__)
        record.asctime = time.strftime(
            "%y%m%d %H:%M:%S", self.converter(record.created))
        prefix = '[%(levelname)1.1s %(asctime)s %(module)s:%(lineno)d]' % \
            record.__dict__
        if self._color:
            prefix = (self._colors.get(record.levelno, self._normal) +
                      prefix + self._normal)
        formatted = prefix + " " + record.message
        if record.exc_info:
            if not record.exc_text:
                record.exc_text = self.formatException(record.exc_info)
        if record.exc_text:
            formatted = formatted.rstrip() + "\n" + record.exc_text
        return formatted.replace("\n", "\n    ")


options = _Options.instance()


# Default options
define("help", type=bool, help="show this help information")
define("logging", default="info",
       help=("Set the Python log level. If 'none', tornado won't touch the "
             "logging configuration."),
       metavar="info|warning|error|none")
define("log_to_stderr", type=bool, default=None,
       help=("Send log output to stderr (colorized if possible). "
             "By default use stderr if --log_file_prefix is not set and "
             "no other logging is configured."))
define("log_file_prefix", type=str, default=None, metavar="PATH",
       help=("Path prefix for log files. "
             "Note that if you are running multiple tornado processes, "
             "log_file_prefix must be different for each of them (e.g. "
             "include the port number)"))
define("log_file_max_size", type=int, default=100 * 1000 * 1000,
       help="max size of log files before rollover")
define("log_file_num_backups", type=int, default=10,
       help="number of log files to keep")
