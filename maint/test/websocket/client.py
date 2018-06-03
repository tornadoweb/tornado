import logging

from tornado import gen
from tornado.ioloop import IOLoop
from tornado.options import define, options, parse_command_line
from tornado.websocket import websocket_connect

define('url', default='ws://localhost:9001')
define('name', default='Tornado')


@gen.engine
def run_tests():
    url = options.url + '/getCaseCount'
    control_ws = yield websocket_connect(url, None)
    num_tests = int((yield control_ws.read_message()))
    logging.info('running %d cases', num_tests)
    msg = yield control_ws.read_message()
    assert msg is None

    for i in range(1, num_tests + 1):
        logging.info('running test case %d', i)
        url = options.url + '/runCase?case=%d&agent=%s' % (i, options.name)
        test_ws = yield websocket_connect(url, None, compression_options={})
        while True:
            message = yield test_ws.read_message()
            if message is None:
                break
            test_ws.write_message(message, binary=isinstance(message, bytes))

    url = options.url + '/updateReports?agent=%s' % options.name
    update_ws = yield websocket_connect(url, None)
    msg = yield update_ws.read_message()
    assert msg is None
    IOLoop.instance().stop()


def main():
    parse_command_line()

    IOLoop.instance().add_callback(run_tests)

    IOLoop.instance().start()


if __name__ == '__main__':
    main()
