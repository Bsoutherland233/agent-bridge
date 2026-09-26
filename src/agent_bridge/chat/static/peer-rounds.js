'use strict';
// No model output is interpreted as HTML or as a command.
const token = sessionStorage.getItem('room-token') || '';
function element(tag, text) { const e = document.createElement(tag); e.textContent = text; return e; }
async function request(path, body) {
  const response = await fetch(path, {method: body === undefined ? 'GET' : 'POST', headers: {'Authorization': 'Bearer '+token, 'Content-Type': 'application/json'}, body: body === undefined ? undefined : JSON.stringify(body)});
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || 'Request failed');
  return data;
}
async function refresh() {
  const host = document.getElementById('rounds');
  try {
    const rounds = await request('/api/peer-approvals');
    host.replaceChildren();
    document.getElementById('error').textContent = '';
    if (!rounds.length) host.append(element('p', 'No pending rounds. Ask your agent to prepare one.'));
    for (const round of rounds) {
      const card = element('article', '');
      card.append(element('h2', round.caller+' → '+round.selection.targets.join(', ')), element('p', 'Round '+round.round_id+' · '+round.selection.source_classification), element('h3', 'Question'), element('pre', round.selection.question), element('h3', 'Selected context'), element('pre', round.selection.context || '(none)'));
      for (const approve of [true, false]) {
        const button = element('button', approve ? 'Approve this round and send' : 'Reject');
        button.onclick = async () => {
          button.disabled = true;
          try { await request('/api/peer-approvals/'+round.round_id, {approve}); await refresh(); }
          catch (e) { document.getElementById('error').textContent = e.message; button.disabled = false; }
        };
        card.append(button);
      }
      host.append(card);
    }
  } catch (e) { document.getElementById('error').textContent = e.message; }
}
document.getElementById('refresh').onclick = refresh;
refresh();
