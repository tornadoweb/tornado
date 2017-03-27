# auto.py is full of patterns mypy doesn't like, so for type checking
# purposes we replace it with interface.py.

from .interface import *
