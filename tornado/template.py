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

"""A simple template system that compiles templates to Python code.

Basic usage looks like::

    t = template.Template("<html>{{ myvalue }}</html>")
    print t.generate(myvalue="XXX")

Loader is a class that loads templates from a root directory and caches
the compiled templates::

    loader = template.Loader("/home/btaylor")
    print loader.load("test.html").generate(myvalue="XXX")

We compile all templates to raw Python. Error-reporting is currently... uh,
interesting. Syntax for the templates::

    ### base.html
    <html>
      <head>
        <title>{% block title %}Default title{% end %}</title>
      </head>
      <body>
        <ul>
          {% for student in students %}
            {% block student %}
              <li>{{ escape(student.name) }}</li>
            {% end %}
          {% end %}
        </ul>
      </body>
    </html>

    ### bold.html
    {% extends "base.html" %}

    {% block title %}A bolder title{% end %}

    {% block student %}
      <li><span style="bold">{{ escape(student.name) }}</span></li>
    {% end %}

Unlike most other template systems, we do not put any restrictions on the
expressions you can include in your statements. if and for blocks get
translated exactly into Python, do you can do complex expressions like::

   {% for student in [p for p in people if p.student and p.age > 23] %}
     <li>{{ escape(student.name) }}</li>
   {% end %}

Translating directly to Python means you can apply functions to expressions
easily, like the escape() function in the examples above. You can pass
functions in to your template just like any other variable::

   ### Python code
   def add(x, y):
      return x + y
   template.execute(add=add)

   ### The template
   {{ add(1, 2) }}

We provide the functions escape(), url_escape(), json_encode(), and squeeze()
to all templates by default.

Typical applications do not create `Template` or `Loader` instances by
hand, but instead use the `render` and `render_string` methods of
`tornado.web.RequestHandler`, which load templates automatically based
on the ``template_path`` `Application` setting.
"""

from __future__ import with_statement

import cStringIO
import datetime
import logging
import os.path
import posixpath
import re

from tornado import escape
from tornado.util import bytes_type

_DEFAULT_AUTOESCAPE = "xhtml_escape"
_UNSET = object()

class Template(object):
    """A compiled template.

    We compile into Python from the given template_string. You can generate
    the template from variables with generate().
    """
    def __init__(self, template_string, name="<string>", loader=None,
                 compress_whitespace=None, autoescape=_UNSET):
        self.name = name
        if compress_whitespace is None:
            compress_whitespace = name.endswith(".html") or \
                name.endswith(".js")
        if autoescape is not _UNSET:
            self.autoescape = autoescape
        elif loader:
            self.autoescape = loader.autoescape
        else:
            self.autoescape = _DEFAULT_AUTOESCAPE
        reader = _TemplateReader(name, escape.native_str(template_string))
        self.file = _File(_parse(reader, self))
        self.code = self._generate_python(loader, compress_whitespace)
        try:
            self.compiled = compile(escape.to_unicode(self.code),
                                    "<template %s>" % self.name,
                                    "exec")
        except Exception:
            formatted_code = _format_code(self.code).rstrip()
            logging.error("%s code:\n%s", self.name, formatted_code)
            raise

    def generate(self, **kwargs):
        """Generate this template with the given arguments."""
        namespace = {
            "escape": escape.xhtml_escape,
            "xhtml_escape": escape.xhtml_escape,
            "url_escape": escape.url_escape,
            "json_encode": escape.json_encode,
            "squeeze": escape.squeeze,
            "linkify": escape.linkify,
            "datetime": datetime,
            "_utf8": escape.utf8,  # for internal use
            "_string_types": (unicode, bytes_type),
        }
        namespace.update(kwargs)
        exec self.compiled in namespace
        execute = namespace["_execute"]
        try:
            return execute()
        except Exception:
            formatted_code = _format_code(self.code).rstrip()
            logging.error("%s code:\n%s", self.name, formatted_code)
            raise

    def _generate_python(self, loader, compress_whitespace):
        buffer = cStringIO.StringIO()
        try:
            # named_blocks maps from names to _NamedBlock objects
            named_blocks = {}
            ancestors = self._get_ancestors(loader)
            ancestors.reverse()
            for ancestor in ancestors:
                ancestor.find_named_blocks(loader, named_blocks)
            self.file.find_named_blocks(loader, named_blocks)
            writer = _CodeWriter(buffer, named_blocks, loader, self,
                                 compress_whitespace)
            ancestors[0].generate(writer)
            return buffer.getvalue()
        finally:
            buffer.close()

    def _get_ancestors(self, loader):
        ancestors = [self.file]
        for chunk in self.file.body.chunks:
            if isinstance(chunk, _ExtendsBlock):
                if not loader:
                    raise ParseError("{% extends %} block found, but no "
                                     "template loader")
                template = loader.load(chunk.name, self.name)
                ancestors.extend(template._get_ancestors(loader))
        return ancestors


class BaseLoader(object):
    """Base class for template loaders."""
    def __init__(self, autoescape=_DEFAULT_AUTOESCAPE):
        """Creates a template loader.

        root_directory may be the empty string if this loader does not
        use the filesystem.

        autoescape must be either None or a string naming a function
        in the template namespace, such as "xhtml_escape".
        """
        self.autoescape = autoescape
        self.templates = {}

    def reset(self):
        """Resets the cache of compiled templates."""
        self.templates = {}

    def resolve_path(self, name, parent_path=None):
        """Converts a possibly-relative path to absolute (used internally)."""
        raise NotImplementedError()

    def load(self, name, parent_path=None):
        """Loads a template."""
        name = self.resolve_path(name, parent_path=parent_path)
        if name not in self.templates:
            self.templates[name] = self._create_template(name)
        return self.templates[name]

    def _create_template(self, name):
        raise NotImplementedError()

class Loader(BaseLoader):
    """A template loader that loads from a single root directory.

    You must use a template loader to use template constructs like
    {% extends %} and {% include %}. Loader caches all templates after
    they are loaded the first time.
    """
    def __init__(self, root_directory, **kwargs):
        super(Loader, self).__init__(**kwargs)
        self.root = os.path.abspath(root_directory)


    def resolve_path(self, name, parent_path=None):
        if parent_path and not parent_path.startswith("<") and \
           not parent_path.startswith("/") and \
           not name.startswith("/"):
            current_path = os.path.join(self.root, parent_path)
            file_dir = os.path.dirname(os.path.abspath(current_path))
            relative_path = os.path.abspath(os.path.join(file_dir, name))
            if relative_path.startswith(self.root):
                name = relative_path[len(self.root) + 1:]
        return name

    def _create_template(self, name):
        path = os.path.join(self.root, name)
        f = open(path, "r")
        template = Template(f.read(), name=name, loader=self)
        f.close()
        return template


class DictLoader(BaseLoader):
    """A template loader that loads from a dictionary."""
    def __init__(self, dict, **kwargs):
        super(DictLoader, self).__init__(**kwargs)
        self.dict = dict

    def resolve_path(self, name, parent_path=None):
        if parent_path and not parent_path.startswith("<") and \
           not parent_path.startswith("/") and \
           not name.startswith("/"):
            file_dir = posixpath.dirname(parent_path)
            name = posixpath.normpath(posixpath.join(file_dir, name))
        return name

    def _create_template(self, name):
        return Template(self.dict[name], name=name, loader=self)


class _Node(object):
    def each_child(self):
        return ()

    def generate(self, writer):
        raise NotImplementedError()

    def find_named_blocks(self, loader, named_blocks):
        for child in self.each_child():
            child.find_named_blocks(loader, named_blocks)


class _File(_Node):
    def __init__(self, body):
        self.body = body

    def generate(self, writer):
        writer.write_line("def _execute():")
        with writer.indent():
            writer.write_line("_buffer = []")
            self.body.generate(writer)
            writer.write_line("return _utf8('').join(_buffer)")

    def each_child(self):
        return (self.body,)



class _ChunkList(_Node):
    def __init__(self, chunks):
        self.chunks = chunks

    def generate(self, writer):
        for chunk in self.chunks:
            chunk.generate(writer)

    def each_child(self):
        return self.chunks


class _NamedBlock(_Node):
    def __init__(self, name, body, template):
        self.name = name
        self.body = body
        self.template = template

    def each_child(self):
        return (self.body,)

    def generate(self, writer):
        block = writer.named_blocks[self.name]
        old = writer.current_template
        writer.current_template = block.template
        block.body.generate(writer)
        writer.current_template = old

    def find_named_blocks(self, loader, named_blocks):
        named_blocks[self.name] = self
        _Node.find_named_blocks(self, loader, named_blocks)


class _ExtendsBlock(_Node):
    def __init__(self, name):
        self.name = name


class _IncludeBlock(_Node):
    def __init__(self, name, reader):
        self.name = name
        self.template_name = reader.name

    def find_named_blocks(self, loader, named_blocks):
        included = loader.load(self.name, self.template_name)
        included.file.find_named_blocks(loader, named_blocks)

    def generate(self, writer):
        included = writer.loader.load(self.name, self.template_name)
        old = writer.current_template
        writer.current_template = included
        included.file.body.generate(writer)
        writer.current_template = old


class _ApplyBlock(_Node):
    def __init__(self, method, body=None):
        self.method = method
        self.body = body

    def each_child(self):
        return (self.body,)

    def generate(self, writer):
        method_name = "apply%d" % writer.apply_counter
        writer.apply_counter += 1
        writer.write_line("def %s():" % method_name)
        with writer.indent():
            writer.write_line("_buffer = []")
            self.body.generate(writer)
            writer.write_line("return _utf8('').join(_buffer)")
        writer.write_line("_buffer.append(%s(%s()))" % (
            self.method, method_name))


class _ControlBlock(_Node):
    def __init__(self, statement, body=None):
        self.statement = statement
        self.body = body

    def each_child(self):
        return (self.body,)

    def generate(self, writer):
        writer.write_line("%s:" % self.statement)
        with writer.indent():
            self.body.generate(writer)


class _IntermediateControlBlock(_Node):
    def __init__(self, statement):
        self.statement = statement

    def generate(self, writer):
        writer.write_line("%s:" % self.statement, writer.indent_size() - 1)


class _Statement(_Node):
    def __init__(self, statement):
        self.statement = statement

    def generate(self, writer):
        writer.write_line(self.statement)


class _Expression(_Node):
    def __init__(self, expression, raw=False):
        self.expression = expression
        self.raw = raw

    def generate(self, writer):
        writer.write_line("_tmp = %s" % self.expression)
        writer.write_line("if isinstance(_tmp, _string_types):"
                          " _tmp = _utf8(_tmp)")
        writer.write_line("else: _tmp = _utf8(str(_tmp))")
        if not self.raw and writer.current_template.autoescape is not None:
            # In python3 functions like xhtml_escape return unicode,
            # so we have to convert to utf8 again.
            writer.write_line("_tmp = _utf8(%s(_tmp))" %
                              writer.current_template.autoescape)
        writer.write_line("_buffer.append(_tmp)")

class _Module(_Expression):
    def __init__(self, expression):
        super(_Module, self).__init__("_modules." + expression,
                                      raw=True)

class _Text(_Node):
    def __init__(self, value):
        self.value = value

    def generate(self, writer):
        value = self.value

        # Compress lots of white space to a single character. If the whitespace
        # breaks a line, have it continue to break a line, but just with a
        # single \n character
        if writer.compress_whitespace and "<pre>" not in value:
            value = re.sub(r"([\t ]+)", " ", value)
            value = re.sub(r"(\s*\n\s*)", "\n", value)

        if value:
            writer.write_line('_buffer.append(%r)' % escape.utf8(value))


class ParseError(Exception):
    """Raised for template syntax errors."""
    pass


class _CodeWriter(object):
    def __init__(self, file, named_blocks, loader, current_template,
                 compress_whitespace):
        self.file = file
        self.named_blocks = named_blocks
        self.loader = loader
        self.current_template = current_template
        self.compress_whitespace = compress_whitespace
        self.apply_counter = 0
        self._indent = 0

    def indent(self):
        return self

    def indent_size(self):
        return self._indent

    def __enter__(self):
        self._indent += 1
        return self

    def __exit__(self, *args):
        assert self._indent > 0
        self._indent -= 1

    def write_line(self, line, indent=None):
        if indent == None:
            indent = self._indent
        for i in xrange(indent):
            self.file.write("    ")
        print >> self.file, line


class _TemplateReader(object):
    def __init__(self, name, text):
        self.name = name
        self.text = text
        self.line = 0
        self.pos = 0

    def find(self, needle, start=0, end=None):
        assert start >= 0, start
        pos = self.pos
        start += pos
        if end is None:
            index = self.text.find(needle, start)
        else:
            end += pos
            assert end >= start
            index = self.text.find(needle, start, end)
        if index != -1:
            index -= pos
        return index

    def consume(self, count=None):
        if count is None:
            count = len(self.text) - self.pos
        newpos = self.pos + count
        self.line += self.text.count("\n", self.pos, newpos)
        s = self.text[self.pos:newpos]
        self.pos = newpos
        return s

    def remaining(self):
        return len(self.text) - self.pos

    def __len__(self):
        return self.remaining()

    def __getitem__(self, key):
        if type(key) is slice:
            size = len(self)
            start, stop, step = key.indices(size)
            if start is None: start = self.pos
            else: start += self.pos
            if stop is not None: stop += self.pos
            return self.text[slice(start, stop, step)]
        elif key < 0:
            return self.text[key]
        else:
            return self.text[self.pos + key]

    def __str__(self):
        return self.text[self.pos:]


def _format_code(code):
    lines = code.splitlines()
    format = "%%%dd  %%s\n" % len(repr(len(lines) + 1))
    return "".join([format % (i + 1, line) for (i, line) in enumerate(lines)])


def _parse(reader, template, in_block=None):
    body = _ChunkList([])
    while True:
        # Find next template directive
        curly = 0
        while True:
            curly = reader.find("{", curly)
            if curly == -1 or curly + 1 == reader.remaining():
                # EOF
                if in_block:
                    raise ParseError("Missing {%% end %%} block for %s" %
                                     in_block)
                body.chunks.append(_Text(reader.consume()))
                return body
            # If the first curly brace is not the start of a special token,
            # start searching from the character after it
            if reader[curly + 1] not in ("{", "%"):
                curly += 1
                continue
            # When there are more than 2 curlies in a row, use the
            # innermost ones.  This is useful when generating languages
            # like latex where curlies are also meaningful
            if (curly + 2 < reader.remaining() and
                reader[curly + 1] == '{' and reader[curly + 2] == '{'):
                curly += 1
                continue
            break

        # Append any text before the special token
        if curly > 0:
            body.chunks.append(_Text(reader.consume(curly)))

        start_brace = reader.consume(2)
        line = reader.line

        # Template directives may be escaped as "{{!" or "{%!".
        # In this case output the braces and consume the "!".
        # This is especially useful in conjunction with jquery templates,
        # which also use double braces.
        if reader.remaining() and reader[0] == "!":
            reader.consume(1)
            body.chunks.append(_Text(start_brace))
            continue

        # Expression
        if start_brace == "{{":
            end = reader.find("}}")
            if end == -1 or reader.find("\n", 0, end) != -1:
                raise ParseError("Missing end expression }} on line %d" % line)
            contents = reader.consume(end).strip()
            reader.consume(2)
            if not contents:
                raise ParseError("Empty expression on line %d" % line)
            body.chunks.append(_Expression(contents))
            continue

        # Block
        assert start_brace == "{%", start_brace
        end = reader.find("%}")
        if end == -1 or reader.find("\n", 0, end) != -1:
            raise ParseError("Missing end block %%} on line %d" % line)
        contents = reader.consume(end).strip()
        reader.consume(2)
        if not contents:
            raise ParseError("Empty block tag ({%% %%}) on line %d" % line)

        operator, space, suffix = contents.partition(" ")
        suffix = suffix.strip()

        # Intermediate ("else", "elif", etc) blocks
        intermediate_blocks = {
            "else": set(["if", "for", "while"]),
            "elif": set(["if"]),
            "except": set(["try"]),
            "finally": set(["try"]),
        }
        allowed_parents = intermediate_blocks.get(operator)
        if allowed_parents is not None:
            if not in_block:
                raise ParseError("%s outside %s block" %
                            (operator, allowed_parents))
            if in_block not in allowed_parents:
                raise ParseError("%s block cannot be attached to %s block" % (operator, in_block))
            body.chunks.append(_IntermediateControlBlock(contents))
            continue

        # End tag
        elif operator == "end":
            if not in_block:
                raise ParseError("Extra {%% end %%} block on line %d" % line)
            return body

        elif operator in ("extends", "include", "set", "import", "from",
                          "comment", "autoescape", "raw", "module"):
            if operator == "comment":
                continue
            if operator == "extends":
                suffix = suffix.strip('"').strip("'")
                if not suffix:
                    raise ParseError("extends missing file path on line %d" % line)
                block = _ExtendsBlock(suffix)
            elif operator in ("import", "from"):
                if not suffix:
                    raise ParseError("import missing statement on line %d" % line)
                block = _Statement(contents)
            elif operator == "include":
                suffix = suffix.strip('"').strip("'")
                if not suffix:
                    raise ParseError("include missing file path on line %d" % line)
                block = _IncludeBlock(suffix, reader)
            elif operator == "set":
                if not suffix:
                    raise ParseError("set missing statement on line %d" % line)
                block = _Statement(suffix)
            elif operator == "autoescape":
                fn = suffix.strip()
                if fn == "None": fn = None
                template.autoescape = fn
                continue
            elif operator == "raw":
                block = _Expression(suffix, raw=True)
            elif operator == "module":
                block = _Module(suffix)
            body.chunks.append(block)
            continue

        elif operator in ("apply", "block", "try", "if", "for", "while"):
            # parse inner body recursively
            block_body = _parse(reader, template, operator)
            if operator == "apply":
                if not suffix:
                    raise ParseError("apply missing method name on line %d" % line)
                block = _ApplyBlock(suffix, block_body)
            elif operator == "block":
                if not suffix:
                    raise ParseError("block missing name on line %d" % line)
                block = _NamedBlock(suffix, block_body, template)
            else:
                block = _ControlBlock(contents, block_body)
            body.chunks.append(block)
            continue

        else:
            raise ParseError("unknown operator: %r" % operator)
