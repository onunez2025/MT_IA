document.addEventListener('DOMContentLoaded', () => {
  // Elementos DOM
  const sidebar = document.getElementById('sidebar');
  const openSidebarBtn = document.getElementById('openSidebarBtn');
  const closeSidebarBtn = document.getElementById('closeSidebarBtn');
  const sidebarOverlay = document.getElementById('sidebarOverlay');
  const newChatBtn = document.getElementById('newChatBtn');
  const chatList = document.getElementById('chatList');
  const clearHistoryBtn = document.getElementById('clearHistoryBtn');
  const modelSelect = document.getElementById('modelSelect');
  const activeModelName = document.getElementById('activeModelName');
  const welcomeContainer = document.getElementById('welcomeContainer');
  const chatFeed = document.getElementById('chatFeed');
  const messagesContainer = document.getElementById('messagesContainer');
  const promptInput = document.getElementById('promptInput');
  const sendBtn = document.getElementById('sendBtn');
  const stopBtn = document.getElementById('stopBtn');
  const statusText = document.getElementById('statusText');

  // Estado global de la app
  let chats = JSON.parse(localStorage.getItem('mt_ia_chats') || '[]');
  let currentChatId = null;
  let isGenerating = false;
  let abortController = null;

  // Inicializar Marked.js con Highlight.js
  if (window.marked) {
    marked.setOptions({
      highlight: function(code, lang) {
        const language = hljs.getLanguage(lang) ? lang : 'plaintext';
        return hljs.highlight(code, { language }).value;
      },
      breaks: true
    });
  }

  // 1. Cargar Modelos desde el Servidor
  async function loadModels() {
    try {
      const response = await fetch('/api/models');
      if (response.ok) {
        const data = await response.json();
        if (data.models && data.models.length > 0) {
          modelSelect.innerHTML = '';
          data.models.forEach(m => {
            const option = document.createElement('option');
            option.value = m.name;
            option.textContent = m.name;
            modelSelect.appendChild(option);
          });
          statusText.textContent = 'Servidor Ollama En Línea';
        }
      }
    } catch (err) {
      console.warn('Usando modelo por defecto llama3.5:3b:', err.message);
    }
  }

  // 2. Gestión de Chats e Historial
  function saveChats() {
    localStorage.setItem('mt_ia_chats', JSON.stringify(chats));
  }

  function createNewChat() {
    const newChat = {
      id: Date.now().toString(),
      title: 'Nuevo chat',
      messages: []
    };
    chats.unshift(newChat);
    saveChats();
    switchChat(newChat.id);
  }

  function switchChat(chatId) {
    currentChatId = chatId;
    const chat = chats.find(c => c.id === chatId);
    
    renderChatList();

    if (!chat || chat.messages.length === 0) {
      welcomeContainer.style.display = 'flex';
      chatFeed.style.display = 'none';
      messagesContainer.innerHTML = '';
    } else {
      welcomeContainer.style.display = 'none';
      chatFeed.style.display = 'block';
      renderMessages(chat.messages);
    }

    if (window.innerWidth <= 768) {
      closeSidebar();
    }
  }

  function deleteChat(chatId, e) {
    e.stopPropagation();
    chats = chats.filter(c => c.id !== chatId);
    saveChats();
    if (currentChatId === chatId) {
      if (chats.length > 0) {
        switchChat(chats[0].id);
      } else {
        createNewChat();
      }
    } else {
      renderChatList();
    }
  }

  function renderChatList() {
    chatList.innerHTML = '';
    chats.forEach(chat => {
      const item = document.createElement('div');
      item.className = `chat-item ${chat.id === currentChatId ? 'active' : ''}`;
      
      const titleSpan = document.createElement('span');
      titleSpan.className = 'chat-item-title';
      titleSpan.textContent = chat.title || 'Nuevo chat';

      const actionsDiv = document.createElement('div');
      actionsDiv.className = 'chat-item-actions';
      
      const delBtn = document.createElement('button');
      delBtn.className = 'icon-btn';
      delBtn.innerHTML = '<i class="fa-regular fa-trash-can"></i>';
      delBtn.title = 'Eliminar';
      delBtn.addEventListener('click', (e) => deleteChat(chat.id, e));

      actionsDiv.appendChild(delBtn);
      item.appendChild(titleSpan);
      item.appendChild(actionsDiv);

      item.addEventListener('click', () => switchChat(chat.id));
      chatList.appendChild(item);
    });
  }

  // 3. Renderizar Mensajes en la Pantalla
  function renderMessages(messages) {
    messagesContainer.innerHTML = '';
    messages.forEach(msg => {
      appendMessageUI(msg.role, msg.content);
    });
    scrollToBottom();
  }

  function appendMessageUI(role, content = '') {
    const row = document.createElement('div');
    row.className = `message-row ${role}`;

    const avatar = document.createElement('div');
    avatar.className = 'avatar';
    avatar.innerHTML = role === 'user' ? 'U' : '<i class="fa-solid fa-brain"></i>';

    const contentDiv = document.createElement('div');
    contentDiv.className = 'message-content';
    
    if (content) {
      contentDiv.innerHTML = formatMarkdown(content);
    }

    row.appendChild(avatar);
    row.appendChild(contentDiv);
    messagesContainer.appendChild(row);

    attachCodeCopyEvents(contentDiv);
    return contentDiv;
  }

  function formatMarkdown(text) {
    if (window.marked) {
      let rawHtml = marked.parse(text);
      // Añadir encabezado con botón de copiar a cada bloque de código
      return rawHtml.replace(/<pre><code class="([^"]*)">([\s\S]*?)<\/code><\/pre>/g, (match, lang, code) => {
        const languageName = lang.replace('language-', '') || 'código';
        return `
          <div class="code-block-wrapper">
            <div class="code-header">
              <span>${languageName}</span>
              <button class="copy-code-btn" onclick="copyCodeSnippet(this)">
                <i class="fa-regular fa-copy"></i> Copiar código
              </button>
            </div>
            <pre><code class="${lang}">${code}</code></pre>
          </div>
        `;
      });
    }
    return text;
  }

  function scrollToBottom() {
    chatFeed.scrollTop = chatFeed.scrollHeight;
  }

  // 4. Enviar Mensaje y Recibir Stream de Ollama
  async function sendMessage(promptText) {
    if (!promptText || isGenerating) return;

    if (!currentChatId) {
      createNewChat();
    }

    const currentChat = chats.find(c => c.id === currentChatId);
    if (!currentChat) return;

    // Si es el primer mensaje, asignar el título del chat
    if (currentChat.messages.length === 0) {
      currentChat.title = promptText.length > 30 ? promptText.substring(0, 30) + '...' : promptText;
    }

    // Agregar mensaje del usuario al estado
    currentChat.messages.push({ role: 'user', content: promptText });
    saveChats();
    renderChatList();

    // Actualizar UI
    welcomeContainer.style.display = 'none';
    chatFeed.style.display = 'block';
    appendMessageUI('user', promptText);

    // Preparar UI para la respuesta del asistente
    const assistantContentDiv = appendMessageUI('assistant', '');
    const cursor = document.createElement('span');
    cursor.className = 'cursor-blink';
    assistantContentDiv.appendChild(cursor);

    promptInput.value = '';
    adjustTextareaHeight();
    setGeneratingState(true);

    abortController = new AbortController();
    let assistantResponseText = '';

    try {
      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          model: modelSelect.value,
          messages: currentChat.messages
        }),
        signal: abortController.signal
      });

      if (!response.ok) {
        throw new Error(`Error en el servidor: ${response.statusText}`);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder('utf-8');

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const chunk = decoder.decode(value, { stream: true });
        const lines = chunk.split('\n').filter(l => l.trim() !== '');

        for (const line of lines) {
          try {
            const parsed = JSON.parse(line);
            if (parsed.message && parsed.message.content) {
              assistantResponseText += parsed.message.content;
              assistantContentDiv.innerHTML = formatMarkdown(assistantResponseText);
              assistantContentDiv.appendChild(cursor);
              attachCodeCopyEvents(assistantContentDiv);
              scrollToBottom();
            }
          } catch (e) {
            // Continuar si es un fragmento JSON parcial
          }
        }
      }

      cursor.remove();
      currentChat.messages.push({ role: 'assistant', content: assistantResponseText });
      saveChats();

    } catch (err) {
      cursor.remove();
      if (err.name === 'AbortError') {
        assistantContentDiv.innerHTML += '<p><em>[Respuesta detenida por el usuario]</em></p>';
      } else {
        assistantContentDiv.innerHTML = `<p style="color: #ef4444;"><i class="fa-solid fa-triangle-exclamation"></i> Error: ${err.message}</p>`;
      }
    } finally {
      setGeneratingState(false);
      abortController = null;
    }
  }

  function setGeneratingState(generating) {
    isGenerating = generating;
    sendBtn.style.display = generating ? 'none' : 'flex';
    stopBtn.style.display = generating ? 'flex' : 'none';
    promptInput.disabled = generating;
  }

  function stopGeneration() {
    if (abortController) {
      abortController.abort();
    }
  }

  // 5. Ajustes y Listeners de Eventos
  function adjustTextareaHeight() {
    promptInput.style.height = 'auto';
    promptInput.style.height = Math.min(promptInput.scrollHeight, 160) + 'px';
    sendBtn.disabled = promptInput.value.trim() === '' || isGenerating;
  }

  promptInput.addEventListener('input', adjustTextareaHeight);

  promptInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      const text = promptInput.value.trim();
      if (text && !isGenerating) {
        sendMessage(text);
      }
    }
  });

  sendBtn.addEventListener('click', () => {
    const text = promptInput.value.trim();
    if (text && !isGenerating) {
      sendMessage(text);
    }
  });

  stopBtn.addEventListener('click', stopGeneration);

  newChatBtn.addEventListener('click', createNewChat);

  clearHistoryBtn.addEventListener('click', () => {
    if (confirm('¿Estás seguro de que deseas borrar todo el historial de conversaciones?')) {
      chats = [];
      saveChats();
      createNewChat();
    }
  });

  modelSelect.addEventListener('change', () => {
    activeModelName.textContent = modelSelect.value;
  });

  // Sugerencias de Inicio
  document.querySelectorAll('.suggestion-card').forEach(card => {
    card.addEventListener('click', () => {
      const prompt = card.getAttribute('data-prompt');
      if (prompt) {
        sendMessage(prompt);
      }
    });
  });

  // Sidebar Móvil
  function openSidebar() {
    sidebar.classList.add('open');
    sidebarOverlay.classList.add('active');
  }

  function closeSidebar() {
    sidebar.classList.remove('open');
    sidebarOverlay.classList.remove('active');
  }

  openSidebarBtn.addEventListener('click', openSidebar);
  closeSidebarBtn.addEventListener('click', closeSidebar);
  sidebarOverlay.addEventListener('click', closeSidebar);

  // Helper para copiar código
  window.copyCodeSnippet = function(button) {
    const wrapper = button.closest('.code-block-wrapper');
    const code = wrapper.querySelector('code').innerText;
    navigator.clipboard.writeText(code).then(() => {
      button.innerHTML = '<i class="fa-solid fa-check"></i> ¡Copiado!';
      setTimeout(() => {
        button.innerHTML = '<i class="fa-regular fa-copy"></i> Copiar código';
      }, 2000);
    });
  };

  function attachCodeCopyEvents(container) {
    if (window.hljs) {
      container.querySelectorAll('pre code').forEach((block) => {
        hljs.highlightElement(block);
      });
    }
  }

  // Inicialización
  loadModels();
  if (chats.length === 0) {
    createNewChat();
  } else {
    switchChat(chats[0].id);
  }
});
