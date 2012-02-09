#!/usr/bin/env python
#
# Copyright 2009 Facebook
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

"""Factory method for returning a database connection api for either MySQLdb or psycopg2"""

from __future__ import absolute_import, division, with_statement

import copy
import itertools
import logging
import time

class MySQLConnection(object):
    """A lightweight wrapper around MySQLdb DB-API connections.

    The main value we provide is wrapping rows in a dict/object so that
    columns can be accessed by name. Typical usage::

        db = database.Connection("localhost", "mydatabase")
        for article in db.query("SELECT * FROM articles"):
            print article.title

    Cursors are hidden by the implementation, but other than that, the methods
    are very similar to the DB-API.

    We explicitly set the timezone to UTC and the character encoding to
    UTF-8 on all connections to avoid time zone and encoding errors.
    """
    import MySQLdb
    import MySQLdb.constants
    import MySQLdb.converters
    import MySQLdb.cursors

    def __init__(self, host, database, user=None, password=None,
             max_idle_time=7*3600):
        self.host = host
        self.database = database
        self.max_idle_time = max_idle_time

        # Fix the access conversions to properly recognize unicode/binary
        FIELD_TYPE = self.MySQLdb.constants.FIELD_TYPE
        FLAG = self.MySQLdb.constants.FLAG
        CONVERSIONS = copy.copy(self.MySQLdb.converters.conversions)

        field_types = [FIELD_TYPE.BLOB, FIELD_TYPE.STRING, FIELD_TYPE.VAR_STRING]
        if 'VARCHAR' in vars(FIELD_TYPE):
            field_types.append(FIELD_TYPE.VARCHAR)

        for field_type in field_types:
            CONVERSIONS[field_type] = [(FLAG.BINARY, str)] + CONVERSIONS[field_type]

        args = dict(conv=CONVERSIONS, use_unicode=True, charset="utf8",
                    db=database, init_command='SET time_zone = "+0:00"',
                    sql_mode="TRADITIONAL")
        if user is not None:
            args["user"] = user
        if password is not None:
            args["passwd"] = password

        # We accept a path to a MySQL socket file or a host(:port) string
        if "/" in host:
            args["unix_socket"] = host
        else:
            self.socket = None
            pair = host.split(":")
            if len(pair) == 2:
                args["host"] = pair[0]
                args["port"] = int(pair[1])
            else:
                args["host"] = host
                args["port"] = 3306

        self._db = None
        self._db_args = args
        self._last_use_time = time.time()
        try:
            self.reconnect()
        except Exception:
            logging.error("Cannot connect to MySQL on %s", self.host,
                          exc_info=True)

    def __del__(self):
        self.close()

    def close(self):
        """Closes this database connection."""
        if getattr(self, "_db", None) is not None:
            self._db.close()
            self._db = None

    def reconnect(self):
        """Closes the existing database connection and re-opens it."""
        self.close()
        self._db = self.MySQLdb.connect(**self._db_args)
        self._db.autocommit(True)

    def iter(self, query, *parameters):
        """Returns an iterator for the given query and parameters."""
        self._ensure_connected()
        cursor = self.MySQLdb.cursors.SSCursor(self._db)
        try:
            self._execute(cursor, query, parameters)
            column_names = [d[0] for d in cursor.description]
            for row in cursor:
                yield Row(zip(column_names, row))
        finally:
            cursor.close()

    def query(self, query, *parameters):
        """Returns a row list for the given query and parameters."""
        cursor = self._cursor()
        try:
            self._execute(cursor, query, parameters)
            column_names = [d[0] for d in cursor.description]
            return [Row(itertools.izip(column_names, row)) for row in cursor]
        finally:
            cursor.close()

    def get(self, query, *parameters):
        """Returns the first row returned for the given query."""
        rows = self.query(query, *parameters)
        if not rows:
            return None
        elif len(rows) > 1:
            raise Exception("Multiple rows returned for Database.get() query")
        else:
            return rows[0]

    # rowcount is a more reasonable default return value than lastrowid,
    # but for historical compatibility execute() must return lastrowid.
    def execute(self, query, *parameters):
        """Executes the given query, returning the lastrowid from the query."""
        return self.execute_lastrowid(query, *parameters)

    def execute_lastrowid(self, query, *parameters):
        """Executes the given query, returning the lastrowid from the query."""
        cursor = self._cursor()
        try:
            self._execute(cursor, query, parameters)
            return cursor.lastrowid
        finally:
            cursor.close()

    def execute_rowcount(self, query, *parameters):
        """Executes the given query, returning the rowcount from the query."""
        cursor = self._cursor()
        try:
            self._execute(cursor, query, parameters)
            return cursor.rowcount
        finally:
            cursor.close()

    def executemany(self, query, parameters):
        """Executes the given query against all the given param sequences.

        We return the lastrowid from the query.
        """
        return self.executemany_lastrowid(query, parameters)

    def executemany_lastrowid(self, query, parameters):
        """Executes the given query against all the given param sequences.

        We return the lastrowid from the query.
        """
        cursor = self._cursor()
        try:
            cursor.executemany(query, parameters)
            return cursor.lastrowid
        finally:
            cursor.close()

    def executemany_rowcount(self, query, parameters):
        """Executes the given query against all the given param sequences.

        We return the rowcount from the query.
        """
        cursor = self._cursor()
        try:
            cursor.executemany(query, parameters)
            return cursor.rowcount
        finally:
            cursor.close()

    def _ensure_connected(self):
        # Mysql by default closes client connections that are idle for
        # 8 hours, but the client library does not report this fact until
        # you try to perform a query and it fails.  Protect against this
        # case by preemptively closing and reopening the connection
        # if it has been idle for too long (7 hours by default).
        if (self._db is None or
            (time.time() - self._last_use_time > self.max_idle_time)):
            self.reconnect()
        self._last_use_time = time.time()

    def _cursor(self):
        self._ensure_connected()
        return self._db.cursor()

    def _execute(self, cursor, query, parameters):
        try:
            return cursor.execute(query, parameters)
        except self.MySQLdb.OperationalError:
            logging.error("Error connecting to MySQL on %s", self.host)
            self.close()
            raise


class PostgresConnection(object):
    """A lightweight wrapper around psycopg2 DB-API connections.

    The main value we provide is wrapping rows in a dict/object so that
    columns can be accessed by name. Typical usage::

        db = database.Connection("localhost", "mydatabase")
        for article in db.query("SELECT * FROM articles"):
            print article.title

    Cursors are hidden by the implementation, but other than that, the methods
    are very similar to the DB-API.
    """
    import psycopg2
    import psycopg2.extensions
    # Default name for the server side cursor
    SSCURSOR_NAME = 'sscursor'

    def __init__(self, host, database, user=None, password=None,
             max_idle_time=None):
        self.host = host
        self.database = database
        self.max_idle_time = max_idle_time

        # Fix the access conversions to properly recognize unicode
        self.psycopg2.extensions.register_type(self.psycopg2.extensions.UNICODE)
        self.psycopg2.extensions.register_type(self.psycopg2.extensions.UNICODEARRAY)

        args = dict(host=host, database=database)
        if user is not None:
            args["user"] = user
        if password is not None:
            args["password"] = password

        self.socket = None
        pair = host.split(":")
        if len(pair) == 2:
            args["host"] = pair[0]
            args["port"] = int(pair[1])
        else:
            args["host"] = host
            args["port"] = 5432

        self._db = None
        self._db_args = args
        self._last_user_time = time.time()
        
        try:
            self.reconnect()
        except Exception:
            logging.error("Cannot connect to PostgreSQL on %s",
                    self.host,
                    exc_info=True)

    def __del__(self):
        self.close()

    def close(self):
        """Closes this database connection."""
        if getattr(self, "_db", None) is not None:
            self._db.close()
            self._db = None

    def reconnect(self):
        """Closes the existing database connection and re-opens it."""
        self.close()
        self._db = self.psycopg2.connect(**self._db_args)

    def iter(self, query, *parameters):
        """Returns an iterator for the given query and parameters."""
        # TODO: Potentially in the future we could allow for asynchronous iteration
        # because postgres allows for named cursors

        self._ensure_connected()
        cursor = self._cursor(self.SSCURSOR_NAME)
        try:
            # named cursors need to fetch a row before cursor.description is populated
            self._execute(cursor, query, parameters)
            first_row = cursor.fetchone()
            column_names = [d[0] for d in cursor.description]
            for row in itertools.chain([first_row], cursor):
                yield Row(zip(column_names, row))
        finally:
            cursor.close()

    def query(self, query, *parameters):
        """Returns a row list for the given query and parameters."""
        cursor = self._cursor()
        try:
            self._execute(cursor, query, parameters)
            column_names = [d[0] for d in cursor.description]
            return [Row(itertools.izip(column_names, row)) for row in cursor]
        finally:
            cursor.close()

    def get(self, query, *parameters):
        """Returns the first row returned for the given query."""
        rows = self.query(query, *parameters)
        if not rows:
            return None
        elif len(rows) > 1:
            raise Exception("Multiple rows returned for Database.get() query")
        else:
            return rows[0]

    def execute(self, query, *parameters):
        """Executes the given query, returning the result from the query (e.g.
        if RETURNING was used) or None."""
        cursor = self._cursor()
        try:
            self._execute_autocommit(cursor, query, parameters)
            return cursor.fetchone()[0]
        except self.psycopg2.ProgrammingError:
            return None
        finally:
            cursor.close()

    def execute_rowcount(self, query, *parameters):
        """Executes the given query, returning the rowcount from the query."""
        cursor = self._cursor()
        try:
            self._execute_autocommit(cursor, query, parameters)
            return cursor.rowcount
        finally:
            cursor.close()

    def executemany(self, query, parameters):
        """Executes the given query against all the given param sequences.

        We return the result from the query (e.g. if RETURNING was used) or None.
        """
        cursor = self._cursor()
        try:
            self._executemany_autocommit(cursor, query, parameters)
            return cursor.fetchone()[0]
        except self.psycopg2.ProgrammingError:
            return None
        finally:
            cursor.close()

    def executemany_rowcount(self, query, parameters):
        """Executes the given query against all the given param sequences.

        We return the rowcount from the query.
        """
        cursor = self._cursor()
        try:
            self._executemany_autocommit(cursor, query, parameters)
            return cursor.rowcount
        finally:
            cursor.close()

    def _ensure_connected(self):
        # By default PostgreSQL does not close connections that idle
        if self.max_idle_time is None:
            self._ensure_connected = self._ensure_connected_without_idle_limit
        else:
            self._ensure_connected = self._ensure_connected_with_idle_limit
        self._ensure_connected()
            
    def _ensure_connected_with_idle_limit(self):
        if (self._db is None or
            (time.time() - self._last_use_time > self.max_idle_time)):
            self.reconnect()
        self._last_use_time = time.time()

    def _ensure_connected_without_idle_limit(self):
        if self._db is None:
            self.reconnect()

    def _cursor(self, name=None):
        self._ensure_connected()
        return self._db.cursor() if name is None else self._db.cursor(name)

    def _execute(self, cursor, query, parameters):
        try:
            return cursor.execute(query, parameters)
        except self.psycopg2.OperationalError:
            logging.error("Error connecting to PostgreSQL on %s", self.host)
            self.close()
            raise

    def _execute_autocommit(self, cursor, query, parameters):
        try:
            self._execute(cursor, query, parameters)
        finally:
            self._db.commit()

    def _executemany_autocommit(self, cursor, query, parameters):
        try:
            return cursor.executemany(query, parameters)
        finally:
            self._db.commit()


class Row(dict):
    """A dict that allows for object-like property access syntax."""
    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError:
            raise AttributeError(name)
