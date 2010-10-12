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

"""A lightweight wrapper around MySQLdb."""

import copy
import MySQLdb.constants
import MySQLdb.converters
import MySQLdb.cursors
import itertools
import logging
import time
import re

try:
    import curses   # For pretty SQL log messages, if available
except:
    curses = None

class Connection(object):
    """A lightweight wrapper around MySQLdb DB-API connections.

    The main value we provide is wrapping rows in a dict/object so that
    columns can be accessed by name. Typical usage:

        db = database.Connection("localhost", "mydatabase")
        for article in db.query("SELECT * FROM articles"):
            print article.title

    Cursors are hidden by the implementation, but other than that, the methods
    are very similar to the DB-API.

    We explicitly set the timezone to UTC and the character encoding to
    UTF-8 on all connections to avoid time zone and encoding errors.
    """
    def __init__(self, host, database, user=None, password=None,
                 max_idle_time=7*3600, debug=False):
        self.host = host
        self.database = database
        self.max_idle_time = max_idle_time
        self.debug = debug

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
        except:
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
        self._db = MySQLdb.connect(**self._db_args)
        self._db.autocommit(True)

    def iter(self, query, *parameters):
        """Returns an iterator for the given query and parameters."""
        self._ensure_connected()
        cursor = MySQLdb.cursors.SSCursor(self._db)
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

    def execute(self, query, *parameters):
        """Executes the given query, returning the lastrowid from the query."""
        cursor = self._cursor()
        try:
            self._execute(cursor, query, parameters)
            return cursor.lastrowid
        finally:
            cursor.close()

    def executemany(self, query, parameters):
        """Executes the given query against all the given param sequences.

        We return the lastrowid from the query.
        """
        cursor = self._cursor()
        try:
            cursor.executemany(query, parameters)
            return cursor.lastrowid
        finally:
            cursor.close()

    def scalar(self, query, *parameters):
        """Returns the first row returned for the given query."""
        rows = self.query(query, *parameters)
        if not rows:
            return None
        else:
            return rows[0][rows[0].keys()[0]]
    
    def array(self, query, *parameters):
        """Returns values in the first column as a list"""
        rows = self.query(query, *parameters)
        if not rows:
          return []
        key = rows[0].keys()[0]
        return [ x[key] for x in rows ]

    def select(self, table, fields="*", limit=None, where=None, group=None, order=None, values=None, **params):
        """ rows = db.select('Users', firstName='Larry', limit=10) """
        sql = [ 'SELECT %s FROM %s' % (fields, table) ]

        if where:
            if type(where) == type([]): where = " AND ".join(where)
            sql.append( 'WHERE ' + where )
        elif params:
            sql.append( 'WHERE ' + ' AND '.join([ p + ' = %s' for p in params]) )

        if group:
            sql.append('GROUP BY ' + group)
        if order:
            sql.append('ORDER BY ' + order)
        if limit:
            sql.append('LIMIT ' + str(limit))

        sql = " ".join(sql)
        if values:
            return self.query(sql, *values)
        return self.query(sql, *params.values())

    def delete(self, table, **params):
        """ db.delete('Users', firstName='Larry') """
        sql = 'DELETE FROM ' + table
        if params:
            sql += ' WHERE ' + ' AND '.join([ p + ' = %s' for p in params])
        return self.execute(sql, *params.values())
        
    def insert(self, table, **params):
        """ user_id = db.insert(table='Users', firstName='Larry', lastName='Page') """
        sql = 'INSERT IGNORE INTO ' + table + ' ('
        sql += (', ').join(params.keys()) + ') VALUES ('
        sql += ', '.join(['%s' for x in range(len(params))]) + ')'
        return self.execute(sql, *params.values())

    def update(self, table, record=None, key='id', **params):
        """ user_id = db.update('Users', 13, firstName='Larry', lastName='Page') """
        sql = 'UPDATE ' + table + ' SET '
        sql += ', '.join([ p + ' = %s' for p in params])
        params = params.values()
        if record:
          sql += ' WHERE ' + key + ' = %s'
          params.append(record)
        return self.execute(sql, *params)

    def _debug(self, sql):
        """ pretty-print SQL """
        c, c2 = "", ""
        if curses:
            fg_color = curses.tigetstr("setaf") or curses.tigetstr("setf") or ""
            c = curses.tparm(fg_color, 5)
            c2 = curses.tparm(fg_color, 7)

        sql = sql.lower()
        keywords = [ 'select', 'delete', 'insert', 'update', 'ignore', 'from', 'order by', 'limit', 'where', 'left', 'inner', 'join', 'outer', 'and', 'or', 'group by', 'limit', 'asc', 'desc', 'on', 'in', 'as', 'sum', 'min', 'max' ]
        for k in keywords:
            k2 = c + k.upper() + c2
            sql = re.sub("\\b" + k + "\\b", k2, sql)

        sql = "\n" + sql.replace("FROM", "\n  FROM")\
            .replace("WHERE", "\n  WHERE")\
            .replace("GROUP BY", "\n  GROUP BY")\
            .replace("ORDER BY", "\n  ORDER BY")\
            .replace("LIMIT", "\n  LIMIT")
        logging.debug(sql)
        
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
            if self.debug:
                self._debug(query)
            # allow us to use question marks instead of %s
            query = query.replace("?", "%s")
            return cursor.execute(query, parameters)
        except OperationalError:
            logging.error("Error connecting to MySQL on %s", self.host)
            self.close()
            raise


class Row(dict):
    """A dict that allows for object-like property access syntax."""
    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError:
            raise AttributeError(name)


# Fix the access conversions to properly recognize unicode/binary
FIELD_TYPE = MySQLdb.constants.FIELD_TYPE
FLAG = MySQLdb.constants.FLAG
CONVERSIONS = copy.deepcopy(MySQLdb.converters.conversions)

field_types = [FIELD_TYPE.BLOB, FIELD_TYPE.STRING, FIELD_TYPE.VAR_STRING]
if 'VARCHAR' in vars(FIELD_TYPE):
    field_types.append(FIELD_TYPE.VARCHAR)

for field_type in field_types:
    CONVERSIONS[field_type].insert(0, (FLAG.BINARY, str))


# Alias some common MySQL exceptions
IntegrityError = MySQLdb.IntegrityError
OperationalError = MySQLdb.OperationalError
