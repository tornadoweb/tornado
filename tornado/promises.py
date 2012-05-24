import tornado.ioloop
from tornado.gen import Task

__all__ = ['promise', 'until']

class Promise(object):
    def __init__(self):
        self._result_args = None
        self._result_kwargs = None
        self._finished = False
        self._callback = None

    def _set_response(self, *args, **kwargs):
        self._result_args = args
        self._result_kwargs = kwargs
        self._finished = True

        if self._callback:
            self._callback()

    def __call__(self, callback=None):
        if self._finished:
            tornado.ioloop.IOLoop.instance().add_callback(callback)
        else:
            self._callback = callback

    def __getattr__(self, name):
        try:
            return super(Promise, self).__getattr__(name)
        except AttributeError:
            if self._result_kwargs:
                try:
                    return self._result_kwargs[name]
                except KeyError:
                    raise AttributeError
        raise AttributeError

    @property
    def value(self):
        assert self._finished

        if len(self._result_args) == 1:
            return self._result_args[0]
        return self._result_args[:]

    @property
    def values(self):
        assert self._finished

        return self._result_args[:]

    @property
    def finished(self):
        return self._finished


def promise(func, *args, **kwargs):
    p = Promise()

    def cb(*args, **kwargs):
        p._set_response(*args, **kwargs)

    kwargs['callback'] = cb
    func(*args, **kwargs)

    return p

def until(*args):
    return [Task(promise) for promise in args]

