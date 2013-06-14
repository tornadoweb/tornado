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

"""This module contains implementations of various third-party
authentication schemes.

All the classes in this file are class mixins designed to be used with
the `tornado.web.RequestHandler` class.  They are used in two ways:

* On a login handler, use methods such as ``authenticate_redirect()``,
  ``authorize_redirect()``, and ``get_authenticated_user()`` to
  establish the user's identity and store authentication tokens to your
  database and/or cookies.
* In non-login handlers, use methods such as ``facebook_request()``
  or ``twitter_request()`` to use the authentication tokens to make
  requests to the respective services.

They all take slightly different arguments due to the fact all these
services implement authentication and authorization slightly differently.
See the individual service classes below for complete documentation.

Example usage for Google OpenID::

    class GoogleLoginHandler(tornado.web.RequestHandler,
                             tornado.auth.GoogleMixin):
        @tornado.web.asynchronous
        @tornado.gen.coroutine
        def get(self):
            if self.get_argument("openid.mode", None):
                user = yield self.get_authenticated_user()
                # Save the user with e.g. set_secure_cookie()
            else:
                yield self.authenticate_redirect()
"""

from __future__ import absolute_import, division, print_function, with_statement

import base64
import binascii
import functools
import hashlib
import hmac
import time
import uuid

from tornado.concurrent import Future, chain_future, return_future
from tornado import gen
from tornado import httpclient
from tornado import escape
from tornado.httputil import url_concat
from tornado.log import gen_log
from tornado.util import bytes_type, u, unicode_type, ArgReplacer

try:
    import urlparse  # py2
except ImportError:
    import urllib.parse as urlparse  # py3

try:
    import urllib.parse as urllib_parse  # py3
except ImportError:
    import urllib as urllib_parse  # py2


class AuthError(Exception):
    pass


def _auth_future_to_callback(callback, future):
    try:
        result = future.result()
    except AuthError as e:
        gen_log.warning(str(e))
        result = None
    callback(result)


def _auth_return_future(f):
    """Similar to tornado.concurrent.return_future, but uses the auth
    module's legacy callback interface.

    Note that when using this decorator the ``callback`` parameter
    inside the function will actually be a future.
    """
    replacer = ArgReplacer(f, 'callback')

    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        future = Future()
        callback, args, kwargs = replacer.replace(future, args, kwargs)
        if callback is not None:
            future.add_done_callback(
                functools.partial(_auth_future_to_callback, callback))
        f(*args, **kwargs)
        return future
    return wrapper


class OpenIdMixin(object):
    """Abstract implementation of OpenID and Attribute Exchange.

    See `GoogleMixin` below for a customized example (which also
    includes OAuth support).

    Class attributes:

    * ``_OPENID_ENDPOINT``: the identity provider's URI.
    """
    @return_future
    def authenticate_redirect(self, callback_uri=None,
                              ax_attrs=["name", "email", "language", "username"],
                              callback=None):
        """Redirects to the authentication URL for this service.

        After authentication, the service will redirect back to the given
        callback URI with additional parameters including ``openid.mode``.

        We request the given attributes for the authenticated user by
        default (name, email, language, and username). If you don't need
        all those attributes for your app, you can request fewer with
        the ax_attrs keyword argument.

        .. versionchanged:: 3.1
           Returns a `.Future` and takes an optional callback.  These are
           not strictly necessary as this method is synchronous,
           but they are supplied for consistency with
           `OAuthMixin.authorize_redirect`.
        """
        callback_uri = callback_uri or self.request.uri
        args = self._openid_args(callback_uri, ax_attrs=ax_attrs)
        self.redirect(self._OPENID_ENDPOINT + "?" + urllib_parse.urlencode(args))
        callback()

    @_auth_return_future
    def get_authenticated_user(self, callback, http_client=None):
        """Fetches the authenticated user data upon redirect.

        This method should be called by the handler that receives the
        redirect from the `authenticate_redirect()` method (which is
        often the same as the one that calls it; in that case you would
        call `get_authenticated_user` if the ``openid.mode`` parameter
        is present and `authenticate_redirect` if it is not).

        The result of this method will generally be used to set a cookie.
        """
        # Verify the OpenID response via direct request to the OP
        args = dict((k, v[-1]) for k, v in self.request.arguments.items())
        args["openid.mode"] = u("check_authentication")
        url = self._OPENID_ENDPOINT
        if http_client is None:
            http_client = self.get_auth_http_client()
        http_client.fetch(url, self.async_callback(
            self._on_authentication_verified, callback),
            method="POST", body=urllib_parse.urlencode(args))

    def _openid_args(self, callback_uri, ax_attrs=[], oauth_scope=None):
        url = urlparse.urljoin(self.request.full_url(), callback_uri)
        args = {
            "openid.ns": "http://specs.openid.net/auth/2.0",
            "openid.claimed_id":
            "http://specs.openid.net/auth/2.0/identifier_select",
            "openid.identity":
            "http://specs.openid.net/auth/2.0/identifier_select",
            "openid.return_to": url,
            "openid.realm": urlparse.urljoin(url, '/'),
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

    def _on_authentication_verified(self, future, response):
        if response.error or b"is_valid:true" not in response.body:
            future.set_exception(AuthError(
                "Invalid OpenID response: %s" % (response.error or
                                                 response.body)))
            return

        # Make sure we got back at least an email from attribute exchange
        ax_ns = None
        for name in self.request.arguments:
            if name.startswith("openid.ns.") and \
                    self.get_argument(name) == u("http://openid.net/srv/ax/1.0"):
                ax_ns = name[10:]
                break

        def get_ax_arg(uri):
            if not ax_ns:
                return u("")
            prefix = "openid." + ax_ns + ".type."
            ax_name = None
            for name in self.request.arguments.keys():
                if self.get_argument(name) == uri and name.startswith(prefix):
                    part = name[len(prefix):]
                    ax_name = "openid." + ax_ns + ".value." + part
                    break
            if not ax_name:
                return u("")
            return self.get_argument(ax_name, u(""))

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
            user["name"] = u(" ").join(name_parts)
        elif email:
            user["name"] = email.split("@")[0]
        if email:
            user["email"] = email
        if locale:
            user["locale"] = locale
        if username:
            user["username"] = username
        claimed_id = self.get_argument("openid.claimed_id", None)
        if claimed_id:
            user["claimed_id"] = claimed_id
        future.set_result(user)

    def get_auth_http_client(self):
        """Returns the `.AsyncHTTPClient` instance to be used for auth requests.

        May be overridden by subclasses to use an HTTP client other than
        the default.
        """
        return httpclient.AsyncHTTPClient()


class OAuthMixin(object):
    """Abstract implementation of OAuth 1.0 and 1.0a.

    See `TwitterMixin` and `FriendFeedMixin` below for example implementations,
    or `GoogleMixin` for an OAuth/OpenID hybrid.

    Class attributes:

    * ``_OAUTH_AUTHORIZE_URL``: The service's OAuth authorization url.
    * ``_OAUTH_ACCESS_TOKEN_URL``: The service's OAuth access token url.
    * ``_OAUTH_VERSION``: May be either "1.0" or "1.0a".
    * ``_OAUTH_NO_CALLBACKS``: Set this to True if the service requires
      advance registration of callbacks.

    Subclasses must also override the `_oauth_get_user_future` and
    `_oauth_consumer_token` methods.
    """
    @return_future
    def authorize_redirect(self, callback_uri=None, extra_params=None,
                           http_client=None, callback=None):
        """Redirects the user to obtain OAuth authorization for this service.

        The ``callback_uri`` may be omitted if you have previously
        registered a callback URI with the third-party service.  For
        some sevices (including Friendfeed), you must use a
        previously-registered callback URI and cannot specify a
        callback via this method.

        This method sets a cookie called ``_oauth_request_token`` which is
        subsequently used (and cleared) in `get_authenticated_user` for
        security purposes.

        Note that this method is asynchronous, although it calls
        `.RequestHandler.finish` for you so it may not be necessary
        to pass a callback or use the `.Future` it returns.  However,
        if this method is called from a function decorated with
        `.gen.coroutine`, you must call it with ``yield`` to keep the
        response from being closed prematurely.

        .. versionchanged:: 3.1
           Now returns a `.Future` and takes an optional callback, for
           compatibility with `.gen.coroutine`.
        """
        if callback_uri and getattr(self, "_OAUTH_NO_CALLBACKS", False):
            raise Exception("This service does not support oauth_callback")
        if http_client is None:
            http_client = self.get_auth_http_client()
        if getattr(self, "_OAUTH_VERSION", "1.0a") == "1.0a":
            http_client.fetch(
                self._oauth_request_token_url(callback_uri=callback_uri,
                                              extra_params=extra_params),
                self.async_callback(
                    self._on_request_token,
                    self._OAUTH_AUTHORIZE_URL,
                    callback_uri,
                    callback))
        else:
            http_client.fetch(
                self._oauth_request_token_url(),
                self.async_callback(
                    self._on_request_token, self._OAUTH_AUTHORIZE_URL,
                    callback_uri,
                    callback))

    @_auth_return_future
    def get_authenticated_user(self, callback, http_client=None):
        """Gets the OAuth authorized user and access token.

        This method should be called from the handler for your
        OAuth callback URL to complete the registration process. We run the
        callback with the authenticated user dictionary.  This dictionary
        will contain an ``access_key`` which can be used to make authorized
        requests to this service on behalf of the user.  The dictionary will
        also contain other fields such as ``name``, depending on the service
        used.
        """
        future = callback
        request_key = escape.utf8(self.get_argument("oauth_token"))
        oauth_verifier = self.get_argument("oauth_verifier", None)
        request_cookie = self.get_cookie("_oauth_request_token")
        if not request_cookie:
            future.set_exception(AuthError(
                "Missing OAuth request token cookie"))
            return
        self.clear_cookie("_oauth_request_token")
        cookie_key, cookie_secret = [base64.b64decode(escape.utf8(i)) for i in request_cookie.split("|")]
        if cookie_key != request_key:
            future.set_exception(AuthError(
                "Request token does not match cookie"))
            return
        token = dict(key=cookie_key, secret=cookie_secret)
        if oauth_verifier:
            token["verifier"] = oauth_verifier
        if http_client is None:
            http_client = self.get_auth_http_client()
        http_client.fetch(self._oauth_access_token_url(token),
                          self.async_callback(self._on_access_token, callback))

    def _oauth_request_token_url(self, callback_uri=None, extra_params=None):
        consumer_token = self._oauth_consumer_token()
        url = self._OAUTH_REQUEST_TOKEN_URL
        args = dict(
            oauth_consumer_key=escape.to_basestring(consumer_token["key"]),
            oauth_signature_method="HMAC-SHA1",
            oauth_timestamp=str(int(time.time())),
            oauth_nonce=escape.to_basestring(binascii.b2a_hex(uuid.uuid4().bytes)),
            oauth_version="1.0",
        )
        if getattr(self, "_OAUTH_VERSION", "1.0a") == "1.0a":
            if callback_uri == "oob":
                args["oauth_callback"] = "oob"
            elif callback_uri:
                args["oauth_callback"] = urlparse.urljoin(
                    self.request.full_url(), callback_uri)
            if extra_params:
                args.update(extra_params)
            signature = _oauth10a_signature(consumer_token, "GET", url, args)
        else:
            signature = _oauth_signature(consumer_token, "GET", url, args)

        args["oauth_signature"] = signature
        return url + "?" + urllib_parse.urlencode(args)

    def _on_request_token(self, authorize_url, callback_uri, callback,
                          response):
        if response.error:
            raise Exception("Could not get request token: %s" % response.error)
        request_token = _oauth_parse_response(response.body)
        data = (base64.b64encode(escape.utf8(request_token["key"])) + b"|" +
                base64.b64encode(escape.utf8(request_token["secret"])))
        self.set_cookie("_oauth_request_token", data)
        args = dict(oauth_token=request_token["key"])
        if callback_uri == "oob":
            self.finish(authorize_url + "?" + urllib_parse.urlencode(args))
            callback()
            return
        elif callback_uri:
            args["oauth_callback"] = urlparse.urljoin(
                self.request.full_url(), callback_uri)
        self.redirect(authorize_url + "?" + urllib_parse.urlencode(args))
        callback()

    def _oauth_access_token_url(self, request_token):
        consumer_token = self._oauth_consumer_token()
        url = self._OAUTH_ACCESS_TOKEN_URL
        args = dict(
            oauth_consumer_key=escape.to_basestring(consumer_token["key"]),
            oauth_token=escape.to_basestring(request_token["key"]),
            oauth_signature_method="HMAC-SHA1",
            oauth_timestamp=str(int(time.time())),
            oauth_nonce=escape.to_basestring(binascii.b2a_hex(uuid.uuid4().bytes)),
            oauth_version="1.0",
        )
        if "verifier" in request_token:
            args["oauth_verifier"] = request_token["verifier"]

        if getattr(self, "_OAUTH_VERSION", "1.0a") == "1.0a":
            signature = _oauth10a_signature(consumer_token, "GET", url, args,
                                            request_token)
        else:
            signature = _oauth_signature(consumer_token, "GET", url, args,
                                         request_token)

        args["oauth_signature"] = signature
        return url + "?" + urllib_parse.urlencode(args)

    def _on_access_token(self, future, response):
        if response.error:
            future.set_exception(AuthError("Could not fetch access token"))
            return

        access_token = _oauth_parse_response(response.body)
        self._oauth_get_user_future(access_token).add_done_callback(
            self.async_callback(self._on_oauth_get_user, access_token, future))

    def _oauth_consumer_token(self):
        """Subclasses must override this to return their OAuth consumer keys.

        The return value should be a `dict` with keys ``key`` and ``secret``.
        """
        raise NotImplementedError()

    @return_future
    def _oauth_get_user_future(self, access_token, callback):
        """Subclasses must override this to get basic information about the
        user.

        Should return a `.Future` whose result is a dictionary
        containing information about the user, which may have been
        retrieved by using ``access_token`` to make a request to the
        service.

        The access token will be added to the returned dictionary to make
        the result of `get_authenticated_user`.

        For backwards compatibility, the callback-based ``_oauth_get_user``
        method is also supported.
        """
        # By default, call the old-style _oauth_get_user, but new code
        # should override this method instead.
        self._oauth_get_user(access_token, callback)

    def _oauth_get_user(self, access_token, callback):
        raise NotImplementedError()

    def _on_oauth_get_user(self, access_token, future, user_future):
        if user_future.exception() is not None:
            future.set_exception(user_future.exception())
            return
        user = user_future.result()
        if not user:
            future.set_exception(AuthError("Error getting user"))
            return
        user["access_token"] = access_token
        future.set_result(user)

    def _oauth_request_parameters(self, url, access_token, parameters={},
                                  method="GET"):
        """Returns the OAuth parameters as a dict for the given request.

        parameters should include all POST arguments and query string arguments
        that will be sent with the request.
        """
        consumer_token = self._oauth_consumer_token()
        base_args = dict(
            oauth_consumer_key=escape.to_basestring(consumer_token["key"]),
            oauth_token=escape.to_basestring(access_token["key"]),
            oauth_signature_method="HMAC-SHA1",
            oauth_timestamp=str(int(time.time())),
            oauth_nonce=escape.to_basestring(binascii.b2a_hex(uuid.uuid4().bytes)),
            oauth_version="1.0",
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
        base_args["oauth_signature"] = escape.to_basestring(signature)
        return base_args

    def get_auth_http_client(self):
        """Returns the `.AsyncHTTPClient` instance to be used for auth requests.

        May be overridden by subclasses to use an HTTP client other than
        the default.
        """
        return httpclient.AsyncHTTPClient()


class OAuth2Mixin(object):
    """Abstract implementation of OAuth 2.0.

    See `FacebookGraphMixin` below for an example implementation.

    Class attributes:

    * ``_OAUTH_AUTHORIZE_URL``: The service's authorization url.
    * ``_OAUTH_ACCESS_TOKEN_URL``:  The service's access token url.
    """
    @return_future
    def authorize_redirect(self, redirect_uri=None, client_id=None,
                           client_secret=None, extra_params=None,
                           callback=None):
        """Redirects the user to obtain OAuth authorization for this service.

        Some providers require that you register a redirect URL with
        your application instead of passing one via this method. You
        should call this method to log the user in, and then call
        ``get_authenticated_user`` in the handler for your
        redirect URL to complete the authorization process.

        .. versionchanged:: 3.1
           Returns a `.Future` and takes an optional callback.  These are
           not strictly necessary as this method is synchronous,
           but they are supplied for consistency with
           `OAuthMixin.authorize_redirect`.
        """
        args = {
            "redirect_uri": redirect_uri,
            "client_id": client_id
        }
        if extra_params:
            args.update(extra_params)
        self.redirect(
            url_concat(self._OAUTH_AUTHORIZE_URL, args))
        callback()

    def _oauth_request_token_url(self, redirect_uri=None, client_id=None,
                                 client_secret=None, code=None,
                                 extra_params=None):
        url = self._OAUTH_ACCESS_TOKEN_URL
        args = dict(
            redirect_uri=redirect_uri,
            code=code,
            client_id=client_id,
            client_secret=client_secret,
        )
        if extra_params:
            args.update(extra_params)
        return url_concat(url, args)


class TwitterMixin(OAuthMixin):
    """Twitter OAuth authentication.

    To authenticate with Twitter, register your application with
    Twitter at http://twitter.com/apps. Then copy your Consumer Key
    and Consumer Secret to the application
    `~tornado.web.Application.settings` ``twitter_consumer_key`` and
    ``twitter_consumer_secret``. Use this mixin on the handler for the
    URL you registered as your application's callback URL.

    When your application is set up, you can use this mixin like this
    to authenticate the user with Twitter and get access to their stream::

        class TwitterLoginHandler(tornado.web.RequestHandler,
                                  tornado.auth.TwitterMixin):
            @tornado.web.asynchronous
            @tornado.gen.coroutine
            def get(self):
                if self.get_argument("oauth_token", None):
                    user = yield self.get_authenticated_user()
                    # Save the user using e.g. set_secure_cookie()
                else:
                    yield self.authorize_redirect()

    The user object returned by `~OAuthMixin.get_authenticated_user`
    includes the attributes ``username``, ``name``, ``access_token``,
    and all of the custom Twitter user attributes described at
    https://dev.twitter.com/docs/api/1.1/get/users/show
    """
    _OAUTH_REQUEST_TOKEN_URL = "https://api.twitter.com/oauth/request_token"
    _OAUTH_ACCESS_TOKEN_URL = "https://api.twitter.com/oauth/access_token"
    _OAUTH_AUTHORIZE_URL = "https://api.twitter.com/oauth/authorize"
    _OAUTH_AUTHENTICATE_URL = "https://api.twitter.com/oauth/authenticate"
    _OAUTH_NO_CALLBACKS = False
    _TWITTER_BASE_URL = "https://api.twitter.com/1.1"

    @return_future
    def authenticate_redirect(self, callback_uri=None, callback=None):
        """Just like `~OAuthMixin.authorize_redirect`, but
        auto-redirects if authorized.

        This is generally the right interface to use if you are using
        Twitter for single-sign on.

        .. versionchanged:: 3.1
           Now returns a `.Future` and takes an optional callback, for
           compatibility with `.gen.coroutine`.
        """
        http = self.get_auth_http_client()
        http.fetch(self._oauth_request_token_url(callback_uri=callback_uri),
                   self.async_callback(
                       self._on_request_token, self._OAUTH_AUTHENTICATE_URL,
                       None, callback))

    @_auth_return_future
    def twitter_request(self, path, callback=None, access_token=None,
                        post_args=None, **args):
        """Fetches the given API path, e.g., ``statuses/user_timeline/btaylor``

        The path should not include the format or API version number.
        (we automatically use JSON format and API version 1).

        If the request is a POST, ``post_args`` should be provided. Query
        string arguments should be given as keyword arguments.

        All the Twitter methods are documented at http://dev.twitter.com/

        Many methods require an OAuth access token which you can
        obtain through `~OAuthMixin.authorize_redirect` and
        `~OAuthMixin.get_authenticated_user`. The user returned through that
        process includes an 'access_token' attribute that can be used
        to make authenticated requests via this method. Example
        usage::

            class MainHandler(tornado.web.RequestHandler,
                              tornado.auth.TwitterMixin):
                @tornado.web.authenticated
                @tornado.web.asynchronous
                @tornado.gen.coroutine
                def get(self):
                    new_entry = yield self.twitter_request(
                        "/statuses/update",
                        post_args={"status": "Testing Tornado Web Server"},
                        access_token=self.current_user["access_token"])
                    if not new_entry:
                        # Call failed; perhaps missing permission?
                        yield self.authorize_redirect()
                        return
                    self.finish("Posted a message!")

        """
        if path.startswith('http:') or path.startswith('https:'):
            # Raw urls are useful for e.g. search which doesn't follow the
            # usual pattern: http://search.twitter.com/search.json
            url = path
        else:
            url = self._TWITTER_BASE_URL + path + ".json"
        # Add the OAuth resource request signature if we have credentials
        if access_token:
            all_args = {}
            all_args.update(args)
            all_args.update(post_args or {})
            method = "POST" if post_args is not None else "GET"
            oauth = self._oauth_request_parameters(
                url, access_token, all_args, method=method)
            args.update(oauth)
        if args:
            url += "?" + urllib_parse.urlencode(args)
        http = self.get_auth_http_client()
        http_callback = self.async_callback(self._on_twitter_request, callback)
        if post_args is not None:
            http.fetch(url, method="POST", body=urllib_parse.urlencode(post_args),
                       callback=http_callback)
        else:
            http.fetch(url, callback=http_callback)

    def _on_twitter_request(self, future, response):
        if response.error:
            future.set_exception(AuthError(
                "Error response %s fetching %s" % (response.error,
                                                   response.request.url)))
            return
        future.set_result(escape.json_decode(response.body))

    def _oauth_consumer_token(self):
        self.require_setting("twitter_consumer_key", "Twitter OAuth")
        self.require_setting("twitter_consumer_secret", "Twitter OAuth")
        return dict(
            key=self.settings["twitter_consumer_key"],
            secret=self.settings["twitter_consumer_secret"])

    @gen.coroutine
    def _oauth_get_user_future(self, access_token):
        user = yield self.twitter_request(
            "/account/verify_credentials",
            access_token=access_token)
        if user:
            user["username"] = user["screen_name"]
        raise gen.Return(user)


class FriendFeedMixin(OAuthMixin):
    """FriendFeed OAuth authentication.

    To authenticate with FriendFeed, register your application with
    FriendFeed at http://friendfeed.com/api/applications. Then copy
    your Consumer Key and Consumer Secret to the application
    `~tornado.web.Application.settings` ``friendfeed_consumer_key``
    and ``friendfeed_consumer_secret``. Use this mixin on the handler
    for the URL you registered as your application's Callback URL.

    When your application is set up, you can use this mixin like this
    to authenticate the user with FriendFeed and get access to their feed::

        class FriendFeedLoginHandler(tornado.web.RequestHandler,
                                     tornado.auth.FriendFeedMixin):
            @tornado.web.asynchronous
            @tornado.gen.coroutine
            def get(self):
                if self.get_argument("oauth_token", None):
                    user = yield self.get_authenticated_user()
                    # Save the user using e.g. set_secure_cookie()
                else:
                    yield self.authorize_redirect()

    The user object returned by `~OAuthMixin.get_authenticated_user()` includes the
    attributes ``username``, ``name``, and ``description`` in addition to
    ``access_token``. You should save the access token with the user;
    it is required to make requests on behalf of the user later with
    `friendfeed_request()`.
    """
    _OAUTH_VERSION = "1.0"
    _OAUTH_REQUEST_TOKEN_URL = "https://friendfeed.com/account/oauth/request_token"
    _OAUTH_ACCESS_TOKEN_URL = "https://friendfeed.com/account/oauth/access_token"
    _OAUTH_AUTHORIZE_URL = "https://friendfeed.com/account/oauth/authorize"
    _OAUTH_NO_CALLBACKS = True
    _OAUTH_VERSION = "1.0"

    @_auth_return_future
    def friendfeed_request(self, path, callback, access_token=None,
                           post_args=None, **args):
        """Fetches the given relative API path, e.g., "/bret/friends"

        If the request is a POST, ``post_args`` should be provided. Query
        string arguments should be given as keyword arguments.

        All the FriendFeed methods are documented at
        http://friendfeed.com/api/documentation.

        Many methods require an OAuth access token which you can
        obtain through `~OAuthMixin.authorize_redirect` and
        `~OAuthMixin.get_authenticated_user`. The user returned
        through that process includes an ``access_token`` attribute that
        can be used to make authenticated requests via this
        method.

        Example usage::

            class MainHandler(tornado.web.RequestHandler,
                              tornado.auth.FriendFeedMixin):
                @tornado.web.authenticated
                @tornado.web.asynchronous
                @tornado.gen.coroutine
                def get(self):
                    new_entry = yield self.friendfeed_request(
                        "/entry",
                        post_args={"body": "Testing Tornado Web Server"},
                        access_token=self.current_user["access_token"])

                    if not new_entry:
                        # Call failed; perhaps missing permission?
                        yield self.authorize_redirect()
                        return
                    self.finish("Posted a message!")

        """
        # Add the OAuth resource request signature if we have credentials
        url = "http://friendfeed-api.com/v2" + path
        if access_token:
            all_args = {}
            all_args.update(args)
            all_args.update(post_args or {})
            method = "POST" if post_args is not None else "GET"
            oauth = self._oauth_request_parameters(
                url, access_token, all_args, method=method)
            args.update(oauth)
        if args:
            url += "?" + urllib_parse.urlencode(args)
        callback = self.async_callback(self._on_friendfeed_request, callback)
        http = self.get_auth_http_client()
        if post_args is not None:
            http.fetch(url, method="POST", body=urllib_parse.urlencode(post_args),
                       callback=callback)
        else:
            http.fetch(url, callback=callback)

    def _on_friendfeed_request(self, future, response):
        if response.error:
            future.set_exception(AuthError(
                "Error response %s fetching %s" % (response.error,
                                                   response.request.url)))
            return
        future.set_result(escape.json_decode(response.body))

    def _oauth_consumer_token(self):
        self.require_setting("friendfeed_consumer_key", "FriendFeed OAuth")
        self.require_setting("friendfeed_consumer_secret", "FriendFeed OAuth")
        return dict(
            key=self.settings["friendfeed_consumer_key"],
            secret=self.settings["friendfeed_consumer_secret"])

    @gen.coroutine
    def _oauth_get_user_future(self, access_token, callback):
        user = yield self.friendfeed_request(
            "/feedinfo/" + access_token["username"],
            include="id,name,description", access_token=access_token)
        if user:
            user["username"] = user["id"]
        callback(user)

    def _parse_user_response(self, callback, user):
        if user:
            user["username"] = user["id"]
        callback(user)


class GoogleMixin(OpenIdMixin, OAuthMixin):
    """Google Open ID / OAuth authentication.

    No application registration is necessary to use Google for
    authentication or to access Google resources on behalf of a user.

    Google implements both OpenID and OAuth in a hybrid mode.  If you
    just need the user's identity, use
    `~OpenIdMixin.authenticate_redirect`.  If you need to make
    requests to Google on behalf of the user, use
    `authorize_redirect`.  On return, parse the response with
    `~OpenIdMixin.get_authenticated_user`. We send a dict containing
    the values for the user, including ``email``, ``name``, and
    ``locale``.

    Example usage::

        class GoogleLoginHandler(tornado.web.RequestHandler,
                                 tornado.auth.GoogleMixin):
           @tornado.web.asynchronous
           @tornado.gen.coroutine
           def get(self):
               if self.get_argument("openid.mode", None):
                   user = yield self.get_authenticated_user()
                   # Save the user with e.g. set_secure_cookie()
               else:
                   yield self.authenticate_redirect()
    """
    _OPENID_ENDPOINT = "https://www.google.com/accounts/o8/ud"
    _OAUTH_ACCESS_TOKEN_URL = "https://www.google.com/accounts/OAuthGetAccessToken"

    @return_future
    def authorize_redirect(self, oauth_scope, callback_uri=None,
                           ax_attrs=["name", "email", "language", "username"],
                           callback=None):
        """Authenticates and authorizes for the given Google resource.

        Some of the available resources which can be used in the ``oauth_scope``
        argument are:

        * Gmail Contacts - http://www.google.com/m8/feeds/
        * Calendar - http://www.google.com/calendar/feeds/
        * Finance - http://finance.google.com/finance/feeds/

        You can authorize multiple resources by separating the resource
        URLs with a space.

        .. versionchanged:: 3.1
           Returns a `.Future` and takes an optional callback.  These are
           not strictly necessary as this method is synchronous,
           but they are supplied for consistency with
           `OAuthMixin.authorize_redirect`.
        """
        callback_uri = callback_uri or self.request.uri
        args = self._openid_args(callback_uri, ax_attrs=ax_attrs,
                                 oauth_scope=oauth_scope)
        self.redirect(self._OPENID_ENDPOINT + "?" + urllib_parse.urlencode(args))
        callback()

    @_auth_return_future
    def get_authenticated_user(self, callback):
        """Fetches the authenticated user data upon redirect."""
        # Look to see if we are doing combined OpenID/OAuth
        oauth_ns = ""
        for name, values in self.request.arguments.items():
            if name.startswith("openid.ns.") and \
                    values[-1] == b"http://specs.openid.net/extensions/oauth/1.0":
                oauth_ns = name[10:]
                break
        token = self.get_argument("openid." + oauth_ns + ".request_token", "")
        if token:
            http = self.get_auth_http_client()
            token = dict(key=token, secret="")
            http.fetch(self._oauth_access_token_url(token),
                       self.async_callback(self._on_access_token, callback))
        else:
            chain_future(OpenIdMixin.get_authenticated_user(self),
                         callback)

    def _oauth_consumer_token(self):
        self.require_setting("google_consumer_key", "Google OAuth")
        self.require_setting("google_consumer_secret", "Google OAuth")
        return dict(
            key=self.settings["google_consumer_key"],
            secret=self.settings["google_consumer_secret"])

    def _oauth_get_user_future(self, access_token):
        return OpenIdMixin.get_authenticated_user(self)


class FacebookMixin(object):
    """Facebook Connect authentication.

    *Deprecated:* New applications should use `FacebookGraphMixin`
    below instead of this class.  This class does not support the
    Future-based interface seen on other classes in this module.

    To authenticate with Facebook, register your application with
    Facebook at http://www.facebook.com/developers/apps.php. Then
    copy your API Key and Application Secret to the application settings
    ``facebook_api_key`` and ``facebook_secret``.

    When your application is set up, you can use this mixin like this
    to authenticate the user with Facebook::

        class FacebookHandler(tornado.web.RequestHandler,
                              tornado.auth.FacebookMixin):
            @tornado.web.asynchronous
            def get(self):
                if self.get_argument("session", None):
                    self.get_authenticated_user(self.async_callback(self._on_auth))
                    return
                yield self.authenticate_redirect()

            def _on_auth(self, user):
                if not user:
                    raise tornado.web.HTTPError(500, "Facebook auth failed")
                # Save the user using, e.g., set_secure_cookie()

    The user object returned by `get_authenticated_user` includes the
    attributes ``facebook_uid`` and ``name`` in addition to session attributes
    like ``session_key``. You should save the session key with the user; it is
    required to make requests on behalf of the user later with
    `facebook_request`.
    """
    @return_future
    def authenticate_redirect(self, callback_uri=None, cancel_uri=None,
                              extended_permissions=None, callback=None):
        """Authenticates/installs this app for the current user.

        .. versionchanged:: 3.1
           Returns a `.Future` and takes an optional callback.  These are
           not strictly necessary as this method is synchronous,
           but they are supplied for consistency with
           `OAuthMixin.authorize_redirect`.
        """
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
            if isinstance(extended_permissions, (unicode_type, bytes_type)):
                extended_permissions = [extended_permissions]
            args["req_perms"] = ",".join(extended_permissions)
        self.redirect("http://www.facebook.com/login.php?" +
                      urllib_parse.urlencode(args))
        callback()

    def authorize_redirect(self, extended_permissions, callback_uri=None,
                           cancel_uri=None, callback=None):
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

        .. versionchanged:: 3.1
           Returns a `.Future` and takes an optional callback.  These are
           not strictly necessary as this method is synchronous,
           but they are supplied for consistency with
           `OAuthMixin.authorize_redirect`.
        """
        return self.authenticate_redirect(callback_uri, cancel_uri,
                                          extended_permissions,
                                          callback=callback)

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
            fields="uid,first_name,last_name,name,locale,pic_square,"
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
            urllib_parse.urlencode(args)
        http = self.get_auth_http_client()
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
            gen_log.warning("HTTP error from Facebook: %s", response.error)
            callback(None)
            return
        try:
            json = escape.json_decode(response.body)
        except Exception:
            gen_log.warning("Invalid JSON from Facebook: %r", response.body)
            callback(None)
            return
        if isinstance(json, dict) and json.get("error_code"):
            gen_log.warning("Facebook error: %d: %r", json["error_code"],
                            json.get("error_msg"))
            callback(None)
            return
        callback(json)

    def _signature(self, args):
        parts = ["%s=%s" % (n, args[n]) for n in sorted(args.keys())]
        body = "".join(parts) + self.settings["facebook_secret"]
        if isinstance(body, unicode_type):
            body = body.encode("utf-8")
        return hashlib.md5(body).hexdigest()

    def get_auth_http_client(self):
        """Returns the `.AsyncHTTPClient` instance to be used for auth requests.

        May be overridden by subclasses to use an HTTP client other than
        the default.
        """
        return httpclient.AsyncHTTPClient()


class FacebookGraphMixin(OAuth2Mixin):
    """Facebook authentication using the new Graph API and OAuth2."""
    _OAUTH_ACCESS_TOKEN_URL = "https://graph.facebook.com/oauth/access_token?"
    _OAUTH_AUTHORIZE_URL = "https://graph.facebook.com/oauth/authorize?"
    _OAUTH_NO_CALLBACKS = False
    _FACEBOOK_BASE_URL = "https://graph.facebook.com"

    @_auth_return_future
    def get_authenticated_user(self, redirect_uri, client_id, client_secret,
                               code, callback, extra_fields=None):
        """Handles the login for the Facebook user, returning a user object.

        Example usage::

            class FacebookGraphLoginHandler(LoginHandler, tornado.auth.FacebookGraphMixin):
              @tornado.web.asynchronous
              @tornado.gen.coroutine
              def get(self):
                  if self.get_argument("code", False):
                      user = yield self.get_authenticated_user(
                          redirect_uri='/auth/facebookgraph/',
                          client_id=self.settings["facebook_api_key"],
                          client_secret=self.settings["facebook_secret"],
                          code=self.get_argument("code"))
                      # Save the user with e.g. set_secure_cookie
                  else:
                      yield self.authorize_redirect(
                          redirect_uri='/auth/facebookgraph/',
                          client_id=self.settings["facebook_api_key"],
                          extra_params={"scope": "read_stream,offline_access"})
        """
        http = self.get_auth_http_client()
        args = {
            "redirect_uri": redirect_uri,
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
        }

        fields = set(['id', 'name', 'first_name', 'last_name',
                      'locale', 'picture', 'link'])
        if extra_fields:
            fields.update(extra_fields)

        http.fetch(self._oauth_request_token_url(**args),
                   self.async_callback(self._on_access_token, redirect_uri, client_id,
                                       client_secret, callback, fields))

    def _on_access_token(self, redirect_uri, client_id, client_secret,
                         future, fields, response):
        if response.error:
            future.set_exception(AuthError('Facebook auth error: %s' % str(response)))
            return

        args = escape.parse_qs_bytes(escape.native_str(response.body))
        session = {
            "access_token": args["access_token"][-1],
            "expires": args.get("expires")
        }

        self.facebook_request(
            path="/me",
            callback=self.async_callback(
                self._on_get_user_info, future, session, fields),
            access_token=session["access_token"],
            fields=",".join(fields)
        )

    def _on_get_user_info(self, future, session, fields, user):
        if user is None:
            future.set_result(None)
            return

        fieldmap = {}
        for field in fields:
            fieldmap[field] = user.get(field)

        fieldmap.update({"access_token": session["access_token"], "session_expires": session.get("expires")})
        future.set_result(fieldmap)

    @_auth_return_future
    def facebook_request(self, path, callback, access_token=None,
                         post_args=None, **args):
        """Fetches the given relative API path, e.g., "/btaylor/picture"

        If the request is a POST, ``post_args`` should be provided. Query
        string arguments should be given as keyword arguments.

        An introduction to the Facebook Graph API can be found at
        http://developers.facebook.com/docs/api

        Many methods require an OAuth access token which you can
        obtain through `~OAuth2Mixin.authorize_redirect` and
        `get_authenticated_user`. The user returned through that
        process includes an ``access_token`` attribute that can be
        used to make authenticated requests via this method.

        Example usage::

            class MainHandler(tornado.web.RequestHandler,
                              tornado.auth.FacebookGraphMixin):
                @tornado.web.authenticated
                @tornado.web.asynchronous
                @tornado.gen.coroutine
                def get(self):
                    new_entry = yield self.facebook_request(
                        "/me/feed",
                        post_args={"message": "I am posting from my Tornado application!"},
                        access_token=self.current_user["access_token"])

                    if not new_entry:
                        # Call failed; perhaps missing permission?
                        yield self.authorize_redirect()
                        return
                    self.finish("Posted a message!")

        The given path is relative to ``self._FACEBOOK_BASE_URL``,
        by default "https://graph.facebook.com".

        .. versionchanged:: 3.1
           Added the ability to override ``self._FACEBOOK_BASE_URL``.
        """
        url = self._FACEBOOK_BASE_URL + path
        all_args = {}
        if access_token:
            all_args["access_token"] = access_token
            all_args.update(args)

        if all_args:
            url += "?" + urllib_parse.urlencode(all_args)
        callback = self.async_callback(self._on_facebook_request, callback)
        http = self.get_auth_http_client()
        if post_args is not None:
            http.fetch(url, method="POST", body=urllib_parse.urlencode(post_args),
                       callback=callback)
        else:
            http.fetch(url, callback=callback)

    def _on_facebook_request(self, future, response):
        if response.error:
            future.set_exception(AuthError("Error response %s fetching %s" %
                                           (response.error, response.request.url)))
            return

        future.set_result(escape.json_decode(response.body))

    def get_auth_http_client(self):
        """Returns the `.AsyncHTTPClient` instance to be used for auth requests.

        May be overridden by subclasses to use an HTTP client other than
        the default.
        """
        return httpclient.AsyncHTTPClient()


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
    base_string = "&".join(_oauth_escape(e) for e in base_elems)

    key_elems = [escape.utf8(consumer_token["secret"])]
    key_elems.append(escape.utf8(token["secret"] if token else ""))
    key = b"&".join(key_elems)

    hash = hmac.new(key, escape.utf8(base_string), hashlib.sha1)
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

    base_string = "&".join(_oauth_escape(e) for e in base_elems)
    key_elems = [escape.utf8(urllib_parse.quote(consumer_token["secret"], safe='~'))]
    key_elems.append(escape.utf8(urllib_parse.quote(token["secret"], safe='~') if token else ""))
    key = b"&".join(key_elems)

    hash = hmac.new(key, escape.utf8(base_string), hashlib.sha1)
    return binascii.b2a_base64(hash.digest())[:-1]


def _oauth_escape(val):
    if isinstance(val, unicode_type):
        val = val.encode("utf-8")
    return urllib_parse.quote(val, safe="~")


def _oauth_parse_response(body):
    # I can't find an officially-defined encoding for oauth responses and
    # have never seen anyone use non-ascii.  Leave the response in a byte
    # string for python 2, and use utf8 on python 3.
    body = escape.native_str(body)
    p = urlparse.parse_qs(body, keep_blank_values=False)
    token = dict(key=p["oauth_token"][0], secret=p["oauth_token_secret"][0])

    # Add the extra parameters the Provider included to the token
    special = ("oauth_token", "oauth_token_secret")
    token.update((k, p[k][0]) for k in p if k not in special)
    return token
