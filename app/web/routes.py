"""Static browser assets and the protected workshop lesson document."""
from flask import Blueprint, current_app, g, make_response, request, send_from_directory
from markupsafe import escape

from ..config import ROOT


blueprint = Blueprint('web', __name__)


def _asset(name, *, no_cache=False):
    response = make_response(send_from_directory(ROOT / 'public', name))
    if no_cache:
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    return response


@blueprint.get('/')
def index():
    return _asset('index.html', no_cache=True)


@blueprint.get('/app.js')
def javascript():
    return _asset('app.js', no_cache=True)


@blueprint.get('/style.css')
def stylesheet():
    return _asset('style.css', no_cache=True)


@blueprint.get('/demo.js')
def simulation_javascript():
    return _asset('demo.js')


@blueprint.get('/room.js')
def room_javascript():
    return _asset('room.js')


@blueprint.get('/ai.js')
def ai_javascript():
    return _asset('ai.js')


@blueprint.get('/discovery.js')
@blueprint.get('/guide.js')
def presentation_javascript():
    return _asset(request.path[1:])


@blueprint.get('/ai-worker.mjs')
def ai_worker():
    response = _asset('ai-worker.mjs')
    response.mimetype = 'text/javascript'
    return response


@blueprint.get('/lessons/<booking_id>')
def lesson(booking_id):
    checkout = current_app.extensions['checkout']
    workshop = checkout.lesson(g.participant['id'], booking_id)
    content = {
        'interview': ('Start with a clear question', 'Before writing code, restate the input and expected output. '
                      'Try a small example, identify edge cases, then explain your approach before implementing it.',
                      'Practice: explain how you would find the largest number in a list without sorting.'),
        'web': ('Give your page a structure', 'HTML describes content. CSS controls presentation. Start with '
                'a heading, paragraph and button, then add spacing, readable colors and clear focus styles.',
                'Practice: sketch a workshop card with a title, date, price and booking button.'),
    }
    title, text, exercise = content[workshop['lesson_key']]
    return make_response(
        f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
        f'<meta name="viewport" content="width=device-width,initial-scale=1"><title>{escape(workshop["title"])}</title>'
        '<link rel="stylesheet" href="/style.css"></head><body><main class="lesson">'
        f'<p>YOUR PROTECTED SAMPLE LESSON</p><h1>{escape(workshop["title"])}</h1>'
        f'<h2>{escape(title)}</h2><p>{escape(text)}</p><p>{escape(exercise)}</p>'
        '<p>Sample content for the Sandbox booking demonstration.</p><a href="/">Back to my bookings</a>'
        '</main></body></html>'
    )
