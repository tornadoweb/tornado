# Testing Tornado Http server.

A simple testcase to test https server
in tornado.

### Prerequisites

* Generate the certificate and key using openssl.

```
openssl req -new -keyout test.key -out test.crt -nodes -days 3650 -x509
```

* Install the required packages


```
pip install -r requirements.txt
```

### Running the test
```
python test_app.py
```
