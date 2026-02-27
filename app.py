"""
app.py
Flask app factory: config loading and blueprint registration.
No business logic, no route handlers, no HTML.
"""
import os
import tempfile

from flask import Flask

from config import MAX_UPLOAD_SIZE_MB
from routes import invoice_bp


def create_app():
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_SIZE_MB * 1024 * 1024

    app.register_blueprint(invoice_bp)

    return app


app = create_app()

if __name__ == "__main__":
    app.run(debug=True, port=5001)
