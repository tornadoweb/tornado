#!/usr/bin/env python
# Usage is like 2to3:
# $ maint/scripts/run_fixers.py -wn --no-diffs tornado

import sys
from lib2to3.main import main

sys.exit(main("custom_fixers"))
