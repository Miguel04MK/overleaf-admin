"""
Entry point for the Overleaf Admin Platform.
Run with: python run.py
"""
import os
from dotenv import load_dotenv

# Load .env before importing app to ensure config is available
load_dotenv()

from app import create_app

app = create_app()

if __name__ == "__main__":
    host = os.getenv("FLASK_HOST", "127.0.0.1")
    port = int(os.getenv("FLASK_PORT", 5000))
    debug = os.getenv("DEBUG", "true").lower() == "true"
    app.run(host=host, port=port, debug=debug)
