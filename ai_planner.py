"""AI-assisted preference interpretation, deterministic catalog matching, and conflict explainer."""
import json
import os
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone


class AIError(Exception):
    def __init__(self, issue, status=400):
        self.issue, self.status = issue, status


class PreferenceInterpreter:
    def __init__(self, api_key=None, provider=None):
        self.gemini_key = api_key or os.getenv('GEMINI_API_KEY')
        self.openai_key = api_key or os.getenv('OPENAI_API_KEY')
        self.provider = provider or ('gemini' if self.gemini_key else ('openai' if self.openai_key else 'heuristic'))

    def _detect_prompt_injection(self, text):
        suspicious_patterns = [
            r'ignore\s+(all\s+)?(previous|prior)\s+instructions',
            r'system\s+prompt',
            r'free\s+(ticket|booking|order)',
            r'price\s*[:=]\s*0',
            r'grant\s+(admin|permission|access)',
            r'override\s+(policy|price|cost|rules)',
            r'make\s+everything\s+free',
            r'disregard\s+rules'
        ]
        lower = text.lower()
        for p in suspicious_patterns:
            if re.search(p, lower):
                return True
        return False

    def _heuristic_parse(self, text, user_tz='UTC', reference_date=None):
        lower = text.lower()
        clarifications = []
        hard_constraints = []
        soft_preferences = []

        # Relative date ambiguity
        if 'next ' in lower:
            for d in ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday', 'week', 'weekend']:
                if f'next {d}' in lower:
                    clarifications.append(f'Ambiguous relative date ("next {d}"); please confirm specific calendar date.')

        # Budget extraction (e.g. "$20", "20 dollars", "under 15", "max 25.50", "under $35")
        budget_match = re.search(r'(?:\$|under\s+\$?|max\s+\$?|budget\s+of\s+\$?|up\s+to\s+\$?)(\d+(?:\.\d{1,2})?)', lower)
        budget_cents = None
        if budget_match:
            val = float(budget_match.group(1))
            budget_cents = int(round(val * 100))
            hard_constraints.append(f'max_budget_cents:{budget_cents}')
            if '$' not in text and 'usd' not in lower and 'dollar' not in lower:
                clarifications.append(f'Interpreted ${val:.2f} as USD; please confirm your currency.')
        else:
            clarifications.append('No budget specified; assuming standard ticket price.')

        # Preferred days
        days = []
        day_names = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
        for d in day_names:
            if d in lower or (len(d) > 3 and d[:3] in lower.split()):
                if d not in days:
                    days.append(d)
        if 'weekend' in lower:
            for d in ['friday', 'saturday', 'sunday']:
                if d not in days:
                    days.append(d)
        if days:
            hard_constraints.append(f'days:{",".join(days)}')
        else:
            clarifications.append('No preferred day specified; all schedule options considered.')

        # Time window
        time_window = {}
        if 'evening' in lower or 'night' in lower:
            time_window['earliest'] = '17:00'
            time_window['latest'] = '23:59'
            hard_constraints.append('time:evening')
        elif 'matinee' in lower or 'afternoon' in lower:
            time_window['earliest'] = '12:00'
            time_window['latest'] = '17:00'
            hard_constraints.append('time:afternoon')
        elif 'morning' in lower:
            time_window['earliest'] = '08:00'
            time_window['latest'] = '12:00'
            hard_constraints.append('time:morning')

        finish_match = re.search(r'(?:finish|end|leave|back)\s+before\s+(\d{1,2})(?:\s*pm|\s*:00)?', lower)
        if finish_match:
            hr = int(finish_match.group(1))
            if hr < 12 and ('pm' in lower or hr in (7, 8, 9, 10, 11)):
                hr += 12
            time_window['finish_before'] = f'{hr:02d}:00'
            hard_constraints.append(f'finish_before:{hr:02d}:00')

        # Soft preferences (movies and travel)
        for pref in ['sci-fi', 'thriller', 'drama', 'action', 'comedy', 'director cut',
                     'remastered', '4k', 'kayak', 'river', 'trek', 'mountain', 'alpine']:
            if pref in lower:
                soft_preferences.append(pref)

        return {
            'raw_text': text,
            'budget_cents': budget_cents,
            'currency': 'USD',
            'preferred_days': days,
            'time_window': time_window,
            'hard_constraints': hard_constraints,
            'soft_preferences': soft_preferences,
            'clarifications': clarifications,
            'injection_detected': False
        }

    def interpret(self, text, user_tz='UTC', reference_date=None):
        if not isinstance(text, str) or not text.strip():
            raise AIError('PREFERENCE_TEXT_REQUIRED', 400)
        clean_text = text.strip()[:1000]

        # Fail-closed Prompt Injection Guard
        if self._detect_prompt_injection(clean_text):
            return {
                'raw_text': clean_text,
                'budget_cents': None,
                'currency': 'USD',
                'preferred_days': [],
                'time_window': {},
                'hard_constraints': ['injection_neutralized'],
                'soft_preferences': [],
                'clarifications': ['Potential prompt injection detected. Policy overrides and pricing manipulations are blocked.'],
                'injection_detected': True
            }

        # Live Gemini API call if key is present
        if self.gemini_key and self.provider == 'gemini':
            try:
                system_instruction = (
                    "You are an AI booking coordinator assistant. Extract structured constraints from user preference text into JSON.\n"
                    "Fields: budget_cents (integer USD cents or null), preferred_days (list of lowercase day strings), "
                    "time_window (dict with earliest, latest, or finish_before HH:MM), hard_constraints (list of strings), "
                    "soft_preferences (list of strings), clarifications (list of questions). Never invent prices or waive costs."
                )
                payload = {
                    "contents": [{"parts": [{"text": f"User preference text: {clean_text}\nTimezone: {user_tz}"}]}],
                    "systemInstruction": {"parts": [{"text": system_instruction}]},
                    "generationConfig": {"response_mime_type": "application/json"}
                }
                url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={self.gemini_key}"
                req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'),
                                             headers={'Content-Type': 'application/json'}, method='POST')
                with urllib.request.urlopen(req, timeout=10) as resp:
                    data = json.load(resp)
                    content_str = data['candidates'][0]['content']['parts'][0]['text']
                    parsed = json.loads(content_str)
                    parsed['raw_text'] = clean_text
                    parsed['currency'] = 'USD'
                    parsed['injection_detected'] = False
                    return parsed
            except Exception:
                # Fail-closed graceful fallback to deterministic parser
                pass

        return self._heuristic_parse(clean_text, user_tz, reference_date)


class DeterministicCatalogMatcher:
    def match(self, member_constraints, catalog_offers, group_size):
        """Deterministically filters authoritative offers against confirmed member constraints."""
        matches = []
        conflicts = []

        for offer in catalog_offers:
            offer_id = offer['id']
            title = offer['title']
            price_cents = offer['priceMinor']
            sched_str = offer['scheduleTime']
            sched_dt = datetime.fromisoformat(sched_str.replace('Z', '+00:00'))
            offer_day = sched_dt.strftime('%A').lower()
            offer_time_hhmm = sched_dt.strftime('%H:%M')

            # Calculate individual share
            if offer['domain'] == 'movie':
                share_cents = price_cents
            else:
                share_cents = (price_cents // group_size) + (1 if price_cents % group_size else 0)

            # Check available adjacent seats / places
            free_resources = [r for r in offer.get('resources', []) if r['state'] == 'FREE']
            if len(free_resources) < group_size:
                conflicts.append({
                    'offerID': offer_id,
                    'title': title,
                    'type': 'SEATS_UNAVAILABLE',
                    'reason': f'Requires {group_size} adjacent seats/places, but only {len(free_resources)} available.'
                })
                continue

            # Calculate end time based on runtime
            meta = offer.get('meta') or {}
            runtime_min = meta.get('runtime_min', 120)
            start_min_of_day = sched_dt.hour * 60 + sched_dt.minute
            end_min_of_day = start_min_of_day + runtime_min
            end_hr = (end_min_of_day // 60) % 24
            end_min = end_min_of_day % 60
            offer_finish_hhmm = f'{end_hr:02d}:{end_min:02d}'

            # Evaluate each member's constraints
            disqualified = False
            for member in member_constraints:
                alias = member.get('alias', 'Member')
                budget = member.get('budget_cents')
                days = member.get('preferred_days', [])
                time_win = member.get('time_window', {})

                # Budget check
                if budget is not None and share_cents > budget:
                    conflicts.append({
                        'offerID': offer_id,
                        'title': title,
                        'type': 'BUDGET_EXCEEDED',
                        'member': alias,
                        'memberBudget': budget,
                        'shareCost': share_cents,
                        'reason': f"{alias}'s budget is ${budget/100:.2f}, but share is ${share_cents/100:.2f}."
                    })
                    disqualified = True
                    break

                # Day check
                if days and offer_day not in days:
                    conflicts.append({
                        'offerID': offer_id,
                        'title': title,
                        'type': 'SCHEDULE_DAY_MISMATCH',
                        'member': alias,
                        'reason': f"{alias} requested {', '.join(days)}, but screening is on {offer_day.capitalize()}."
                    })
                    disqualified = True
                    break

                # Time window: earliest
                if time_win.get('earliest') and offer_time_hhmm < time_win['earliest']:
                    conflicts.append({
                        'offerID': offer_id,
                        'title': title,
                        'type': 'SCHEDULE_TIME_EARLY',
                        'member': alias,
                        'reason': f"{alias} requested starting after {time_win['earliest']}, but start is {offer_time_hhmm}."
                    })
                    disqualified = True
                    break

                # Time window: latest
                if time_win.get('latest') and offer_time_hhmm > time_win['latest']:
                    conflicts.append({
                        'offerID': offer_id,
                        'title': title,
                        'type': 'SCHEDULE_TIME_LATE',
                        'member': alias,
                        'reason': f"{alias} needs to start earlier than {time_win['latest']}, but start is {offer_time_hhmm}."
                    })
                    disqualified = True
                    break

                # Finish before
                if time_win.get('finish_before'):
                    fb_parts = [int(p) for p in time_win['finish_before'].split(':')]
                    fb_limit_min = fb_parts[0] * 60 + fb_parts[1]
                    if end_min_of_day > fb_limit_min:
                        conflicts.append({
                            'offerID': offer_id,
                            'title': title,
                            'type': 'SCHEDULE_FINISH_LATE',
                            'member': alias,
                            'reason': f"{alias} needs to finish before {time_win['finish_before']}, but '{title}' ends at {offer_finish_hhmm}."
                        })
                        disqualified = True
                        break

            if not disqualified:
                matches.append(offer)

        return {'matches': matches, 'conflicts': conflicts}


class GroupPlanExplainer:
    def explain(self, matches, conflicts, member_constraints):
        """Generates a truthful, transparent explanation for group agreement."""
        n_members = len(member_constraints)

        if matches:
            best = matches[0]
            price_val = best['value']
            title = best['title']
            sched = best['scheduleTime']
            dt = datetime.fromisoformat(sched.replace('Z', '+00:00'))
            formatted_time = dt.strftime('%A at %H:%M UTC')

            explanation = (
                f"We found {len(matches)} suitable option{'s' if len(matches) > 1 else ''}! "
                f"Top recommendation: '{title}' on {formatted_time}. "
                f"Each participant pays ${price_val} USD, which satisfies all confirmed member budgets "
                f"and has {len([r for r in best['resources'] if r['state'] == 'FREE'])} available seats."
            )
            return explanation

        # Handle Conflicts transparently
        budget_conflicts = [c for c in conflicts if c['type'] == 'BUDGET_EXCEEDED']
        sched_conflicts = [c for c in conflicts if c['type'] in ('SCHEDULE_DAY_MISMATCH', 'SCHEDULE_TIME_LATE', 'SCHEDULE_TIME_EARLY', 'SCHEDULE_FINISH_LATE')]
        seat_conflicts = [c for c in conflicts if c['type'] == 'SEATS_UNAVAILABLE']

        if seat_conflicts:
            c = seat_conflicts[0]
            return f"Adjacent capacity conflict: {c['reason']} Please select a screening with more adjacent openings."

        if budget_conflicts:
            c = budget_conflicts[0]
            explanation = (
                f"No option currently fits all constraints. {c['reason']} "
                f"Consider adjusting your budget ceiling or choosing a matinee screening."
            )
            return explanation

        if sched_conflicts:
            c = sched_conflicts[0]
            explanation = (
                f"Schedule conflict detected: {c['reason']} "
                f"Try widening your available days or time window."
            )
            return explanation

        return "No offerings matched the group's current constraints. Please relax timing or budget limits."
