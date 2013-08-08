__author__ = 'bruno farina'

import sys
import random
import string


# The session Data Access Object handles interactions with the sessions collection
class SessionDAO:

    def __init__(self, database):
        self.db = database
        self.sessions = database.sessions

    # will start a new session id by adding a new document to the sessions collection
    # returns the sessionID or None
    def start_session(self, username):

        session_id = self.get_random_str(32)
        session = {'username': username, '_id': session_id}

        try:
            self.sessions.insert(session)
        except:
            print("Unexpected error on start_session:", sys.exc_info()[0])
            return None

        return str(session['_id'])

    # will send a new user session by deleting from sessions table
    def end_session(self, session_id):

        if session_id is None:
            return

        self.sessions.remove({'_id': session_id})

        return

    # if there is a valid session, it is returned
    def get_session(self, session_id):

        if session_id is None:
            return None

        session = self.sessions.find_one({'_id': session_id})

        return session

    # get the username of the current session, or None if the session is not valid
    def get_username(self, session_id):

        session = self.get_session(session_id)
        if session is None:
            return None
        else:
            return session['username']

    def get_random_str(self, num_chars):
        random_string = ""
        for i in range(num_chars):
            random_string = random_string + random.choice(string.ascii_letters)
        return random_string
