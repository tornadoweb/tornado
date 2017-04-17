import cgi
import os
import pymongo
import utils
import sessionDAO
import tornado.web
import userDAO

__author__ = 'bruno farina'

connection_string = "mongodb://localhost"
connection = pymongo.MongoClient(connection_string)
database = connection.blog

users = userDAO.UserDAO(database)
sessions = sessionDAO.SessionDAO(database)

class BaseHandler(tornado.web.RequestHandler):
    def get_current_user(self):
        return 
       
    def post_current_user(self):
        return 

class IndexHandler(BaseHandler):
    def get(self):
        cookie = self.get_cookie("session")
        username = sessions.get_username(cookie)
        self.render('blog_template.html', username = username)      
    
class SignupHandler(BaseHandler):
    def get(self):
        return self.render("signup.html",
                           username="", password="",
                           password_error="",
                           email="", username_error="", email_error="",
                           verify_error="")
        
    def post(self):
        email    = self.get_argument("email")
        username = self.get_argument("username")
        password = self.get_argument("password")
        verify   = self.get_argument("verify")
    
        # set these up in case we have an error case
        errors = {'username': cgi.escape(username), 'email': cgi.escape(email)}
        
        if utils.validate_signup(username, password, verify, email, errors):
    
            if not users.add_user(username, password, email):
                # this was a duplicate
                errors['username_error'] = "Username already in use. Please choose another"
                return self.render("signup.html", errors)
    
            session_id = sessions.start_session(username)
            print (session_id)
            self.set_cookie("session", session_id)
            self.redirect("/welcome")
        else:
            print ("user did not validate")
            return self.render("signup.html", errors)

class LoginHandler(BaseHandler):
    def get(self):
        self.render('login.html', username="", password="", login_error="")
        
    def post(self):
        username = self.get_argument("username")
        password = self.get_argument("password")
    
        print ("user submitted: ", username, "| pass: ", password)
    
        user_record = users.validate_login(username, password)
        if user_record:

            # username is stored in the user collection in the _id key
            session_id = sessions.start_session(user_record['_id'])
    
            if session_id is None:
                self.redirect("/internal_error")
            cookie = session_id
            self.set_cookie("session", cookie)
            self.redirect("/welcome")
        else:
            return self.render("login.html",
                               username=cgi.escape(username),
                               password="",
                               login_error="Invalid Login")     

class WelcomeHandler(BaseHandler):
    def get(self):
        # check for a cookie, if present, then extract value
        cookie = self.get_cookie("session")
        username = sessions.get_username(cookie)  # see if user is logged in
        if username is None:
            print ("welcome: can't identify user...redirecting to signup")
            self.redirect("/signup")
    
        return self.render("welcome.html", username=username)  
    
class LogoutHandler(BaseHandler):
    def get(self):
        cookie = self.get_cookie("session")
        sessions.end_session(cookie)
        self.set_cookie("session", "")
        self.redirect("/signup")

class InternalError(tornado.web.HTTPError):
    def get(self):
        self.render("error_template", error = "System has encountered a DB error")
    
settings = {
    "template_path": os.path.join(os.path.dirname(__file__), "templates")
}

handlers = [
        (r"/", IndexHandler),
        (r"/login", LoginHandler),
        (r"/signup", SignupHandler),
        (r"/welcome", WelcomeHandler),
        (r"/logout", LogoutHandler),
        (r"/internal_error", InternalError)]


application = tornado.web.Application(handlers , **settings)

application.listen(8888)
tornado.ioloop.IOLoop.instance().start()