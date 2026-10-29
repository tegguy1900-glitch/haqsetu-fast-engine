"""Entry point for tier-1. Usage:  python -m tests.run_units   (or python tests/run_units.py)"""
import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
from tests import test_units
if __name__ == "__main__":
    sys.exit(test_units.run())
