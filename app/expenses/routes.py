"""Informal expense-split HTTP endpoints; CSRF/session enforced by the app guard."""
from flask import Blueprint, current_app, g, jsonify, request

from .ocr import ReceiptScanError
from .service import ALL, ExpenseError

blueprint = Blueprint('expenses', __name__)


def _expenses():
    return current_app.extensions['expenses']


def _scanner():
    return current_app.extensions['receipt_scanner']


def _body():
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        raise ExpenseError('INVALID_REQUEST')
    return body


@blueprint.get('/api/expenses/profile')
def get_profile():
    return jsonify(profile=_expenses().get_profile(g.participant['id']))


@blueprint.post('/api/expenses/profile')
def set_profile():
    body = _body()
    profile = _expenses().set_profile(g.participant['id'], body.get('displayName'), body.get('upiID'))
    return jsonify(profile=profile)


@blueprint.get('/api/expenses/friends')
def list_friends():
    return jsonify(friends=_expenses().list_friends(g.participant['id']))


@blueprint.post('/api/expenses/friends')
def add_friend():
    body = _body()
    friends = _expenses().add_friend(g.participant['id'], body.get('name'),
                                     body.get('upiID', ''), body.get('whatsapp', ''))
    return jsonify(friends=friends)


@blueprint.post('/api/expenses/friends/<friend_id>/delete')
def delete_friend(friend_id):
    return jsonify(friends=_expenses().remove_friend(g.participant['id'], friend_id))


@blueprint.get('/api/expenses/groups')
def groups_summary():
    return jsonify(groups=_expenses().groups_summary(g.participant['id']))


@blueprint.get('/api/expenses/splits')
def list_splits():
    raw_group = request.args.get('group')
    group_id = ALL if raw_group is None else (None if raw_group == 'none' else raw_group)
    return jsonify(splits=_expenses().list_splits(g.participant['id'], group_id=group_id))


@blueprint.post('/api/expenses/splits')
def create_split():
    body = _body()
    split = _expenses().create_split(
        g.participant['id'], body.get('title'), body.get('category'), body.get('currency', 'USD'),
        body.get('shares'), group_id=body.get('groupID'), source=body.get('source', 'manual'),
        receipt_meta=body.get('receiptMeta'))
    return jsonify(split=split)


@blueprint.post('/api/expenses/splits/<split_id>/settle')
def settle_share(split_id):
    body = _body()
    split = _expenses().settle_share(g.participant['id'], split_id, body.get('shareID'), bool(body.get('settled')))
    return jsonify(split=split)


@blueprint.get('/api/expenses/scan-status')
def scan_status():
    return jsonify(_scanner().status())


@blueprint.post('/api/expenses/scan-receipt')
def scan_receipt():
    request.max_content_length = 8 * 1024 * 1024 + 8192
    upload = request.files.get('receipt')
    if upload is None or not upload.filename:
        raise ReceiptScanError('RECEIPT_IMAGE_REQUIRED', 400)
    image_bytes = upload.stream.read(8 * 1024 * 1024 + 1)
    content_type = (upload.mimetype or '').lower()
    preview = _scanner().scan(image_bytes, content_type)
    return jsonify(scope='receipt_scan_preview', saved=False, **preview)


@blueprint.get('/api/expenses/subscriptions')
def list_subscriptions():
    return jsonify(subscriptions=_expenses().list_subscriptions(g.participant['id']))


@blueprint.post('/api/expenses/subscriptions')
def create_subscription():
    body = _body()
    subscriptions = _expenses().create_subscription(
        g.participant['id'], body.get('name'), body.get('monthlyAmountMinor'), body.get('billingDay'),
        body.get('currency', 'USD'), body.get('participants', []))
    return jsonify(subscriptions=subscriptions)


@blueprint.post('/api/expenses/subscriptions/<subscription_id>/delete')
def delete_subscription(subscription_id):
    return jsonify(subscriptions=_expenses().remove_subscription(g.participant['id'], subscription_id))


@blueprint.get('/api/expenses/analytics')
def analytics():
    return jsonify(analytics=_expenses().analytics(g.participant['id']))
