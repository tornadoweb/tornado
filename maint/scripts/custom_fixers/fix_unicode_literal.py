import re
from lib2to3.pgen2 import token
from lib2to3 import fixer_base
from lib2to3.fixer_util import Name, Call

_literal_re = re.compile(ur"[uU][rR]?[\'\"]")

class FixUnicodeLiteral(fixer_base.BaseFix):
    BM_compatible = True
    PATTERN = """STRING"""

    def transform(self, node, results):
        if node.type == token.STRING and _literal_re.match(node.value):
            new = node.clone()
            new.value = new.value[1:]
            new.prefix = ''
            node.replace(Call(Name(u'u', prefix=node.prefix), [new]))
