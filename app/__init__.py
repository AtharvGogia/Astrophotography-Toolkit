"""Astrophotography Toolkit web app."""
import threading

from flask import Flask, jsonify, request

from . import catalogs, settings, skymap


def create_app(load_skymap=True):
    app = Flask(__name__, static_folder=settings.STATIC_DIR, static_url_path='/static')
    app.config['MAX_CONTENT_LENGTH'] = settings.MAX_UPLOAD_BYTES

    from .routes import analyzer, calculator, pages, planner
    app.register_blueprint(pages.bp)
    app.register_blueprint(calculator.bp)
    app.register_blueprint(analyzer.bp)
    app.register_blueprint(planner.bp)

    @app.errorhandler(413)
    def too_large(_):
        msg = f'That file is larger than this site accepts ({settings.MAX_UPLOAD_MB} MB). Try a JPG or a smaller export.'
        if request.path.startswith('/api/'):
            return jsonify({'error': msg}), 413
        return msg, 413

    # /health is the one to use on Cloud Run, which reserves paths ending in "z" (/healthz there
    # is answered by Google's front end, not the app).
    @app.get('/health')
    @app.get('/healthz')
    def healthz():
        return {'ok': True, 'skymap': skymap.is_loaded()}

    # Warm-up: the target search index, the sky map and the plate-solving index.
    # Locally this happens in background threads so the server starts at once. On hosts that only
    # give CPU during requests (Cloud Run), WARMUP_SYNC does it before serving instead.
    if settings.WARMUP_SYNC:
        catalogs.targets()
        if load_skymap:
            skymap.load(background=False)
            from .solver import index
            index.get()
    else:
        if load_skymap:
            skymap.load()
        threading.Thread(target=catalogs.targets, daemon=True).start()
        # The place list (location search) loads on first use when hosted, to keep cold starts short.
        from .catalogs import places
        threading.Thread(target=places.warm, daemon=True).start()
        if load_skymap:
            from .solver import index
            threading.Thread(target=index.get, daemon=True).start()
    return app
