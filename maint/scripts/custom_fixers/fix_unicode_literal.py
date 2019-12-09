from lib2to3 import fixer_base
from lib2to3.fixer_util import String


class FixUnicodeLiteral(fixer_base.BaseFix):
    BM_compatible = True
    PATTERN = """
    power< 'u'
        trailer<
            '('
                arg=any
            ')'
        >
    >
    """

    def transform(self, node, results):
        arg = results["arg"]
        node.replace(String('u' + arg.value, prefix=node.prefix))
