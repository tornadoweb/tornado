import tornado.ioloop
import tornado.gen

from concurrent.futures import _base

class _WorkItem(object):
    def __init__(self, future, fn, args, kwargs):
        self.future = future
        self.fn = fn
        self.args = args
        self.kwargs = kwargs

    def run(self):
        if not self.future.set_running_or_notify_cancel():
            return

        self.kwargs['callback'] = self
        self.fn(*self.args, **self.kwargs)


    def __call__(self, *args, **kwargs):
        self.future.set_result((args, kwargs))



class TornadoExecutor(_base.Executor):
    def __init__(self, ioloop=None):
        self._shutdown = False
        if ioloop is None:
            self._ioloop = tornado.ioloop.IOLoop.instance()
        else:
            self._ioloop = ioloop

    def submit(self, fn, *args, **kwargs):
        if self._shutdown:
            raise RuntimeError('cannot schedule new futures after shutdown')

        f = _base.Future()
        w = _WorkItem(f, fn, args, kwargs)
        self._ioloop.add_callback(w.run)
        return f

    def shutdown(self, wait=True):
        # TODO
        raise NotImplemented

class FutureWait(tornado.gen.YieldPoint):
    def __init__(self, future):
        self.future = future

    def start(self, runner):
        self.runner = runner
        self.key = object()
        runner.register_callback(self.key)
        self.future.add_done_callback(runner.result_callback(self.key))

    def is_ready(self):
        return self.runner.is_ready(self.key)

    def get_result(self):
        return self.runner.pop_result(self.key)
