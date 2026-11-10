{% load static %}// 당번표 서비스 워커: 푸시 알림 표시와 클릭 시 해당 화면 열기
self.addEventListener("push", event => {
  let d = {};
  try { d = event.data ? event.data.json() : {}; } catch (e) { d = {body: event.data ? event.data.text() : ""}; }
  const title = d.title || "당번 알림";
  event.waitUntil(self.registration.showNotification(title, {
    body: d.body || "", data: {url: d.url || "/"}, icon: "{% static 'duty/icon-192.png' %}",
  }));
});

self.addEventListener("notificationclick", event => {
  event.notification.close();
  const url = new URL((event.notification.data && event.notification.data.url) || "/", self.location.origin).href;
  event.waitUntil(clients.matchAll({type: "window", includeUncontrolled: true}).then(list => {
    const same = list.find(c => c.url === url);
    if (same) return same.focus();
    const c = list.find(c => "navigate" in c);
    if (c) return c.navigate(url).then(n => n ? n.focus() : clients.openWindow(url)).catch(() => clients.openWindow(url));
    return clients.openWindow(url);
  }));
});
