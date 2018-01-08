from tornado import gen


@gen.coroutine
def hello():
    yield gen.sleep(0.001)
    raise gen.Return("hello")
