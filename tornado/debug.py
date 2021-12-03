import os.path
import re
import sys
import traceback
from pprint import pformat
import tornado

from tornado import template


SENSITIVE_SETTINGS_RE = re.compile(
    'api|key|pass|salt|secret|signature|token',
    flags=re.IGNORECASE
)


class ExceptionReporter:
    def __init__(self, exc_info, handler):
        self.exc_type = exc_info[0]
        self.exc_value = exc_info[1]
        self.exc_tb = exc_info[2]
        self.handler = handler

    def get_response(self):
        loader = template.Loader(os.path.dirname(os.path.abspath(__file__)))
        t = loader.load('debug.html')
        return t.generate(
            traceback=traceback,
            pprint=pprint,
            handler=self.handler,
            app_settings=self.get_app_settings(),
            exc_type=self.exc_type,
            exc_value=self.exc_value,
            exc_tb=self.exc_tb,
            frames=self.get_traceback_frames(),
            tornado_version=tornado.version,
            sys_version='%d.%d.%d' % sys.version_info[0:3],
            sys_executable=sys.executable,
            sys_path=sys.path,
        )

    def get_app_settings(self):
        settings = {}

        for arg, value in self.handler.application.settings.items():
            if SENSITIVE_SETTINGS_RE.search(arg):
                value = '*' * 15
            settings[arg] = value

        return settings

    def get_source_lines(self, tb):
        filename = tb.tb_frame.f_code.co_filename
        lineno = tb.tb_lineno
        lines = []
        try:
            with open(filename, 'rb') as f:
                _lines = f.read().splitlines()
                for _lineno in range(
                    max(lineno - 5, 0), 
                    min(lineno + 5, len(_lines))
                ):
                    lines.append((_lineno + 1, _lines[_lineno]))
        except Exception as e:
            # could not open file
            pass

        return lines

    def get_traceback_frames(self):
        frames = []

        tb = self.exc_tb
        while tb:
            frames.append({
                'lineno': tb.tb_lineno,
                'filename': tb.tb_frame.f_code.co_filename,
                'function': tb.tb_frame.f_code.co_name,
                'module_name': tb.tb_frame.f_globals.get('__name__') or '',
                'vars': tb.tb_frame.f_locals,
                'lines': self.get_source_lines(tb),
            })
            tb = tb.tb_next

        frames.reverse()
        return frames 


def pprint(value):
    try:
        return pformat(value, width=1)
    except Exception as e:
        return 'Error in formatting: %s: %s' % (e.__class__.__name__, e)
