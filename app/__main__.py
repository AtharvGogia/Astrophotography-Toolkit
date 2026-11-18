"""Run the toolkit: python -m app"""
import os

from . import create_app, settings

if __name__ == '__main__':
    app = create_app()
    if not settings.load_api_key():
        print('Note: no astrometry.net API key set; the Analyzer will not work (see README).')
    print('Open http://127.0.0.1:5000')
    # Debug mode (interactive debugger, auto-reload) only when explicitly asked for.
    app.run(port=5000, debug=os.environ.get('FLASK_DEBUG') == '1')
