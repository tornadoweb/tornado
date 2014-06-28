Templates and UI
================


Templates
~~~~~~~~~

You can use any template language supported by Python, but Tornado ships
with its own templating language that is a lot faster and more flexible
than many of the most popular templating systems out there. See the
`tornado.template` module documentation for complete documentation.

A Tornado template is just HTML (or any other text-based format) with
Python control sequences and expressions embedded within the markup:

::

    <html>
       <head>
          <title>{{ title }}</title>
       </head>
       <body>
         <ul>
           {% for item in items %}
             <li>{{ escape(item) }}</li>
           {% end %}
         </ul>
       </body>
     </html>

If you saved this template as "template.html" and put it in the same
directory as your Python file, you could render this template with:

::

    class MainHandler(tornado.web.RequestHandler):
        def get(self):
            items = ["Item 1", "Item 2", "Item 3"]
            self.render("template.html", title="My title", items=items)

Tornado templates support *control statements* and *expressions*.
Control statements are surrounded by ``{%`` and ``%}``, e.g.,
``{% if len(items) > 2 %}``. Expressions are surrounded by ``{{`` and
``}}``, e.g., ``{{ items[0] }}``.

Control statements more or less map exactly to Python statements. We
support ``if``, ``for``, ``while``, and ``try``, all of which are
terminated with ``{% end %}``. We also support *template inheritance*
using the ``extends`` and ``block`` statements, which are described in
detail in the documentation for the `tornado.template`.

Expressions can be any Python expression, including function calls.
Template code is executed in a namespace that includes the following
objects and functions (Note that this list applies to templates rendered
using ``RequestHandler.render`` and ``render_string``. If you're using
the ``template`` module directly outside of a ``RequestHandler`` many of
these entries are not present).

-  ``escape``: alias for ``tornado.escape.xhtml_escape``
-  ``xhtml_escape``: alias for ``tornado.escape.xhtml_escape``
-  ``url_escape``: alias for ``tornado.escape.url_escape``
-  ``json_encode``: alias for ``tornado.escape.json_encode``
-  ``squeeze``: alias for ``tornado.escape.squeeze``
-  ``linkify``: alias for ``tornado.escape.linkify``
-  ``datetime``: the Python ``datetime`` module
-  ``handler``: the current ``RequestHandler`` object
-  ``request``: alias for ``handler.request``
-  ``current_user``: alias for ``handler.current_user``
-  ``locale``: alias for ``handler.locale``
-  ``_``: alias for ``handler.locale.translate``
-  ``static_url``: alias for ``handler.static_url``
-  ``xsrf_form_html``: alias for ``handler.xsrf_form_html``
-  ``reverse_url``: alias for ``Application.reverse_url``
-  All entries from the ``ui_methods`` and ``ui_modules``
   ``Application`` settings
-  Any keyword arguments passed to ``render`` or ``render_string``

When you are building a real application, you are going to want to use
all of the features of Tornado templates, especially template
inheritance. Read all about those features in the `tornado.template`
section (some features, including ``UIModules`` are implemented in the
``web`` module)

Under the hood, Tornado templates are translated directly to Python. The
expressions you include in your template are copied verbatim into a
Python function representing your template. We don't try to prevent
anything in the template language; we created it explicitly to provide
the flexibility that other, stricter templating systems prevent.
Consequently, if you write random stuff inside of your template
expressions, you will get random Python errors when you execute the
template.

All template output is escaped by default, using the
``tornado.escape.xhtml_escape`` function. This behavior can be changed
globally by passing ``autoescape=None`` to the ``Application`` or
``TemplateLoader`` constructors, for a template file with the
``{% autoescape None %}`` directive, or for a single expression by
replacing ``{{ ... }}`` with ``{% raw ...%}``. Additionally, in each of
these places the name of an alternative escaping function may be used
instead of ``None``.

Note that while Tornado's automatic escaping is helpful in avoiding
XSS vulnerabilities, it is not sufficient in all cases.  Expressions
that appear in certain locations, such as in Javascript or CSS, may need
additional escaping.  Additionally, either care must be taken to always
use double quotes and ``xhtml_escape`` in HTML attributes that may contain
untrusted content, or a separate escaping function must be used for
attributes (see e.g. http://wonko.com/post/html-escaping)

Localization
~~~~~~~~~~~~

The locale of the current user (whether they are logged in or not) is
always available as ``self.locale`` in the request handler and as
``locale`` in templates. The name of the locale (e.g., ``en_US``) is
available as ``locale.name``, and you can translate strings with the
``locale.translate`` method. Templates also have the global function
call ``_()`` available for string translation. The translate function
has two forms:

::

    _("Translate this string")

which translates the string directly based on the current locale, and

::

    _("A person liked this", "%(num)d people liked this",
      len(people)) % {"num": len(people)}

which translates a string that can be singular or plural based on the
value of the third argument. In the example above, a translation of the
first string will be returned if ``len(people)`` is ``1``, or a
translation of the second string will be returned otherwise.

The most common pattern for translations is to use Python named
placeholders for variables (the ``%(num)d`` in the example above) since
placeholders can move around on translation.

Here is a properly localized template:

::

    <html>
       <head>
          <title>FriendFeed - {{ _("Sign in") }}</title>
       </head>
       <body>
         <form action="{{ request.path }}" method="post">
           <div>{{ _("Username") }} <input type="text" name="username"/></div>
           <div>{{ _("Password") }} <input type="password" name="password"/></div>
           <div><input type="submit" value="{{ _("Sign in") }}"/></div>
           {% module xsrf_form_html() %}
         </form>
       </body>
     </html>

By default, we detect the user's locale using the ``Accept-Language``
header sent by the user's browser. We choose ``en_US`` if we can't find
an appropriate ``Accept-Language`` value. If you let user's set their
locale as a preference, you can override this default locale selection
by overriding ``get_user_locale`` in your request handler:

::

    class BaseHandler(tornado.web.RequestHandler):
        def get_current_user(self):
            user_id = self.get_secure_cookie("user")
            if not user_id: return None
            return self.backend.get_user_by_id(user_id)

        def get_user_locale(self):
            if "locale" not in self.current_user.prefs:
                # Use the Accept-Language header
                return None
            return self.current_user.prefs["locale"]

If ``get_user_locale`` returns ``None``, we fall back on the
``Accept-Language`` header.

You can load all the translations for your application using the
``tornado.locale.load_translations`` method. It takes in the name of the
directory which should contain CSV files named after the locales whose
translations they contain, e.g., ``es_GT.csv`` or ``fr_CA.csv``. The
method loads all the translations from those CSV files and infers the
list of supported locales based on the presence of each CSV file. You
typically call this method once in the ``main()`` method of your server:

::

    def main():
        tornado.locale.load_translations(
            os.path.join(os.path.dirname(__file__), "translations"))
        start_server()

You can get the list of supported locales in your application with
``tornado.locale.get_supported_locales()``. The user's locale is chosen
to be the closest match based on the supported locales. For example, if
the user's locale is ``es_GT``, and the ``es`` locale is supported,
``self.locale`` will be ``es`` for that request. We fall back on
``en_US`` if no close match can be found.

See the `tornado.locale`
documentation for detailed information on the CSV format and other
localization methods.

.. _ui-modules:

UI modules
~~~~~~~~~~

Tornado supports *UI modules* to make it easy to support standard,
reusable UI widgets across your application. UI modules are like special
functional calls to render components of your page, and they can come
packaged with their own CSS and JavaScript.

For example, if you are implementing a blog, and you want to have blog
entries appear on both the blog home page and on each blog entry page,
you can make an ``Entry`` module to render them on both pages. First,
create a Python module for your UI modules, e.g., ``uimodules.py``:

::

    class Entry(tornado.web.UIModule):
        def render(self, entry, show_comments=False):
            return self.render_string(
                "module-entry.html", entry=entry, show_comments=show_comments)

Tell Tornado to use ``uimodules.py`` using the ``ui_modules`` setting in
your application:

::

    class HomeHandler(tornado.web.RequestHandler):
        def get(self):
            entries = self.db.query("SELECT * FROM entries ORDER BY date DESC")
            self.render("home.html", entries=entries)

    class EntryHandler(tornado.web.RequestHandler):
        def get(self, entry_id):
            entry = self.db.get("SELECT * FROM entries WHERE id = %s", entry_id)
            if not entry: raise tornado.web.HTTPError(404)
            self.render("entry.html", entry=entry)

    settings = {
        "ui_modules": uimodules,
    }
    application = tornado.web.Application([
        (r"/", HomeHandler),
        (r"/entry/([0-9]+)", EntryHandler),
    ], **settings)

Within ``home.html``, you reference the ``Entry`` module rather than
printing the HTML directly:

::

    {% for entry in entries %}
      {% module Entry(entry) %}
    {% end %}

Within ``entry.html``, you reference the ``Entry`` module with the
``show_comments`` argument to show the expanded form of the entry:

::

    {% module Entry(entry, show_comments=True) %}

Modules can include custom CSS and JavaScript functions by overriding
the ``embedded_css``, ``embedded_javascript``, ``javascript_files``, or
``css_files`` methods:

::

    class Entry(tornado.web.UIModule):
        def embedded_css(self):
            return ".entry { margin-bottom: 1em; }"

        def render(self, entry, show_comments=False):
            return self.render_string(
                "module-entry.html", show_comments=show_comments)

Module CSS and JavaScript will be included once no matter how many times
a module is used on a page. CSS is always included in the ``<head>`` of
the page, and JavaScript is always included just before the ``</body>``
tag at the end of the page.

When additional Python code is not required, a template file itself may
be used as a module. For example, the preceding example could be
rewritten to put the following in ``module-entry.html``:

::

    {{ set_resources(embedded_css=".entry { margin-bottom: 1em; }") }}
    <!-- more template html... -->

This revised template module would be invoked with

::

    {% module Template("module-entry.html", show_comments=True) %}

The ``set_resources`` function is only available in templates invoked
via ``{% module Template(...) %}``. Unlike the ``{% include ... %}``
directive, template modules have a distinct namespace from their
containing template - they can only see the global template namespace
and their own keyword arguments.
