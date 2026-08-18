# backend/tests/conftest.py
import pytest
import sys
import os

# Add backend directory to path for all tests
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
