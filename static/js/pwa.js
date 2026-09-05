// ============================================
// PWA - Instalación / Desinstalación
// ============================================

let deferredPrompt = null;
let isAppInstalled = false;

// Detectar si la app ya está instalada (standalone mode)
function checkIfInstalled() {
  const isStandalone = window.matchMedia('(display-mode: standalone)').matches ||
                       window.navigator.standalone === true ||
                       document.referrer.startsWith('android-app://');
  isAppInstalled = isStandalone;
  return isAppInstalled;
}

// Actualizar visibilidad de botones según estado de instalación
function updateInstallUI() {
  const installBtn = document.getElementById('install-app-btn');
  const uninstallItem = document.getElementById('uninstall-app-item');
  const isInstalled = checkIfInstalled();

  if (installBtn) {
    // Mostrar botón de instalar solo si:
    // 1. No está instalada
    // 2. El navegador soporta beforeinstallprompt (Chrome, Edge, etc.)
    // 3. No es iOS (Safari no soporta beforeinstallprompt)
    const canInstall = !isInstalled && deferredPrompt !== null;
    installBtn.style.display = canInstall ? 'inline-flex' : 'none';
  }

  if (uninstallItem) {
    uninstallItem.style.display = isInstalled ? 'flex' : 'none';
  }
}

// Registrar Service Worker
if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js')
      .then(reg => console.log('Service Worker registrado:', reg.scope))
      .catch(err => console.error('Error registrando Service Worker:', err));
  });
}

// Capturar el evento beforeinstallprompt
window.addEventListener('beforeinstallprompt', (e) => {
  e.preventDefault();
  deferredPrompt = e;
  updateInstallUI();
});

// Cuando la app se instala
window.addEventListener('appinstalled', () => {
  deferredPrompt = null;
  isAppInstalled = true;
  updateInstallUI();
  // Recargar para actualizar la UI
  setTimeout(() => window.location.reload(), 500);
});

// Botón "Instalar aplicación"
document.addEventListener('click', (e) => {
  if (e.target.closest('#install-app-btn')) {
    e.preventDefault();
    if (deferredPrompt) {
      deferredPrompt.prompt();
      deferredPrompt.userChoice.then((choiceResult) => {
        if (choiceResult.outcome === 'accepted') {
          console.log('App instalada');
        }
        deferredPrompt = null;
        updateInstallUI();
      });
    }
  }
});

// Botón "Desinstalar"
document.addEventListener('click', (e) => {
  if (e.target.closest('#uninstall-app-item')) {
    e.preventDefault();
    uninstallApp();
  }
});

// Función para desinstalar la app
async function uninstallApp() {
  // Para Chrome/Edge en desktop
  if (navigator.userAgentData && navigator.userAgentData.brands) {
    const isChrome = navigator.userAgentData.brands.some(b => b.brand.includes('Chrome'));
    const isEdge = navigator.userAgentData.brands.some(b => b.brand.includes('Edge'));
    if (isChrome || isEdge) {
      // Intentar usar la API de desinstalación si está disponible
      if (window.navigator && window.navigator.userAgentData) {
        // No hay API directa de desinstalación, mostrar instrucciones
        showUninstallInstructions();
        return;
      }
    }
  }

  // Para Android Chrome
  if (/Android/i.test(navigator.userAgent) && /Chrome/i.test(navigator.userAgent)) {
    showUninstallInstructions();
    return;
  }

  // Para iOS Safari
  if (/iPhone|iPad|iPod/i.test(navigator.userAgent)) {
    showUninstallInstructions();
    return;
  }

  // Fallback: mostrar instrucciones
  showUninstallInstructions();
}

// Mostrar instrucciones de desinstalación
function showUninstallInstructions() {
  const modal = document.getElementById('uninstall-modal');
  if (modal) {
    modal.style.display = 'flex';
  }
}

// Cerrar modal de desinstalación
document.addEventListener('click', (e) => {
  if (e.target.closest('#close-uninstall-modal') || e.target.id === 'uninstall-modal') {
    const modal = document.getElementById('uninstall-modal');
    if (modal) modal.style.display = 'none';
  }
});

// ============================================
// Menú de Configuración
// ============================================

// Abrir/cerrar menú de configuración
document.addEventListener('click', (e) => {
  const settingsBtn = e.target.closest('#settings-btn');
  const settingsMenu = document.getElementById('settings-menu');

  if (settingsBtn) {
    e.preventDefault();
    e.stopPropagation();
    if (settingsMenu) {
      settingsMenu.classList.toggle('open');
    }
  } else if (settingsMenu && settingsMenu.classList.contains('open')) {
    // Cerrar si se hace clic fuera del menú
    if (!settingsMenu.contains(e.target) && !e.target.closest('#settings-btn')) {
      settingsMenu.classList.remove('open');
    }
  }
});

// Inicializar al cargar
document.addEventListener('DOMContentLoaded', () => {
  checkIfInstalled();
  updateInstallUI();

  // Escuchar cambios en display-mode (cuando se instala/desinstala)
  window.matchMedia('(display-mode: standalone)').addEventListener('change', (e) => {
    isAppInstalled = e.matches;
    updateInstallUI();
  });
});