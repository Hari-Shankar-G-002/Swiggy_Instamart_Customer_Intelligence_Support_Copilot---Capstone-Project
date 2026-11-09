(() => {
  const form = document.getElementById('policyForm');
  const question = document.getElementById('policyQuestion');
  const messages = document.getElementById('chatMessages');
  function appendMessage(type, text, sources = []) {
    const wrap = document.createElement('div'); wrap.className = `chat-message ${type}`;
    const label = document.createElement('div'); label.className = 'bubble-label'; label.textContent = type === 'user' ? 'YOU' : 'POLICY COPILOT';
    const bubble = document.createElement('div'); bubble.className = 'bubble'; bubble.textContent = text;
    wrap.append(label, bubble);
    if (sources.length) {
      const chips = document.createElement('div'); chips.className = 'source-chips';
      sources.forEach(source => { const chip = document.createElement('span'); chip.className = 'source-chip'; chip.textContent = source; chips.append(chip); });
      wrap.append(chips);
    }
    messages.append(wrap); messages.scrollTop = messages.scrollHeight;
  }
  async function ask(value) {
    const q = value.trim(); if (!q) return;
    appendMessage('user', q); question.value = '';
    const button = form.querySelector('button'); button.disabled = true; button.textContent = 'Retrieving…';
    try {
      const result = await API.post('/api/policy/answer', { question: q });
      appendMessage('assistant', result.answer || 'No answer returned.', result.sources || []);
    } catch (error) { appendMessage('assistant', `I could not reach the policy service: ${error.message}`); }
    finally { button.disabled = false; button.innerHTML = 'Ask question <span>↗</span>'; }
  }
  form.addEventListener('submit', e => { e.preventDefault(); ask(question.value); });
  document.getElementById('clearChat').addEventListener('click', () => {
    messages.innerHTML = '<div class="chat-message assistant"><div class="bubble-label">POLICY COPILOT</div><div class="bubble">Conversation cleared. Ask a policy question to begin.</div></div>';
  });
  document.querySelectorAll('.sample-question').forEach(button => button.addEventListener('click', () => ask(button.textContent)));
})();
