# Testing Tornado Database Backed Application.

A simple testcase to test database-backed application
in tornado, here postgres is the database.

### Prerequisites

* Make sure postgres is installed.

* Add the postgres database, user, host, port in app file.

```
DB_NAME  = "your_db"
USER     = "your_user"
PASSWORD = "your_password"
HOST     = "your_host"
PORT     = "5432"
```

* Install the required packages

```
pip install -r requirements.txt
```

### Running the test

```
python test_app.py
```
