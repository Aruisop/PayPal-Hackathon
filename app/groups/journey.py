"""Read-only guidance derived from saved coordination, never payment authority."""


def journey(phase, *, member_count, confirmed_count, own_confirmed, organizer):
    steps = ['gather', 'preferences', 'compare', 'payment', 'ticket']
    if phase == 'confirmed':
        stage, title, action, label = 'ticket', 'Your group plan is complete.', 'ticket', 'See my ticket'
        detail = 'Every required capture is verified. Open your own private demonstration ticket.'
    elif phase in ('awaiting_authorizations', 'finalizing', 'recovery_required', 'cancelling'):
        stage, title, action, label = 'payment', 'Your share. Your decision.', 'payment', 'Review my payment status'
        detail = ('A payment outcome needs review. Keep the saved reservation while recovery is unresolved.'
                  if phase in ('recovery_required', 'cancelling') else
                  'Review your own saved share below. Tickets stay locked until every required capture is verified.')
    elif member_count < 2:
        stage, title, action, label = 'gather', 'A good plan starts with your people.', 'invite', 'Invite a friend'
        detail = 'Share one invite. Each person joins with a separate browser profile and confirms their own preferences.'
    elif not own_confirmed:
        stage, title, action, label = 'preferences', 'Start with what works for you.', 'preferences', 'Set my preferences'
        detail = 'Review your budget, availability and likes privately. Nothing is confirmed on your behalf.'
    elif confirmed_count < member_count:
        stage, title, action, label = 'preferences', 'Your part is ready. Give everyone a say.', 'compare', 'See group readiness'
        detail = f'{confirmed_count} of {member_count} people have confirmed. Compare plans after everyone confirms.'
    else:
        stage, title, action, label = 'compare', 'Find your common ground.', 'compare', 'Compare our plans'
        detail = ('Compare eligible experiences, then review places and exact shares.' if organizer else
                  'Compare eligible experiences together. Your organizer reviews places and exact shares.')
    index = steps.index(stage)
    return dict(stage=stage, title=title, detail=detail, action=action, actionLabel=label,
                ownConfirmed=own_confirmed,
                steps=[dict(id=step, status='complete' if i < index else 'current' if i == index else 'upcoming')
                       for i, step in enumerate(steps)])
