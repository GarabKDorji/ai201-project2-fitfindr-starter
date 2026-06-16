"""
Makes the project root importable so tests can do `from tools import ...`
regardless of which directory pytest is launched from.
"""

import os
import sys

# The directory containing this conftest.py is the project root.
sys.path.insert(0, os.path.dirname(__file__))
