/**
 * Push Notifications Service Worker
 * Este ficheiro é registado como service worker para receber notificações push
 */

/* eslint-disable no-restricted-globals */

// Evento de instalação do service worker
self.addEventListener('install', (event) => {
  console.log('Service Worker: Instalado');
  self.skipWaiting();
});

// Evento de activação
self.addEventListener('activate', (event) => {
  console.log('Service Worker: Ativado');
  event.waitUntil(self.clients.claim());
});

// Receber notificação push
self.addEventListener('push', (event) => {
  console.log('Service Worker: Push recebido', event);
  
  let data = {
    title: 'CreditoIMO',
    body: 'Nova notificação',
    icon: '/logo192.png',
    badge: '/logo192.png',
    tag: 'creditoimo-notification',
    data: {}
  };
  
  if (event.data) {
    try {
      const payload = event.data.json();
      data = {
        title: payload.title || data.title,
        body: payload.body || payload.message || data.body,
        icon: payload.icon || data.icon,
        badge: payload.badge || data.badge,
        tag: payload.tag || data.tag,
        data: payload.data || payload
      };
    } catch (e) {
      data.body = event.data.text();
    }
  }
  
  const options = {
    body: data.body,
    icon: data.icon,
    badge: data.badge,
    tag: data.tag,
    data: data.data,
    vibrate: [100, 50, 100],
    requireInteraction: true,
    actions: [
      { action: 'view', title: 'Ver', icon: '/logo192.png' },
      { action: 'dismiss', title: 'Dispensar' }
    ]
  };
  
  event.waitUntil(
    self.registration.showNotification(data.title, options)
  );
});

// Clique na notificação
self.addEventListener('notificationclick', (event) => {
  console.log('Service Worker: Notificação clicada', event);
  
  event.notification.close();
  
  const data = event.notification.data || {};
  let url = '/';
  
  // Determinar URL com base nos dados da notificação
  if (data.process_id) {
    url = `/process/${data.process_id}`;
  } else if (data.url) {
    url = data.url;
  }
  
  if (event.action === 'dismiss') {
    return;
  }
  
  event.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((clientList) => {
      // Procurar janela já aberta
      for (const client of clientList) {
        if (client.url.includes(self.location.origin) && 'focus' in client) {
          client.navigate(url);
          return client.focus();
        }
      }
      // Abrir nova janela
      if (self.clients.openWindow) {
        return self.clients.openWindow(url);
      }
    })
  );
});

// Fechar notificação
self.addEventListener('notificationclose', (event) => {
  console.log('Service Worker: Notificação fechada', event);
});
