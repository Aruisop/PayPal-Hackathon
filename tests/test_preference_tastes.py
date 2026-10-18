"""No-key descriptive phrases must reach the explicit preference review."""
import unittest
from unittest.mock import patch

from ai_planner import PreferenceInterpreter


class PreferenceTasteTests(unittest.TestCase):
    def test_natural_science_fiction_phrase_survives_local_review(self):
        with patch('urllib.request.urlopen') as network:
            value = PreferenceInterpreter(provider='manual').interpret(
                'Any day and time, under $25. I enjoy science fiction.', 'UTC')
        network.assert_not_called()
        self.assertEqual(value['budget_cents'], 2500)
        self.assertIn('science fiction', value['soft_preferences'])
        self.assertEqual(value['processingMode'], 'manual_fallback')
        self.assertFalse(value.get('isConfirmed', False))

    def test_common_descriptions_are_editable_tastes_without_invented_constraints(self):
        for phrase in ('sci fi', 'space opera', 'hiking', 'paddling', 'psychological mystery', 'emotional stories'):
            with self.subTest(phrase=phrase):
                value = PreferenceInterpreter(provider='manual').interpret('Any day and time. I enjoy ' + phrase)
                self.assertIn(phrase, value['soft_preferences'])
                self.assertIsNone(value['budget_cents'])
                self.assertEqual(value['time_window'], {})


if __name__ == '__main__':
    unittest.main()
