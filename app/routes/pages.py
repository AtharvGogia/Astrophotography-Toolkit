"""HTML pages."""
import os

from flask import Blueprint, current_app, render_template, request, send_from_directory, url_for

from .. import settings

bp = Blueprint('pages', __name__)

# (endpoint, label) in nav order. Only tools that work are listed.
NAV = [('pages.planner', 'Planner'), ('pages.exposure', 'Exposure'), ('pages.framing', 'Framing'),
       ('pages.analyzer', 'Analyzer')]


def asset(filename):
    """Static URL with the file's mtime appended, so browsers refetch edited files."""
    path = os.path.join(current_app.static_folder, filename)
    try:
        version = int(os.path.getmtime(path))
    except OSError:
        version = 0
    return url_for('static', filename=filename, v=version)


def site_url():
    """The site's public origin, without a trailing slash."""
    return settings.PUBLIC_URL or request.url_root.rstrip('/')


@bp.app_context_processor
def inject_globals():
    return {'nav_items': NAV, 'asset': asset, 'hosted': settings.HOSTED,
            'max_upload_mb': settings.MAX_UPLOAD_MB, 'site_url': site_url}


@bp.get('/manifest.webmanifest')
def manifest():
    return send_from_directory(current_app.static_folder, 'manifest.webmanifest',
                               mimetype='application/manifest+json', max_age=86400)


@bp.get('/sw.js')
def service_worker():
    # Served from the root so it can look after every page; always revalidated so updates land.
    resp = send_from_directory(current_app.static_folder, 'js/sw.js', mimetype='text/javascript', max_age=0)
    resp.headers['Cache-Control'] = 'no-cache'
    return resp


@bp.get('/favicon.ico')
def favicon():
    return send_from_directory(current_app.static_folder, 'favicon.ico', max_age=86400)


@bp.get('/')
def index():
    return render_template('home.html')


@bp.get('/planner')
def planner():
    return render_template('planner.html')


@bp.get('/exposure')
def exposure():
    return render_template('exposure.html')


@bp.get('/framing')
def framing():
    return render_template('framing.html')


@bp.get('/analyzer')
def analyzer():
    return render_template('analyzer.html')
