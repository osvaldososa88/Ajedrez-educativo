// Chat de la partida
let chatSocket = null;
let chatInitialized = false;

function initChat() {
    if (chatInitialized) return;
    chatInitialized = true;

    // Botones
    const openChatBtn = document.getElementById('btn-open-chat');
    const closeChatBtn = document.getElementById('btn-close-chat');
    const chatPanel = document.getElementById('chat-panel');
    const chatForm = document.getElementById('chat-form');
    const chatInput = document.getElementById('chat-input');
    const chatMessages = document.getElementById('chat-messages');
    const chatClosedMsg = document.getElementById('chat-closed-msg');

    if (openChatBtn) {
        openChatBtn.addEventListener('click', () => {
            if (chatPanel) chatPanel.classList.add('open');
            // Pedir historial al servidor
            if (window.chessApp && window.chessApp.socket && window.chessApp.socket.readyState === WebSocket.OPEN) {
                window.chessApp.socket.send(JSON.stringify({ type: 'get_chat_history' }));
            }
        });
    }

    if (closeChatBtn) {
        closeChatBtn.addEventListener('click', () => {
            if (chatPanel) chatPanel.classList.remove('open');
        });
    }

    if (chatForm) {
        chatForm.addEventListener('submit', (e) => {
            e.preventDefault();
            const msg = chatInput.value.trim();
            if (!msg) return;

            if (window.chessApp && window.chessApp.socket && window.chessApp.socket.readyState === WebSocket.OPEN) {
                window.chessApp.socket.send(JSON.stringify({
                    type: 'send_chat',
                    message: msg
                }));
                chatInput.value = '';
            }
        });
    }

    // Escuchar mensajes del chat en el socket existente
    // Las notificaciones del chat llegan a través del mismo socket del juego
}

// Procesar mensajes de chat recibidos por el socket del juego
function handleChatMessage(data) {
    const chatMessages = document.getElementById('chat-messages');
    if (!chatMessages) return;

    // Quitar el mensaje de "chat cerrado"
    const closedEl = document.getElementById('chat-closed-msg');
    if (closedEl) closedEl.style.display = 'none';

    const isOwn = data.sender === (typeof USER_NAME !== 'undefined' ? USER_NAME : '');
    const msgEl = document.createElement('div');
    msgEl.className = `chat-msg ${isOwn ? 'own' : 'other'}`;
    msgEl.innerHTML = `
        <span class="chat-msg-sender">${data.sender}</span>
        <span class="chat-msg-content">${escapeHtml(data.content)}</span>
    `;
    chatMessages.appendChild(msgEl);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

function handleChatHistory(data) {
    const chatMessages = document.getElementById('chat-messages');
    if (!chatMessages) return;

    chatMessages.innerHTML = '';

    if (data.messages && data.messages.length === 0) {
        chatMessages.innerHTML = '<div style="text-align:center;color:var(--text-secondary);font-size:0.85rem;padding:1rem;">Sin mensajes todavía.</div>';
        return;
    }

    data.messages.forEach(msg => {
        const isOwn = msg.sender === (typeof USER_NAME !== 'undefined' ? USER_NAME : '');
        const msgEl = document.createElement('div');
        msgEl.className = `chat-msg ${isOwn ? 'own' : 'other'}`;
        msgEl.innerHTML = `
            <span class="chat-msg-sender">${msg.sender}</span>
            <span class="chat-msg-content">${escapeHtml(msg.content)}</span>
        `;
        chatMessages.appendChild(msgEl);
    });
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

// Actualizar estado del chat según estado de la partida
function updateChatState(gameState) {
    const chatForm = document.getElementById('chat-form');
    const chatInput = document.getElementById('chat-input');
    const chatClosedMsg = document.getElementById('chat-closed-msg');

    if (!chatForm || !chatInput) return;

    const isActive = gameState && gameState.status === 'IN_PROGRESS';

    if (!isActive) {
        chatForm.style.display = 'none';
        if (chatClosedMsg) {
            chatClosedMsg.style.display = 'block';
        }
    }
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}