"""Astrophotography Toolkit web app."""
import threading

from flask import Flask

from . import catalogs, settings, skymap


def create_app(load_skymap=True):
    app = Flask(__name__, static_folder=settings.STATIC_DIR, static_url_path='/static')
    app.config['MAX_CONTENT_LENGTH'] = settings.MAX_UPLOAD_BYTES

    from .routes import analyzer, calculator, pages
    app.register_blueprint(pages.bp)
    app.register_blueprint(calculator.bp)
    app.register_blueprint(analyzer.bp)

    if load_skymap:
        skymap.load()
    # Build the target search index in the background so the first search is instant.
    threading.Thread(target=catalogs.targets, daemon=True).start()
    return app
