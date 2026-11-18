"""HTML pages."""
import os

from flask import Blueprint, current_app, redirect, render_template, url_for

bp = Blueprint('pages', __name__)

# (endpoint, label) in nav order. Only tools that work are listed.
NAV = [('pages.exposure', 'Exposure'), ('pages.framing', 'Framing'), ('pages.analyzer', 'Analyzer')]


def asset(filename):
    """Static URL with the file's mtime appended, so browsers refetch edited files."""
    path = os.path.join(current_app.static_folder, filename)
    try:
        version = int(os.path.getmtime(path))
    except OSError:
        version = 0
    return url_for('static', filename=filename, v=version)


@bp.app_context_processor
def inject_globals():
    return {'nav_items': NAV, 'asset': asset}


@bp.get('/')
def index():
    return redirect(url_for('pages.exposure'))


@bp.get('/exposure')
def exposure():
    return render_template('exposure.html')


@bp.get('/framing')
def framing():
    return render_template('framing.html')


@bp.get('/analyzer')
def analyzer():
    return render_template('analyzer.html')
