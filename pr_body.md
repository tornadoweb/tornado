Several `raise` statements across the codebase pass format arguments to exception constructors using a comma instead of `%` operator:

```python
# Before (comma creates a tuple message):
raise ValueError("message %s", value)

# After (proper string formatting):
raise ValueError("message %s" % value)
```

When Python's `Exception.__init__` receives multiple arguments, `str(e)` shows the raw tuple representation instead of a formatted message. For example, `ValueError("unsupported auth_mode %s", "digest")` displays as:

```
ValueError: ('unsupported auth_mode %s', 'digest')
```

instead of:

```
ValueError: unsupported auth_mode digest
```

Affected locations:
- `web.py`: `_convert_header_value`, `xsrf_token`, `stream_request_body`, `_has_stream_request_body`
- `websocket.py`: `_PerMessageDeflateCompressor.__init__`, `_PerMessageDeflateDecompressor.__init__`, `_process_server_headers`
- `simple_httpclient.py`: HTTP basic auth mode validation
- `netutil.py`: Unix socket bind validation
- `concurrent.py`: `run_on_executor` argument validation
