import asyncio
import sys

# Use the selector event loop on windows. Do this in tornado/test/__init__.py
# instead of runtests.py so it happens no matter how the test is run (such as
# through editor integrations).
if sys.platform == "win32" and hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())  # type: ignore
