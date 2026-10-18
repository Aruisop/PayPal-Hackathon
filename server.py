"""GroupPay HTTP boundary and explicit migration/recovery commands."""
import argparse
import hmac
import os
from pathlib import Path
from urllib.parse import urlparse
from flask import Flask, g, jsonify, make_response, request, send_from_directory
from markupsafe import escape
from ai_planner import AIError, PreferenceInterpreter
from checkout import Checkout, CheckoutError
from collab_booking import BookingError, CollabBooking
from groups import GroupError, Groups
from payments import PayPal, PayPalError
from room import Room
from rescue import PlanRescue
from storage import Store
from ticketing import ticket_svg

ROOT = Path(__file__).resolve().parent


def database_url():
    value = os.getenv('DATABASE_URL', 'sqlite:///instance/workshops.db')
    if value.startswith('sqlite:///'):
        path = value[len('sqlite:///'):]
        if path != ':memory:' and not Path(path).is_absolute():
            return 'sqlite:///' + (ROOT / path).as_posix()
    return value

def load_env():
    path = ROOT / '.env'
    if path.exists():
        for line in path.read_text(encoding='utf-8-sig').splitlines():
            if line.strip() and not line.lstrip().startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ.setdefault(key.strip(), value.strip().strip("\"'"))

def create_app(config=None, paypal=None):
    app = Flask(__name__, static_folder=None)
    app.config.update(DATABASE_URL=database_url(),
        APP_ENV=os.getenv('APP_ENV', 'development'), APP_ORIGIN=os.getenv('APP_ORIGIN', 'http://localhost:8000').rstrip('/'),
        COOKIE_SECURE=os.getenv('COOKIE_SECURE', 'false').lower() == 'true', MAX_CONTENT_LENGTH=16384)
    if config:
        app.config.update(config)
    if app.config['APP_ENV'] == 'production':
        if not app.config['DATABASE_URL'].startswith(('postgres://', 'postgresql://', 'postgresql+psycopg://')):
            raise RuntimeError('Production requires durable managed PostgreSQL, not local SQLite')
        if not app.config['APP_ORIGIN'].startswith('https://') or not app.config['COOKIE_SECURE']:
            raise RuntimeError('Production requires HTTPS APP_ORIGIN and COOKIE_SECURE=true')
    store = Store(app.config['DATABASE_URL'])
    if app.config['APP_ENV'] != 'production':
        store.migrate(target=5)
        store.seed()
    else:
        from sqlalchemy import select
        from storage import versions
        with store.engine.connect() as connection:
            if connection.execute(select(versions.c.revision).where(versions.c.id == 1)).scalar() != 5:
                raise RuntimeError('Run python server.py migrate before starting')
    adapter = paypal or PayPal(os.getenv('PAYPAL_CLIENT_ID', ''), os.getenv('PAYPAL_CLIENT_SECRET', ''),
                               os.getenv('PAYPAL_MERCHANT_ID', ''))
    checkout = Checkout(store, adapter)
    groups = Groups(store, checkout, app.config['APP_ORIGIN'])
    booking = CollabBooking(store, app.config['APP_ORIGIN'], adapter)
    room = Room(store)
    rescue = PlanRescue(store)
    app.extensions.update(store=store, checkout=checkout, groups=groups, paypal=adapter, booking=booking, room=room)

    @app.before_request
    def authorize():
        if request.host != urlparse(app.config['APP_ORIGIN']).netloc:
            return jsonify(error='INVALID_HOST'), 400
        g.participant = store.participant(request.cookies.get('workshop_session'))
        if (request.path.startswith('/api/') and request.path != '/api/config') or request.path.startswith('/lessons/'):
            if not g.participant:
                return jsonify(error='PARTICIPANT_SESSION_REQUIRED'), 401
        if request.method == 'POST':
            if (request.headers.get('Origin') != app.config['APP_ORIGIN'] or not g.participant or
                not hmac.compare_digest(request.headers.get('X-CSRF-Token', ''), g.participant['csrf_token'])):
                return jsonify(error='INVALID_ORIGIN_OR_CSRF'), 403

    @app.after_request
    def headers(response):
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['X-Frame-Options'] = 'DENY'
        return response

    @app.errorhandler(CheckoutError)
    def checkout_error(error):
        return jsonify(error=error.issue), error.status

    @app.errorhandler(GroupError)
    def group_error(error):
        return jsonify(error=error.issue), error.status

    @app.errorhandler(BookingError)
    def booking_error(error):
        return jsonify(error=error.issue), error.status

    @app.errorhandler(AIError)
    def ai_error(error):
        return jsonify(error=error.issue), error.status

    @app.errorhandler(PayPalError)
    def paypal_error(error):
        return jsonify(error=error.issue, debugID=error.debug_id), error.status

    @app.errorhandler(404)
    def not_found(_):
        return jsonify(error='NOT_FOUND'), 404

    @app.errorhandler(400)
    def invalid_json(_):
        return jsonify(error='INVALID_REQUEST'), 400

    @app.get('/')
    def index():
        res = make_response(send_from_directory(ROOT / 'public', 'index.html'))
        res.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        return res

    @app.get('/app.js')
    def javascript():
        res = make_response(send_from_directory(ROOT / 'public', 'app.js'))
        res.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        return res

    @app.get('/style.css')
    def stylesheet():
        res = make_response(send_from_directory(ROOT / 'public', 'style.css'))
        res.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        return res

    @app.get('/demo.js')
    def simulation_javascript():
        return send_from_directory(ROOT / 'public', 'demo.js')

    @app.get('/room.js')
    def room_javascript():
        return send_from_directory(ROOT / 'public', 'room.js')

    @app.get('/ai.js')
    def ai_javascript():
        return send_from_directory(ROOT / 'public', 'ai.js')

    @app.get('/discovery.js')
    @app.get('/guide.js')
    def presentation_javascript():
        return send_from_directory(ROOT / 'public', request.path[1:])

    @app.get('/ai-worker.mjs')
    def ai_worker():
        response = make_response(send_from_directory(ROOT / 'public', 'ai-worker.mjs'))
        response.mimetype = 'text/javascript'
        return response

    @app.post('/api/planning/preview')
    def preview_preference():
        body = request.get_json()
        if not isinstance(body, dict):
            raise AIError('INVALID_REQUEST')
        interpretation = PreferenceInterpreter().interpret(body.get('rawText'), user_tz=body.get('userTz', 'UTC'))
        return jsonify(scope='interpretation_preview', saved=False, interpretation=interpretation)

    @app.get('/api/config')
    def configuration():
        token = None
        if not g.participant:
            g.participant, token = store.new_participant()
        response = jsonify(clientID=adapter.client_id, configured=adapter.configured, participantID=g.participant['id'],
            csrfToken=g.participant['csrf_token'], workshops=store.catalog(), bookings=checkout.list(g.participant['id']),
            planningMode='gemini' if os.getenv('GEMINI_API_KEY', '').strip() else 'local')
        if token:
            response.set_cookie('workshop_session', token, max_age=30 * 86400, httponly=True,
                                secure=app.config['COOKIE_SECURE'], samesite='Strict', path='/')
        return response

    @app.get('/api/bookings')
    def my_bookings():
        return jsonify(bookings=checkout.list(g.participant['id']))

    @app.get('/api/groups')
    def my_groups():
        return jsonify(groups=groups.list(g.participant['id']))

    @app.post('/api/groups')
    def create_group():
        body = request.get_json()
        return jsonify(groups.create(g.participant['id'], body.get('name') if isinstance(body, dict) else None))

    @app.post('/api/groups/join')
    def join_group():
        body = request.get_json()
        return jsonify(groups.join(g.participant['id'], body.get('inviteToken') if isinstance(body, dict) else None))

    @app.get('/api/groups/<group_id>')
    def my_group(group_id):
        return jsonify(groups.view(g.participant['id'], group_id))

    @app.get('/api/groups/<group_id>/room')
    def group_room(group_id):
        return jsonify(room.view(g.participant['id'], group_id, request.args.get('after')))

    @app.post('/api/groups/<group_id>/rescue')
    def rescue_plan(group_id):
        body = request.get_json()
        if not isinstance(body, dict):
            raise AIError('INVALID_REQUEST')
        return jsonify(rescue.suggest(g.participant['id'], group_id, body.get('domain', 'movie')))

    @app.post('/api/groups/<group_id>/messages')
    def send_room_message(group_id):
        body = request.get_json()
        return jsonify(room.post_message(g.participant['id'], group_id,
            body.get('text') if isinstance(body, dict) else None))

    @app.post('/api/groups/<group_id>/selection')
    def select_group_workshop(group_id):
        body = request.get_json()
        return jsonify(groups.select_workshop(g.participant['id'], group_id,
            body.get('workshopID') if isinstance(body, dict) else None))

    @app.get('/api/catalog/offers')
    def get_offers():
        domain = request.args.get('domain')
        return jsonify(offers=store.offers(domain))

    @app.post('/api/groups/<group_id>/profile')
    def set_group_profile(group_id):
        body = request.get_json()
        if not isinstance(body, dict) or type(body.get('shareProgress', False)) is not bool:
            raise BookingError('INVALID_REQUEST', 400)
        return jsonify(booking.set_profile(g.participant['id'], group_id, body.get('alias', ''), body.get('shareProgress', False)))

    @app.post('/api/groups/<group_id>/quote')
    def get_group_quote(group_id):
        body = request.get_json()
        if not isinstance(body, dict) or not body.get('offerID'):
            raise BookingError('OFFER_REQUIRED', 400)
        return jsonify(booking.quote(g.participant['id'], group_id, body.get('offerID'), body.get('resourceIDs')))

    @app.post('/api/groups/<group_id>/freeze')
    def freeze_group(group_id):
        body = request.get_json()
        if not isinstance(body, dict) or not body.get('offerID'):
            raise BookingError('OFFER_REQUIRED', 400)
        return jsonify(booking.freeze(g.participant['id'], group_id, body.get('offerID'), body.get('resourceIDs')))

    @app.get('/api/groups/<group_id>/booking')
    def get_group_booking(group_id):
        return jsonify(booking.view(g.participant['id'], group_id))

    @app.post('/api/groups/<group_id>/booking/consent')
    def give_group_consent(group_id):
        return jsonify(booking.give_consent(g.participant['id'], group_id))

    @app.post('/api/groups/<group_id>/preferences')
    def submit_group_preference(group_id):
        body = request.get_json()
        if not isinstance(body, dict) or not body.get('rawText'):
            raise BookingError('PREFERENCE_TEXT_REQUIRED', 400)
        return jsonify(booking.submit_preference(g.participant['id'], group_id, body.get('rawText'),
                                                 body.get('userTz', 'UTC'), body.get('referenceDate')))

    @app.get('/api/groups/<group_id>/preferences')
    def get_group_preference(group_id):
        return jsonify(booking.planning.get_preference(g.participant['id'], group_id))

    @app.post('/api/groups/<group_id>/preferences/confirm')
    def confirm_group_preference(group_id):
        body = request.get_json()
        if not isinstance(body, dict) or not isinstance(body.get('confirmedConstraints'), dict):
            raise BookingError('CONSTRAINTS_REQUIRED', 400)
        return jsonify(booking.confirm_preference(g.participant['id'], group_id, body.get('confirmedConstraints')))

    @app.get('/api/groups/<group_id>/plan')
    def get_group_plan(group_id):
        domain = request.args.get('domain', 'movie')
        return jsonify(booking.get_group_plan(g.participant['id'], group_id, domain))

    @app.post('/api/groups/<group_id>/contributions/order')
    def initiate_group_contribution_order(group_id):
        return jsonify(booking.initiate_contribution_order(g.participant['id'], group_id))

    @app.post('/api/groups/<group_id>/contributions/authorize')
    def authorize_group_contribution(group_id):
        return jsonify(booking.authorize_contribution(g.participant['id'], group_id))

    @app.post('/api/groups/<group_id>/contributions/reconcile')
    def reconcile_group_contribution(group_id):
        return jsonify(booking.reconcile_contribution(g.participant['id'], group_id))

    @app.post('/api/groups/<group_id>/booking/void')
    def void_group_booking(group_id):
        return jsonify(booking.void_booking(g.participant['id'], group_id))

    @app.post('/api/groups/<group_id>/finalize')
    def finalize_group_booking(group_id):
        return jsonify(booking.finalize_booking(g.participant['id'], group_id))

    @app.post('/api/groups/<group_id>/recover')
    def recover_group_booking(group_id):
        return jsonify(booking.payments.recover(g.participant['id'], group_id))

    @app.get('/api/groups/<group_id>/ticket')
    def get_group_ticket(group_id):
        return jsonify(booking.get_my_ticket(g.participant['id'], group_id))

    @app.get('/api/groups/<group_id>/ticket/qr')
    def get_group_ticket_qr(group_id):
        ticket = booking.get_my_ticket(g.participant['id'], group_id)
        response = make_response(ticket_svg(ticket['ticketCode']))
        response.mimetype = 'image/svg+xml'
        return response

    @app.post('/api/groups/<group_id>/ticket/check')
    def check_group_ticket(group_id):
        ticket = booking.get_my_ticket(g.participant['id'], group_id)
        body = request.get_json()
        code = body.get('ticketCode') if isinstance(body, dict) else None
        if not isinstance(code, str) or len(code) > 256:
            raise BookingError('TICKET_CODE_REQUIRED', 400)
        valid = hmac.compare_digest(code.encode('utf-8'), ticket['ticketCode'].encode('utf-8'))
        result = dict(valid=valid, scope='private-demonstration-ticket')
        if valid:
            result.update(ticketID=ticket['ticketID'], offeringTitle=ticket['title'],
                          assignedResource=ticket['assignedResource'])
        return jsonify(result)

    @app.get('/api/bookings/<booking_id>')
    def my_booking(booking_id):
        return jsonify(checkout.view(g.participant['id'], booking_id))

    @app.post('/api/orders')
    def create_order():
        body = request.get_json()
        if not isinstance(body, dict) or not isinstance(body.get('workshopID'), str):
            raise CheckoutError('WORKSHOP_REQUIRED', 400)
        return jsonify(checkout.initiate(g.participant['id'], body['workshopID']))

    @app.post('/api/orders/<order_id>/capture')
    def capture_order(order_id):
        return jsonify(checkout.capture(g.participant['id'], order_id))

    @app.post('/api/bookings/<booking_id>/reconcile')
    def reconcile(booking_id):
        return jsonify(checkout.reconcile(g.participant['id'], booking_id))

    @app.post('/api/bookings/<booking_id>/cancel')
    def cancel(booking_id):
        return jsonify(checkout.cancel(g.participant['id'], booking_id))

    @app.get('/lessons/<booking_id>')
    def lesson(booking_id):
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
        return make_response(f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1"><title>{escape(workshop["title"])}</title>'
            '<link rel="stylesheet" href="/style.css"></head><body><main class="lesson">'
            f'<p>YOUR PROTECTED SAMPLE LESSON</p><h1>{escape(workshop["title"])}</h1>'
            f'<h2>{escape(title)}</h2><p>{escape(text)}</p><p>{escape(exercise)}</p>'
            '<p>Sample content for the Sandbox booking demonstration.</p><a href="/">Back to my bookings</a>'
            '</main></body></html>')

    return app

if __name__ == '__main__':
    load_env()
    parser = argparse.ArgumentParser()
    parser.add_argument('command', nargs='?', choices=['serve', 'migrate', 'recover'], default='serve')
    args = parser.parse_args()
    if args.command == 'migrate':
        store = Store(database_url())
        store.migrate(target=5)
        store.seed()
        print('Database revision 5 applied; catalog seeded if empty. No database URL displayed.')
    elif args.command == 'recover':
        application = create_app()
        result = application.extensions['booking'].payments.recover_pending()
        print('Recovery pass:', result)
    else:
        from waitress import serve
        application = create_app()
        print('Workshop Sandbox checkout at ' + application.config['APP_ORIGIN'], flush=True)
        serve(application, host='0.0.0.0' if application.config['APP_ENV'] == 'production' else '127.0.0.1',
              port=int(os.getenv('PORT', '8000')), threads=4)
