# -*- coding: utf-8 -*-
from __future__ import absolute_import

from tornado.web import RequestHandler, Application, asynchronous
from tornado.blueprints import Blueprint
from tornado.test.util import unittest
from tornado.testing import AsyncHTTPTestCase, AsyncTestCase, ExpectLog, gen_test

""" auth module
"""
AUTH = Blueprint("auth")

@AUTH.route("/login")
class LoginHandler(RequestHandler):

    def get(self):
        self.write("Login Page")


@AUTH.route("/logout")
class LogoutHandler(RequestHandler):
    def get(self):
        self.write("Logged out")


""" user module
"""
USER = Blueprint("user")

@USER.route("/students")
class StudentsHandler(RequestHandler):
    def get(self):
        self.write("Students List")


@USER.route("/teachers")
class TeachersHandler(RequestHandler):

    def get(self):
        self.write("Teachers List")


class BlueprintsTest(AsyncHTTPTestCase):
    def get_app(self):
        self.app = Application()
        AUTH.register(self.app, url_prefix="/auth")
        USER.register(self.app, url_prefix="/user")
        return self.app

    def test_auth_login(self):
        response = self.fetch("/auth/login")
        # Test contents of response
        self.assertEqual(response.body, b"Login Page")

    def test_auth_logout(self):
        response = self.fetch("/auth/logout")
        # Test contents of response
        self.assertEqual(response.body, b"Logged out")

    def test_user_students(self):
        response = self.fetch("/user/students")
        # Test contents of response
        self.assertEqual(response.body, b"Students List")

    def test_user_teachers(self):
        response = self.fetch("/user/teachers")
        # Test contents of response
        self.assertEqual(response.body, b"Teachers List")


if __name__ == '__main__':
    pass
