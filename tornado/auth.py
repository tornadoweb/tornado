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

"""Implementations of various third-party authentication schemes.

All the classes in this file are class Mixins designed to be used with
web.py RequestHandler classes. The primary methods for each service are
authenticate_redirect(), authorize_redirect(), and get_authenticated_user().
The former should be called to redirect the user to, e.g., the OpenID
authentication page on the third party service, and the latter should
be called upon return to get the user data from the data returned by
the third party service.

They all take slightly different arguments due to the fact all these
services implement authentication and authorization slightly differently.
See the individual service classes below for complete documentation.

Example usage for Google OpenID::

    class GoogleHandler(tornado.web.RequestHandler, tornado.auth.GoogleMixin):
        @tornado.web.asynchronous
        def get(self):
            if self.get_argument("openid.mode", None):
                self.get_authenticated_user(self.async_callback(self._on_auth))
                return
            self.authenticate_redirect()

        def _on_auth(self, user):
            if not user:
                raise tornado.web.HTTPError(500, "Google auth failed")
            # Save the user with, e.g., set_secure_cookie()

"""

import base64
import binascii
import cgi
import hashlib
import hmac
import logging
import time
import urllib
import urlparse
import uuid

from tornado import httpclient
from tornado import escape
from tornado.httputil import url_concat
from tornado.util import bytes_type, b

class OpenIdMixin(object):
    """Abstract implementation of OpenID and Attribute Exchange.

    See GoogleMixin below for example implementations.
    """
    def authenticate_redirect(self, callback_uri=None,
                              ax_attrs=["name","email","language","username"]):
        """Returns the authentication URL for this service.

        After authentication, the service will redirect back to the given
        callback URI.

        We request the given attributes for the authenticated user by
        default (name, email, language, and username). If you don't need
        all those attributes for your app, you can request fewer with
        the ax_attrs keyword argument.
        """
        callback_uri = callback_uri or self.request.uri
        args = self._openid_args(callback_uri, ax_attrs=ax_attrs)
        self.redirect(self._OPENID_ENDPOINT + "?" + urllib.urlencode(args))

    def get_authenticated_user(self, callback):
        """Fetches the authenticated user data upon redirect.

        This method should be called by the handler that receives the
        redirect from the authenticate_redirect() or authorize_redirect()
        methods.
        """
        # Verify the OpenID response via direct request to the OP
        args = dict((k, v[-1]) for k, v in self.request.arguments.iteritems())
        args["openid.mode"] = u"check_authentication"
        url = self._OPENID_ENDPOINT
        http = httpclient.AsyncHTTPClient()
        http.fetch(url, self.async_callback(
            self._on_authentication_verified, callback),
            method="POST", body=urllib.urlencode(args))

    def _openid_args(self, callback_uri, ax_attrs=[], oauth_scope=None):
        url = urlparse.urljoin(self.request.full_url(), callback_uri)
        args = {
            "openid.ns": "http://specs.openid.net/auth/2.0",
            "openid.claimed_id":
                "http://specs.openid.net/auth/2.0/identifier_select",
            "openid.identity":
                "http://specs.openid.net/auth/2.0/identifier_select",
            "openid.return_to": url,
            "openid.realm": self.request.protocol + "://" + self.request.host + "/",
            "openid.mode": "checkid_setup",
        }
        if ax_attrs:
            args.update({
                "openid.ns.ax": "http://openid.net/srv/ax/1.0",
                "openid.ax.mode": "fetch_request",
            })
            ax_attrs = set(ax_attrs)
            required = []
            if "name" in ax_attrs:
                ax_attrs -= set(["name", "firstname", "fullname", "lastname"])
                required += ["firstname", "fullname", "lastname"]
                args.update({
                    "openid.ax.type.firstname":
                        "http://axschema.org/namePerson/first",
                    "openid.ax.type.fullname":
                        "http://axschema.org/namePerson",
                    "openid.ax.type.lastname":
                        "http://axschema.org/namePerson/last",
                })
            known_attrs = {
                "email": "http://axschema.org/contact/email",
                "language": "http://axschema.org/pref/language",
                "username": "http://axschema.org/namePerson/friendly",
            }
            for name in ax_attrs:
                args["openid.ax.type." + name] = known_attrs[name]
                required.append(name)
            args["openid.ax.required"] = ",".join(required)
        if oauth_scope:
            args.update({
                "openid.ns.oauth":
                    "http://specs.openid.net/extensions/oauth/1.0",
                "openid.oauth.consumer": self.request.host.split(":")[0],
                "openid.oauth.scope": oauth_scope,
            })
        return args

    def _on_authentication_verified(self, callback, response):
        if response.error or b("is_valid:true") not in response.body:
            logging.warning("Invalid OpenID response: %s", response.error or
                            response.body)
            callback(None)
            return

        # Make sure we got back at least an email from attribute exchange
        ax_ns = None
        for name in self.request.arguments.iterkeys():
            if name.startswith("openid.ns.") and \
               self.get_argument(name) == u"http://openid.net/srv/ax/1.0":
                ax_ns = name[10:]
                break
        def get_ax_arg(uri):
            if not ax_ns: return u""
            prefix = "openid." + ax_ns + ".type."
            ax_name = None
            for name in self.request.arguments.iterkeys():
                if self.get_argument(name) == uri and name.startswith(prefix):
                    part = name[len(prefix):]
                    ax_name = "openid." + ax_ns + ".value." + part
                    break
            if not ax_name: return u""
            return self.get_argument(ax_name, u"")

        email = get_ax_arg("http://axschema.org/contact/email")
        name = get_ax_arg("http://axschema.org/namePerson")
        first_name = get_ax_arg("http://axschema.org/namePerson/first")
        last_name = get_ax_arg("http://axschema.org/namePerson/last")
        username = get_ax_arg("http://axschema.org/namePerson/friendly")
        locale = get_ax_arg("http://axschema.org/pref/language").lower()
        user = dict()
        name_parts = []
        if first_name:
            user["first_name"] = first_name
            name_parts.append(first_name)
        if last_name:
            user["last_name"] = last_name
            name_parts.append(last_name)
        if name:
            user["name"] = name
        elif name_parts:
            user["name"] = u" ".join(name_parts)
        elif email:
            user["name"] = email.split("@")[0]
        if email: user["email"] = email
        if locale: user["locale"] = locale
        if username: user["username"] = username
        callback(user)


class OAuthMixin(object):
    """Abstract implementation of OAuth.

    See TwitterMixin and FriendFeedMixin below for example implementations.
    """

    def authorize_redirect(self, callback_uri=None, extra_params=None):
        """Redirects the user to obtain OAuth authorization for this service.

        Twitter and FriendFeed both require that you register a Callback
        URL with your application. You should call this method to log the
        user in, and then call get_authenticated_user() in the handler
        you registered as your Callback URL to complete the authorization
        process.

        This method sets a cookie called _oauth_request_token which is
        subsequently used (and cleared) in get_authenticated_user for
        security purposes.
        """
        if callback_uri and getattr(self, "_OAUTH_NO_CALLBACKS", False):
            raise Exception("This service does not support oauth_callback")
        http = httpclient.AsyncHTTPClient()
        if getattr(self, "_OAUTH_VERSION", "1.0a") == "1.0a":
            http.fetch(self._oauth_request_token_url(callback_uri=callback_uri,
                extra_params=extra_params),
                self.async_callback(
                    self._on_request_token,
                    self._OAUTH_AUTHORIZE_URL,
                callback_uri))
        else:
            http.fetch(self._oauth_request_token_url(), self.async_callback(
                self._on_request_token, self._OAUTH_AUTHORIZE_URL, callback_uri))


    def get_authenticated_user(self, callback):
        """Gets the OAuth authorized user and access token on callback.

        This method should be called from the handler for your registered
        OAuth Callback URL to complete the registration process. We call
        callback with the authenticated user, which in addition to standard
        attributes like 'name' includes the 'access_key' attribute, which
        contains the OAuth access you can use to make authorized requests
        to this service on behalf of the user.

        """
        request_key = self.get_argument("oauth_token")
        oauth_verifier = self.get_argument("oauth_verifier", None)
        request_cookie = self.get_cookie("_oauth_request_token")
        if not request_cookie:
            logging.warning("Missing OAuth request token cookie")
            callback(None)
            return
        self.clear_cookie("_oauth_request_token")
        cookie_key, cookie_secret = [base64.b64decode(i) for i in request_cookie.split("|")]
        if cookie_key != request_key:
            logging.warning("Request token does not match cookie")
            callback(None)
            return
        token = dict(key=cookie_key, secret=cookie_secret)
        if oauth_verifier:
          token["verifier"] = oauth_verifier
        http = httpclient.AsyncHTTPClient()
        http.fetch(self._oauth_access_token_url(token), self.async_callback(
            self._on_access_token, callback))

    def _oauth_request_token_url(self, callback_uri= None, extra_params=None):
        consumer_token = self._oauth_consumer_token()
        url = self._OAUTH_REQUEST_TOKEN_URL
        args = dict(
            oauth_consumer_key=consumer_token["key"],
            oauth_signature_method="HMAC-SHA1",
            oauth_timestamp=str(int(time.time())),
            oauth_nonce=binascii.b2a_hex(uuid.uuid4().bytes),
            oauth_version=getattr(self, "_OAUTH_VERSION", "1.0a"),
        )
        if getattr(self, "_OAUTH_VERSION", "1.0a") == "1.0a":
            if callback_uri:
                args["oauth_callback"] = urlparse.urljoin(
                    self.request.full_url(), callback_uri)
            if extra_params: args.update(extra_params)
            signature = _oauth10a_signature(consumer_token, "GET", url, args)
        else:
            signature = _oauth_signature(consumer_token, "GET", url, args)

        args["oauth_signature"] = signature
        return url + "?" + urllib.urlencode(args)

    def _on_request_token(self, authorize_url, callback_uri, response):
        if response.error:
            raise Exception("Could not get request token")
        request_token = _oauth_parse_response(response.body)
        data = "|".join([base64.b64encode(request_token["key"]),
            base64.b64encode(request_token["secret"])])
        self.set_cookie("_oauth_request_token", data)
        args = dict(oauth_token=request_token["key"])
        if callback_uri:
            args["oauth_callback"] = urlparse.urljoin(
                self.request.full_url(), callback_uri)
        self.redirect(authorize_url + "?" + urllib.urlencode(args))

    def _oauth_access_token_url(self, request_token):
        consumer_token = self._oauth_consumer_token()
        url = self._OAUTH_ACCESS_TOKEN_URL
        args = dict(
            oauth_consumer_key=consumer_token["key"],
            oauth_token=request_token["key"],
            oauth_signature_method="HMAC-SHA1",
            oauth_timestamp=str(int(time.time())),
            oauth_nonce=binascii.b2a_hex(uuid.uuid4().bytes),
            oauth_version=getattr(self, "_OAUTH_VERSION", "1.0a"),
        )
        if "verifier" in request_token:
          args["oauth_verifier"]=request_token["verifier"]

        if getattr(self, "_OAUTH_VERSION", "1.0a") == "1.0a":
            signature = _oauth10a_signature(consumer_token, "GET", url, args,
                                            request_token)
        else:
            signature = _oauth_signature(consumer_token, "GET", url, args,
                                         request_token)

        args["oauth_signature"] = signature
        return url + "?" + urllib.urlencode(args)

    def _on_access_token(self, callback, response):
        if response.error:
            logging.warning("Could not fetch access token")
            callback(None)
            return

        access_token = _oauth_parse_response(response.body)
        user = self._oauth_get_user(access_token, self.async_callback(
             self._on_oauth_get_user, access_token, callback))

    def _oauth_get_user(self, access_token, callback):
        raise NotImplementedError()

    def _on_oauth_get_user(self, access_token, callback, user):
        if not user:
            callback(None)
            return
        user["access_token"] = access_token
        callback(user)

    def _oauth_request_parameters(self, url, access_token, parameters={},
                                  method="GET"):
        """Returns the OAuth parameters as a dict for the given request.

        parameters should include all POST arguments and query string arguments
        that will be sent with the request.
        """
        consumer_token = self._oauth_consumer_token()
        base_args = dict(
            oauth_consumer_key=consumer_token["key"],
            oauth_token=access_token["key"],
            oauth_signature_method="HMAC-SHA1",
            oauth_timestamp=str(int(time.time())),
            oauth_nonce=binascii.b2a_hex(uuid.uuid4().bytes),
            oauth_version=getattr(self, "_OAUTH_VERSION", "1.0a"),
        )
        args = {}
        args.update(base_args)
        args.update(parameters)
        if getattr(self, "_OAUTH_VERSION", "1.0a") == "1.0a":
            signature = _oauth10a_signature(consumer_token, method, url, args,
                                         access_token)
        else:
            signature = _oauth_signature(consumer_token, method, url, args,
                                         access_token)
        base_args["oauth_signature"] = signature
        return base_args

class OAuth2Mixin(object):
    """Abstract implementation of OAuth v 2."""

    def authorize_redirect(self, redirect_uri=None, client_id=None,
                           client_secret=None, extra_params=None ):
        """Redirects the user to obtain OAuth authorization for this service.

        Some providers require that you register a Callback
        URL with your application. You should call this method to log the
        user in, and then call get_authenticated_user() in the handler
        you registered as your Callback URL to complete the authorization
        process.
        """
        args = {
          "redirect_uri": redirect_uri,
          "client_id": client_id
        }
        if extra_params: args.update(extra_params)
        self.redirect(
                url_concat(self._OAUTH_AUTHORIZE_URL, args))

    def _oauth_request_token_url(self, redirect_uri= None, client_id = None,
                                 client_secret=None, code=None,
                                 extra_params=None):
        url = self._OAUTH_ACCESS_TOKEN_URL
        args = dict(
            redirect_uri=redirect_uri,
            code=code,
            client_id=client_id,
            client_secret=client_secret,
            )
        if extra_params: args.update(extra_params)
        return url_concat(url, args)

class TwitterMixin(OAuthMixin):
    """Twitter OAuth authentication.

    To authenticate with Twitter, register your application with
    Twitter at http://twitter.com/apps. Then copy your Consumer Key and
    Consumer Secret to the application settings 'twitter_consumer_key' and
    'twitter_consumer_secret'. Use this Mixin on the handler for the URL
    you registered as your application's Callback URL.

    When your application is set up, you can use this Mixin like this
    to authenticate the user with Twitter and get access to their stream::

        class TwitterHandler(tornado.web.RequestHandler,
                             tornado.auth.TwitterMixin):
            @tornado.web.asynchronous
            def get(self):
                if self.get_argument("oauth_token", None):
                    self.get_authenticated_user(self.async_callback(self._on_auth))
                    return
                self.authorize_redirect()

            def _on_auth(self, user):
                if not user:
                    raise tornado.web.HTTPError(500, "Twitter auth failed")
                # Save the user using, e.g., set_secure_cookie()

    The user object returned by get_authenticated_user() includes the
    attributes 'username', 'name', and all of the custom Twitter user
    attributes describe at
    http://apiwiki.twitter.com/Twitter-REST-API-Method%3A-users%C2%A0show
    in addition to 'access_token'. You should save the access token with
    the user; it is required to make requests on behalf of the user later
    with twitter_request().
    """
    _OAUTH_REQUEST_TOKEN_URL = "http://api.twitter.com/oauth/request_token"
    _OAUTH_ACCESS_TOKEN_URL = "http://api.twitter.com/oauth/access_token"
    _OAUTH_AUTHORIZE_URL = "http://api.twitter.com/oauth/authorize"
    _OAUTH_AUTHENTICATE_URL = "http://api.twitter.com/oauth/authenticate"
    _OAUTH_NO_CALLBACKS = False


    def authenticate_redirect(self):
        """Just like authorize_redirect(), but auto-redirects if authorized.

        This is generally the right interface to use if you are using
        Twitter for single-sign on.
        """
        http = httpclient.AsyncHTTPClient()
        http.fetch(self._oauth_request_token_url(), self.async_callback(
            self._on_request_token, self._OAUTH_AUTHENTICATE_URL, None))

    def twitter_request(self, path, callback, access_token=None,
                           post_args=None, **args):
        """Fetches the given API path, e.g., "/statuses/user_timeline/btaylor"

        The path should not include the format (we automatically append
        ".json" and parse the JSON output).

        If the request is a POST, post_args should be provided. Query
        string arguments should be given as keyword arguments.

        All the Twitter methods are documented at
        http://apiwiki.twitter.com/Twitter-API-Documentation.

        Many methods require an OAuth access token which you can obtain
        through authorize_redirect() and get_authenticated_user(). The
        user returned through that process includes an 'access_token'
        attribute that can be used to make authenticated requests via
        this method. Example usage::

            class MainHandler(tornado.web.RequestHandler,
                              tornado.auth.TwitterMixin):
                @tornado.web.authenticated
                @tornado.web.asynchronous
                def get(self):
                    self.twitter_request(
                        "/statuses/update",
                        post_args={"status": "Testing Tornado Web Server"},
                        access_token=user["access_token"],
                        callback=self.async_callback(self._on_post))

                def _on_post(self, new_entry):
                    if not new_entry:
                        # Call failed; perhaps missing permission?
                        self.authorize_redirect()
                        return
                    self.finish("Posted a message!")

        """
        # Add the OAuth resource request signature if we have credentials
        url = "http://api.twitter.com/1" + path + ".json"
        if access_token:
            all_args = {}
            all_args.update(args)
            all_args.update(post_args or {})
            consumer_token = self._oauth_consumer_token()
            method = "POST" if post_args is not None else "GET"
            oauth = self._oauth_request_parameters(
                url, access_token, all_args, method=method)
            args.update(oauth)
        if args: url += "?" + urllib.urlencode(args)
        callback = self.async_callback(self._on_twitter_request, callback)
        http = httpclient.AsyncHTTPClient()
        if post_args is not None:
            http.fetch(url, method="POST", body=urllib.urlencode(post_args),
                       callback=callback)
        else:
            http.fetch(url, callback=callback)

    def _on_twitter_request(self, callback, response):
        if response.error:
            logging.warning("Error response %s fetching %s", response.error,
                            response.request.url)
            callback(None)
            return
        callback(escape.json_decode(response.body))

    def _oauth_consumer_token(self):
        self.require_setting("twitter_consumer_key", "Twitter OAuth")
        self.require_setting("twitter_consumer_secret", "Twitter OAuth")
        return dict(
            key=self.settings["twitter_consumer_key"],
            secret=self.settings["twitter_consumer_secret"])

    def _oauth_get_user(self, access_token, callback):
        callback = self.async_callback(self._parse_user_response, callback)
        self.twitter_request(
            "/users/show/" + access_token["screen_name"],
            access_token=access_token, callback=callback)

    def _parse_user_response(self, callback, user):
        if user:
            user["username"] = user["screen_name"]
        callback(user)


class FriendFeedMixin(OAuthMixin):
    """FriendFeed OAuth authentication.

    To authenticate with FriendFeed, register your application with
    FriendFeed at http://friendfeed.com/api/applications. Then
    copy your Consumer Key and Consumer Secret to the application settings
    'friendfeed_consumer_key' and 'friendfeed_consumer_secret'. Use
    this Mixin on the handler for the URL you registered as your
    application's Callback URL.

    When your application is set up, you can use this Mixin like this
    to authenticate the user with FriendFeed and get access to their feed::

        class FriendFeedHandler(tornado.web.RequestHandler,
                                tornado.auth.FriendFeedMixin):
            @tornado.web.asynchronous
            def get(self):
                if self.get_argument("oauth_token", None):
                    self.get_authenticated_user(self.async_callback(self._on_auth))
                    return
                self.authorize_redirect()

            def _on_auth(self, user):
                if not user:
                    raise tornado.web.HTTPError(500, "FriendFeed auth failed")
                # Save the user using, e.g., set_secure_cookie()

    The user object returned by get_authenticated_user() includes the
    attributes 'username', 'name', and 'description' in addition to
    'access_token'. You should save the access token with the user;
    it is required to make requests on behalf of the user later with
    friendfeed_request().
    """
    _OAUTH_VERSION = "1.0"
    _OAUTH_REQUEST_TOKEN_URL = "https://friendfeed.com/account/oauth/request_token"
    _OAUTH_ACCESS_TOKEN_URL = "https://friendfeed.com/account/oauth/access_token"
    _OAUTH_AUTHORIZE_URL = "https://friendfeed.com/account/oauth/authorize"
    _OAUTH_NO_CALLBACKS = True
    _OAUTH_VERSION = "1.0"


    def friendfeed_request(self, path, callback, access_token=None,
                           post_args=None, **args):
        """Fetches the given relative API path, e.g., "/bret/friends"

        If the request is a POST, post_args should be provided. Query
        string arguments should be given as keyword arguments.

        All the FriendFeed methods are documented at
        http://friendfeed.com/api/documentation.

        Many methods require an OAuth access token which you can obtain
        through authorize_redirect() and get_authenticated_user(). The
        user returned through that process includes an 'access_token'
        attribute that can be used to make authenticated requests via
        this method. Example usage::

            class MainHandler(tornado.web.RequestHandler,
                              tornado.auth.FriendFeedMixin):
                @tornado.web.authenticated
                @tornado.web.asynchronous
                def get(self):
                    self.friendfeed_request(
                        "/entry",
                        post_args={"body": "Testing Tornado Web Server"},
                        access_token=self.current_user["access_token"],
                        callback=self.async_callback(self._on_post))

                def _on_post(self, new_entry):
                    if not new_entry:
                        # Call failed; perhaps missing permission?
                        self.authorize_redirect()
                        return
                    self.finish("Posted a message!")

        """
        # Add the OAuth resource request signature if we have credentials
        url = "http://friendfeed-api.com/v2" + path
        if access_token:
            all_args = {}
            all_args.update(args)
            all_args.update(post_args or {})
            consumer_token = self._oauth_consumer_token()
            method = "POST" if post_args is not None else "GET"
            oauth = self._oauth_request_parameters(
                url, access_token, all_args, method=method)
            args.update(oauth)
        if args: url += "?" + urllib.urlencode(args)
        callback = self.async_callback(self._on_friendfeed_request, callback)
        http = httpclient.AsyncHTTPClient()
        if post_args is not None:
            http.fetch(url, method="POST", body=urllib.urlencode(post_args),
                       callback=callback)
        else:
            http.fetch(url, callback=callback)

    def _on_friendfeed_request(self, callback, response):
        if response.error:
            logging.warning("Error response %s fetching %s", response.error,
                            response.request.url)
            callback(None)
            return
        callback(escape.json_decode(response.body))

    def _oauth_consumer_token(self):
        self.require_setting("friendfeed_consumer_key", "FriendFeed OAuth")
        self.require_setting("friendfeed_consumer_secret", "FriendFeed OAuth")
        return dict(
            key=self.settings["friendfeed_consumer_key"],
            secret=self.settings["friendfeed_consumer_secret"])

    def _oauth_get_user(self, access_token, callback):
        callback = self.async_callback(self._parse_user_response, callback)
        self.friendfeed_request(
            "/feedinfo/" + access_token["username"],
            include="id,name,description", access_token=access_token,
            callback=callback)

    def _parse_user_response(self, callback, user):
        if user:
            user["username"] = user["id"]
        callback(user)


class GoogleMixin(OpenIdMixin, OAuthMixin):
    """Google Open ID / OAuth authentication.

    No application registration is necessary to use Google for authentication
    or to access Google resources on behalf of a user. To authenticate with
    Google, redirect with authenticate_redirect(). On return, parse the
    response with get_authenticated_user(). We send a dict containing the
    values for the user, including 'email', 'name', and 'locale'.
    Example usage::

        class GoogleHandler(tornado.web.RequestHandler, tornado.auth.GoogleMixin):
           @tornado.web.asynchronous
           def get(self):
               if self.get_argument("openid.mode", None):
                   self.get_authenticated_user(self.async_callback(self._on_auth))
                   return
            self.authenticate_redirect()

            def _on_auth(self, user):
                if not user:
                    raise tornado.web.HTTPError(500, "Google auth failed")
                # Save the user with, e.g., set_secure_cookie()

    """
    _OPENID_ENDPOINT = "https://www.google.com/accounts/o8/ud"
    _OAUTH_ACCESS_TOKEN_URL = "https://www.google.com/accounts/OAuthGetAccessToken"

    def authorize_redirect(self, oauth_scope, callback_uri=None,
                           ax_attrs=["name","email","language","username"]):
        """Authenticates and authorizes for the given Google resource.

        Some of the available resources are:

        * Gmail Contacts - http://www.google.com/m8/feeds/
        * Calendar - http://www.google.com/calendar/feeds/
        * Finance - http://finance.google.com/finance/feeds/

        You can authorize multiple resources by separating the resource
        URLs with a space.
        """
        callback_uri = callback_uri or self.request.uri
        args = self._openid_args(callback_uri, ax_attrs=ax_attrs,
                                 oauth_scope=oauth_scope)
        self.redirect(self._OPENID_ENDPOINT + "?" + urllib.urlencode(args))

    def get_authenticated_user(self, callback):
        """Fetches the authenticated user data upon redirect."""
        # Look to see if we are doing combined OpenID/OAuth
        oauth_ns = ""
        for name, values in self.request.arguments.iteritems():
            if name.startswith("openid.ns.") and \
               values[-1] == u"http://specs.openid.net/extensions/oauth/1.0":
                oauth_ns = name[10:]
                break
        token = self.get_argument("openid." + oauth_ns + ".request_token", "")
        if token:
            http = httpclient.AsyncHTTPClient()
            token = dict(key=token, secret="")
            http.fetch(self._oauth_access_token_url(token),
                       self.async_callback(self._on_access_token, callback))
        else:
            OpenIdMixin.get_authenticated_user(self, callback)

    def _oauth_consumer_token(self):
        self.require_setting("google_consumer_key", "Google OAuth")
        self.require_setting("google_consumer_secret", "Google OAuth")
        return dict(
            key=self.settings["google_consumer_key"],
            secret=self.settings["google_consumer_secret"])

    def _oauth_get_user(self, access_token, callback):
        OpenIdMixin.get_authenticated_user(self, callback)

class FacebookMixin(object):
    """Facebook Connect authentication.

    New applications should consider using `FacebookGraphMixin` below instead
    of this class.

    To authenticate with Facebook, register your application with
    Facebook at http://www.facebook.com/developers/apps.php. Then
    copy your API Key and Application Secret to the application settings
    'facebook_api_key' and 'facebook_secret'.

    When your application is set up, you can use this Mixin like this
    to authenticate the user with Facebook::

        class FacebookHandler(tornado.web.RequestHandler,
                              tornado.auth.FacebookMixin):
            @tornado.web.asynchronous
            def get(self):
                if self.get_argument("session", None):
                    self.get_authenticated_user(self.async_callback(self._on_auth))
                    return
                self.authenticate_redirect()

            def _on_auth(self, user):
                if not user:
                    raise tornado.web.HTTPError(500, "Facebook auth failed")
                # Save the user using, e.g., set_secure_cookie()

    The user object returned by get_authenticated_user() includes the
    attributes 'facebook_uid' and 'name' in addition to session attributes
    like 'session_key'. You should save the session key with the user; it is
    required to make requests on behalf of the user later with
    facebook_request().
    """
    def authenticate_redirect(self, callback_uri=None, cancel_uri=None,
                              extended_permissions=None):
        """Authenticates/installs this app for the current user."""
        self.require_setting("facebook_api_key", "Facebook Connect")
        callback_uri = callback_uri or self.request.uri
        args = {
            "api_key": self.settings["facebook_api_key"],
            "v": "1.0",
            "fbconnect": "true",
            "display": "page",
            "next": urlparse.urljoin(self.request.full_url(), callback_uri),
            "return_session": "true",
        }
        if cancel_uri:
            args["cancel_url"] = urlparse.urljoin(
                self.request.full_url(), cancel_uri)
        if extended_permissions:
            if isinstance(extended_permissions, (unicode, bytes_type)):
                extended_permissions = [extended_permissions]
            args["req_perms"] = ",".join(extended_permissions)
        self.redirect("http://www.facebook.com/login.php?" +
                      urllib.urlencode(args))

    def authorize_redirect(self, extended_permissions, callback_uri=None,
                           cancel_uri=None):
        """Redirects to an authorization request for the given FB resource.

        The available resource names are listed at
        http://wiki.developers.facebook.com/index.php/Extended_permission.
        The most common resource types include:

        * publish_stream
        * read_stream
        * email
        * sms

        extended_permissions can be a single permission name or a list of
        names. To get the session secret and session key, call
        get_authenticated_user() just as you would with
        authenticate_redirect().
        """
        self.authenticate_redirect(callback_uri, cancel_uri,
                                   extended_permissions)

    def get_authenticated_user(self, callback):
        """Fetches the authenticated Facebook user.

        The authenticated user includes the special Facebook attributes
        'session_key' and 'facebook_uid' in addition to the standard
        user attributes like 'name'.
        """
        self.require_setting("facebook_api_key", "Facebook Connect")
        session = escape.json_decode(self.get_argument("session"))
        self.facebook_request(
            method="facebook.users.getInfo",
            callback=self.async_callback(
                self._on_get_user_info, callback, session),
            session_key=session["session_key"],
            uids=session["uid"],
            fields="uid,first_name,last_name,name,locale,pic_square," \
                   "profile_url,username")

    def facebook_request(self, method, callback, **args):
        """Makes a Facebook API REST request.

        We automatically include the Facebook API key and signature, but
        it is the callers responsibility to include 'session_key' and any
        other required arguments to the method.

        The available Facebook methods are documented here:
        http://wiki.developers.facebook.com/index.php/API

        Here is an example for the stream.get() method::

            class MainHandler(tornado.web.RequestHandler,
                              tornado.auth.FacebookMixin):
                @tornado.web.authenticated
                @tornado.web.asynchronous
                def get(self):
                    self.facebook_request(
                        method="stream.get",
                        callback=self.async_callback(self._on_stream),
                        session_key=self.current_user["session_key"])

                def _on_stream(self, stream):
                    if stream is None:
                       # Not authorized to read the stream yet?
                       self.redirect(self.authorize_redirect("read_stream"))
                       return
                    self.render("stream.html", stream=stream)

        """
        self.require_setting("facebook_api_key", "Facebook Connect")
        self.require_setting("facebook_secret", "Facebook Connect")
        if not method.startswith("facebook."):
            method = "facebook." + method
        args["api_key"] = self.settings["facebook_api_key"]
        args["v"] = "1.0"
        args["method"] = method
        args["call_id"] = str(long(time.time() * 1e6))
        args["format"] = "json"
        args["sig"] = self._signature(args)
        url = "http://api.facebook.com/restserver.php?" + \
            urllib.urlencode(args)
        http = httpclient.AsyncHTTPClient()
        http.fetch(url, callback=self.async_callback(
            self._parse_response, callback))

    def _on_get_user_info(self, callback, session, users):
        if users is None:
            callback(None)
            return
        callback({
            "name": users[0]["name"],
            "first_name": users[0]["first_name"],
            "last_name": users[0]["last_name"],
            "uid": users[0]["uid"],
            "locale": users[0]["locale"],
            "pic_square": users[0]["pic_square"],
            "profile_url": users[0]["profile_url"],
            "username": users[0].get("username"),
            "session_key": session["session_key"],
            "session_expires": session.get("expires"),
        })

    def _parse_response(self, callback, response):
        if response.error:
            logging.warning("HTTP error from Facebook: %s", response.error)
            callback(None)
            return
        try:
            json = escape.json_decode(response.body)
        except Exception:
            logging.warning("Invalid JSON from Facebook: %r", response.body)
            callback(None)
            return
        if isinstance(json, dict) and json.get("error_code"):
            logging.warning("Facebook error: %d: %r", json["error_code"],
                            json.get("error_msg"))
            callback(None)
            return
        callback(json)

    def _signature(self, args):
        parts = ["%s=%s" % (n, args[n]) for n in sorted(args.keys())]
        body = "".join(parts) + self.settings["facebook_secret"]
        if isinstance(body, unicode): body = body.encode("utf-8")
        return hashlib.md5(body).hexdigest()

class FacebookGraphMixin(OAuth2Mixin):
    """Facebook authentication using the new Graph API and OAuth2."""
    _OAUTH_ACCESS_TOKEN_URL = "https://graph.facebook.com/oauth/access_token?"
    _OAUTH_AUTHORIZE_URL = "https://graph.facebook.com/oauth/authorize?"
    _OAUTH_NO_CALLBACKS = False

    def get_authenticated_user(self, redirect_uri, client_id, client_secret,
                              code, callback, extra_fields=None):
      """Handles the login for the Facebook user, returning a user object.

      Example usage::

          class FacebookGraphLoginHandler(LoginHandler, tornado.auth.FacebookGraphMixin):
            @tornado.web.asynchronous
            def get(self):
                if self.get_argument("code", False):
                    self.get_authenticated_user(
                      redirect_uri='/auth/facebookgraph/',
                      client_id=self.settings["facebook_api_key"],
                      client_secret=self.settings["facebook_secret"],
                      code=self.get_argument("code"),
                      callback=self.async_callback(
                        self._on_login))
                    return
                self.authorize_redirect(redirect_uri='/auth/facebookgraph/',
                                        client_id=self.settings["facebook_api_key"],
                                        extra_params={"scope": "read_stream,offline_access"})

            def _on_login(self, user):
              logging.error(user)
              self.finish()

      """
      http = httpclient.AsyncHTTPClient()
      args = {
        "redirect_uri": redirect_uri,
        "code": code,
        "client_id": client_id,
        "client_secret": client_secret,
      }

      fields = set(['id', 'name', 'first_name', 'last_name',
                    'locale', 'picture', 'link'])
      if extra_fields: fields.update(extra_fields)

      http.fetch(self._oauth_request_token_url(**args),
          self.async_callback(self._on_access_token, redirect_uri, client_id,
                              client_secret, callback, fields))

    def _on_access_token(self, redirect_uri, client_id, client_secret,
                        callback, fields, response):
      if response.error:
          logging.warning('Facebook auth error: %s' % str(response))
          callback(None)
          return

      args = escape.parse_qs_bytes(escape.native_str(response.body))
      session = {
          "access_token": args["access_token"][-1],
          "expires": args.get("expires")
      }

      self.facebook_request(
          path="/me",
          callback=self.async_callback(
              self._on_get_user_info, callback, session, fields),
          access_token=session["access_token"],
          fields=",".join(fields)
          )


    def _on_get_user_info(self, callback, session, fields, user):
        if user is None:
            callback(None)
            return

        fieldmap = {}
        for field in fields:
            fieldmap[field] = user.get(field)

        fieldmap.update({"access_token": session["access_token"], "session_expires": session.get("expires")})
        callback(fieldmap)

    def facebook_request(self, path, callback, access_token=None,
                           post_args=None, **args):
        """Fetches the given relative API path, e.g., "/btaylor/picture"

        If the request is a POST, post_args should be provided. Query
        string arguments should be given as keyword arguments.

        An introduction to the Facebook Graph API can be found at
        http://developers.facebook.com/docs/api

        Many methods require an OAuth access token which you can obtain
        through authorize_redirect() and get_authenticated_user(). The
        user returned through that process includes an 'access_token'
        attribute that can be used to make authenticated requests via
        this method. Example usage::

            class MainHandler(tornado.web.RequestHandler,
                              tornado.auth.FacebookGraphMixin):
                @tornado.web.authenticated
                @tornado.web.asynchronous
                def get(self):
                    self.facebook_request(
                        "/me/feed",
                        post_args={"message": "I am posting from my Tornado application!"},
                        access_token=self.current_user["access_token"],
                        callback=self.async_callback(self._on_post))

                def _on_post(self, new_entry):
                    if not new_entry:
                        # Call failed; perhaps missing permission?
                        self.authorize_redirect()
                        return
                    self.finish("Posted a message!")

        """
        url = "https://graph.facebook.com" + path
        all_args = {}
        if access_token:
            all_args["access_token"] = access_token
            all_args.update(args)
            all_args.update(post_args or {})
        if all_args: url += "?" + urllib.urlencode(all_args)
        callback = self.async_callback(self._on_facebook_request, callback)
        http = httpclient.AsyncHTTPClient()
        if post_args is not None:
            http.fetch(url, method="POST", body=urllib.urlencode(post_args),
                       callback=callback)
        else:
            http.fetch(url, callback=callback)

    def _on_facebook_request(self, callback, response):
        if response.error:
            logging.warning("Error response %s fetching %s", response.error,
                            response.request.url)
            callback(None)
            return
        callback(escape.json_decode(response.body))

def _oauth_signature(consumer_token, method, url, parameters={}, token=None):
    """Calculates the HMAC-SHA1 OAuth signature for the given request.

    See http://oauth.net/core/1.0/#signing_process
    """
    parts = urlparse.urlparse(url)
    scheme, netloc, path = parts[:3]
    normalized_url = scheme.lower() + "://" + netloc.lower() + path

    base_elems = []
    base_elems.append(method.upper())
    base_elems.append(normalized_url)
    base_elems.append("&".join("%s=%s" % (k, _oauth_escape(str(v)))
                               for k, v in sorted(parameters.items())))
    base_string =  "&".join(_oauth_escape(e) for e in base_elems)

    key_elems = [consumer_token["secret"]]
    key_elems.append(token["secret"] if token else "")
    key = "&".join(key_elems)

    hash = hmac.new(key, base_string, hashlib.sha1)
    return binascii.b2a_base64(hash.digest())[:-1]

def _oauth10a_signature(consumer_token, method, url, parameters={}, token=None):
    """Calculates the HMAC-SHA1 OAuth 1.0a signature for the given request.

    See http://oauth.net/core/1.0a/#signing_process
    """
    parts = urlparse.urlparse(url)
    scheme, netloc, path = parts[:3]
    normalized_url = scheme.lower() + "://" + netloc.lower() + path

    base_elems = []
    base_elems.append(method.upper())
    base_elems.append(normalized_url)
    base_elems.append("&".join("%s=%s" % (k, _oauth_escape(str(v)))
                               for k, v in sorted(parameters.items())))

    base_string =  "&".join(_oauth_escape(e) for e in base_elems)
    key_elems = [urllib.quote(consumer_token["secret"], safe='~')]
    key_elems.append(urllib.quote(token["secret"], safe='~') if token else "")
    key = "&".join(key_elems)

    hash = hmac.new(key, base_string, hashlib.sha1)
    return binascii.b2a_base64(hash.digest())[:-1]

def _oauth_escape(val):
    if isinstance(val, unicode):
        val = val.encode("utf-8")
    return urllib.quote(val, safe="~")


def _oauth_parse_response(body):
    p = cgi.parse_qs(body, keep_blank_values=False)
    token = dict(key=p["oauth_token"][0], secret=p["oauth_token_secret"][0])

    # Add the extra parameters the Provider included to the token
    special = ("oauth_token", "oauth_token_secret")
    token.update((k, p[k][0]) for k in p if k not in special)
    return token


