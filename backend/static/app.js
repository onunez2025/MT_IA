/* ═══════════════════════════════════════════════════════════════
   SOLE AI — chat frontend
   ═══════════════════════════════════════════════════════════════ */

const API_URL       = '/api/chat';
const chatContainer = document.getElementById('chatContainer');
const chatForm      = document.getElementById('chatForm');
const questionInput = document.getElementById('questionInput');
const sendBtn       = document.getElementById('sendBtn');
const roleSelect    = document.getElementById('roleSelect');

// ── Helpers ──────────────────────────────────────────────────────

/** Scroll chat to bottom */
function scrollBottom() {
    chatContainer.scrollTop = chatContainer.scrollHeight;
}

/** Format timestamp as HH:MM */
function fmtTime(iso) {
    const d = iso ? new Date(iso) : new Date();
    return d.toLocaleTimeString('es-PE', { hour: '2-digit', minute: '2-digit' });
}

/** Escape HTML to prevent XSS */
function escHtml(str) {
    return str
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}

/** Convert plain text with newlines to HTML paragraphs/lists */
function formatResponse(text) {
    // Preserve bullet points (lines starting with •  -  *)
    const lines = escHtml(text).split('\n');
    const html = [];
    let inList = false;

    for (const raw of lines) {
        const line = raw.trim();
        if (!line) {
            if (inList) { html.push('</ul>'); inList = false; }
            continue;
        }
        const isBullet = /^[•\-\*]\s+/.test(line);
        if (isBullet) {
            if (!inList) { html.push('<ul class="resp-list">'); inList = true; }
            html.push(`<li>${line.replace(/^[•\-\*]\s+/, '')}</li>`);
        } else {
            if (inList) { html.push('</ul>'); inList = false; }
            html.push(`<p>${line}</p>`);
        }
    }
    if (inList) html.push('</ul>');
    return html.join('');
}

// ── Message rendering ─────────────────────────────────────────────

function appendUserMessage(text) {
    const el = document.createElement('div');
    el.className = 'message user-message';
    el.innerHTML = `
        <div class="avatar">👤</div>
        <div class="bubble">${escHtml(text)}</div>
    `;
    chatContainer.appendChild(el);
    scrollBottom();
}

function appendAiMessage(text, sources = [], timestamp = null) {
    const el = document.createElement('div');
    el.className = 'message ai-message';

    // Hora en zona horaria de Lima (UTC-5) — forzada para que no dependa de la config del equipo
    const localTime = new Date().toLocaleTimeString('es-PE', {
        hour: '2-digit',
        minute: '2-digit',
        timeZone: 'America/Lima',
    });

    // Build source badges
    let badges = '';
    if (sources && sources.length > 0) {
        const unique = [...new Set(sources.map(s => s.tool))];
        badges = unique.map(tool =>
            `<span class="source-badge">📊 ${escHtml(tool)}</span>`
        ).join(' ');
        badges += `<span class="source-badge" style="color:#6b7280;border-color:#dde1e7;background:#f9fafb">🕐 ${localTime}</span>`;
    }

    el.innerHTML = `
        <div class="avatar">🤖</div>
        <div class="bubble">
            ${formatResponse(text)}
            ${badges ? `<div class="badges">${badges}</div>` : ''}
        </div>
    `;
    chatContainer.appendChild(el);
    scrollBottom();
}

function appendErrorMessage(msg) {
    const el = document.createElement('div');
    el.className = 'message ai-message';
    el.innerHTML = `
        <div class="avatar">🤖</div>
        <div class="bubble error-bubble">
            <p>⚠️ ${escHtml(msg)}</p>
        </div>
    `;
    chatContainer.appendChild(el);
    scrollBottom();
}

// ── Typing indicator ──────────────────────────────────────────────

let typingEl = null;

function showTyping() {
    typingEl = document.createElement('div');
    typingEl.className = 'message ai-message';
    typingEl.id = 'typing';
    typingEl.innerHTML = `
        <div class="avatar">🤖</div>
        <div class="bubble typing-bubble">
            <span class="dot"></span>
            <span class="dot"></span>
            <span class="dot"></span>
        </div>
    `;
    chatContainer.appendChild(typingEl);
    scrollBottom();
}

function hideTyping() {
    if (typingEl) { typingEl.remove(); typingEl = null; }
}

// ── API call ──────────────────────────────────────────────────────

async function sendQuestion(question) {
    const role = roleSelect.value;

    const res = await fetch(API_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            question,
            user_id: 'web-user',
            roles: [role],
        }),
    });

    if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `Error ${res.status}`);
    }

    return res.json();
}

// ── Main submit handler ───────────────────────────────────────────

chatForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const question = questionInput.value.trim();
    if (!question) return;

    // Lock UI
    questionInput.value = '';
    questionInput.disabled = true;
    sendBtn.disabled = true;

    appendUserMessage(question);
    showTyping();

    try {
        const data = await sendQuestion(question);

        hideTyping();

        if (data.status === 'success') {
            // Respuesta normal con datos
            appendAiMessage(data.response, data.sources);
        } else if (data.status === 'blocked') {
            // RBAC: el usuario no tiene permiso
            appendErrorMessage('🔒 No tienes permiso para acceder a esta información.');
        } else if (data.response) {
            // Error con mensaje amigable (ej: "no entendí tu pregunta")
            // → mostrar como mensaje AI normal, sin burbuja roja
            appendAiMessage(data.response, []);
        } else {
            // Error técnico sin mensaje amigable
            appendErrorMessage(data.error_message || 'No pude procesar tu pregunta. Inténtalo de otra forma.');
        }
    } catch (err) {
        hideTyping();
        appendErrorMessage(
            err.message.includes('Failed to fetch')
                ? 'Sin conexión al servidor. Verifica tu red.'
                : err.message
        );
    } finally {
        questionInput.disabled = false;
        sendBtn.disabled = false;
        questionInput.focus();
    }
});

// Enter sends, Shift+Enter newline (no-op aquí pues es input de una línea)
questionInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        chatForm.dispatchEvent(new Event('submit'));
    }
});
