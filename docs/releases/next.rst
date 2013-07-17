What's new in the next version of Tornado
=========================================

In Progress
-----------

* `.WSGIContainer` now calls the iterable's ``close()`` method even if
  an error is raised, in compliance with the spec.
* Fixed an incorrect error message when handler methods return a value
  other than None or a Future.
* `.xhtml_escape` now escapes apostrophes as well.
* `.Subprocess` no longer leaks file descriptors if `subprocess.Popen` fails.
* `.IOLoop` now frees callback objects earlier, reducing memory usage
  while idle.
* `.FacebookGraphMixin` has been updated to use the current Facebook login
  URL, which saves a redirect.
* `.GoogleOAuth2Mixin` has been added so that Google's OAuth2 only apps are able to get a context without OpenID (which uses OAuth 1).