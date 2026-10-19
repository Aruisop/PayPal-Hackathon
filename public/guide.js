'use strict';
(function (root) {
  const steps = [
    {icon: '◌', eyebrow: '01 / YOUR PEOPLE', title: 'Start with a small group.', description: 'Create a room and copy its invite. Each friend opens it in a different browser profile or device. Ordinary tabs share one identity.', context: 'Testing alone? The solo demo lab lets you explore three fictional participants without changing saved bookings.'},
    {icon: '✦', eyebrow: '02 / FIND THE COMMON GROUND', title: 'Everyone gets a say.', description: 'Describe your budget and timing in your private planning space. Review the extracted fields and confirm. Shared group chat is a separate conversation.', context: 'Stuck on a conflict? Plan Rescue checks what a small change to your own preferences could unlock. You review every proposed edit.'},
    {icon: '◎', eyebrow: '03 / YOUR SHARE, YOUR CHOICE', title: 'A reservation is not a charge.', description: 'Your organizer reviews exact shares and holds places for 15 minutes. Each person then checks consent and approves their own hold in PayPal. No friend pays for the whole group.', context: 'Authorization holds funds. The organizer completes sequential capture only after every required authorization is verified. Unknown outcomes stay locked for recheck.'},
    {icon: '✓', eyebrow: '04 / READY FOR YOUR NEXT STORY', title: 'Your ticket is yours.', description: 'When every required capture is verified as completed, your private ticket appears. Save it, print it, or verify its owned record. Reloading keeps your booking.', context: 'This is a Sandbox prototype with fictional suppliers. Demo tickets are not real venue admission or Apple/Google Wallet passes.'},
  ];
  let index = 0, opener = null;
  const $ = (id) => document.getElementById(id);
  function render() {
    const step = steps[index];
    for (const [id, text] of Object.entries({'guide-title': step.title, 'guide-description': step.description, 'guide-eyebrow': step.eyebrow, 'guide-context': step.context, 'guide-visual': step.icon, 'guide-number': `0${index + 1} / 04`})) $(id).textContent = text;
    $('guide-prev').disabled = index === 0;
    $('guide-next').textContent = index === 3 ? 'Got it, let’s go ↗' : 'Next →';
    $('guide-dots').replaceChildren(...steps.map((_, i) => {
      const button = document.createElement('button'); button.type = 'button'; button.className = i === index ? 'active' : '';
      button.setAttribute('aria-label', `Walkthrough step ${i + 1}`); button.setAttribute('aria-pressed', String(i === index));
      button.addEventListener('click', () => { index = i; render(); }); return button;
    }));
  }
  function show(step = 0) { opener = document.activeElement; index = Math.max(0, Math.min(3, step)); render(); $('guide-modal').hidden = false; $('guide-close').focus(); }
  function close() { $('guide-modal').hidden = true; opener?.focus(); }
  document.addEventListener('DOMContentLoaded', () => {
    for (const id of ['show-guide-btn', 'rail-guide']) $(id).addEventListener('click', () => show());
    $('guide-prev').addEventListener('click', () => { index = Math.max(0, index - 1); render(); });
    $('guide-next').addEventListener('click', () => { if (index === 3) close(); else { index++; render(); } });
    $('guide-close').addEventListener('click', close);
  });
  root.GroupPayGuide = {show};
})(window);
