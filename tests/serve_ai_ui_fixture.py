"""Isolated local fixture for DOM integration; never loads the user's .env."""
from pathlib import Path
import os
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evaluation.http_benchmark import NoPayments
from app import create_app
from waitress import serve


if __name__ == '__main__':
    # The fixture must not discover a real provider key through process defaults.
    os.environ['GEMINI_API_KEY'] = ''
    with tempfile.TemporaryDirectory(prefix='grouppay-dom-') as directory:
        app = create_app(dict(DATABASE_URL='sqlite:///' + (Path(directory) / 'fixture.db').as_posix(),
            APP_ENV='development', APP_ORIGIN='http://127.0.0.1:8021', COOKIE_SECURE=False, TESTING=True),
            paypal=NoPayments())
        print('Isolated AI UI fixture at http://127.0.0.1:8021; no user database or payments.', flush=True)
        try:
            serve(app, host='127.0.0.1', port=8021, threads=4)
        finally:
            app.extensions['store'].engine.dispose()
