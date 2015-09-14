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
