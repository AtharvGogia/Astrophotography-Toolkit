"""Astrophotography Toolkit web app."""
import threading

from flask import Flask

from . import catalogs, settings, skymap


def create_app(load_skymap=True):
    app = Flask(__name__, static_folder=settings.STATIC_DIR, static_url_path='/static')
    app.config['MAX_CONTENT_LENGTH'] = settings.MAX_UPLOAD_BYTES

    from .routes import analyzer, calculator, pages, planner
    app.register_blueprint(pages.bp)
    app.register_blueprint(calculator.bp)
    app.register_blueprint(analyzer.bp)
    app.register_blueprint(planner.bp)

    if load_skymap:
        skymap.load()
    # Warm up in the background so the first search / first analysis doesn't wait:
    # the target search index, and the plate-solving index (built once, then loaded from disk).
    threading.Thread(target=catalogs.targets, daemon=True).start()
    if load_skymap:
        from .solver import index
        threading.Thread(target=index.get, daemon=True).start()
    return app
