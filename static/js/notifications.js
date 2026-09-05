// Notificaciones en tiempo real via WebSocket

let notificationSocket = null;
let unreadCount = 0;

function connectNotifications() {
    if (!document.body.dataset.userId) return;
    if (!window.WebSocket) return;

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/notifications/`;

    notificationSocket = new WebSocket(wsUrl);

    notificationSocket.onopen = () => {
        console.log('Canal de notificaciones conectado');
    };

    notificationSocket.onclose = () => {
        // Intentar reconectar después de 3 segundos
        setTimeout(connectNotifications, 3000);
    };

    notificationSocket.onmessage = (event) => {
        const data = JSON.parse(event.data);

        if (data.type === 'unread_notifications') {
            renderUnreadBadge(data.notifications.length);
        } else if (data.type === 'notification') {
            handleNewNotification(data.notification);
        } else if (data.type === 'notification_read') {
            // Actualizar badge
            const count = Math.max(0, unreadCount - 1);
            renderUnreadBadge(count);
        }
    };
}

function renderUnreadBadge(count) {
    unreadCount = count;
    const badge = document.getElementById('notif-badge');
    const bell = document.getElementById('notif-bell');
    if (badge) {
        if (count > 0) {
            badge.textContent = count > 9 ? '9+' : count;
            badge.style.display = 'flex';
        } else {
            badge.style.display = 'none';
        }
    }
    if (bell) {
        const dropdown = document.getElementById('notif-dropdown');
        if (dropdown) {
            dropdown.innerHTML = '';
            if (unreadCount === 0) {
                dropdown.innerHTML = '<div style="padding: 1rem; text-align: center; color: var(--text-secondary); font-size: 0.85rem;">No tienes notificaciones.</div>';
            }
        }
    }
}

function handleNewNotification(notification) {
    // Actualizar contador
    renderUnreadBadge(unreadCount + 1);

    // Agregar a la lista del dropdown
    const dropdown = document.getElementById('notif-dropdown');
    if (dropdown) {
        // Quitar mensaje vacío
        const emptyEl = dropdown.querySelector('div[style*="text-align: center"]');
        if (emptyEl) emptyEl.remove();

        const item = document.createElement('a');
        item.href = notification.game_id ? `/games/game/${notification.game_id}/` : '#';
        item.className = 'notif-item';
        item.style.cssText = 'display:flex;align-items:center;gap:0.5rem;padding:0.6rem 0.85rem;border-radius:6px;text-decoration:none;color:var(--text-primary);font-size:0.85rem;transition:background-color 0.15s ease;';
        item.addEventListener('click', () => {
            if (notificationSocket && notificationSocket.readyState === WebSocket.OPEN) {
                notificationSocket.send(JSON.stringify({ type: 'mark_read', notification_id: notification.id }));
            }
        });
        item.innerHTML = `<span>🔔</span><span>${notification.message}</span>`;
        dropdown.prepend(item);
    }

    // Mostrar toast
    showNotificationToast(notification);
}

function showNotificationToast(notification) {
    // Eliminar toast anterior si existe
    const oldToast = document.getElementById('notif-toast');
    if (oldToast) oldToast.remove();

    const toast = document.createElement('div');
    toast.id = 'notif-toast';
    toast.style.cssText = `
        position: fixed; bottom: 1.5rem; right: 1.5rem; z-index: 3000;
        background: var(--bg-surface); border: 1px solid var(--accent-color);
        border-radius: 12px; padding: 1rem 1.25rem; box-shadow: var(--shadow-lg);
        max-width: 320px; font-size: 0.9rem; cursor: pointer;
        animation: slideIn 0.3s ease;
    `;
    toast.innerHTML = `
        <div style="display:flex;gap:0.75rem;align-items:flex-start;">
            <span style="font-size:1.5rem;">🔔</span>
            <div>
                <strong style="display:block;margin-bottom:0.25rem;">¡Aviso!</strong>
                <span style="color:var(--text-secondary);">${notification.message}</span>
            </div>
        </div>
    `;

    if (notification.game_id) {
        toast.addEventListener('click', () => {
            window.location.href = `/games/game/${notification.game_id}/`;
        });
    }

    document.body.appendChild(toast);

    setTimeout(() => toast.remove(), 8000);
}

// Cerrar dropdown al hacer clic fuera
document.addEventListener('click', (e) => {
    const bell = document.getElementById('notif-bell');
    const dropdown = document.getElementById('notif-dropdown');
    const settingsMenu = document.getElementById('settings-menu');

    if (bell) {
        const bellContainer = bell.closest('.notif-container');
        if (bellContainer && !bellContainer.contains(e.target)) {
            if (dropdown && dropdown.classList.contains('show')) {
                dropdown.classList.remove('show');
            }
        } else if (bellContainer && bellContainer.contains(e.target) && !e.target.closest('.notif-item')) {
            if (dropdown) dropdown.classList.toggle('show');
        }
    }

    // Cerrar settings menu si está abierto
    if (settingsMenu && settingsMenu.classList.contains('open')) {
        if (!settingsMenu.contains(e.target) && !e.target.closest('#settings-btn')) {
            settingsMenu.classList.remove('open');
        }
    }
});

document.addEventListener('DOMContentLoaded', () => {
    connectNotifications();
});