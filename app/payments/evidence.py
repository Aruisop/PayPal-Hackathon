"""Pure validation of authenticated PayPal evidence for frozen contributions."""
from decimal import Decimal, InvalidOperation

from payments import PayPalError
from storage import money


def require(condition, issue):
    if not condition:
        raise PayPalError(issue)


def validate_amount(resource, contribution, purchase):
    amount = resource.get('amount', {})
    try:
        valid = (amount.get('currency_code') == purchase['currency'] and
                 Decimal(str(amount.get('value'))) == Decimal(money(contribution['share_cents'])))
    except (InvalidOperation, ValueError, TypeError):
        valid = False
    require(valid, 'PROVIDER_AMOUNT_MISMATCH')


def validate_order(order, contribution, purchase, expected_merchant):
    require(order.get('id') == contribution['order_id'], 'ORDER_CORRELATION_MISMATCH')
    require(order.get('intent') == 'AUTHORIZE', 'ORDER_INTENT_MISMATCH')
    units = order.get('purchase_units', [])
    require(isinstance(units, list) and len(units) == 1, 'PURCHASE_UNIT_MISMATCH')
    unit = units[0]
    require(unit.get('reference_id') == contribution['id'] and
            unit.get('custom_id') == contribution['id'], 'CONTRIBUTION_CORRELATION_MISMATCH')
    validate_amount(unit, contribution, purchase)
    merchant = unit.get('payee', {}).get('merchant_id')
    require(isinstance(merchant, str) and bool(merchant), 'MERCHANT_ID_MISSING')
    require(not expected_merchant or merchant == expected_merchant, 'MERCHANT_MISMATCH')
    return unit, merchant


def validate_authorization(resource, contribution, purchase, listed_in_order=False):
    require(resource.get('id') == contribution['authorization_id'], 'AUTHORIZATION_CORRELATION_MISMATCH')
    validate_amount(resource, contribution, purchase)
    related = resource.get('supplementary_data', {}).get('related_ids', {})
    require(related.get('order_id', contribution['order_id']) == contribution['order_id'],
            'AUTHORIZATION_CORRELATION_MISMATCH')
    require(listed_in_order or related.get('order_id') == contribution['order_id'],
            'AUTHORIZATION_LINKAGE_MISSING')


def validate_capture(resource, contribution, purchase, listed_in_order=False):
    require(resource.get('id') == contribution['capture_id'], 'CAPTURE_CORRELATION_MISMATCH')
    validate_amount(resource, contribution, purchase)
    related = resource.get('supplementary_data', {}).get('related_ids', {})
    require(related.get('order_id', contribution['order_id']) == contribution['order_id'],
            'CAPTURE_CORRELATION_MISMATCH')
    require(related.get('authorization_id', contribution['authorization_id']) == contribution['authorization_id'],
            'CAPTURE_CORRELATION_MISMATCH')
    require(listed_in_order or related.get('order_id') == contribution['order_id'] or
            related.get('authorization_id') == contribution['authorization_id'],
            'CAPTURE_LINKAGE_MISSING')


def validate_refund(resource, operation, contribution, purchase):
    require(resource.get('id') == operation['provider_id'], 'REFUND_CORRELATION_MISMATCH')
    validate_amount(resource, contribution, purchase)
    links = resource.get('links', [])
    require(any(link.get('rel') == 'up' and
                link.get('href', '').rstrip('/').endswith('/captures/' + operation['target_id'])
                for link in links), 'REFUND_LINKAGE_MISSING')
