In `TCPClient._create_stream`, if `IOStream()` constructor raises `OSError`, the except handler references `stream` which was never assigned:

```python
try:
    stream = IOStream(socket_obj, max_buffer_size=max_buffer_size)
except OSError as e:
    fu = Future()
    fu.set_exception(e)
    return stream, fu  # NameError: 'stream' is not defined
```

This causes a `NameError` that masks the original `OSError`, making it impossible to diagnose the root cause from the traceback.

Additionally the socket object would be leaked since it's never closed in the error path.

Fixed by returning the `socket_obj` instead of the undefined `stream` variable, and closing the socket before returning.
