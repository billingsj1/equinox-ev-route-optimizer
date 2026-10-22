"""
Vercel Serverless Function entry point.
Exposes the FastAPI app for Vercel deployment.
"""
import sys
import os

# Add parent directory to python path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from ui.app import app

# Export for Vercel WSGI/ASGI handler
handler = app
