"""Model-output and trusted-constraint regressions; no live provider calls."""
import io
import json
import unittest
from unittest.mock import patch

from app.planning.interpreter import AIError, PreferenceInterpreter, validate_constraints


class PlanningContractTests(unittest.TestCase):
    def response(self, value):
        return io.BytesIO(json.dumps({'candidates': [{'content': {'parts': [{'text': json.dumps(value)}]}}]}).encode())

    def test_valid_model_result_is_labelled_and_key_not_in_url(self):
        with patch('urllib.request.urlopen', return_value=self.response({'budget_cents': 1500, 'preferred_days': ['Friday']})) as request:
            result = PreferenceInterpreter(api_key='fake-secret', provider='gemini').interpret('Friday under $15')
        self.assertEqual(result['processingMode'], 'gemini')
        self.assertEqual(result['preferred_days'], ['friday'])
        self.assertNotIn('fake-secret', request.call_args.args[0].full_url)
        self.assertIn('reference_date', request.call_args.args[0].data.decode())

    def test_invalid_model_output_discloses_fallback(self):
        for invalid in ({'budget_cents': -10}, {'budget_cents': True}, {'price': 0},
                        {'budget_cents': '1500'}, {'preferred_days': ['Funday']},
                        {'time_window': {'latest': '25:00'}}, {'hard_constraints': ['vegan only']}):
            with self.subTest(invalid=invalid), patch('urllib.request.urlopen', return_value=self.response(invalid)):
                result = PreferenceInterpreter(api_key='fake', provider='gemini').interpret('Friday under $15')
                self.assertEqual(result['processingMode'], 'manual_fallback')
                self.assertEqual(result['fallbackReason'], 'MODEL_UNAVAILABLE_OR_INVALID_OUTPUT')

    def test_bounded_inputs_and_timezone(self):
        p = PreferenceInterpreter(provider='manual')
        for kwargs in ({'text': 'x' * 1001}, {'text': 'Friday', 'user_tz': 'Invalid/Timezone'},
                       {'text': 'Friday', 'reference_date': 'not-date'}):
            with self.assertRaises(AIError):
                p.interpret(**kwargs)
        for constraints in ({'budget_cents': 10000001}, {'dates': ['2026-02-30']},
                            {'soft_preferences': ['x' * 161]}, {'timezone': None}):
            with self.assertRaises(AIError):
                validate_constraints(constraints)

    def test_unknown_owner_tool_currency_fields_rejected(self):
        for constraints in ({'currency': 'EUR'}, {'order_id': '123'}, {'participant_id': 'other'},
                            {'time_window': {'earliest': '22:00', 'latest': '18:00'}}):
            with self.assertRaises(AIError):
                validate_constraints(constraints)

    def test_explicit_times_and_unsupported_timing(self):
        p = PreferenceInterpreter(provider='manual')
        result = p.interpret('Friday after 9pm before 11pm under $20')
        self.assertEqual(result['time_window'], {'earliest': '21:00', 'latest': '23:00'})
        self.assertTrue(p.interpret('Friday around 7pm')['clarifications'])
        self.assertTrue(p.interpret('Friday before 9')['clarifications'])

    def test_any_day_and_time_clear_inferred_windows(self):
        p = PreferenceInterpreter(provider='manual')
        for text in ('Any day and time under $20', 'Friday evening or any day and time under $20',
                     'Any day, anytime under $20'):
            result = p.interpret(text)
            self.assertEqual(result['preferred_days'], [])
            self.assertEqual(result['time_window'], {})
            self.assertEqual(result['budget_cents'], 2000)
