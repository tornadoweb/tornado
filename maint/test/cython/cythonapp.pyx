import cython
from tornado import gen
import pythonmodule

async def native_coroutine():
    x = await pythonmodule.hello()
    if x != "hello":
        raise ValueError("expected hello, got %r" % x)
    return "goodbye"

@gen.coroutine
def decorated_coroutine():
    x = yield pythonmodule.hello()
    if x != "hello":
        raise ValueError("expected hello, got %r" % x)
    return "goodbye"

# The binding directive is necessary for compatibility with
# ArgReplacer (and therefore return_future), but only because
# this is a static function.
@cython.binding(True)
def function_with_args(one, two, three):
    return (one, two, three)


class AClass:
    # methods don't need the binding directive.
    def method_with_args(one, two, three):
        return (one, two, three)
