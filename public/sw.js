// 桃園看降落：讓頁面可以安裝成手機小工具。資料一律即時抓，不做離線快取。
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', e => e.waitUntil(self.clients.claim()));
self.addEventListener('fetch', () => {});
