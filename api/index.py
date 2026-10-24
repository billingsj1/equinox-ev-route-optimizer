import sys
import os

# Adds the project root directory (parent of 'api/') to Python's module search path
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(current_dir, ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from ui.app import app

# Vercel ASGI entry point
# Exports the FastAPI instance as 'app'
app = app
