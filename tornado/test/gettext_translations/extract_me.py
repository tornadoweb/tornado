# Dummy source file to allow creation of the initial .po file in the
# same way as a real project.  I'm not entirely sure about the real
# workflow here, but this seems to work.
#
# 1) xgettext --language=Python --keyword=_:1,2 -d tornado_test extract_me.py -o tornado_test.po
# 2) Edit tornado_test.po, setting CHARSET and setting msgstr
# 3) msgfmt tornado_test.po -o tornado_test.mo
# 4) Put the file in the proper location: $LANG/LC_MESSAGES
_("school")
