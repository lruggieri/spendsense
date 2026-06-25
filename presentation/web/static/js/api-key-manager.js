/* MCP API key management page */
(function () {
  'use strict';

  function buildKeyCard(k) {
    const card = document.createElement('div');
    card.className = 'card';
    card.style.marginBottom = '.5rem';

    const title = document.createElement('strong');
    title.textContent = k.label || '(no label)';
    card.appendChild(title);

    if (k.revoked) {
      const em = document.createElement('em');
      em.textContent = ' (revoked)';
      card.appendChild(em);
    }

    const meta = document.createElement('p');
    meta.style.margin = '0.25rem 0';
    meta.textContent = `ID: ${k.id}`;
    card.appendChild(meta);

    const meta2 = document.createElement('p');
    meta2.style.margin = '0.25rem 0';
    meta2.textContent = `Scope: ${k.scope}  |  Created: ${k.created_at || ''}`;
    card.appendChild(meta2);

    if (!k.revoked) {
      const btn = document.createElement('button');
      btn.className = 'btn btn-secondary btn-sm';
      btn.style.marginTop = '.5rem';
      btn.textContent = 'Revoke';
      btn.addEventListener('click', () => revokeKey(k.id));
      card.appendChild(btn);
    }

    return card;
  }

  async function loadKeys() {
    const container = document.getElementById('keys-list');
    try {
      const resp = await fetch('/api/mcp-keys');
      const data = await resp.json();
      container.textContent = '';
      if (!data.keys || data.keys.length === 0) {
        container.textContent = 'No keys yet.';
        return;
      }
      data.keys.forEach((k) => container.appendChild(buildKeyCard(k)));
    } catch (_err) {
      container.textContent = 'Failed to load keys.';
    }
  }

  async function revokeKey(keyId) {
    if (!confirm('Revoke this key? It cannot be undone.')) return;
    const resp = await fetch('/api/mcp-keys/revoke', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ key_id: keyId }),
    });
    if (resp.ok) {
      loadKeys();
    } else {
      alert('Failed to revoke key.');
    }
  }

  document.getElementById('btn-create').addEventListener('click', async () => {
    const label = document.getElementById('key-label').value.trim();
    const scope = document.getElementById('key-scope').value;
    if (!label) { alert('Label is required.'); return; }

    const resp = await fetch('/api/mcp-keys/create', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ label, scope }),
    });
    const data = await resp.json();
    if (!resp.ok) {
      alert(data.error || 'Failed to create key.');
      return;
    }
    const box = document.getElementById('new-key-box');
    document.getElementById('new-key-value').textContent = data.key;
    box.style.display = '';
    loadKeys();
  });

  document.getElementById('btn-copy').addEventListener('click', () => {
    const val = document.getElementById('new-key-value').textContent;
    navigator.clipboard.writeText(val).then(() => {
      document.getElementById('btn-copy').textContent = 'Copied!';
    });
  });

  loadKeys();
})();
