"""Private QR and owner verification behavior, using only a fake payment provider."""
import unittest
from unittest.mock import patch
from xml.etree import ElementTree

import test_phase4_fulfillment as fulfillment
from ticketing import ticket_svg


class TicketingTests(unittest.TestCase):
    setUp = fulfillment.Phase4FulfillmentTests.setUp
    tearDown = fulfillment.Phase4FulfillmentTests.tearDown
    post = fulfillment.Phase4FulfillmentTests.post
    create_authorized_group = fulfillment.Phase4FulfillmentTests.create_authorized_group

    def test_pending_payment_and_outsiders_cannot_access_qr_or_check(self):
        gid = self.create_authorized_group()
        for client in (self.organizer, self.member, self.outsider):
            self.assertEqual(client.get(f'/api/groups/{gid}/ticket/qr').status_code, 404)
            self.assertEqual(self.post(client, f'/api/groups/{gid}/ticket/check',
                {'ticketCode': 'unknown'}).status_code, 404)

    def test_qr_encodes_only_current_participants_existing_ticket(self):
        gid = self.create_authorized_group()
        self.assertEqual(self.post(self.organizer, f'/api/groups/{gid}/finalize', {}).json['state'], 'CONFIRMED')
        ticket = self.organizer.get(f'/api/groups/{gid}/ticket').json
        with patch('server.ticket_svg', return_value=b'<svg/>') as encode:
            response = self.organizer.get(f'/api/groups/{gid}/ticket/qr')
        encode.assert_called_once_with(ticket['ticketCode'])
        self.assertEqual(response.mimetype, 'image/svg+xml')
        self.assertEqual(response.headers['Cache-Control'], 'no-store')
        response = self.organizer.get(f'/api/groups/{gid}/ticket/qr')
        self.assertEqual(ElementTree.fromstring(response.data).tag, '{http://www.w3.org/2000/svg}svg')
        self.assertEqual(self.outsider.get(f'/api/groups/{gid}/ticket/qr').status_code, 404)

    def test_owner_check_rejects_another_members_ticket_without_redeeming(self):
        gid = self.create_authorized_group()
        self.post(self.organizer, f'/api/groups/{gid}/finalize', {})
        own = self.organizer.get(f'/api/groups/{gid}/ticket').json
        other = self.member.get(f'/api/groups/{gid}/ticket').json
        path = f'/api/groups/{gid}/ticket/check'
        for _ in range(2):
            response = self.post(self.organizer, path, {'ticketCode': own['ticketCode']})
            self.assertTrue(response.json['valid'])
            self.assertEqual(response.json['ticketID'], own['ticketID'])
        for code in (other['ticketCode'], '<script>', '🔒'):
            response = self.post(self.organizer, path, {'ticketCode': code})
            self.assertEqual(response.json, {'valid': False, 'scope': 'private-demonstration-ticket'})
        self.assertEqual(self.post(self.organizer, path, {'ticketCode': 123}).status_code, 400)
        self.assertEqual(self.post(self.outsider, path, {'ticketCode': own['ticketCode']}).status_code, 404)
        self.assertEqual(self.organizer.post(path, json={'ticketCode': own['ticketCode']}).status_code, 403)

    def test_encoder_builds_svg_with_a_real_qr_matrix(self):
        svg = ElementTree.fromstring(ticket_svg('TICKET-private-example'))
        self.assertTrue(svg.findall('.//{http://www.w3.org/2000/svg}path'))


if __name__ == '__main__':
    unittest.main()
