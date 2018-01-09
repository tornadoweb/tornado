#!/usr/bin/env python
#
# A simple benchmark of tornado template rendering, based on
# https://github.com/mitsuhiko/jinja2/blob/master/examples/bench.py

import sys
from timeit import Timer

from tornado.options import options, define, parse_command_line
from tornado.template import Template

define('num', default=100, help='number of iterations')
define('dump', default=False, help='print template generated code and exit')

context = {
    'page_title': 'mitsuhiko\'s benchmark',
    'table': [dict(a=1, b=2, c=3, d=4, e=5,
                   f=6, g=7, h=8, i=9, j=10) for x in range(1000)]
}

tmpl = Template("""\
<!doctype html>
<html>
  <head>
    <title>{{ page_title }}</title>
  </head>
  <body>
    <div class="header">
      <h1>{{ page_title }}</h1>
    </div>
    <ul class="navigation">
    {% for href, caption in [ \
        ('index.html', 'Index'), \
        ('downloads.html', 'Downloads'), \
        ('products.html', 'Products') \
      ] %}
      <li><a href="{{ href }}">{{ caption }}</a></li>
    {% end %}
    </ul>
    <div class="table">
      <table>
      {% for row in table %}
        <tr>
        {% for cell in row %}
          <td>{{ cell }}</td>
        {% end %}
        </tr>
      {% end %}
      </table>
    </div>
  </body>
</html>\
""")


def render():
    tmpl.generate(**context)


def main():
    parse_command_line()
    if options.dump:
        print(tmpl.code)
        sys.exit(0)
    t = Timer(render)
    results = t.timeit(options.num) / options.num
    print('%0.3f ms per iteration' % (results * 1000))


if __name__ == '__main__':
    main()
