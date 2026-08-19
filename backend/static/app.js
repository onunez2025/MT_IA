/* ═══════════════════════════════════════════════════════════════
   SOLE AI — chat frontend  v4
   Arquitectura agéntica: las respuestas son texto libre generado
   por el LLM (markdown básico), no plantillas fijas.
   ═══════════════════════════════════════════════════════════════ */

const API_URL       = '/api/chat';
const chatContainer = document.getElementById('chatContainer');
const chatForm      = document.getElementById('chatForm');
const questionInput = document.getElementById('questionInput');
const sendBtn       = document.getElementById('sendBtn');
const roleSelect    = document.getElementById('roleSelect');

// ── Helpers ──────────────────────────────────────────────────────

function scrollBottom() {
    chatContainer.scrollTop = chatContainer.scrollHeight;
}

function escHtml(str) {
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}

/**
 * Convierte texto con markdown básico a HTML seguro.
 * Soporta: **bold**, *italic*, listas (-, *, •), listas numeradas,
 * líneas horizontales (---), párrafos y saltos de línea.
 */
function formatResponse(text) {
    if (!text) return '';

    const lines = text.split('\n');
    const html  = [];
    let inUl = false;
    let inOl = false;

    const closeList = () => {
        if (inUl) { html.push('</ul>'); inUl = false; }
        if (inOl) { html.push('</ol>'); inOl = false; }
    };

    /** Aplica inline markdown (bold, italic, código) a una línea ya escapada. */
    const inlineMarkdown = (raw) => {
        let s = escHtml(raw);
        // **bold** o __bold__
        s = s.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
        s = s.replace(/__(.+?)__/g, '<strong>$1</strong>');
        // *italic* o _italic_  (cuidado con guiones de listas)
        s = s.replace(/(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)/g, '<em>$1</em>');
        // `código`
        s = s.replace(/`(.+?)`/g, '<code>$1</code>');
        return s;
    };

    for (let i = 0; i < lines.length; i++) {
        const raw  = lines[i];
        const line = raw.trimEnd();

        // Línea vacía → cierra listas, agrega separador
        if (!line.trim()) {
            closeList();
            // No agregar <br> redundantes entre bloques
            if (html.length && html[html.length - 1] !== '<br>') {
                html.push('<br>');
            }
            continue;
        }

        // Regla horizontal (---, ___, ***)
        if (/^[-_*]{3,}$/.test(line.trim())) {
            closeList();
            html.push('<hr>');
            continue;
        }

        // Encabezados # ## ###
        const hMatch = line.match(/^(#{1,3})\s+(.+)/);
        if (hMatch) {
            closeList();
            const level = Math.min(hMatch[1].length + 3, 6); // h4..h6 para no dominar el estilo
            html.push(`<h${level} class="resp-h">${inlineMarkdown(hMatch[2])}</h${level}>`);
            continue;
        }

        // Lista desordenada (-, *, •)
        const ulMatch = line.match(/^[\s]*[-*•]\s+(.+)/);
        if (ulMatch) {
            if (inOl) { html.push('</ol>'); inOl = false; }
            if (!inUl) { html.push('<ul class="resp-list">'); inUl = true; }
            html.push(`<li>${inlineMarkdown(ulMatch[1])}</li>`);
            continue;
        }

        // Lista ordenada (1. 2. 3.)
        const olMatch = line.match(/^[\s]*(\d+)\.\s+(.+)/);
        if (olMatch) {
            if (inUl) { html.push('</ul>'); inUl = false; }
            if (!inOl) { html.push('<ol class="resp-list">'); inOl = true; }
            html.push(`<li>${inlineMarkdown(olMatch[2])}</li>`);
            continue;
        }

        // Párrafo normal
        closeList();
        html.push(`<p>${inlineMarkdown(line)}</p>`);
    }

    closeList();

    // Limpiar <br> redundantes al inicio/final
    while (html.length && html[0] === '<br>') html.shift();
    while (html.length && html[html.length - 1] === '<br>') html.pop();

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

function appendAiMessage(text, sources = []) {
    const el = document.createElement('div');
    el.className = 'message ai-message';

    // Hora en Lima (UTC-5)
    const localTime = new Date().toLocaleTimeString('es-PE', {
        hour: '2-digit',
        minute: '2-digit',
        timeZone: 'America/Lima',
    });

    // Badges: herramientas usadas + timestamp
    let badges = '';
    if (sources && sources.length > 0) {
        const unique = [...new Set(sources.map(s => s.tool))];
        badges = unique.map(t =>
            `<span class="source-badge">📊 ${escHtml(t)}</span>`
        ).join(' ');
        badges += `<span class="source-badge time-badge">🕐 ${localTime}</span>`;
    } else {
        // Mensajes sin herramientas (saludos, out-of-scope): mostrar solo hora
        badges = `<span class="source-badge time-badge">🕐 ${localTime}</span>`;
    }

    el.innerHTML = `
        <div class="avatar">🤖</div>
        <div class="bubble">
            ${formatResponse(text)}
            <div class="badges">${badges}</div>
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

// ── Submit handler ────────────────────────────────────────────────

chatForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const question = questionInput.value.trim();
    if (!question) return;

    questionInput.value = '';
    questionInput.disabled = true;
    sendBtn.disabled = true;

    appendUserMessage(question);
    showTyping();

    try {
        const data = await sendQuestion(question);
        hideTyping();

        if (data.status === 'success') {
            appendAiMessage(data.response, data.sources);
        } else if (data.status === 'blocked') {
            appendErrorMessage('🔒 No tienes permiso para acceder a esta información.');
        } else if (data.response) {
            // Error con mensaje amigable → mostrar como burbuja normal
            appendAiMessage(data.response, []);
        } else {
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

// Enter envía, Shift+Enter no hace nada (input de una línea)
questionInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        chatForm.dispatchEvent(new Event('submit'));
    }
});
