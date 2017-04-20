import sys
import logging

# For Windows versions not supporting ANSI terminal codes, we need colorama
# installed to get colored output
if sys.platform.startswith('win32'):
    try:
        import colorama
    except ImportError:
        colorama = None

import tornado.log

# First initialize colorama on Windows
if sys.platform.startswith('win'):
    if colorama is not None:
        colorama.init()

# Setup pretty logging
tornado.log.enable_pretty_logging()

logger = logging.getLogger("colored")
logger.setLevel(logging.DEBUG)

logger.info("some information")
logger.warning("a warning")
logger.error("an error")
logger.critical("a critical error")
logger.debug("debug info")
