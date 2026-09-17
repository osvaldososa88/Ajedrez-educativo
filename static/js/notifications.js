// Notificaciones en tiempo real via WebSocket con fallback HTTP

let notificationSocket = null;
let unreadCount = 0;
let wsFailed = false;

function connectNotifications() {
    if (!document.body.dataset.userId) return;
    if (!window.WebSocket) {
        wsFailed = true;
        fetchNotificationsHTTP();
        return;
    }

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/notifications/`;

    notificationSocket = new WebSocket(wsUrl);

    notificationSocket.onopen = () => {
        console.log('Canal de notificaciones conectado');
        wsFailed = false;
    };

    notificationSocket.onclose = () => {
        if (!wsFailed) {
            wsFailed = true;
            fetchNotificationsHTTP();
        }
        setTimeout(connectNotifications, 10000);
    };

    notificationSocket.onerror = () => {
        wsFailed = true;
        if (notificationSocket) {
            notificationSocket.close();
            notificationSocket = null;
        }
        fetchNotificationsHTTP();
    };

    notificationSocket.onmessage = (event) => {
        const data = JSON.parse(event.data);

        if (data.type === 'unread_notifications') {
            renderUnreadBadge(data.notifications.length);
            renderNotificationDropdown(data.notifications);
        } else if (data.type === 'notification') {
            handleNewNotification(data.notification);
        } else if (data.type === 'notification_read') {
            const count = Math.max(0, unreadCount - 1);
            renderUnreadBadge(count);
        }
    };
}

function fetchNotificationsHTTP() {
    fetch('/games/api/notifications/')
        .then(r => r.json())
        .then(data => {
            renderUnreadBadge(data.unread_count);
            renderNotificationDropdown(data.notifications);
        })
        .catch(() => {});
}

function renderUnreadBadge(count) {
    unreadCount = count;
    const badge = document.getElementById('notif-badge');
    if (badge) {
        if (count > 0) {
            badge.textContent = count > 9 ? '9+' : count;
            badge.style.display = 'flex';
        } else {
            badge.style.display = 'none';
        }
    }
}

function renderNotificationDropdown(notifications) {
    const dropdown = document.getElementById('notif-dropdown');
    if (!dropdown) return;
    dropdown.innerHTML = '';
    if (!notifications || notifications.length === 0) {
        dropdown.innerHTML = `
            <div style="padding: 1.5rem 1rem; text-align: center;">
                <div style="font-size: 2rem; margin-bottom: 0.75rem; opacity: 0.5;">🔔</div>
                <div style="color: var(--text-secondary); font-size: 0.9rem; font-weight: 500;">Estás al día</div>
                <div style="color: var(--text-secondary); font-size: 0.8rem; margin-top: 0.25rem; opacity: 0.7;">No tienes notificaciones nuevas</div>
            </div>
        `;
        return;
    }
    // There are notifications - render them
    notifications.forEach(n => {
        const item = document.createElement('a');
        item.href = n.game_id ? `/games/game/${n.game_id}/` : '#';
        item.className = 'notif-item';
        item.style.cssText = 'display:flex;align-items:flex-start;gap:0.6rem;padding:0.6rem 0.85rem;border-radius:6px;text-decoration:none;color:var(--text-primary);font-size:0.85rem;transition:background-color 0.15s ease;';
        item.addEventListener('click', () => markNotificationRead(n.id));
        const timeStr = n.created_at ? new Date(n.created_at).toLocaleString('es-ES', {
            day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit'
        }) : '';
        item.innerHTML = `
            <span style="font-size:1.1rem;flex-shrink:0;">🔔</span>
            <div style="flex:1;min-width:0;">
                <div style="font-size:0.8rem;color:var(--text-secondary);margin-bottom:0.15rem;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${timeStr}</div>
                <div style="word-break:break-word;">${n.message}</div>
            </div>
            ${n.is_read ? '' : '<span style="width:6px;height:6px;border-radius:50%;background:var(--accent-color);flex-shrink:0;margin-top:0.3rem;"></span>'}
        `;
        dropdown.appendChild(item);
    });
    // Show "Marcar todo como leído" at bottom
    const footer = document.createElement('div');
    footer.style.cssText = 'padding:0.5rem 0.85rem;border-top:1px solid var(--border-color);margin-top:0.25rem;';
    footer.innerHTML = `<button id="mark-all-read-btn" style="width:100%;background:none;border:none;color:var(--accent-color);font-size:0.8rem;cursor:pointer;padding:0.3rem;">Marcar todas como leídas</button>`;
    dropdown.appendChild(footer);
    document.getElementById('mark-all-read-btn')?.addEventListener('click', () => markAllNotificationsRead());
}

function markNotificationRead(notificationId) {
    if (notificationSocket && notificationSocket.readyState === WebSocket.OPEN) {
        notificationSocket.send(JSON.stringify({ type: 'mark_read', notification_id: notificationId }));
    } else {
        fetch(`/games/api/notifications/${notificationId}/read/`, {
            method: 'POST',
            headers: { 'X-CSRFToken': getCookie('csrftoken') }
        })
        .then(r => r.json())
        .then(data => renderUnreadBadge(data.unread_count))
        .catch(() => {});
    }
}

function markAllNotificationsRead() {
    fetch('/games/api/notifications/read-all/', {
        method: 'POST',
        headers: { 'X-CSRFToken': getCookie('csrftoken') }
    })
    .then(r => r.json())
    .then(data => {
        renderUnreadBadge(0);
        renderNotificationDropdown([]);
    })
    .catch(() => {});
}

function getCookie(name) {
    let v = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let c of cookies) {
            c = c.trim();
            if (c.substring(0, name.length + 1) === (name + '=')) {
                v = decodeURIComponent(c.substring(name.length + 1));
                break;
            }
        }
    }
    return v;
}

function handleNewNotification(notification) {
    renderUnreadBadge(unreadCount + 1);

    const dropdown = document.getElementById('notif-dropdown');
    if (dropdown) {
        // Remove empty state if present
        const emptyEl = dropdown.querySelector('div[style*="text-align: center"]');
        if (emptyEl) emptyEl.remove();

        const item = document.createElement('a');
        item.href = notification.game_id ? `/games/game/${notification.game_id}/` : '#';
        item.className = 'notif-item';
        item.style.cssText = 'display:flex;align-items:flex-start;gap:0.6rem;padding:0.6rem 0.85rem;border-radius:6px;text-decoration:none;color:var(--text-primary);font-size:0.85rem;transition:background-color 0.15s ease;';
        item.addEventListener('click', () => markNotificationRead(notification.id));
        const timeStr = notification.created_at ? new Date(notification.created_at).toLocaleString('es-ES', {
            day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit'
        }) : '';
        item.innerHTML = `
            <span style="font-size:1.1rem;flex-shrink:0;">🔔</span>
            <div style="flex:1;min-width:0;">
                <div style="font-size:0.8rem;color:var(--text-secondary);margin-bottom:0.15rem;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${timeStr}</div>
                <div style="word-break:break-word;">${notification.message}</div>
            </div>
            <span style="width:6px;height:6px;border-radius:50%;background:var(--accent-color);flex-shrink:0;margin-top:0.3rem;"></span>
        `;
        dropdown.prepend(item);

        // Ensure footer with "marcar todo" exists
        if (!document.getElementById('mark-all-read-btn')) {
            const footer = document.createElement('div');
            footer.style.cssText = 'padding:0.5rem 0.85rem;border-top:1px solid var(--border-color);margin-top:0.25rem;';
            footer.innerHTML = `<button id="mark-all-read-btn" style="width:100%;background:none;border:none;color:var(--accent-color);font-size:0.8rem;cursor:pointer;padding:0.3rem;">Marcar todas como leídas</button>`;
            dropdown.appendChild(footer);
            document.getElementById('mark-all-read-btn')?.addEventListener('click', () => markAllNotificationsRead());
        }
    }

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