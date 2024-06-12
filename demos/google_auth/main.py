"""Demo app for GoogleOAuth2Mixin

Recommended usage:
- Register an app with Google following the instructions at
  https://www.tornadoweb.org/en/stable/auth.html#tornado.auth.GoogleOAuth2Mixin
- Use "http://localhost:8888/auth/google" as the redirect URI.
- Create a file in this directory called main.cfg, containing two lines (python syntax):
    google_oauth_key="..."
    google_oauth_secret="..."
- Run this file with `python main.py --config_file=main.cfg`
- Visit "http://localhost:8888" in your browser.
"""

import asyncio
import json
import tornado
import urllib.parse

from tornado.options import define, options
from tornado.web import url

define("port", default=8888, help="run on the given port", type=int)
define("google_oauth_key", help="Google OAuth Key")
define("google_oauth_secret", help="Google OAuth Secret")
define(
    "config_file",
    help="tornado config file",
    callback=lambda path: tornado.options.parse_config_file(path, final=False),
)


class BaseHandler(tornado.web.RequestHandler):
    def get_current_user(self):
        user_cookie = self.get_signed_cookie("googledemo_user")
        if user_cookie:
            return json.loads(user_cookie)
        return None


class IndexHandler(BaseHandler, tornado.auth.GoogleOAuth2Mixin):
    @tornado.web.authenticated
    async def get(self):
        try:
            # This is redundant: we got the userinfo in the login handler.
            # But this demonstrates the usage of oauth2_request outside of
            # the login flow, and getting anything more than userinfo
            # leads to more approval prompts and complexity.
            user_info = await self.oauth2_request(
                "https://www.googleapis.com/oauth2/v1/userinfo",
                access_token=self.current_user["access_token"],
            )
        except tornado.httpclient.HTTPClientError as e:
            print(e.response.body)
            raise
        self.write(f"Hello {user_info['name']}")


class LoginHandler(BaseHandler, tornado.auth.GoogleOAuth2Mixin):
    async def get(self):
        redirect_uri = urllib.parse.urljoin(
            self.application.settings["redirect_base_uri"],
            self.reverse_url("google_oauth"),
        )
        if self.get_argument("code", False):
            access = await self.get_authenticated_user(
                redirect_uri=redirect_uri, code=self.get_argument("code")
            )
            user = await self.oauth2_request(
                "https://www.googleapis.com/oauth2/v1/userinfo",
                access_token=access["access_token"],
            )
            # Save the user and access token.
            user_cookie = dict(id=user["id"], access_token=access["access_token"])
            self.set_signed_cookie("googledemo_user", json.dumps(user_cookie))
            self.redirect("/")
        else:
            self.authorize_redirect(
                redirect_uri=redirect_uri,
                client_id=self.get_google_oauth_settings()["key"],
                scope=["profile", "email"],
                response_type="code",
                extra_params={"approval_prompt": "auto"},
            )


class LogoutHandler(BaseHandler):
    def get(self):
        self.clear_cookie("user")
        self.redirect("/")


async def main():
    tornado.options.parse_command_line()
    app = tornado.web.Application(
        [
            url(r"/", IndexHandler),
            url(r"/auth/google", LoginHandler, name="google_oauth"),
            url(r"/logout", LogoutHandler),
        ],
        redirect_base_uri=f"http://localhost:{options.port}",
        google_oauth=dict(
            key=options.google_oauth_key, secret=options.google_oauth_secret
        ),
        debug=True,
        cookie_secret="__TODO:_GENERATE_YOUR_OWN_RANDOM_VALUE_HERE__",
        login_url="/auth/google",
    )
    app.listen(options.port)
    shutdown_event = asyncio.Event()
    await shutdown_event.wait()


if __name__ == "__main__":
    asyncio.run(main())
