Running and deploying
=====================

Static files and aggressive file caching
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

You can serve static files from Tornado by specifying the
``static_path`` setting in your application:

::

    settings = {
        "static_path": os.path.join(os.path.dirname(__file__), "static"),
        "cookie_secret": "__TODO:_GENERATE_YOUR_OWN_RANDOM_VALUE_HERE__",
        "login_url": "/login",
        "xsrf_cookies": True,
    }
    application = tornado.web.Application([
        (r"/", MainHandler),
        (r"/login", LoginHandler),
        (r"/(apple-touch-icon\.png)", tornado.web.StaticFileHandler,
         dict(path=settings['static_path'])),
    ], **settings)

This setting will automatically make all requests that start with
``/static/`` serve from that static directory, e.g.,
`http://localhost:8888/static/foo.png <http://localhost:8888/static/foo.png>`_
will serve the file ``foo.png`` from the specified static directory. We
also automatically serve ``/robots.txt`` and ``/favicon.ico`` from the
static directory (even though they don't start with the ``/static/``
prefix).

In the above settings, we have explicitly configured Tornado to serve
``apple-touch-icon.png`` “from” the root with the ``StaticFileHandler``,
though it is physically in the static file directory. (The capturing
group in that regular expression is necessary to tell
``StaticFileHandler`` the requested filename; capturing groups are
passed to handlers as method arguments.) You could do the same thing to
serve e.g. ``sitemap.xml`` from the site root. Of course, you can also
avoid faking a root ``apple-touch-icon.png`` by using the appropriate
``<link />`` tag in your HTML.

To improve performance, it is generally a good idea for browsers to
cache static resources aggressively so browsers won't send unnecessary
``If-Modified-Since`` or ``Etag`` requests that might block the
rendering of the page. Tornado supports this out of the box with *static
content versioning*.

To use this feature, use the ``static_url()`` method in your templates
rather than typing the URL of the static file directly in your HTML:

::

    <html>
       <head>
          <title>FriendFeed - {{ _("Home") }}</title>
       </head>
       <body>
         <div><img src="{{ static_url("images/logo.png") }}"/></div>
       </body>
     </html>

The ``static_url()`` function will translate that relative path to a URI
that looks like ``/static/images/logo.png?v=aae54``. The ``v`` argument
is a hash of the content in ``logo.png``, and its presence makes the
Tornado server send cache headers to the user's browser that will make
the browser cache the content indefinitely.

Since the ``v`` argument is based on the content of the file, if you
update a file and restart your server, it will start sending a new ``v``
value, so the user's browser will automatically fetch the new file. If
the file's contents don't change, the browser will continue to use a
locally cached copy without ever checking for updates on the server,
significantly improving rendering performance.

In production, you probably want to serve static files from a more
optimized static file server like `nginx <http://nginx.net/>`_. You can
configure most any web server to support these caching semantics. Here
is the nginx configuration we use at FriendFeed:

::

    location /static/ {
        root /var/friendfeed/static;
        if ($query_string) {
            expires max;
        }
     }

.. _debug-mode:

Debug mode and automatic reloading
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

If you pass ``debug=True`` to the ``Application`` constructor, the app
will be run in debug/development mode. In this mode, several features
intended for convenience while developing will be enabled (each of which
is also available as an individual flag; if both are specified the
individual flag takes precedence):

* ``autoreload=True``: The app will watch for changes to its source
  files and reload itself when anything changes. This reduces the need
  to manually restart the server during development. However, certain
  failures (such as syntax errors at import time) can still take the
  server down in a way that debug mode cannot currently recover from.
* ``compiled_template_cache=False``: Templates will not be cached.
* ``static_hash_cache=False``: Static file hashes (used by the
  ``static_url`` function) will not be cached
* ``serve_traceback=True``: When an exception in a ``RequestHandler``
  is not caught, an error page including a stack trace will be
  generated.

Autoreload mode is not compatible with the multi-process mode of ``HTTPServer``.
You must not give ``HTTPServer.start`` an argument other than 1 (or
call `tornado.process.fork_processes`) if you are using autoreload mode.

The automatic reloading feature of debug mode is available as a
standalone module in ``tornado.autoreload``.  The two can be used in
combination to provide extra robustness against syntax errors: set
``autoreload=True`` within the app to detect changes while it is running,
and start it with ``python -m tornado.autoreload myserver.py`` to catch
any syntax errors or other errors at startup.

Reloading loses any Python interpreter command-line arguments (e.g. ``-u``)
because it re-executes Python using ``sys.executable`` and ``sys.argv``.
Additionally, modifying these variables will cause reloading to behave
incorrectly.

On some platforms (including Windows and Mac OSX prior to 10.6), the
process cannot be updated "in-place", so when a code change is
detected the old server exits and a new one starts.  This has been
known to confuse some IDEs.


Running Tornado in production
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

At FriendFeed, we use `nginx <http://nginx.net/>`_ as a load balancer
and static file server. We run multiple instances of the Tornado web
server on multiple frontend machines. We typically run one Tornado
frontend per core on the machine (sometimes more depending on
utilization).

When running behind a load balancer like nginx, it is recommended to
pass ``xheaders=True`` to the ``HTTPServer`` constructor. This will tell
Tornado to use headers like ``X-Real-IP`` to get the user's IP address
instead of attributing all traffic to the balancer's IP address.

This is a barebones nginx config file that is structurally similar to
the one we use at FriendFeed. It assumes nginx and the Tornado servers
are running on the same machine, and the four Tornado servers are
running on ports 8000 - 8003:

::

    user nginx;
    worker_processes 1;

    error_log /var/log/nginx/error.log;
    pid /var/run/nginx.pid;

    events {
        worker_connections 1024;
        use epoll;
    }

    http {
        # Enumerate all the Tornado servers here
        upstream frontends {
            server 127.0.0.1:8000;
            server 127.0.0.1:8001;
            server 127.0.0.1:8002;
            server 127.0.0.1:8003;
        }

        include /etc/nginx/mime.types;
        default_type application/octet-stream;

        access_log /var/log/nginx/access.log;

        keepalive_timeout 65;
        proxy_read_timeout 200;
        sendfile on;
        tcp_nopush on;
        tcp_nodelay on;
        gzip on;
        gzip_min_length 1000;
        gzip_proxied any;
        gzip_types text/plain text/html text/css text/xml
                   application/x-javascript application/xml
                   application/atom+xml text/javascript;

        # Only retry if there was a communication error, not a timeout
        # on the Tornado server (to avoid propagating "queries of death"
        # to all frontends)
        proxy_next_upstream error;

        server {
            listen 80;

            # Allow file uploads
            client_max_body_size 50M;

            location ^~ /static/ {
                root /var/www;
                if ($query_string) {
                    expires max;
                }
            }
            location = /favicon.ico {
                rewrite (.*) /static/favicon.ico;
            }
            location = /robots.txt {
                rewrite (.*) /static/robots.txt;
            }

            location / {
                proxy_pass_header Server;
                proxy_set_header Host $http_host;
                proxy_redirect off;
                proxy_set_header X-Real-IP $remote_addr;
                proxy_set_header X-Scheme $scheme;
                proxy_pass http://frontends;
            }
        }
    }

WSGI and Google AppEngine
~~~~~~~~~~~~~~~~~~~~~~~~~

Tornado comes with limited support for `WSGI <http://wsgi.org/>`_.
However, since WSGI does not support non-blocking requests, you cannot
use any of the asynchronous/non-blocking features of Tornado in your
application if you choose to use WSGI instead of Tornado's HTTP server.
Some of the features that are not available in WSGI applications:
``@tornado.web.asynchronous``, the ``httpclient`` module, and the
``auth`` module.

You can create a valid WSGI application from your Tornado request
handlers by using ``WSGIApplication`` in the ``wsgi`` module instead of
using ``tornado.web.Application``. Here is an example that uses the
built-in WSGI ``CGIHandler`` to make a valid `Google
AppEngine <http://code.google.com/appengine/>`_ application:

::

    import tornado.web
    import tornado.wsgi
    import wsgiref.handlers

    class MainHandler(tornado.web.RequestHandler):
        def get(self):
            self.write("Hello, world")

    if __name__ == "__main__":
        application = tornado.wsgi.WSGIApplication([
            (r"/", MainHandler),
        ])
        wsgiref.handlers.CGIHandler().run(application)

See the `appengine example application
<https://github.com/tornadoweb/tornado/tree/stable/demos/appengine>`_ for a
full-featured AppEngine app built on Tornado.
