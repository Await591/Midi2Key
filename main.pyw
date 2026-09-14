#!/usr/bin/env python
"""Midi2Key entry point (no console window; double-click friendly)."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from midi2key.cli import main

if __name__ == "__main__":
    sys.exit(main())
