``tornado.auth`` --- Third-party login with OpenID and OAuth
============================================================

.. automodule:: tornado.auth

   Common protocols
   ----------------

   These classes implement the OpenID and OAuth standards.  They will
   generally need to be subclassed to use them with any particular site.
   The degree of customization required will vary, but in most cases
   overridding the class attributes (which are named beginning with
   underscores for historical reasons) should be sufficient.

   .. autoclass:: OpenIdMixin
      :members:

   .. autoclass:: OAuthMixin

      .. automethod:: authorize_redirect
      .. automethod:: get_authenticated_user
      .. automethod:: _oauth_consumer_token
      .. automethod:: _oauth_get_user_future
      .. automethod:: get_auth_http_client

   .. autoclass:: OAuth2Mixin
      :members:

   Google
   ------

   .. autoclass:: GoogleMixin
      :members:

   Facebook
   --------

   .. autoclass:: FacebookGraphMixin
      :members:

   .. autoclass:: FacebookMixin
      :members:

   Twitter
   -------

   .. autoclass:: TwitterMixin
      :members:

   FriendFeed
   ----------

   .. autoclass:: FriendFeedMixin
      :members:

