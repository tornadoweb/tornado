__author__ = 'bruno farina'

import pymongo

# The User Data Access Object handles all interactions with the User collection.
class UserDAO:

    def __init__(self, db):
        self.db = db
        self.users = self.db.users

    def validate_login(self, username, password):

        user = None
        try:
            user = self.users.find_one({'_id': username})
            print("User has been retrieved!")
        except:
            print("Unable to query database for user")

        if user is None:
            print("User not in database")
            return None

        if user['password'] != password:
            print("user password is not a match")
            return None

        # Looks good
        return user


    # creates a new user in the users collection
    def add_user(self, username, password, email):
        
        user = {'_id': username, 'password': password}
        if email != "":
            user['email'] = email

        try:
            self.users.insert(user)

            print("User has been inserted with success!")

        except pymongo.errors.OperationFailure:
            print("oops, mongo error")
            return False
        except pymongo.errors.DuplicateKeyError:
            print("oops, username is already taken")
            return False

        return True


