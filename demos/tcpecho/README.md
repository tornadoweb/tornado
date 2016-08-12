TCP echo demo
=============

This demo shows how to use Tornado's asynchronous TCP client and
server by implementing `handle_stream` as a coroutine.

To run the server:

```
$ python server.py
```

The client will send the message given with the `--message` option
(which defaults to "ping"), wait for a response, then quit. To run:

```
$ python client.py --message="your message here"
```

Alternatively, you can interactively send messages to the echo server
with a telnet client. For example:

```
$ telnet localhost 9888
Trying ::1...
Connected to localhost.
Escape character is '^]'.
ping
ping
```
