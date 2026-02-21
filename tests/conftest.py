import sys
import os

# Ensure the project root is in sys.path so `from app.main import app` works
# with relative imports inside the app package
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)