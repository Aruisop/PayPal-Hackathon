"""Individual workshop checkout HTTP endpoints."""
from flask import Blueprint, current_app, g, jsonify, request

from checkout import CheckoutError


blueprint = Blueprint('workshops', __name__)


def _checkout():
    return current_app.extensions['checkout']


@blueprint.get('/api/bookings')
def my_bookings():
    return jsonify(bookings=_checkout().list(g.participant['id']))


@blueprint.get('/api/bookings/<booking_id>')
def my_booking(booking_id):
    return jsonify(_checkout().view(g.participant['id'], booking_id))


@blueprint.post('/api/orders')
def create_order():
    body = request.get_json()
    if not isinstance(body, dict) or not isinstance(body.get('workshopID'), str):
        raise CheckoutError('WORKSHOP_REQUIRED', 400)
    return jsonify(_checkout().initiate(g.participant['id'], body['workshopID']))


@blueprint.post('/api/orders/<order_id>/capture')
def capture_order(order_id):
    return jsonify(_checkout().capture(g.participant['id'], order_id))


@blueprint.post('/api/bookings/<booking_id>/reconcile')
def reconcile(booking_id):
    return jsonify(_checkout().reconcile(g.participant['id'], booking_id))


@blueprint.post('/api/bookings/<booking_id>/cancel')
def cancel(booking_id):
    return jsonify(_checkout().cancel(g.participant['id'], booking_id))
