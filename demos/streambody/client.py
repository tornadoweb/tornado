'''Demo code of the functionality in the Tornado "streambody" branch,
providing support for streaming request body data in POST and PUT requests.

The streambody branch is available at:
https://github.com/nephics/tornado

Run the demo by first starting the server and then the client.
'''

import os
import sys
# use the local version of tornado
sys.path.insert(0, os.path.abspath('../..'))

import hashlib
import tornado.httpclient as httpclient


def upload(path, body):
    url = 'http://localhost:8888' + path
    http_client = httpclient.HTTPClient()
    request = httpclient.HTTPRequest(url, 'PUT', body=body,
            headers={'Content-Type': 'text/plain'})
    try:
        response = http_client.fetch(request)
        # the server's calculated md5 hash is in the second line of the response
        msg, md5 = response.body.decode('utf8').split('\n')
        print(msg)
        return md5
    except httpclient.HTTPError as e:
        print("Error:", e)
        sys.exit()

def main():
    # generate 350k of random data, and remeber the MD5 hash
    body = os.urandom(350000)
    md5_orig = hashlib.md5(body).hexdigest()

    # upload using normal upload handler
    md5 = upload('/', body)
    if md5 != md5_orig:
        print('!! Hash mismatch with default upload handler !!')
        return

    # upload using streambody handler
    md5 = upload('/stream', body)
    if md5 != md5_orig:
        print('!! Hash mismatch with streambody handler !!')
        return

    print('Hashes of uploaded data match the original.')

if __name__ == '__main__':
    main()
