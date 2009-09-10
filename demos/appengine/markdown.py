#!/usr/bin/env python
# Copyright (c) 2007-2008 ActiveState Corp.
# License: MIT (http://www.opensource.org/licenses/mit-license.php)

r"""A fast and complete Python implementation of Markdown.

[from http://daringfireball.net/projects/markdown/]
> Markdown is a text-to-HTML filter; it translates an easy-to-read /
> easy-to-write structured text format into HTML.  Markdown's text
> format is most similar to that of plain text email, and supports
> features such as headers, *emphasis*, code blocks, blockquotes, and
> links.
>
> Markdown's syntax is designed not as a generic markup language, but
> specifically to serve as a front-end to (X)HTML. You can use span-level
> HTML tags anywhere in a Markdown document, and you can use block level
> HTML tags (like <div> and <table> as well).

Module usage:

    >>> import markdown2
    >>> markdown2.markdown("*boo!*")  # or use `html = markdown_path(PATH)`
    u'<p><em>boo!</em></p>\n'

    >>> markdowner = Markdown()
    >>> markdowner.convert("*boo!*")
    u'<p><em>boo!</em></p>\n'
    >>> markdowner.convert("**boom!**")
    u'<p><strong>boom!</strong></p>\n'

This implementation of Markdown implements the full "core" syntax plus a
number of extras (e.g., code syntax coloring, footnotes) as described on
<http://code.google.com/p/python-markdown2/wiki/Extras>.
"""

cmdln_desc = """A fast and complete Python implementation of Markdown, a
text-to-HTML conversion tool for web writers.
"""

# Dev Notes:
# - There is already a Python markdown processor
#   (http://www.freewisdom.org/projects/python-markdown/).
# - Python's regex syntax doesn't have '\z', so I'm using '\Z'. I'm
#   not yet sure if there implications with this. Compare 'pydoc sre'
#   and 'perldoc perlre'.

__version_info__ = (1, 0, 1, 14) # first three nums match Markdown.pl
__version__ = '1.0.1.14'
__author__ = "Trent Mick"

import os
import sys
from pprint import pprint
import re
import logging
try:
    from hashlib import md5
except ImportError:
    from md5 import md5
import optparse
from random import random
import codecs



#---- Python version compat

if sys.version_info[:2] < (2,4):
    from sets import Set as set
    def reversed(sequence):
        for i in sequence[::-1]:
            yield i
    def _unicode_decode(s, encoding, errors='xmlcharrefreplace'):
        return unicode(s, encoding, errors)
else:
    def _unicode_decode(s, encoding, errors='strict'):
        return s.decode(encoding, errors)


#---- globals

DEBUG = False
log = logging.getLogger("markdown")

DEFAULT_TAB_WIDTH = 4

# Table of hash values for escaped characters:
def _escape_hash(s):
    # Lame attempt to avoid possible collision with someone actually
    # using the MD5 hexdigest of one of these chars in there text.
    # Other ideas: random.random(), uuid.uuid()
    #return md5(s).hexdigest()   # Markdown.pl effectively does this.
    return 'md5-'+md5(s).hexdigest()
g_escape_table = dict([(ch, _escape_hash(ch))
                       for ch in '\\`*_{}[]()>#+-.!'])



#---- exceptions

class MarkdownError(Exception):
    pass



#---- public api

def markdown_path(path, encoding="utf-8",
                  html4tags=False, tab_width=DEFAULT_TAB_WIDTH,
                  safe_mode=None, extras=None, link_patterns=None,
                  use_file_vars=False):
    text = codecs.open(path, 'r', encoding).read()
    return Markdown(html4tags=html4tags, tab_width=tab_width,
                    safe_mode=safe_mode, extras=extras,
                    link_patterns=link_patterns,
                    use_file_vars=use_file_vars).convert(text)

def markdown(text, html4tags=False, tab_width=DEFAULT_TAB_WIDTH,
             safe_mode=None, extras=None, link_patterns=None,
             use_file_vars=False):
    return Markdown(html4tags=html4tags, tab_width=tab_width,
                    safe_mode=safe_mode, extras=extras,
                    link_patterns=link_patterns,
                    use_file_vars=use_file_vars).convert(text)

class Markdown(object):
    # The dict of "extras" to enable in processing -- a mapping of
    # extra name to argument for the extra. Most extras do not have an
    # argument, in which case the value is None.
    #
    # This can be set via (a) subclassing and (b) the constructor
    # "extras" argument.
    extras = None

    urls = None
    titles = None
    html_blocks = None
    html_spans = None
    html_removed_text = "[HTML_REMOVED]"  # for compat with markdown.py

    # Used to track when we're inside an ordered or unordered list
    # (see _ProcessListItems() for details):
    list_level = 0

    _ws_only_line_re = re.compile(r"^[ \t]+$", re.M)

    def __init__(self, html4tags=False, tab_width=4, safe_mode=None,
                 extras=None, link_patterns=None, use_file_vars=False):
        if html4tags:
            self.empty_element_suffix = ">"
        else:
            self.empty_element_suffix = " />"
        self.tab_width = tab_width

        # For compatibility with earlier markdown2.py and with
        # markdown.py's safe_mode being a boolean, 
        #   safe_mode == True -> "replace"
        if safe_mode is True:
            self.safe_mode = "replace"
        else:
            self.safe_mode = safe_mode

        if self.extras is None:
            self.extras = {}
        elif not isinstance(self.extras, dict):
            self.extras = dict([(e, None) for e in self.extras])
        if extras:
            if not isinstance(extras, dict):
                extras = dict([(e, None) for e in extras])
            self.extras.update(extras)
        assert isinstance(self.extras, dict)
        self._instance_extras = self.extras.copy()
        self.link_patterns = link_patterns
        self.use_file_vars = use_file_vars
        self._outdent_re = re.compile(r'^(\t|[ ]{1,%d})' % tab_width, re.M)

    def reset(self):
        self.urls = {}
        self.titles = {}
        self.html_blocks = {}
        self.html_spans = {}
        self.list_level = 0
        self.extras = self._instance_extras.copy()
        if "footnotes" in self.extras:
            self.footnotes = {}
            self.footnote_ids = []

    def convert(self, text):
        """Convert the given text."""
        # Main function. The order in which other subs are called here is
        # essential. Link and image substitutions need to happen before
        # _EscapeSpecialChars(), so that any *'s or _'s in the <a>
        # and <img> tags get encoded.

        # Clear the global hashes. If we don't clear these, you get conflicts
        # from other articles when generating a page which contains more than
        # one article (e.g. an index page that shows the N most recent
        # articles):
        self.reset()

        if not isinstance(text, unicode):
            #TODO: perhaps shouldn't presume UTF-8 for string input?
            text = unicode(text, 'utf-8')

        if self.use_file_vars:
            # Look for emacs-style file variable hints.
            emacs_vars = self._get_emacs_vars(text)
            if "markdown-extras" in emacs_vars:
                splitter = re.compile("[ ,]+")
                for e in splitter.split(emacs_vars["markdown-extras"]):
                    if '=' in e:
                        ename, earg = e.split('=', 1)
                        try:
                            earg = int(earg)
                        except ValueError:
                            pass
                    else:
                        ename, earg = e, None
                    self.extras[ename] = earg

        # Standardize line endings:
        text = re.sub("\r\n|\r", "\n", text)

        # Make sure $text ends with a couple of newlines:
        text += "\n\n"

        # Convert all tabs to spaces.
        text = self._detab(text)

        # Strip any lines consisting only of spaces and tabs.
        # This makes subsequent regexen easier to write, because we can
        # match consecutive blank lines with /\n+/ instead of something
        # contorted like /[ \t]*\n+/ .
        text = self._ws_only_line_re.sub("", text)

        if self.safe_mode:
            text = self._hash_html_spans(text)

        # Turn block-level HTML blocks into hash entries
        text = self._hash_html_blocks(text, raw=True)

        # Strip link definitions, store in hashes.
        if "footnotes" in self.extras:
            # Must do footnotes first because an unlucky footnote defn
            # looks like a link defn:
            #   [^4]: this "looks like a link defn"
            text = self._strip_footnote_definitions(text)
        text = self._strip_link_definitions(text)

        text = self._run_block_gamut(text)

        if "footnotes" in self.extras:
            text = self._add_footnotes(text)

        text = self._unescape_special_chars(text)

        if self.safe_mode:
            text = self._unhash_html_spans(text)

        text += "\n"
        return text

    _emacs_oneliner_vars_pat = re.compile(r"-\*-\s*([^\r\n]*?)\s*-\*-", re.UNICODE)
    # This regular expression is intended to match blocks like this:
    #    PREFIX Local Variables: SUFFIX
    #    PREFIX mode: Tcl SUFFIX
    #    PREFIX End: SUFFIX
    # Some notes:
    # - "[ \t]" is used instead of "\s" to specifically exclude newlines
    # - "(\r\n|\n|\r)" is used instead of "$" because the sre engine does
    #   not like anything other than Unix-style line terminators.
    _emacs_local_vars_pat = re.compile(r"""^
        (?P<prefix>(?:[^\r\n|\n|\r])*?)
        [\ \t]*Local\ Variables:[\ \t]*
        (?P<suffix>.*?)(?:\r\n|\n|\r)
        (?P<content>.*?\1End:)
        """, re.IGNORECASE | re.MULTILINE | re.DOTALL | re.VERBOSE)

    def _get_emacs_vars(self, text):
        """Return a dictionary of emacs-style local variables.

        Parsing is done loosely according to this spec (and according to
        some in-practice deviations from this):
        http://www.gnu.org/software/emacs/manual/html_node/emacs/Specifying-File-Variables.html#Specifying-File-Variables
        """
        emacs_vars = {}
        SIZE = pow(2, 13) # 8kB

        # Search near the start for a '-*-'-style one-liner of variables.
        head = text[:SIZE]
        if "-*-" in head:
            match = self._emacs_oneliner_vars_pat.search(head)
            if match:
                emacs_vars_str = match.group(1)
                assert '\n' not in emacs_vars_str
                emacs_var_strs = [s.strip() for s in emacs_vars_str.split(';')
                                  if s.strip()]
                if len(emacs_var_strs) == 1 and ':' not in emacs_var_strs[0]:
                    # While not in the spec, this form is allowed by emacs:
                    #   -*- Tcl -*-
                    # where the implied "variable" is "mode". This form
                    # is only allowed if there are no other variables.
                    emacs_vars["mode"] = emacs_var_strs[0].strip()
                else:
                    for emacs_var_str in emacs_var_strs:
                        try:
                            variable, value = emacs_var_str.strip().split(':', 1)
                        except ValueError:
                            log.debug("emacs variables error: malformed -*- "
                                      "line: %r", emacs_var_str)
                            continue
                        # Lowercase the variable name because Emacs allows "Mode"
                        # or "mode" or "MoDe", etc.
                        emacs_vars[variable.lower()] = value.strip()

        tail = text[-SIZE:]
        if "Local Variables" in tail:
            match = self._emacs_local_vars_pat.search(tail)
            if match:
                prefix = match.group("prefix")
                suffix = match.group("suffix")
                lines = match.group("content").splitlines(0)
                #print "prefix=%r, suffix=%r, content=%r, lines: %s"\
                #      % (prefix, suffix, match.group("content"), lines)

                # Validate the Local Variables block: proper prefix and suffix
                # usage.
                for i, line in enumerate(lines):
                    if not line.startswith(prefix):
                        log.debug("emacs variables error: line '%s' "
                                  "does not use proper prefix '%s'"
                                  % (line, prefix))
                        return {}
                    # Don't validate suffix on last line. Emacs doesn't care,
                    # neither should we.
                    if i != len(lines)-1 and not line.endswith(suffix):
                        log.debug("emacs variables error: line '%s' "
                                  "does not use proper suffix '%s'"
                                  % (line, suffix))
                        return {}

                # Parse out one emacs var per line.
                continued_for = None
                for line in lines[:-1]: # no var on the last line ("PREFIX End:")
                    if prefix: line = line[len(prefix):] # strip prefix
                    if suffix: line = line[:-len(suffix)] # strip suffix
                    line = line.strip()
                    if continued_for:
                        variable = continued_for
                        if line.endswith('\\'):
                            line = line[:-1].rstrip()
                        else:
                            continued_for = None
                        emacs_vars[variable] += ' ' + line
                    else:
                        try:
                            variable, value = line.split(':', 1)
                        except ValueError:
                            log.debug("local variables error: missing colon "
                                      "in local variables entry: '%s'" % line)
                            continue
                        # Do NOT lowercase the variable name, because Emacs only
                        # allows "mode" (and not "Mode", "MoDe", etc.) in this block.
                        value = value.strip()
                        if value.endswith('\\'):
                            value = value[:-1].rstrip()
                            continued_for = variable
                        else:
                            continued_for = None
                        emacs_vars[variable] = value

        # Unquote values.
        for var, val in emacs_vars.items():
            if len(val) > 1 and (val.startswith('"') and val.endswith('"')
               or val.startswith('"') and val.endswith('"')):
                emacs_vars[var] = val[1:-1]

        return emacs_vars

    # Cribbed from a post by Bart Lateur:
    # <http://www.nntp.perl.org/group/perl.macperl.anyperl/154>
    _detab_re = re.compile(r'(.*?)\t', re.M)
    def _detab_sub(self, match):
        g1 = match.group(1)
        return g1 + (' ' * (self.tab_width - len(g1) % self.tab_width))
    def _detab(self, text):
        r"""Remove (leading?) tabs from a file.

            >>> m = Markdown()
            >>> m._detab("\tfoo")
            '    foo'
            >>> m._detab("  \tfoo")
            '    foo'
            >>> m._detab("\t  foo")
            '      foo'
            >>> m._detab("  foo")
            '  foo'
            >>> m._detab("  foo\n\tbar\tblam")
            '  foo\n    bar blam'
        """
        if '\t' not in text:
            return text
        return self._detab_re.subn(self._detab_sub, text)[0]

    _block_tags_a = 'p|div|h[1-6]|blockquote|pre|table|dl|ol|ul|script|noscript|form|fieldset|iframe|math|ins|del'
    _strict_tag_block_re = re.compile(r"""
        (                       # save in \1
            ^                   # start of line  (with re.M)
            <(%s)               # start tag = \2
            \b                  # word break
            (.*\n)*?            # any number of lines, minimally matching
            </\2>               # the matching end tag
            [ \t]*              # trailing spaces/tabs
            (?=\n+|\Z)          # followed by a newline or end of document
        )
        """ % _block_tags_a,
        re.X | re.M)

    _block_tags_b = 'p|div|h[1-6]|blockquote|pre|table|dl|ol|ul|script|noscript|form|fieldset|iframe|math'
    _liberal_tag_block_re = re.compile(r"""
        (                       # save in \1
            ^                   # start of line  (with re.M)
            <(%s)               # start tag = \2
            \b                  # word break
            (.*\n)*?            # any number of lines, minimally matching
            .*</\2>             # the matching end tag
            [ \t]*              # trailing spaces/tabs
            (?=\n+|\Z)          # followed by a newline or end of document
        )
        """ % _block_tags_b,
        re.X | re.M)

    def _hash_html_block_sub(self, match, raw=False):
        html = match.group(1)
        if raw and self.safe_mode:
            html = self._sanitize_html(html)
        key = _hash_text(html)
        self.html_blocks[key] = html
        return "\n\n" + key + "\n\n"

    def _hash_html_blocks(self, text, raw=False):
        """Hashify HTML blocks

        We only want to do this for block-level HTML tags, such as headers,
        lists, and tables. That's because we still want to wrap <p>s around
        "paragraphs" that are wrapped in non-block-level tags, such as anchors,
        phrase emphasis, and spans. The list of tags we're looking for is
        hard-coded.

        @param raw {boolean} indicates if these are raw HTML blocks in
            the original source. It makes a difference in "safe" mode.
        """
        if '<' not in text:
            return text

        # Pass `raw` value into our calls to self._hash_html_block_sub.
        hash_html_block_sub = _curry(self._hash_html_block_sub, raw=raw)

        # First, look for nested blocks, e.g.:
        #   <div>
        #       <div>
        #       tags for inner block must be indented.
        #       </div>
        #   </div>
        #
        # The outermost tags must start at the left margin for this to match, and
        # the inner nested divs must be indented.
        # We need to do this before the next, more liberal match, because the next
        # match will start at the first `<div>` and stop at the first `</div>`.
        text = self._strict_tag_block_re.sub(hash_html_block_sub, text)

        # Now match more liberally, simply from `\n<tag>` to `</tag>\n`
        text = self._liberal_tag_block_re.sub(hash_html_block_sub, text)

        # Special case just for <hr />. It was easier to make a special
        # case than to make the other regex more complicated.   
        if "<hr" in text:
            _hr_tag_re = _hr_tag_re_from_tab_width(self.tab_width)
            text = _hr_tag_re.sub(hash_html_block_sub, text)

        # Special case for standalone HTML comments:
        if "<!--" in text:
            start = 0
            while True:
                # Delimiters for next comment block.
                try:
                    start_idx = text.index("<!--", start)
                except ValueError, ex:
                    break
                try:
                    end_idx = text.index("-->", start_idx) + 3
                except ValueError, ex:
                    break

                # Start position for next comment block search.
                start = end_idx

                # Validate whitespace before comment.
                if start_idx:
                    # - Up to `tab_width - 1` spaces before start_idx.
                    for i in range(self.tab_width - 1):
                        if text[start_idx - 1] != ' ':
                            break
                        start_idx -= 1
                        if start_idx == 0:
                            break
                    # - Must be preceded by 2 newlines or hit the start of
                    #   the document.
                    if start_idx == 0:
                        pass
                    elif start_idx == 1 and text[0] == '\n':
                        start_idx = 0  # to match minute detail of Markdown.pl regex
                    elif text[start_idx-2:start_idx] == '\n\n':
                        pass
                    else:
                        break

                # Validate whitespace after comment.
                # - Any number of spaces and tabs.
                while end_idx < len(text):
                    if text[end_idx] not in ' \t':
                        break
                    end_idx += 1
                # - Must be following by 2 newlines or hit end of text.
                if text[end_idx:end_idx+2] not in ('', '\n', '\n\n'):
                    continue

                # Escape and hash (must match `_hash_html_block_sub`).
                html = text[start_idx:end_idx]
                if raw and self.safe_mode:
                    html = self._sanitize_html(html)
                key = _hash_text(html)
                self.html_blocks[key] = html
                text = text[:start_idx] + "\n\n" + key + "\n\n" + text[end_idx:]

        if "xml" in self.extras:
            # Treat XML processing instructions and namespaced one-liner
            # tags as if they were block HTML tags. E.g., if standalone
            # (i.e. are their own paragraph), the following do not get 
            # wrapped in a <p> tag:
            #    <?foo bar?>
            #
            #    <xi:include xmlns:xi="http://www.w3.org/2001/XInclude" href="chapter_1.md"/>
            _xml_oneliner_re = _xml_oneliner_re_from_tab_width(self.tab_width)
            text = _xml_oneliner_re.sub(hash_html_block_sub, text)

        return text

    def _strip_link_definitions(self, text):
        # Strips link definitions from text, stores the URLs and titles in
        # hash references.
        less_than_tab = self.tab_width - 1
    
        # Link defs are in the form:
        #   [id]: url "optional title"
        _link_def_re = re.compile(r"""
            ^[ ]{0,%d}\[(.+)\]: # id = \1
              [ \t]*
              \n?               # maybe *one* newline
              [ \t]*
            <?(.+?)>?           # url = \2
              [ \t]*
            (?:
                \n?             # maybe one newline
                [ \t]*
                (?<=\s)         # lookbehind for whitespace
                ['"(]
                ([^\n]*)        # title = \3
                ['")]
                [ \t]*
            )?  # title is optional
            (?:\n+|\Z)
            """ % less_than_tab, re.X | re.M | re.U)
        return _link_def_re.sub(self._extract_link_def_sub, text)

    def _extract_link_def_sub(self, match):
        id, url, title = match.groups()
        key = id.lower()    # Link IDs are case-insensitive
        self.urls[key] = self._encode_amps_and_angles(url)
        if title:
            self.titles[key] = title.replace('"', '&quot;')
        return ""

    def _extract_footnote_def_sub(self, match):
        id, text = match.groups()
        text = _dedent(text, skip_first_line=not text.startswith('\n')).strip()
        normed_id = re.sub(r'\W', '-', id)
        # Ensure footnote text ends with a couple newlines (for some
        # block gamut matches).
        self.footnotes[normed_id] = text + "\n\n"
        return ""

    def _strip_footnote_definitions(self, text):
        """A footnote definition looks like this:

            [^note-id]: Text of the note.

                May include one or more indented paragraphs.

        Where,
        - The 'note-id' can be pretty much anything, though typically it
          is the number of the footnote.
        - The first paragraph may start on the next line, like so:
            
            [^note-id]:
                Text of the note.
        """
        less_than_tab = self.tab_width - 1
        footnote_def_re = re.compile(r'''
            ^[ ]{0,%d}\[\^(.+)\]:   # id = \1
            [ \t]*
            (                       # footnote text = \2
              # First line need not start with the spaces.
              (?:\s*.*\n+)
              (?:
                (?:[ ]{%d} | \t)  # Subsequent lines must be indented.
                .*\n+
              )*
            )
            # Lookahead for non-space at line-start, or end of doc.
            (?:(?=^[ ]{0,%d}\S)|\Z)
            ''' % (less_than_tab, self.tab_width, self.tab_width),
            re.X | re.M)
        return footnote_def_re.sub(self._extract_footnote_def_sub, text)


    _hr_res = [
        re.compile(r"^[ ]{0,2}([ ]?\*[ ]?){3,}[ \t]*$", re.M),
        re.compile(r"^[ ]{0,2}([ ]?\-[ ]?){3,}[ \t]*$", re.M),
        re.compile(r"^[ ]{0,2}([ ]?\_[ ]?){3,}[ \t]*$", re.M),
    ]

    def _run_block_gamut(self, text):
        # These are all the transformations that form block-level
        # tags like paragraphs, headers, and list items.

        text = self._do_headers(text)

        # Do Horizontal Rules:
        hr = "\n<hr"+self.empty_element_suffix+"\n"
        for hr_re in self._hr_res:
            text = hr_re.sub(hr, text)

        text = self._do_lists(text)

        if "pyshell" in self.extras:
            text = self._prepare_pyshell_blocks(text)

        text = self._do_code_blocks(text)

        text = self._do_block_quotes(text)

        # We already ran _HashHTMLBlocks() before, in Markdown(), but that
        # was to escape raw HTML in the original Markdown source. This time,
        # we're escaping the markup we've just created, so that we don't wrap
        # <p> tags around block-level tags.
        text = self._hash_html_blocks(text)

        text = self._form_paragraphs(text)

        return text

    def _pyshell_block_sub(self, match):
        lines = match.group(0).splitlines(0)
        _dedentlines(lines)
        indent = ' ' * self.tab_width
        s = ('\n' # separate from possible cuddled paragraph
             + indent + ('\n'+indent).join(lines)
             + '\n\n')
        return s
        
    def _prepare_pyshell_blocks(self, text):
        """Ensure that Python interactive shell sessions are put in
        code blocks -- even if not properly indented.
        """
        if ">>>" not in text:
            return text

        less_than_tab = self.tab_width - 1
        _pyshell_block_re = re.compile(r"""
            ^([ ]{0,%d})>>>[ ].*\n   # first line
            ^(\1.*\S+.*\n)*         # any number of subsequent lines
            ^\n                     # ends with a blank line
            """ % less_than_tab, re.M | re.X)

        return _pyshell_block_re.sub(self._pyshell_block_sub, text)

    def _run_span_gamut(self, text):
        # These are all the transformations that occur *within* block-level
        # tags like paragraphs, headers, and list items.
    
        text = self._do_code_spans(text)
    
        text = self._escape_special_chars(text)
    
        # Process anchor and image tags.
        text = self._do_links(text)
    
        # Make links out of things like `<http://example.com/>`
        # Must come after _do_links(), because you can use < and >
        # delimiters in inline links like [this](<url>).
        text = self._do_auto_links(text)

        if "link-patterns" in self.extras:
            text = self._do_link_patterns(text)
    
        text = self._encode_amps_and_angles(text)
    
        text = self._do_italics_and_bold(text)
    
        # Do hard breaks:
        text = re.sub(r" {2,}\n", " <br%s\n" % self.empty_element_suffix, text)
    
        return text

    # "Sorta" because auto-links are identified as "tag" tokens.
    _sorta_html_tokenize_re = re.compile(r"""
        (
            # tag
            </?         
            (?:\w+)                                     # tag name
            (?:\s+(?:[\w-]+:)?[\w-]+=(?:".*?"|'.*?'))*  # attributes
            \s*/?>
            |
            # auto-link (e.g., <http://www.activestate.com/>)
            <\w+[^>]*>
            |
            <!--.*?-->      # comment
            |
            <\?.*?\?>       # processing instruction
        )
        """, re.X)
    
    def _escape_special_chars(self, text):
        # Python markdown note: the HTML tokenization here differs from
        # that in Markdown.pl, hence the behaviour for subtle cases can
        # differ (I believe the tokenizer here does a better job because
        # it isn't susceptible to unmatched '<' and '>' in HTML tags).
        # Note, however, that '>' is not allowed in an auto-link URL
        # here.
        escaped = []
        is_html_markup = False
        for token in self._sorta_html_tokenize_re.split(text):
            if is_html_markup:
                # Within tags/HTML-comments/auto-links, encode * and _
                # so they don't conflict with their use in Markdown for
                # italics and strong.  We're replacing each such
                # character with its corresponding MD5 checksum value;
                # this is likely overkill, but it should prevent us from
                # colliding with the escape values by accident.
                escaped.append(token.replace('*', g_escape_table['*'])
                                    .replace('_', g_escape_table['_']))
            else:
                escaped.append(self._encode_backslash_escapes(token))
            is_html_markup = not is_html_markup
        return ''.join(escaped)

    def _hash_html_spans(self, text):
        # Used for safe_mode.

        def _is_auto_link(s):
            if ':' in s and self._auto_link_re.match(s):
                return True
            elif '@' in s and self._auto_email_link_re.match(s):
                return True
            return False

        tokens = []
        is_html_markup = False
        for token in self._sorta_html_tokenize_re.split(text):
            if is_html_markup and not _is_auto_link(token):
                sanitized = self._sanitize_html(token)
                key = _hash_text(sanitized)
                self.html_spans[key] = sanitized
                tokens.append(key)
            else:
                tokens.append(token)
            is_html_markup = not is_html_markup
        return ''.join(tokens)

    def _unhash_html_spans(self, text):
        for key, sanitized in self.html_spans.items():
            text = text.replace(key, sanitized)
        return text

    def _sanitize_html(self, s):
        if self.safe_mode == "replace":
            return self.html_removed_text
        elif self.safe_mode == "escape":
            replacements = [
                ('&', '&amp;'),
                ('<', '&lt;'),
                ('>', '&gt;'),
            ]
            for before, after in replacements:
                s = s.replace(before, after)
            return s
        else:
            raise MarkdownError("invalid value for 'safe_mode': %r (must be "
                                "'escape' or 'replace')" % self.safe_mode)

    _tail_of_inline_link_re = re.compile(r'''
          # Match tail of: [text](/url/) or [text](/url/ "title")
          \(            # literal paren
            [ \t]*
            (?P<url>            # \1
                <.*?>
                |
                .*?
            )
            [ \t]*
            (                   # \2
              (['"])            # quote char = \3
              (?P<title>.*?)
              \3                # matching quote
            )?                  # title is optional
          \)
        ''', re.X | re.S)
    _tail_of_reference_link_re = re.compile(r'''
          # Match tail of: [text][id]
          [ ]?          # one optional space
          (?:\n[ ]*)?   # one optional newline followed by spaces
          \[
            (?P<id>.*?)
          \]
        ''', re.X | re.S)

    def _do_links(self, text):
        """Turn Markdown link shortcuts into XHTML <a> and <img> tags.

        This is a combination of Markdown.pl's _DoAnchors() and
        _DoImages(). They are done together because that simplified the
        approach. It was necessary to use a different approach than
        Markdown.pl because of the lack of atomic matching support in
        Python's regex engine used in $g_nested_brackets.
        """
        MAX_LINK_TEXT_SENTINEL = 3000  # markdown2 issue 24

        # `anchor_allowed_pos` is used to support img links inside
        # anchors, but not anchors inside anchors. An anchor's start
        # pos must be `>= anchor_allowed_pos`.
        anchor_allowed_pos = 0

        curr_pos = 0
        while True: # Handle the next link.
            # The next '[' is the start of:
            # - an inline anchor:   [text](url "title")
            # - a reference anchor: [text][id]
            # - an inline img:      ![text](url "title")
            # - a reference img:    ![text][id]
            # - a footnote ref:     [^id]
            #   (Only if 'footnotes' extra enabled)
            # - a footnote defn:    [^id]: ...
            #   (Only if 'footnotes' extra enabled) These have already
            #   been stripped in _strip_footnote_definitions() so no
            #   need to watch for them.
            # - a link definition:  [id]: url "title"
            #   These have already been stripped in
            #   _strip_link_definitions() so no need to watch for them.
            # - not markup:         [...anything else...
            try:
                start_idx = text.index('[', curr_pos)
            except ValueError:
                break
            text_length = len(text)

            # Find the matching closing ']'.
            # Markdown.pl allows *matching* brackets in link text so we
            # will here too. Markdown.pl *doesn't* currently allow
            # matching brackets in img alt text -- we'll differ in that
            # regard.
            bracket_depth = 0
            for p in range(start_idx+1, min(start_idx+MAX_LINK_TEXT_SENTINEL, 
                                            text_length)):
                ch = text[p]
                if ch == ']':
                    bracket_depth -= 1
                    if bracket_depth < 0:
                        break
                elif ch == '[':
                    bracket_depth += 1
            else:
                # Closing bracket not found within sentinel length.
                # This isn't markup.
                curr_pos = start_idx + 1
                continue
            link_text = text[start_idx+1:p]

            # Possibly a footnote ref?
            if "footnotes" in self.extras and link_text.startswith("^"):
                normed_id = re.sub(r'\W', '-', link_text[1:])
                if normed_id in self.footnotes:
                    self.footnote_ids.append(normed_id)
                    result = '<sup class="footnote-ref" id="fnref-%s">' \
                             '<a href="#fn-%s">%s</a></sup>' \
                             % (normed_id, normed_id, len(self.footnote_ids))
                    text = text[:start_idx] + result + text[p+1:]
                else:
                    # This id isn't defined, leave the markup alone.
                    curr_pos = p+1
                continue

            # Now determine what this is by the remainder.
            p += 1
            if p == text_length:
                return text

            # Inline anchor or img?
            if text[p] == '(': # attempt at perf improvement
                match = self._tail_of_inline_link_re.match(text, p)
                if match:
                    # Handle an inline anchor or img.
                    is_img = start_idx > 0 and text[start_idx-1] == "!"
                    if is_img:
                        start_idx -= 1

                    url, title = match.group("url"), match.group("title")
                    if url and url[0] == '<':
                        url = url[1:-1]  # '<url>' -> 'url'
                    # We've got to encode these to avoid conflicting
                    # with italics/bold.
                    url = url.replace('*', g_escape_table['*']) \
                             .replace('_', g_escape_table['_'])
                    if title:
                        title_str = ' title="%s"' \
                            % title.replace('*', g_escape_table['*']) \
                                   .replace('_', g_escape_table['_']) \
                                   .replace('"', '&quot;')
                    else:
                        title_str = ''
                    if is_img:
                        result = '<img src="%s" alt="%s"%s%s' \
                            % (url, link_text.replace('"', '&quot;'),
                               title_str, self.empty_element_suffix)
                        curr_pos = start_idx + len(result)
                        text = text[:start_idx] + result + text[match.end():]
                    elif start_idx >= anchor_allowed_pos:
                        result_head = '<a href="%s"%s>' % (url, title_str)
                        result = '%s%s</a>' % (result_head, link_text)
                        # <img> allowed from curr_pos on, <a> from
                        # anchor_allowed_pos on.
                        curr_pos = start_idx + len(result_head)
                        anchor_allowed_pos = start_idx + len(result)
                        text = text[:start_idx] + result + text[match.end():]
                    else:
                        # Anchor not allowed here.
                        curr_pos = start_idx + 1
                    continue

            # Reference anchor or img?
            else:
                match = self._tail_of_reference_link_re.match(text, p)
                if match:
                    # Handle a reference-style anchor or img.
                    is_img = start_idx > 0 and text[start_idx-1] == "!"
                    if is_img:
                        start_idx -= 1
                    link_id = match.group("id").lower()
                    if not link_id:
                        link_id = link_text.lower()  # for links like [this][]
                    if link_id in self.urls:
                        url = self.urls[link_id]
                        # We've got to encode these to avoid conflicting
                        # with italics/bold.
                        url = url.replace('*', g_escape_table['*']) \
                                 .replace('_', g_escape_table['_'])
                        title = self.titles.get(link_id)
                        if title:
                            title = title.replace('*', g_escape_table['*']) \
                                         .replace('_', g_escape_table['_'])
                            title_str = ' title="%s"' % title
                        else:
                            title_str = ''
                        if is_img:
                            result = '<img src="%s" alt="%s"%s%s' \
                                % (url, link_text.replace('"', '&quot;'),
                                   title_str, self.empty_element_suffix)
                            curr_pos = start_idx + len(result)
                            text = text[:start_idx] + result + text[match.end():]
                        elif start_idx >= anchor_allowed_pos:
                            result = '<a href="%s"%s>%s</a>' \
                                % (url, title_str, link_text)
                            result_head = '<a href="%s"%s>' % (url, title_str)
                            result = '%s%s</a>' % (result_head, link_text)
                            # <img> allowed from curr_pos on, <a> from
                            # anchor_allowed_pos on.
                            curr_pos = start_idx + len(result_head)
                            anchor_allowed_pos = start_idx + len(result)
                            text = text[:start_idx] + result + text[match.end():]
                        else:
                            # Anchor not allowed here.
                            curr_pos = start_idx + 1
                    else:
                        # This id isn't defined, leave the markup alone.
                        curr_pos = match.end()
                    continue

            # Otherwise, it isn't markup.
            curr_pos = start_idx + 1

        return text 


    _setext_h_re = re.compile(r'^(.+)[ \t]*\n(=+|-+)[ \t]*\n+', re.M)
    def _setext_h_sub(self, match):
        n = {"=": 1, "-": 2}[match.group(2)[0]]
        demote_headers = self.extras.get("demote-headers")
        if demote_headers:
            n = min(n + demote_headers, 6)
        return "<h%d>%s</h%d>\n\n" \
               % (n, self._run_span_gamut(match.group(1)), n)

    _atx_h_re = re.compile(r'''
        ^(\#{1,6})  # \1 = string of #'s
        [ \t]*
        (.+?)       # \2 = Header text
        [ \t]*
        (?<!\\)     # ensure not an escaped trailing '#'
        \#*         # optional closing #'s (not counted)
        \n+
        ''', re.X | re.M)
    def _atx_h_sub(self, match):
        n = len(match.group(1))
        demote_headers = self.extras.get("demote-headers")
        if demote_headers:
            n = min(n + demote_headers, 6)
        return "<h%d>%s</h%d>\n\n" \
               % (n, self._run_span_gamut(match.group(2)), n)

    def _do_headers(self, text):
        # Setext-style headers:
        #     Header 1
        #     ========
        #  
        #     Header 2
        #     --------
        text = self._setext_h_re.sub(self._setext_h_sub, text)

        # atx-style headers:
        #   # Header 1
        #   ## Header 2
        #   ## Header 2 with closing hashes ##
        #   ...
        #   ###### Header 6
        text = self._atx_h_re.sub(self._atx_h_sub, text)

        return text


    _marker_ul_chars  = '*+-'
    _marker_any = r'(?:[%s]|\d+\.)' % _marker_ul_chars
    _marker_ul = '(?:[%s])' % _marker_ul_chars
    _marker_ol = r'(?:\d+\.)'

    def _list_sub(self, match):
        lst = match.group(1)
        lst_type = match.group(3) in self._marker_ul_chars and "ul" or "ol"
        result = self._process_list_items(lst)
        if self.list_level:
            return "<%s>\n%s</%s>\n" % (lst_type, result, lst_type)
        else:
            return "<%s>\n%s</%s>\n\n" % (lst_type, result, lst_type)

    def _do_lists(self, text):
        # Form HTML ordered (numbered) and unordered (bulleted) lists.

        for marker_pat in (self._marker_ul, self._marker_ol):
            # Re-usable pattern to match any entire ul or ol list:
            less_than_tab = self.tab_width - 1
            whole_list = r'''
                (                   # \1 = whole list
                  (                 # \2
                    [ ]{0,%d}
                    (%s)            # \3 = first list item marker
                    [ \t]+
                  )
                  (?:.+?)
                  (                 # \4
                      \Z
                    |
                      \n{2,}
                      (?=\S)
                      (?!           # Negative lookahead for another list item marker
                        [ \t]*
                        %s[ \t]+
                      )
                  )
                )
            ''' % (less_than_tab, marker_pat, marker_pat)
        
            # We use a different prefix before nested lists than top-level lists.
            # See extended comment in _process_list_items().
            #
            # Note: There's a bit of duplication here. My original implementation
            # created a scalar regex pattern as the conditional result of the test on
            # $g_list_level, and then only ran the $text =~ s{...}{...}egmx
            # substitution once, using the scalar as the pattern. This worked,
            # everywhere except when running under MT on my hosting account at Pair
            # Networks. There, this caused all rebuilds to be killed by the reaper (or
            # perhaps they crashed, but that seems incredibly unlikely given that the
            # same script on the same server ran fine *except* under MT. I've spent
            # more time trying to figure out why this is happening than I'd like to
            # admit. My only guess, backed up by the fact that this workaround works,
            # is that Perl optimizes the substition when it can figure out that the
            # pattern will never change, and when this optimization isn't on, we run
            # afoul of the reaper. Thus, the slightly redundant code to that uses two
            # static s/// patterns rather than one conditional pattern.

            if self.list_level:
                sub_list_re = re.compile("^"+whole_list, re.X | re.M | re.S)
                text = sub_list_re.sub(self._list_sub, text)
            else:
                list_re = re.compile(r"(?:(?<=\n\n)|\A\n?)"+whole_list,
                                     re.X | re.M | re.S)
                text = list_re.sub(self._list_sub, text)

        return text
    
    _list_item_re = re.compile(r'''
        (\n)?               # leading line = \1
        (^[ \t]*)           # leading whitespace = \2
        (%s) [ \t]+         # list marker = \3
        ((?:.+?)            # list item text = \4
         (\n{1,2}))         # eols = \5
        (?= \n* (\Z | \2 (%s) [ \t]+))
        ''' % (_marker_any, _marker_any),
        re.M | re.X | re.S)

    _last_li_endswith_two_eols = False
    def _list_item_sub(self, match):
        item = match.group(4)
        leading_line = match.group(1)
        leading_space = match.group(2)
        if leading_line or "\n\n" in item or self._last_li_endswith_two_eols:
            item = self._run_block_gamut(self._outdent(item))
        else:
            # Recursion for sub-lists:
            item = self._do_lists(self._outdent(item))
            if item.endswith('\n'):
                item = item[:-1]
            item = self._run_span_gamut(item)
        self._last_li_endswith_two_eols = (len(match.group(5)) == 2)
        return "<li>%s</li>\n" % item

    def _process_list_items(self, list_str):
        # Process the contents of a single ordered or unordered list,
        # splitting it into individual list items.
    
        # The $g_list_level global keeps track of when we're inside a list.
        # Each time we enter a list, we increment it; when we leave a list,
        # we decrement. If it's zero, we're not in a list anymore.
        #
        # We do this because when we're not inside a list, we want to treat
        # something like this:
        #
        #       I recommend upgrading to version
        #       8. Oops, now this line is treated
        #       as a sub-list.
        #
        # As a single paragraph, despite the fact that the second line starts
        # with a digit-period-space sequence.
        #
        # Whereas when we're inside a list (or sub-list), that line will be
        # treated as the start of a sub-list. What a kludge, huh? This is
        # an aspect of Markdown's syntax that's hard to parse perfectly
        # without resorting to mind-reading. Perhaps the solution is to
        # change the syntax rules such that sub-lists must start with a
        # starting cardinal number; e.g. "1." or "a.".
        self.list_level += 1
        self._last_li_endswith_two_eols = False
        list_str = list_str.rstrip('\n') + '\n'
        list_str = self._list_item_re.sub(self._list_item_sub, list_str)
        self.list_level -= 1
        return list_str

    def _get_pygments_lexer(self, lexer_name):
        try:
            from pygments import lexers, util
        except ImportError:
            return None
        try:
            return lexers.get_lexer_by_name(lexer_name)
        except util.ClassNotFound:
            return None

    def _color_with_pygments(self, codeblock, lexer, **formatter_opts):
        import pygments
        import pygments.formatters

        class HtmlCodeFormatter(pygments.formatters.HtmlFormatter):
            def _wrap_code(self, inner):
                """A function for use in a Pygments Formatter which
                wraps in <code> tags.
                """
                yield 0, "<code>"
                for tup in inner:
                    yield tup 
                yield 0, "</code>"

            def wrap(self, source, outfile):
                """Return the source with a code, pre, and div."""
                return self._wrap_div(self._wrap_pre(self._wrap_code(source)))

        formatter = HtmlCodeFormatter(cssclass="codehilite", **formatter_opts)
        return pygments.highlight(codeblock, lexer, formatter)

    def _code_block_sub(self, match):
        codeblock = match.group(1)
        codeblock = self._outdent(codeblock)
        codeblock = self._detab(codeblock)
        codeblock = codeblock.lstrip('\n')  # trim leading newlines
        codeblock = codeblock.rstrip()      # trim trailing whitespace

        if "code-color" in self.extras and codeblock.startswith(":::"):
            lexer_name, rest = codeblock.split('\n', 1)
            lexer_name = lexer_name[3:].strip()
            lexer = self._get_pygments_lexer(lexer_name)
            codeblock = rest.lstrip("\n")   # Remove lexer declaration line.
            if lexer:
                formatter_opts = self.extras['code-color'] or {}
                colored = self._color_with_pygments(codeblock, lexer,
                                                    **formatter_opts)
                return "\n\n%s\n\n" % colored

        codeblock = self._encode_code(codeblock)
        return "\n\n<pre><code>%s\n</code></pre>\n\n" % codeblock

    def _do_code_blocks(self, text):
        """Process Markdown `<pre><code>` blocks."""
        code_block_re = re.compile(r'''
            (?:\n\n|\A)
            (               # $1 = the code block -- one or more lines, starting with a space/tab
              (?:
                (?:[ ]{%d} | \t)  # Lines must start with a tab or a tab-width of spaces
                .*\n+
              )+
            )
            ((?=^[ ]{0,%d}\S)|\Z)   # Lookahead for non-space at line-start, or end of doc
            ''' % (self.tab_width, self.tab_width),
            re.M | re.X)

        return code_block_re.sub(self._code_block_sub, text)


    # Rules for a code span:
    # - backslash escapes are not interpreted in a code span
    # - to include one or or a run of more backticks the delimiters must
    #   be a longer run of backticks
    # - cannot start or end a code span with a backtick; pad with a
    #   space and that space will be removed in the emitted HTML
    # See `test/tm-cases/escapes.text` for a number of edge-case
    # examples.
    _code_span_re = re.compile(r'''
            (?<!\\)
            (`+)        # \1 = Opening run of `
            (?!`)       # See Note A test/tm-cases/escapes.text
            (.+?)       # \2 = The code block
            (?<!`)
            \1          # Matching closer
            (?!`)
        ''', re.X | re.S)

    def _code_span_sub(self, match):
        c = match.group(2).strip(" \t")
        c = self._encode_code(c)
        return "<code>%s</code>" % c

    def _do_code_spans(self, text):
        #   *   Backtick quotes are used for <code></code> spans.
        # 
        #   *   You can use multiple backticks as the delimiters if you want to
        #       include literal backticks in the code span. So, this input:
        #     
        #         Just type ``foo `bar` baz`` at the prompt.
        #     
        #       Will translate to:
        #     
        #         <p>Just type <code>foo `bar` baz</code> at the prompt.</p>
        #     
        #       There's no arbitrary limit to the number of backticks you
        #       can use as delimters. If you need three consecutive backticks
        #       in your code, use four for delimiters, etc.
        #
        #   *   You can use spaces to get literal backticks at the edges:
        #     
        #         ... type `` `bar` `` ...
        #     
        #       Turns to:
        #     
        #         ... type <code>`bar`</code> ...
        return self._code_span_re.sub(self._code_span_sub, text)

    def _encode_code(self, text):
        """Encode/escape certain characters inside Markdown code runs.
        The point is that in code, these characters are literals,
        and lose their special Markdown meanings.
        """
        replacements = [
            # Encode all ampersands; HTML entities are not
            # entities within a Markdown code span.
            ('&', '&amp;'),
            # Do the angle bracket song and dance:
            ('<', '&lt;'),
            ('>', '&gt;'),
            # Now, escape characters that are magic in Markdown:
            ('*', g_escape_table['*']),
            ('_', g_escape_table['_']),
            ('{', g_escape_table['{']),
            ('}', g_escape_table['}']),
            ('[', g_escape_table['[']),
            (']', g_escape_table[']']),
            ('\\', g_escape_table['\\']),
        ]
        for before, after in replacements:
            text = text.replace(before, after)
        return text

    _strong_re = re.compile(r"(\*\*|__)(?=\S)(.+?[*_]*)(?<=\S)\1", re.S)
    _em_re = re.compile(r"(\*|_)(?=\S)(.+?)(?<=\S)\1", re.S)
    _code_friendly_strong_re = re.compile(r"\*\*(?=\S)(.+?[*_]*)(?<=\S)\*\*", re.S)
    _code_friendly_em_re = re.compile(r"\*(?=\S)(.+?)(?<=\S)\*", re.S)
    def _do_italics_and_bold(self, text):
        # <strong> must go first:
        if "code-friendly" in self.extras:
            text = self._code_friendly_strong_re.sub(r"<strong>\1</strong>", text)
            text = self._code_friendly_em_re.sub(r"<em>\1</em>", text)
        else:
            text = self._strong_re.sub(r"<strong>\2</strong>", text)
            text = self._em_re.sub(r"<em>\2</em>", text)
        return text
    

    _block_quote_re = re.compile(r'''
        (                           # Wrap whole match in \1
          (
            ^[ \t]*>[ \t]?          # '>' at the start of a line
              .+\n                  # rest of the first line
            (.+\n)*                 # subsequent consecutive lines
            \n*                     # blanks
          )+
        )
        ''', re.M | re.X)
    _bq_one_level_re = re.compile('^[ \t]*>[ \t]?', re.M);

    _html_pre_block_re = re.compile(r'(\s*<pre>.+?</pre>)', re.S)
    def _dedent_two_spaces_sub(self, match):
        return re.sub(r'(?m)^  ', '', match.group(1))

    def _block_quote_sub(self, match):
        bq = match.group(1)
        bq = self._bq_one_level_re.sub('', bq)  # trim one level of quoting
        bq = self._ws_only_line_re.sub('', bq)  # trim whitespace-only lines
        bq = self._run_block_gamut(bq)          # recurse

        bq = re.sub('(?m)^', '  ', bq)
        # These leading spaces screw with <pre> content, so we need to fix that:
        bq = self._html_pre_block_re.sub(self._dedent_two_spaces_sub, bq)

        return "<blockquote>\n%s\n</blockquote>\n\n" % bq

    def _do_block_quotes(self, text):
        if '>' not in text:
            return text
        return self._block_quote_re.sub(self._block_quote_sub, text)

    def _form_paragraphs(self, text):
        # Strip leading and trailing lines:
        text = text.strip('\n')

        # Wrap <p> tags.
        grafs = re.split(r"\n{2,}", text)
        for i, graf in enumerate(grafs):
            if graf in self.html_blocks:
                # Unhashify HTML blocks
                grafs[i] = self.html_blocks[graf]
            else:
                # Wrap <p> tags.
                graf = self._run_span_gamut(graf)
                grafs[i] = "<p>" + graf.lstrip(" \t") + "</p>"

        return "\n\n".join(grafs)

    def _add_footnotes(self, text):
        if self.footnotes:
            footer = [
                '<div class="footnotes">',
                '<hr' + self.empty_element_suffix,
                '<ol>',
            ]
            for i, id in enumerate(self.footnote_ids):
                if i != 0:
                    footer.append('')
                footer.append('<li id="fn-%s">' % id)
                footer.append(self._run_block_gamut(self.footnotes[id]))
                backlink = ('<a href="#fnref-%s" '
                    'class="footnoteBackLink" '
                    'title="Jump back to footnote %d in the text.">'
                    '&#8617;</a>' % (id, i+1))
                if footer[-1].endswith("</p>"):
                    footer[-1] = footer[-1][:-len("</p>")] \
                        + '&nbsp;' + backlink + "</p>"
                else:
                    footer.append("\n<p>%s</p>" % backlink)
                footer.append('</li>')
            footer.append('</ol>')
            footer.append('</div>')
            return text + '\n\n' + '\n'.join(footer)
        else:
            return text

    # Ampersand-encoding based entirely on Nat Irons's Amputator MT plugin:
    #   http://bumppo.net/projects/amputator/
    _ampersand_re = re.compile(r'&(?!#?[xX]?(?:[0-9a-fA-F]+|\w+);)')
    _naked_lt_re = re.compile(r'<(?![a-z/?\$!])', re.I)
    _naked_gt_re = re.compile(r'''(?<![a-z?!/'"-])>''', re.I)

    def _encode_amps_and_angles(self, text):
        # Smart processing for ampersands and angle brackets that need
        # to be encoded.
        text = self._ampersand_re.sub('&amp;', text)
    
        # Encode naked <'s
        text = self._naked_lt_re.sub('&lt;', text)

        # Encode naked >'s
        # Note: Other markdown implementations (e.g. Markdown.pl, PHP
        # Markdown) don't do this.
        text = self._naked_gt_re.sub('&gt;', text)
        return text

    def _encode_backslash_escapes(self, text):
        for ch, escape in g_escape_table.items():
            text = text.replace("\\"+ch, escape)
        return text

    _auto_link_re = re.compile(r'<((https?|ftp):[^\'">\s]+)>', re.I)
    def _auto_link_sub(self, match):
        g1 = match.group(1)
        return '<a href="%s">%s</a>' % (g1, g1)

    _auto_email_link_re = re.compile(r"""
          <
           (?:mailto:)?
          (
              [-.\w]+
              \@
              [-\w]+(\.[-\w]+)*\.[a-z]+
          )
          >
        """, re.I | re.X | re.U)
    def _auto_email_link_sub(self, match):
        return self._encode_email_address(
            self._unescape_special_chars(match.group(1)))

    def _do_auto_links(self, text):
        text = self._auto_link_re.sub(self._auto_link_sub, text)
        text = self._auto_email_link_re.sub(self._auto_email_link_sub, text)
        return text

    def _encode_email_address(self, addr):
        #  Input: an email address, e.g. "foo@example.com"
        #
        #  Output: the email address as a mailto link, with each character
        #      of the address encoded as either a decimal or hex entity, in
        #      the hopes of foiling most address harvesting spam bots. E.g.:
        #
        #    <a href="&#x6D;&#97;&#105;&#108;&#x74;&#111;:&#102;&#111;&#111;&#64;&#101;
        #       x&#x61;&#109;&#x70;&#108;&#x65;&#x2E;&#99;&#111;&#109;">&#102;&#111;&#111;
        #       &#64;&#101;x&#x61;&#109;&#x70;&#108;&#x65;&#x2E;&#99;&#111;&#109;</a>
        #
        #  Based on a filter by Matthew Wickline, posted to the BBEdit-Talk
        #  mailing list: <http://tinyurl.com/yu7ue>
        chars = [_xml_encode_email_char_at_random(ch)
                 for ch in "mailto:" + addr]
        # Strip the mailto: from the visible part.
        addr = '<a href="%s">%s</a>' \
               % (''.join(chars), ''.join(chars[7:]))
        return addr
    
    def _do_link_patterns(self, text):
        """Caveat emptor: there isn't much guarding against link
        patterns being formed inside other standard Markdown links, e.g.
        inside a [link def][like this].

        Dev Notes: *Could* consider prefixing regexes with a negative
        lookbehind assertion to attempt to guard against this.
        """
        link_from_hash = {}
        for regex, repl in self.link_patterns:
            replacements = []
            for match in regex.finditer(text):
                if hasattr(repl, "__call__"):
                    href = repl(match)
                else:
                    href = match.expand(repl)
                replacements.append((match.span(), href))
            for (start, end), href in reversed(replacements):
                escaped_href = (
                    href.replace('"', '&quot;')  # b/c of attr quote
                        # To avoid markdown <em> and <strong>:
                        .replace('*', g_escape_table['*'])
                        .replace('_', g_escape_table['_']))
                link = '<a href="%s">%s</a>' % (escaped_href, text[start:end])
                hash = md5(link).hexdigest()
                link_from_hash[hash] = link
                text = text[:start] + hash + text[end:]
        for hash, link in link_from_hash.items():
            text = text.replace(hash, link)
        return text
    
    def _unescape_special_chars(self, text):
        # Swap back in all the special characters we've hidden.
        for ch, hash in g_escape_table.items():
            text = text.replace(hash, ch)
        return text

    def _outdent(self, text):
        # Remove one level of line-leading tabs or spaces
        return self._outdent_re.sub('', text)


class MarkdownWithExtras(Markdown):
    """A markdowner class that enables most extras:

    - footnotes
    - code-color (only has effect if 'pygments' Python module on path)

    These are not included:
    - pyshell (specific to Python-related documenting)
    - code-friendly (because it *disables* part of the syntax)
    - link-patterns (because you need to specify some actual
      link-patterns anyway)
    """
    extras = ["footnotes", "code-color"]


#---- internal support functions

# From http://aspn.activestate.com/ASPN/Cookbook/Python/Recipe/52549
def _curry(*args, **kwargs):
    function, args = args[0], args[1:]
    def result(*rest, **kwrest):
        combined = kwargs.copy()
        combined.update(kwrest)
        return function(*args + rest, **combined)
    return result

# Recipe: regex_from_encoded_pattern (1.0)
def _regex_from_encoded_pattern(s):
    """'foo'    -> re.compile(re.escape('foo'))
       '/foo/'  -> re.compile('foo')
       '/foo/i' -> re.compile('foo', re.I)
    """
    if s.startswith('/') and s.rfind('/') != 0:
        # Parse it: /PATTERN/FLAGS
        idx = s.rfind('/')
        pattern, flags_str = s[1:idx], s[idx+1:]
        flag_from_char = {
            "i": re.IGNORECASE,
            "l": re.LOCALE,
            "s": re.DOTALL,
            "m": re.MULTILINE,
            "u": re.UNICODE,
        }
        flags = 0
        for char in flags_str:
            try:
                flags |= flag_from_char[char]
            except KeyError:
                raise ValueError("unsupported regex flag: '%s' in '%s' "
                                 "(must be one of '%s')"
                                 % (char, s, ''.join(flag_from_char.keys())))
        return re.compile(s[1:idx], flags)
    else: # not an encoded regex
        return re.compile(re.escape(s))

# Recipe: dedent (0.1.2)
def _dedentlines(lines, tabsize=8, skip_first_line=False):
    """_dedentlines(lines, tabsize=8, skip_first_line=False) -> dedented lines
    
        "lines" is a list of lines to dedent.
        "tabsize" is the tab width to use for indent width calculations.
        "skip_first_line" is a boolean indicating if the first line should
            be skipped for calculating the indent width and for dedenting.
            This is sometimes useful for docstrings and similar.
    
    Same as dedent() except operates on a sequence of lines. Note: the
    lines list is modified **in-place**.
    """
    DEBUG = False
    if DEBUG: 
        print "dedent: dedent(..., tabsize=%d, skip_first_line=%r)"\
              % (tabsize, skip_first_line)
    indents = []
    margin = None
    for i, line in enumerate(lines):
        if i == 0 and skip_first_line: continue
        indent = 0
        for ch in line:
            if ch == ' ':
                indent += 1
            elif ch == '\t':
                indent += tabsize - (indent % tabsize)
            elif ch in '\r\n':
                continue # skip all-whitespace lines
            else:
                break
        else:
            continue # skip all-whitespace lines
        if DEBUG: print "dedent: indent=%d: %r" % (indent, line)
        if margin is None:
            margin = indent
        else:
            margin = min(margin, indent)
    if DEBUG: print "dedent: margin=%r" % margin

    if margin is not None and margin > 0:
        for i, line in enumerate(lines):
            if i == 0 and skip_first_line: continue
            removed = 0
            for j, ch in enumerate(line):
                if ch == ' ':
                    removed += 1
                elif ch == '\t':
                    removed += tabsize - (removed % tabsize)
                elif ch in '\r\n':
                    if DEBUG: print "dedent: %r: EOL -> strip up to EOL" % line
                    lines[i] = lines[i][j:]
                    break
                else:
                    raise ValueError("unexpected non-whitespace char %r in "
                                     "line %r while removing %d-space margin"
                                     % (ch, line, margin))
                if DEBUG:
                    print "dedent: %r: %r -> removed %d/%d"\
                          % (line, ch, removed, margin)
                if removed == margin:
                    lines[i] = lines[i][j+1:]
                    break
                elif removed > margin:
                    lines[i] = ' '*(removed-margin) + lines[i][j+1:]
                    break
            else:
                if removed:
                    lines[i] = lines[i][removed:]
    return lines

def _dedent(text, tabsize=8, skip_first_line=False):
    """_dedent(text, tabsize=8, skip_first_line=False) -> dedented text

        "text" is the text to dedent.
        "tabsize" is the tab width to use for indent width calculations.
        "skip_first_line" is a boolean indicating if the first line should
            be skipped for calculating the indent width and for dedenting.
            This is sometimes useful for docstrings and similar.
    
    textwrap.dedent(s), but don't expand tabs to spaces
    """
    lines = text.splitlines(1)
    _dedentlines(lines, tabsize=tabsize, skip_first_line=skip_first_line)
    return ''.join(lines)


class _memoized(object):
   """Decorator that caches a function's return value each time it is called.
   If called later with the same arguments, the cached value is returned, and
   not re-evaluated.

   http://wiki.python.org/moin/PythonDecoratorLibrary
   """
   def __init__(self, func):
      self.func = func
      self.cache = {}
   def __call__(self, *args):
      try:
         return self.cache[args]
      except KeyError:
         self.cache[args] = value = self.func(*args)
         return value
      except TypeError:
         # uncachable -- for instance, passing a list as an argument.
         # Better to not cache than to blow up entirely.
         return self.func(*args)
   def __repr__(self):
      """Return the function's docstring."""
      return self.func.__doc__


def _xml_oneliner_re_from_tab_width(tab_width):
    """Standalone XML processing instruction regex."""
    return re.compile(r"""
        (?:
            (?<=\n\n)       # Starting after a blank line
            |               # or
            \A\n?           # the beginning of the doc
        )
        (                           # save in $1
            [ ]{0,%d}
            (?:
                <\?\w+\b\s+.*?\?>   # XML processing instruction
                |
                <\w+:\w+\b\s+.*?/>  # namespaced single tag
            )
            [ \t]*
            (?=\n{2,}|\Z)       # followed by a blank line or end of document
        )
        """ % (tab_width - 1), re.X)
_xml_oneliner_re_from_tab_width = _memoized(_xml_oneliner_re_from_tab_width)

def _hr_tag_re_from_tab_width(tab_width):
     return re.compile(r"""
        (?:
            (?<=\n\n)       # Starting after a blank line
            |               # or
            \A\n?           # the beginning of the doc
        )
        (                       # save in \1
            [ ]{0,%d}
            <(hr)               # start tag = \2
            \b                  # word break
            ([^<>])*?           # 
            /?>                 # the matching end tag
            [ \t]*
            (?=\n{2,}|\Z)       # followed by a blank line or end of document
        )
        """ % (tab_width - 1), re.X)
_hr_tag_re_from_tab_width = _memoized(_hr_tag_re_from_tab_width)


def _xml_encode_email_char_at_random(ch):
    r = random()
    # Roughly 10% raw, 45% hex, 45% dec.
    # '@' *must* be encoded. I [John Gruber] insist.
    # Issue 26: '_' must be encoded.
    if r > 0.9 and ch not in "@_":
        return ch
    elif r < 0.45:
        # The [1:] is to drop leading '0': 0x63 -> x63
        return '&#%s;' % hex(ord(ch))[1:]
    else:
        return '&#%s;' % ord(ch)

def _hash_text(text):
    return 'md5:'+md5(text.encode("utf-8")).hexdigest()


#---- mainline

class _NoReflowFormatter(optparse.IndentedHelpFormatter):
    """An optparse formatter that does NOT reflow the description."""
    def format_description(self, description):
        return description or ""

def _test():
    import doctest
    doctest.testmod()

def main(argv=None):
    if argv is None:
        argv = sys.argv
    if not logging.root.handlers:
        logging.basicConfig()

    usage = "usage: %prog [PATHS...]"
    version = "%prog "+__version__
    parser = optparse.OptionParser(prog="markdown2", usage=usage,
        version=version, description=cmdln_desc,
        formatter=_NoReflowFormatter())
    parser.add_option("-v", "--verbose", dest="log_level",
                      action="store_const", const=logging.DEBUG,
                      help="more verbose output")
    parser.add_option("--encoding",
                      help="specify encoding of text content")
    parser.add_option("--html4tags", action="store_true", default=False, 
                      help="use HTML 4 style for empty element tags")
    parser.add_option("-s", "--safe", metavar="MODE", dest="safe_mode",
                      help="sanitize literal HTML: 'escape' escapes "
                           "HTML meta chars, 'replace' replaces with an "
                           "[HTML_REMOVED] note")
    parser.add_option("-x", "--extras", action="append",
                      help="Turn on specific extra features (not part of "
                           "the core Markdown spec). Supported values: "
                           "'code-friendly' disables _/__ for emphasis; "
                           "'code-color' adds code-block syntax coloring; "
                           "'link-patterns' adds auto-linking based on patterns; "
                           "'footnotes' adds the footnotes syntax;"
                           "'xml' passes one-liner processing instructions and namespaced XML tags;"
                           "'pyshell' to put unindented Python interactive shell sessions in a <code> block.")
    parser.add_option("--use-file-vars",
                      help="Look for and use Emacs-style 'markdown-extras' "
                           "file var to turn on extras. See "
                           "<http://code.google.com/p/python-markdown2/wiki/Extras>.")
    parser.add_option("--link-patterns-file",
                      help="path to a link pattern file")
    parser.add_option("--self-test", action="store_true",
                      help="run internal self-tests (some doctests)")
    parser.add_option("--compare", action="store_true",
                      help="run against Markdown.pl as well (for testing)")
    parser.set_defaults(log_level=logging.INFO, compare=False,
                        encoding="utf-8", safe_mode=None, use_file_vars=False)
    opts, paths = parser.parse_args()
    log.setLevel(opts.log_level)

    if opts.self_test:
        return _test()

    if opts.extras:
        extras = {}
        for s in opts.extras:
            splitter = re.compile("[,;: ]+")
            for e in splitter.split(s):
                if '=' in e:
                    ename, earg = e.split('=', 1)
                    try:
                        earg = int(earg)
                    except ValueError:
                        pass
                else:
                    ename, earg = e, None
                extras[ename] = earg
    else:
        extras = None

    if opts.link_patterns_file:
        link_patterns = []
        f = open(opts.link_patterns_file)
        try:
            for i, line in enumerate(f.readlines()):
                if not line.strip(): continue
                if line.lstrip().startswith("#"): continue
                try:
                    pat, href = line.rstrip().rsplit(None, 1)
                except ValueError:
                    raise MarkdownError("%s:%d: invalid link pattern line: %r"
                                        % (opts.link_patterns_file, i+1, line))
                link_patterns.append(
                    (_regex_from_encoded_pattern(pat), href))
        finally:
            f.close()
    else:
        link_patterns = None

    from os.path import join, dirname, abspath, exists
    markdown_pl = join(dirname(dirname(abspath(__file__))), "test",
                       "Markdown.pl")
    for path in paths:
        if opts.compare:
            print "==== Markdown.pl ===="
            perl_cmd = 'perl %s "%s"' % (markdown_pl, path)
            o = os.popen(perl_cmd)
            perl_html = o.read()
            o.close()
            sys.stdout.write(perl_html)
            print "==== markdown2.py ===="
        html = markdown_path(path, encoding=opts.encoding,
                             html4tags=opts.html4tags,
                             safe_mode=opts.safe_mode,
                             extras=extras, link_patterns=link_patterns,
                             use_file_vars=opts.use_file_vars)
        sys.stdout.write(
            html.encode(sys.stdout.encoding or "utf-8", 'xmlcharrefreplace'))
        if opts.compare:
            test_dir = join(dirname(dirname(abspath(__file__))), "test")
            if exists(join(test_dir, "test_markdown2.py")):
                sys.path.insert(0, test_dir)
                from test_markdown2 import norm_html_from_html
                norm_html = norm_html_from_html(html)
                norm_perl_html = norm_html_from_html(perl_html)
            else:
                norm_html = html
                norm_perl_html = perl_html
            print "==== match? %r ====" % (norm_perl_html == norm_html)


if __name__ == "__main__":
    sys.exit( main(sys.argv) )

