#!/usr/bin/env python
"""A simplistic Twitter viewer to demonstrate the use of TwitterMixin.

To run this app, you must first register an application with Twitter:
  1) Go to https://dev.twitter.com/apps and create an application.
     Your application must have a callback URL registered with Twitter.
     It doesn't matter what it is, but it has to be there (Twitter won't
     let you use localhost in a registered callback URL, but that won't stop
     you from running this demo on localhost).
  2) Create a file called "secrets.cfg" and put your consumer key and
     secret (which Twitter gives you when you register an app) in it:
       twitter_consumer_key = 'asdf1234'
       twitter_consumer_secret = 'qwer5678'
     (you could also generate a random value for "cookie_secret" and put it
     in the same file, although it's not necessary to run this demo)
  3) Run this program and go to http://localhost:8888 (by default) in your
     browser.
"""

import logging

from tornado.auth import TwitterMixin
from tornado.escape import json_decode, json_encode
from tornado.ioloop import IOLoop
from tornado import gen
from tornado.options import define, options, parse_command_line, parse_config_file
from tornado.web import Application, RequestHandler, authenticated

define('port', default=8888, help="port to listen on")
define('config_file', default='secrets.cfg',
       help='filename for additional configuration')

define('debug', default=False, group='application',
       help="run in debug mode (with automatic reloading)")
# The following settings should probably be defined in secrets.cfg
define('twitter_consumer_key', type=str, group='application')
define('twitter_consumer_secret', type=str, group='application')
define('cookie_secret', type=str, group='application',
       default='__TODO:_GENERATE_YOUR_OWN_RANDOM_VALUE__',
       help="signing key for secure cookies")

class BaseHandler(RequestHandler):
    COOKIE_NAME = 'twitterdemo_user'

    def get_current_user(self):
        user_json = self.get_secure_cookie(self.COOKIE_NAME)
        if not user_json:
            return None
        return json_decode(user_json)

class MainHandler(BaseHandler, TwitterMixin):
    @authenticated
    @gen.coroutine
    def get(self):
        timeline = yield self.twitter_request(
            '/statuses/home_timeline',
            access_token=self.current_user['access_token'])
        self.render('home.html', timeline=timeline)

class LoginHandler(BaseHandler, TwitterMixin):
    @gen.coroutine
    def get(self):
        if self.get_argument('oauth_token', None):
            user = yield self.get_authenticated_user()
            del user["description"]
            self.set_secure_cookie(self.COOKIE_NAME, json_encode(user))
            self.redirect(self.get_argument('next', '/'))
        else:
            yield self.authorize_redirect(callback_uri=self.request.full_url())

class LogoutHandler(BaseHandler):
    def get(self):
        self.clear_cookie(self.COOKIE_NAME)

def main():
    parse_command_line(final=False)
    parse_config_file(options.config_file)

    app = Application(
        [
            ('/', MainHandler),
            ('/login', LoginHandler),
            ('/logout', LogoutHandler),
        ],
        login_url='/login',
        **options.group_dict('application'))
    app.listen(options.port)

    logging.info('Listening on http://localhost:%d' % options.port)
    IOLoop.instance().start()

if __name__ == '__main__':
    main()
