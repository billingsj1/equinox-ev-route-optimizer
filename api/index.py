import sys
import os

# Add parent directory to path so engine, pipeline, ui can be imported
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from ui.app import app

# Vercel ASGI entry point
# Exports the FastAPI instance as 'app'
app = app
