from tornado.ioloop import IOLoop
from tornado.httpserver import HTTPServer
from tornado.options import parse_command_line
from tornado import web
from tornado import gen

import momoko

DB_NAME  = "your_db"
USER     = "your_user"
PASSWORD = "your_password"
HOST     = "your_host"
PORT     = "5432"


def get_postgres_connection_dsn():
    dsn = "dbname=%s " % (DB_NAME)
    dsn += "user=%s " % (USER)
    dsn += "password=%s " % (PASSWORD)
    dsn += "host=%s " % (HOST)
    dsn += "port=%s" % (PORT)
    return dsn


class BaseHandler(web.RequestHandler):
    @property
    def db(self):
        return self.application.db


class TutorialHandler(BaseHandler):
    @gen.coroutine
    def get(self):
        # Here you add code to read data from Postgres.
        cursor = yield self.db.execute("SELECT 1;")
        self.write("Results: %s" % cursor.fetchone())
        self.write('Some text here!')
        self.finish()

def create_app():
    application = web.Application([
        (r'/', TutorialHandler)
    ], debug=True)

    ioloop = IOLoop.instance()

    application.db = momoko.Pool(
        dsn=get_postgres_connection_dsn(),
        size=1,
        ioloop=ioloop,
    )

    # this is a one way to run ioloop in sync
    future = application.db.connect()
    ioloop.add_future(future, lambda f: ioloop.stop())
    ioloop.start()
    future.result()  # raises exception on connection error
    return application, ioloop

if __name__ == "__main__":
    parse_command_line()
    application, ioloop = create_app()
    http_server = HTTPServer(application)
    http_server.listen(8888, 'localhost')
    ioloop.start()
