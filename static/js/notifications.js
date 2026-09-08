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
        dropdown.innerHTML = '<div style="padding: 1rem; text-align: center; color: var(--text-secondary); font-size: 0.85rem;">No tienes notificaciones.</div>';
        return;
    }
    notifications.forEach(n => {
        const item = document.createElement('a');
        item.href = n.game_id ? `/games/game/${n.game_id}/` : '#';
        item.className = 'notif-item';
        item.style.cssText = 'display:flex;align-items:center;gap:0.5rem;padding:0.6rem 0.85rem;border-radius:6px;text-decoration:none;color:var(--text-primary);font-size:0.85rem;transition:background-color 0.15s ease;';
        item.addEventListener('click', () => markNotificationRead(n.id));
        item.innerHTML = `<span>🔔</span><span>${n.message}</span>`;
        dropdown.appendChild(item);
    });
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
        const emptyEl = dropdown.querySelector('div[style*="text-align: center"]');
        if (emptyEl) emptyEl.remove();

        const item = document.createElement('a');
        item.href = notification.game_id ? `/games/game/${notification.game_id}/` : '#';
        item.className = 'notif-item';
        item.style.cssText = 'display:flex;align-items:center;gap:0.5rem;padding:0.6rem 0.85rem;border-radius:6px;text-decoration:none;color:var(--text-primary);font-size:0.85rem;transition:background-color 0.15s ease;';
        item.addEventListener('click', () => markNotificationRead(notification.id));
        item.innerHTML = `<span>🔔</span><span>${notification.message}</span>`;
        dropdown.prepend(item);
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