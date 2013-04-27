#!/usr/bin/env python
#-*-coding: utf-8 -*-
"""
    author comger@gmail.com
"""
from tornado import httpclient
from tornado.httputil import url_concat
from tornado.auth import OAuth2Mixin
import logging,json
import urllib



class WeiboAuth2Minix(OAuth2Mixin):
    """docstring for WeiboAuth2Minix"""
    _OAUTH_AUTHORIZE_URL = "https://api.weibo.com/oauth2/authorize"
    _OAUTH_ACCESS_TOKEN_URL = "https://api.weibo.com/oauth2/access_token"


    def authorize_redirect(self, redirect_uri,client_id,client_secret = None, extra_params=None ):
        """调用父类方法跳转认证获取code, Weibo认证需要加入
           参数response_type:(code)和state所以作为附加参数传递给父类方法"""
        args = {
            "response_type" : "code",
        }
        if extra_params:
            args.update(extra_params)
        
        super(WeiboAuth2Minix, self).authorize_redirect(redirect_uri,client_id,client_secret,
                args)


    def get_authenticated_user(self, code, redirect_uri ,client_id,client_secret, callback, extra_params=None ):
        ''' get logined user info '''
        args = {
            "redirect_uri":redirect_uri,
            "code":code,
            "client_id":client_id,
            "client_secret":client_secret
        }
        
        def get_user(res):
            api = url_concat('https://api.weibo.com/2/users/show.json',res)
            self.get_auth_http_client().fetch(api,callback = callback)

        
        self.get_access_token(get_user, **args)

    
    def parse_access_token(self, response, callback):
        ''' loads json and callback result'''
        res = json.loads(response.body)
        if res.get('error',None):
            callback(None)
            return 

        self.set_secure_cookie('access_token',res['access_token'])
        callback(res)        


    def get_access_token(self, callback = None, **kwargs):
        
        def parse(response):
            self.parse_access_token(response, callback)

        self.get_auth_http_client().fetch(self._OAUTH_ACCESS_TOKEN_URL,method = "POST", body = urllib.urlencode(kwargs), callback = parse)

   
    def reply_mblog(self, mid, comment, callback):
        ''' 回复微博信息

            mid : 微博id,
            comment : 回复内容
        '''
        api = 'https://api.weibo.com/2/comments/create.json'
        data = dict(id= mid, comment = comment)
        data.update(access_token = self.get_secure_cookie('access_token'))
        self.get_auth_http_client().fetch(api,method = "POST", body = urllib.urlencode(data), callback = callback)


    def get_auth_http_client(self):
        return httpclient.AsyncHTTPClient()
