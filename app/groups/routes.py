"""Collaborative planning, booking, payment, and ticket HTTP endpoints."""
import hmac
import os

from flask import Blueprint, current_app, g, jsonify, make_response, request

from ai_planner import AIError, PreferenceInterpreter
from collab_booking import BookingError
blueprint = Blueprint('groups', __name__)


def _extension(name):
    return current_app.extensions[name]


@blueprint.post('/api/planning/preview')
def preview_preference():
    body = request.get_json()
    if not isinstance(body, dict):
        raise AIError('INVALID_REQUEST')
    interpretation = PreferenceInterpreter().interpret(body.get('rawText'), user_tz=body.get('userTz', 'UTC'))
    return jsonify(scope='interpretation_preview', saved=False, interpretation=interpretation)


@blueprint.get('/api/config')
def configuration():
    store, checkout, adapter = _extension('store'), _extension('checkout'), _extension('paypal')
    token = None
    if not g.participant:
        g.participant, token = store.new_participant()
    response = jsonify(
        clientID=adapter.client_id, configured=adapter.configured, participantID=g.participant['id'],
        csrfToken=g.participant['csrf_token'], workshops=store.catalog(), bookings=checkout.list(g.participant['id']),
        planningMode='gemini' if os.getenv('GEMINI_API_KEY', '').strip() else 'local',
    )
    if token:
        response.set_cookie('workshop_session', token, max_age=30 * 86400, httponly=True,
                            secure=current_app.config['COOKIE_SECURE'], samesite='Strict', path='/')
    return response


@blueprint.get('/api/groups')
def my_groups():
    return jsonify(groups=_extension('groups').list(g.participant['id']))


@blueprint.post('/api/groups')
def create_group():
    body = request.get_json()
    return jsonify(_extension('groups').create(g.participant['id'], body.get('name') if isinstance(body, dict) else None))


@blueprint.post('/api/groups/join')
def join_group():
    body = request.get_json()
    return jsonify(_extension('groups').join(g.participant['id'], body.get('inviteToken') if isinstance(body, dict) else None))


@blueprint.get('/api/groups/<group_id>')
def my_group(group_id):
    return jsonify(_extension('groups').view(g.participant['id'], group_id))


@blueprint.get('/api/groups/<group_id>/room')
def group_room(group_id):
    return jsonify(_extension('room').view(g.participant['id'], group_id, request.args.get('after')))


@blueprint.post('/api/groups/<group_id>/rescue')
def rescue_plan(group_id):
    body = request.get_json()
    if not isinstance(body, dict):
        raise AIError('INVALID_REQUEST')
    return jsonify(_extension('rescue').suggest(g.participant['id'], group_id, body.get('domain', 'movie')))


@blueprint.get('/api/ai/status')
def ai_status():
    return jsonify(_extension('recommendations').encoder.status())


@blueprint.post('/api/groups/<group_id>/recommendations')
def recommend_group(group_id):
    body = request.get_json()
    if not isinstance(body, dict):
        raise AIError('INVALID_REQUEST')
    return jsonify(_extension('recommendations').recommend(
        g.participant['id'], group_id, body.get('domain', 'movie'), body.get('objective', 'compromise')
    ))


@blueprint.post('/api/groups/<group_id>/messages')
def send_room_message(group_id):
    body = request.get_json()
    return jsonify(_extension('room').post_message(g.participant['id'], group_id, body.get('text') if isinstance(body, dict) else None))


@blueprint.post('/api/groups/<group_id>/selection')
def select_group_workshop(group_id):
    body = request.get_json()
    return jsonify(_extension('groups').select_workshop(
        g.participant['id'], group_id, body.get('workshopID') if isinstance(body, dict) else None
    ))


@blueprint.get('/api/catalog/offers')
def get_offers():
    return jsonify(offers=_extension('store').offers(request.args.get('domain')))


@blueprint.post('/api/groups/<group_id>/profile')
def set_group_profile(group_id):
    body = request.get_json()
    if not isinstance(body, dict) or type(body.get('shareProgress', False)) is not bool:
        raise BookingError('INVALID_REQUEST', 400)
    return jsonify(_extension('booking').set_profile(
        g.participant['id'], group_id, body.get('alias', ''), body.get('shareProgress', False)
    ))


@blueprint.post('/api/groups/<group_id>/quote')
def get_group_quote(group_id):
    body = request.get_json()
    if not isinstance(body, dict) or not body.get('offerID'):
        raise BookingError('OFFER_REQUIRED', 400)
    return jsonify(_extension('booking').quote(g.participant['id'], group_id, body.get('offerID'), body.get('resourceIDs')))


@blueprint.post('/api/groups/<group_id>/freeze')
def freeze_group(group_id):
    body = request.get_json()
    if not isinstance(body, dict) or not body.get('offerID'):
        raise BookingError('OFFER_REQUIRED', 400)
    return jsonify(_extension('booking').freeze(g.participant['id'], group_id, body.get('offerID'), body.get('resourceIDs')))


@blueprint.get('/api/groups/<group_id>/booking')
def get_group_booking(group_id):
    return jsonify(_extension('booking').view(g.participant['id'], group_id))


@blueprint.post('/api/groups/<group_id>/booking/consent')
def give_group_consent(group_id):
    return jsonify(_extension('booking').give_consent(g.participant['id'], group_id))


@blueprint.post('/api/groups/<group_id>/preferences')
def submit_group_preference(group_id):
    body = request.get_json()
    if not isinstance(body, dict) or not body.get('rawText'):
        raise BookingError('PREFERENCE_TEXT_REQUIRED', 400)
    return jsonify(_extension('booking').submit_preference(
        g.participant['id'], group_id, body.get('rawText'), body.get('userTz', 'UTC'), body.get('referenceDate')
    ))


@blueprint.get('/api/groups/<group_id>/preferences')
def get_group_preference(group_id):
    return jsonify(_extension('booking').planning.get_preference(g.participant['id'], group_id))


@blueprint.post('/api/groups/<group_id>/preferences/confirm')
def confirm_group_preference(group_id):
    body = request.get_json()
    if not isinstance(body, dict) or not isinstance(body.get('confirmedConstraints'), dict):
        raise BookingError('CONSTRAINTS_REQUIRED', 400)
    return jsonify(_extension('booking').confirm_preference(g.participant['id'], group_id, body.get('confirmedConstraints')))


@blueprint.get('/api/groups/<group_id>/plan')
def get_group_plan(group_id):
    return jsonify(_extension('booking').get_group_plan(g.participant['id'], group_id, request.args.get('domain', 'movie')))


@blueprint.post('/api/groups/<group_id>/contributions/order')
def initiate_group_contribution_order(group_id):
    return jsonify(_extension('booking').initiate_contribution_order(g.participant['id'], group_id))


@blueprint.post('/api/groups/<group_id>/contributions/authorize')
def authorize_group_contribution(group_id):
    return jsonify(_extension('booking').authorize_contribution(g.participant['id'], group_id))


@blueprint.post('/api/groups/<group_id>/contributions/reconcile')
def reconcile_group_contribution(group_id):
    return jsonify(_extension('booking').reconcile_contribution(g.participant['id'], group_id))


@blueprint.post('/api/groups/<group_id>/booking/void')
def void_group_booking(group_id):
    return jsonify(_extension('booking').void_booking(g.participant['id'], group_id))


@blueprint.post('/api/groups/<group_id>/finalize')
def finalize_group_booking(group_id):
    return jsonify(_extension('booking').finalize_booking(g.participant['id'], group_id))


@blueprint.post('/api/groups/<group_id>/recover')
def recover_group_booking(group_id):
    return jsonify(_extension('booking').payments.recover(g.participant['id'], group_id))


@blueprint.get('/api/groups/<group_id>/ticket')
def get_group_ticket(group_id):
    return jsonify(_extension('booking').get_my_ticket(g.participant['id'], group_id))


@blueprint.get('/api/groups/<group_id>/ticket/qr')
def get_group_ticket_qr(group_id):
    ticket = _extension('booking').get_my_ticket(g.participant['id'], group_id)
    # Kept late-bound for the historical server.ticket_svg test seam.
    from server import ticket_svg
    response = make_response(ticket_svg(ticket['ticketCode']))
    response.mimetype = 'image/svg+xml'
    return response


@blueprint.post('/api/groups/<group_id>/ticket/check')
def check_group_ticket(group_id):
    ticket = _extension('booking').get_my_ticket(g.participant['id'], group_id)
    body = request.get_json()
    code = body.get('ticketCode') if isinstance(body, dict) else None
    if not isinstance(code, str) or len(code) > 256:
        raise BookingError('TICKET_CODE_REQUIRED', 400)
    valid = hmac.compare_digest(code.encode('utf-8'), ticket['ticketCode'].encode('utf-8'))
    result = dict(valid=valid, scope='private-demonstration-ticket')
    if valid:
        result.update(ticketID=ticket['ticketID'], offeringTitle=ticket['title'], assignedResource=ticket['assignedResource'])
    return jsonify(result)
