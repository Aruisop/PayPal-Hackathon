"""Context-aware assistant: retrieved facts first, decisions always user-owned."""
import hashlib
import json
import re
from datetime import datetime, timezone

from sqlalchemy import select

from app.planning.interpreter import AIError, DeterministicCatalogMatcher, validate_constraints
from app.planning.service import Planning
from app.shared.storage import (group_member_preferences, group_member_profiles, group_memberships,
                                purchase_contributions, room_messages, shared_purchases, workshop_groups)


WORDS = re.compile(r"[a-z0-9]+")

# Example utterances per intent. They are embedded once with the same local model as the user's question,
# so routing follows meaning rather than keywords. A weak match falls back to the general answer.
INTENT_EXAMPLES = {
    'payment': ('What is the status of our payment and authorization?', 'Has my share been paid and will I be charged?',
                'Is there any risk with the payment, a refund or a cancellation?'),
    'roster': ('Who is in the group and has everyone joined?', 'How do I invite more friends to this room?'),
    'comparison': ('Which movies or outings fit everyone in the group?', 'Compare and recommend plans for us.'),
    'blockers': ('Why are we blocked or stuck?', 'What conflicts are stopping us from booking?'),
    'preferences': ('What are my confirmed budget, days and times?', 'Have I confirmed my preferences yet?'),
    'next': ('What is our next best step?', 'What should we do now?'),
    'greeting': ('Hi', 'Hello there', 'Hey, good morning', 'Thanks, that helps'),
}
INTENT_THRESHOLD = 0.62


def _tokens(text):
    return set(WORDS.findall(str(text).lower()))


GREETING_WORDS = {'hi', 'hii', 'hiii', 'hello', 'hey', 'heyy', 'yo', 'thanks', 'thank', 'you', 'ok', 'okay', 'good',
                  'morning', 'evening', 'afternoon', 'there', 'cool', 'great'}


def _dot(left, right):
    return sum(a * b for a, b in zip(left, right))


class ContextualAssistant:
    """Small, deterministic assistant with contextual retrieval and explicit guardrails."""

    MODE = 'contextual_rag_agent_v1'

    def __init__(self, store, origin, encoder=None):
        self.store = store
        self.origin = origin.rstrip('/')
        self.planning = Planning(store)
        self.encoder = encoder
        self._intent_vectors = None

    def _semantic(self, prompt, chunks, limit=8):
        """Rank room facts and route the question by meaning with the local encoder.

        Runs after the database connection is closed. Returns None when the local model is unavailable so the
        caller can label the keyword fallback honestly.
        """
        if self.encoder is None:
            return None
        try:
            documents = getattr(self.encoder, 'encode_documents', self.encoder.encode)
            if self._intent_vectors is None:
                labels = [(name, text) for name, texts in INTENT_EXAMPLES.items() for text in texts]
                vectors = documents([text for _, text in labels])
                self._intent_vectors = [(name, vector) for (name, _), vector in zip(labels, vectors)]
            texts = [chunk['text'][:600] for chunk in chunks]
            vectors = documents(texts)
            query = self.encoder.encode([prompt.strip()])[0]
        except Exception:
            return None
        best_intent, best_score = 'general', -1.0
        for name, vector in self._intent_vectors:
            score = _dot(query, vector)
            if score > best_score:
                best_intent, best_score = name, score
        scored = sorted(((_dot(query, vector) + chunk['weight'] * 0.02, chunk['id'], chunk)
                         for chunk, vector in zip(chunks, vectors)), key=lambda item: (item[0], item[1]), reverse=True)
        return dict(
            intent=best_intent if best_score >= INTENT_THRESHOLD else 'general',
            intentScore=round(best_score, 4),
            chunks=[item[2] for item in scored[:max(1, limit)]],
            model=getattr(self.encoder, 'profile', {}).get('repository'),
        )

    def _snapshot(self, participant_id, group_id):
        with self.store.engine.connect() as connection:
            self.planning._member(connection, participant_id, group_id)
            group = connection.execute(select(workshop_groups).where(
                workshop_groups.c.id == group_id)).mappings().first()
            members = connection.execute(select(group_memberships.c.participant_id).where(
                group_memberships.c.group_id == group_id).order_by(
                group_memberships.c.joined_at, group_memberships.c.id)).scalars().all()
            profiles = {row['participant_id']: row for row in connection.execute(select(group_member_profiles).where(
                group_member_profiles.c.group_id == group_id)).mappings()}
            aliases = {}
            for index, pid in enumerate(members):
                profile = profiles.get(pid)
                aliases[pid] = (profile['alias'] if profile and (pid == participant_id or profile['consent_coarse_progress'])
                                else f'Member {index + 1}')
            prefs = {row['participant_id']: row for row in connection.execute(select(group_member_preferences).where(
                group_member_preferences.c.group_id == group_id)).mappings()}
            own_pref = prefs.get(participant_id)
            confirmed_count = sum(1 for pid in members if pid in prefs and prefs[pid]['is_confirmed'] and prefs[pid]['confirmed_constraints_json'])
            messages = list(reversed(connection.execute(select(room_messages).where(
                room_messages.c.group_id == group_id).order_by(
                room_messages.c.created_at.desc(), room_messages.c.id.desc()).limit(40)).mappings().all()))
            purchase = connection.execute(select(shared_purchases).where(
                shared_purchases.c.group_id == group_id).order_by(
                shared_purchases.c.created_at.desc(), shared_purchases.c.id.desc()).limit(1)).mappings().first()
            my_contribution = connection.execute(select(purchase_contributions).where(
                purchase_contributions.c.purchase_id == purchase['id'],
                purchase_contributions.c.participant_id == participant_id)).mappings().first() if purchase else None
            all_offers = self.planning._offers(connection)

        domains = ('movie', 'excursion')
        plan_by_domain = {}
        all_confirmed = confirmed_count == len(members)
        if all_confirmed:
            constraints = [validate_constraints(json.loads(prefs[pid]['confirmed_constraints_json'])) for pid in members]
            matcher = DeterministicCatalogMatcher()
            own_index = members.index(participant_id)
            for domain in domains:
                domain_offers = [offer for offer in all_offers if offer['domain'] == domain]
                plan_by_domain[domain] = matcher.match(constraints, domain_offers, len(members), own_index=own_index)

        return dict(
            capturedAt=datetime.now(timezone.utc).isoformat(),
            groupID=group_id,
            groupName=group['name'],
            organizerID=group['organizer_id'],
            inviteURL=f"{self.origin}/?invite={group['invite_token']}" if group['organizer_id'] == participant_id else None,
            memberCount=len(members),
            confirmedCount=confirmed_count,
            allConfirmed=all_confirmed,
            aliases=aliases,
            ownAlias=aliases[participant_id],
            ownConfirmed=bool(own_pref and own_pref['is_confirmed'] and own_pref['confirmed_constraints_json']),
            ownConstraints=validate_constraints(json.loads(own_pref['confirmed_constraints_json']))
            if own_pref and own_pref['is_confirmed'] and own_pref['confirmed_constraints_json'] else None,
            messages=[dict(alias=aliases.get(row['participant_id'], 'Former member'), text=row['text'],
                           createdAt=row['created_at']) for row in messages],
            purchase=dict(state=purchase['state'], currency=purchase['currency'], holdDeadline=purchase['hold_deadline'])
            if purchase else None,
            myContribution=(dict(state=my_contribution['state'], shareCents=my_contribution['share_cents'],
                                 assignedResourceID=my_contribution['assigned_resource_id']) if my_contribution else None),
            planByDomain=plan_by_domain,
        )

    @staticmethod
    def _build_chunks(snapshot):
        chunks = [
            dict(id='guardrails', weight=4, text=(
                'The assistant cannot confirm preferences, reserve places, authorize or capture payments, '
                'issue tickets, change inventory, or change consent. It only explains current saved state and '
                'possible next user actions.'
            )),
            dict(id='group_state', weight=4, text=(
                f"Group has {snapshot['memberCount']} members, {snapshot['confirmedCount']} confirmed preferences, "
                f"all confirmed={snapshot['allConfirmed']}."
            )),
        ]
        if snapshot['ownConstraints']:
            own = snapshot['ownConstraints']
            chunks.append(dict(id='own_constraints', weight=4, text=(
                f"Your confirmed constraints: budget_cents={own['budget_cents']}, days={own['preferred_days']}, "
                f"dates={own['dates']}, timezone={own['timezone']}, time_window={own['time_window']}, "
                f"likes={own['soft_preferences']}."
            )))
        if snapshot['purchase']:
            purchase = snapshot['purchase']
            share = snapshot['myContribution']
            chunks.append(dict(id='payment_state', weight=4, text=(
                f"Saved booking state={purchase['state']}, hold_deadline={purchase['holdDeadline']}, "
                f"my_share_state={share['state'] if share else 'unknown'}, my_share_cents={share['shareCents'] if share else 'unknown'}."
            )))
        for domain, result in snapshot['planByDomain'].items():
            matches = result.get('matches', [])
            top = '; '.join(f"{offer['title']} ({offer['shareValues'][0]} USD first listed share)" for offer in matches[:3])
            chunks.append(dict(id=f'plan_{domain}', weight=3, text=(
                f"{domain} plan has {len(matches)} eligible options. Top options: {top or 'none'}."
            )))
            blocked = result.get('blockedOptions', [])
            if blocked:
                chunks.append(dict(id=f'blocked_{domain}', weight=3, text=(
                    f"{domain} blocked options count={len(blocked)}. "
                    f"First blocker own_conflicts={blocked[0].get('ownConflicts', [])} other_constraints_block={blocked[0].get('otherConstraintsBlock', False)}."
                )))
        for index, message in enumerate(snapshot['messages'][-20:], start=1):
            chunks.append(dict(id=f'message_{index}', weight=1,
                               text=f"{message['alias']} said: {message['text']}"))
        return chunks

    @staticmethod
    def _retrieve(query, chunks, limit=8):
        query_tokens = _tokens(query)
        scored = []
        for chunk in chunks:
            overlap = len(query_tokens.intersection(_tokens(chunk['text'])))
            score = overlap * 2 + chunk['weight']
            scored.append((score, chunk['id'], chunk))
        scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
        selected = [item[2] for item in scored[:max(1, limit)]]
        return selected

    @staticmethod
    def _intent(prompt):
        text = prompt.lower()
        if _tokens(text) and _tokens(text) <= GREETING_WORDS:
            return 'greeting'
        if any(key in text for key in ('pay', 'payment', 'authorize', 'capture', 'refund', 'cancel')):
            return 'payment'
        if any(key in text for key in ('invite', 'join', 'member', 'roster')):
            return 'roster'
        if any(key in text for key in ('compare', 'match', 'recommend', 'ai', 'suggest', 'option')):
            return 'comparison'
        if any(key in text for key in ('block', 'why not', 'cannot', 'stuck', 'conflict')):
            return 'blockers'
        if any(key in text for key in ('next', 'step', 'ready', 'what should', 'what now', 'do now')):
            return 'next'
        if any(key in text for key in ('preference', 'budget', 'time', 'day', 'date')):
            return 'preferences'
        return 'general'

    def _next_actions(self, snapshot, domain):
        actions = []
        if snapshot['memberCount'] < 2:
            actions.append('Invite another member so shared planning can run.')
        if not snapshot['ownConfirmed']:
            actions.append('Review and confirm your own preferences; drafts are not active constraints.')
        if snapshot['confirmedCount'] < snapshot['memberCount']:
            actions.append('Wait for each member to confirm their own preferences before comparing plans.')
        elif domain in snapshot['planByDomain'] and snapshot['planByDomain'][domain].get('matches'):
            actions.append('Organizer can review seats/places and request an exact server quote.')
        elif domain in snapshot['planByDomain']:
            actions.append('Use Plan Rescue to preview your own budget/time adjustments without changing others.')
        purchase = snapshot['purchase']
        if purchase and purchase['state'] == 'AWAITING_AUTHORIZATIONS':
            actions.append('Each member approves only their own share in PayPal before final capture.')
        elif purchase and purchase['state'] == 'FINALIZING':
            actions.append('Keep the reservation; organizer can complete the capture pass.')
        elif purchase and purchase['state'] == 'RECOVERY_REQUIRED':
            actions.append('Reconcile saved payment outcomes before any replacement action.')
        return actions[:4]

    @staticmethod
    def _decisions(snapshot, domain):
        decisions = [
            dict(key='consent_and_payment_authority',
                 status='locked',
                 explanation='Assistant does not have authority to consent, authorize, capture, cancel, or issue tickets.'),
            dict(key='preference_confirmation_gate',
                 status='met' if snapshot['allConfirmed'] else 'pending',
                 explanation='Group matching can only rely on confirmed preferences.'),
        ]
        if domain in snapshot['planByDomain']:
            matches = len(snapshot['planByDomain'][domain].get('matches', []))
            decisions.append(dict(key='domain_options', status='met' if matches else 'blocked',
                                  explanation=f'{matches} eligible option(s) currently satisfy confirmed constraints in {domain}.'))
        return decisions

    @staticmethod
    def _risks(snapshot):
        risks = []
        purchase = snapshot['purchase']
        if purchase and purchase['state'] == 'RECOVERY_REQUIRED':
            risks.append('Payment outcome unresolved: do not assume completion until recovery confirms final provider evidence.')
        if snapshot['confirmedCount'] < snapshot['memberCount']:
            risks.append('Not all members are confirmed yet: recommendation outcomes can change when remaining members confirm.')
        if not snapshot['messages']:
            risks.append('No shared chat history yet: context is limited to profile and planning state.')
        return risks

    def _answer(self, snapshot, domain, intent):
        purchase = snapshot['purchase']
        if intent == 'payment':
            if not purchase:
                return ('No group payment flow has started yet. The next safe step is to confirm preferences, '
                        'choose a verified option, and let the organizer request an exact quote and hold.')
            if purchase['state'] == 'AWAITING_AUTHORIZATIONS':
                return ('The booking is held and awaiting individual approvals. Each member should authorize only '
                        'their own share; capture happens only after all required authorizations are verified.')
            if purchase['state'] == 'FINALIZING':
                return 'Authorizations are in; organizer can complete capture. Keep the reservation unchanged until confirmed.'
            if purchase['state'] == 'RECOVERY_REQUIRED':
                return ('A payment outcome is unresolved. Reconcile saved provider evidence first; do not create a replacement '
                        'purchase or treat this as completed.')
            if purchase['state'] == 'CONFIRMED':
                return 'The purchase is confirmed; each member can view only their own ticket details.'
            return f"Current purchase state is {purchase['state']}. Follow the room next-action guidance for this state."

        if intent in ('comparison', 'blockers') and domain in snapshot['planByDomain']:
            plan = snapshot['planByDomain'][domain]
            matches = plan.get('matches', [])
            if matches:
                top = ', '.join(offer['title'] for offer in matches[:3])
                return f"I found {len(matches)} eligible {domain} option(s) right now. Top options: {top}."
            blocked = plan.get('blockedOptions', [])
            if blocked:
                return ('No eligible option is available yet for this domain. Use the blockers list and Plan Rescue to preview '
                        'changes to your own constraints only.')
            return 'No eligible options are available in this domain right now.'

        if intent == 'next':
            actions = self._next_actions(snapshot, domain)
            if actions:
                return f'Your most useful next step: {actions[0]}'
            return 'Nothing is blocking you right now. Review the eligible options in the comparison tab.'

        if intent == 'roster':
            if snapshot['memberCount'] < 2:
                return 'You currently need at least one more member. Share the invite link from the room to continue collaborative planning.'
            if snapshot['confirmedCount'] < snapshot['memberCount']:
                return (f"Your group has {snapshot['memberCount']} members; {snapshot['confirmedCount']} have confirmed preferences. "
                        'Each person confirms their own constraints privately.')
            return 'Roster and confirmations are ready for comparing plans.'

        if intent == 'preferences':
            if snapshot['ownConfirmed']:
                return 'Your preferences are confirmed. Any new edits remain draft-only until you confirm again.'
            return 'Your preferences are not confirmed yet. Review extracted fields and confirm to activate them for group comparison.'

        if intent == 'greeting':
            name = '' if snapshot['ownAlias'].startswith('Member ') else f" {snapshot['ownAlias']}"
            return (f"Hi{name}. \"{snapshot['groupName']}\" has {snapshot['memberCount']} member(s) and "
                    f"{snapshot['confirmedCount']} confirmed preferences. Ask me what to do next, what is blocking the plan, "
                    'or where payment stands.')

        return ('I can only answer questions about this room: next steps, blockers, preferences, members and payment state. '
                'I did not match your question to one of those, so try rephrasing it.')

    def chat(self, participant_id, group_id, prompt, domain='movie', objective='compromise', history=None):
        if domain not in ('movie', 'excursion'):
            raise AIError('INVALID_DOMAIN')
        if objective not in ('compare', 'compromise', 'average'):
            raise AIError('INVALID_RECOMMENDATION_OBJECTIVE')
        if not isinstance(prompt, str) or not prompt.strip() or len(prompt.strip()) > 1000:
            raise AIError('MESSAGE_TEXT_REQUIRED')
        if history is not None and (not isinstance(history, list) or len(history) > 24):
            raise AIError('INVALID_REQUEST')
        snapshot = self._snapshot(participant_id, group_id)
        chunks = self._build_chunks(snapshot)
        semantic = self._semantic(prompt, chunks)
        if semantic:
            intent, selected = semantic['intent'], semantic['chunks']
            retrieval = dict(mode='semantic_local_embeddings', model=semantic['model'],
                             intentScore=semantic['intentScore'], intent=intent)
        else:
            intent, selected = self._intent(prompt), self._retrieve(prompt, chunks)
            retrieval = dict(mode='keyword_fallback', model=None, intentScore=None, intent=intent)
        decisions = self._decisions(snapshot, domain)
        next_actions = self._next_actions(snapshot, domain)
        risks = self._risks(snapshot)
        answer = self._answer(snapshot, domain, intent)
        fingerprint = hashlib.sha256(json.dumps(dict(
            groupID=snapshot['groupID'],
            domain=domain,
            memberCount=snapshot['memberCount'],
            confirmedCount=snapshot['confirmedCount'],
            purchaseState=snapshot['purchase']['state'] if snapshot['purchase'] else None,
            ownConfirmed=snapshot['ownConfirmed'],
            chunkIDs=[chunk['id'] for chunk in selected],
        ), sort_keys=True, separators=(',', ':')).encode()).hexdigest()[:16]
        return dict(
            mode=self.MODE,
            domain=domain,
            objective=objective,
            answer=answer,
            decisions=decisions,
            nextActions=next_actions,
            riskFlags=risks,
            retrieval=retrieval,
            context=dict(
                capturedAt=snapshot['capturedAt'],
                chunkCount=len(selected),
                usedChunkIDs=[chunk['id'] for chunk in selected],
                snapshotHash=fingerprint,
            ),
        )