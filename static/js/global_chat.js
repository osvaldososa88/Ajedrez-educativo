// Chat global de la comunidad

class GlobalChatApp {
    constructor() {
        this.messagesEl = document.getElementById('global-chat-messages');
        this.form = document.getElementById('global-chat-form');
        this.input = document.getElementById('global-chat-input');

        if (!this.messagesEl || !this.form) return;

        this.connect();
        this.initEvents();
    }

    connect() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws/global_chat/`;

        this.socket = new WebSocket(wsUrl);

        this.socket.onmessage = (event) => {
            const data = JSON.parse(event.data);
            if (data.type === 'chat_history') {
                this.renderHistory(data.messages);
            } else if (data.type === 'chat_message') {
                this.appendMessage(data);
            }
        };

        this.socket.onclose = () => {
            // Reconectar tras 3 segundos
            setTimeout(() => this.connect(), 3000);
        };
    }

    initEvents() {
        this.form.addEventListener('submit', (e) => {
            e.preventDefault();
            const msg = this.input.value.trim();
            if (!msg) return;

            if (this.socket && this.socket.readyState === WebSocket.OPEN) {
                this.socket.send(JSON.stringify({
                    type: 'send_chat',
                    message: msg
                }));
                this.input.value = '';
            }
        });
    }

    renderHistory(messages) {
        this.messagesEl.innerHTML = '';
        if (!messages || messages.length === 0) {
            this.messagesEl.innerHTML = '<div style="text-align:center;color:var(--text-secondary);font-size:0.85rem;padding:1rem;">Sé el primero en escribir. ¡Organiza un torneo o propón un desafío! ♟️</div>';
            return;
        }
        messages.forEach(msg => this.appendMessage(msg, false));
        this.messagesEl.scrollTop = this.messagesEl.scrollHeight;
    }

    appendMessage(data) {
        // Quitar el mensaje de "sin mensajes" si existe
        const emptyEl = this.messagesEl.querySelector('div[style*="text-align:center"]');
        if (emptyEl && emptyEl.textContent.includes('Organiza')) emptyEl.remove();

        const isOwn = data.sender === GLOBAL_CHAT_USER;
        const msgEl = document.createElement('div');
        msgEl.className = `chat-msg ${isOwn ? 'own' : 'other'}`;
        msgEl.innerHTML = `
            <span class="chat-msg-sender">${escapeHtml(data.sender)}</span>
            <span class="chat-msg-content">${escapeHtml(data.content)}</span>
        `;
        this.messagesEl.appendChild(msgEl);
        this.messagesEl.scrollTop = this.messagesEl.scrollHeight;
    }
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

document.addEventListener('DOMContentLoaded', () => {
    window.globalChatApp = new GlobalChatApp();
});