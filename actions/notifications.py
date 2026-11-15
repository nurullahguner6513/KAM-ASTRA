import asyncio
from typing import List, Dict, Set

# Attempt to import winrt. If missing, we fail gracefully
try:
    from winrt.windows.ui.notifications.management import UserNotificationListener
except ImportError:
    UserNotificationListener = None

class NotificationMonitor:
    def __init__(self):
        self._seen_ids: Set[int] = set()
        self._listener = None
        self._has_access = False

    async def initialize(self) -> bool:
        if UserNotificationListener is None:
            print("[Notifications] winrt modulleri eksik. Bildirim takibi yapilamayacak.")
            return False
            
        try:
            self._listener = UserNotificationListener.current
            access = await self._listener.request_access_async()
            # 1 == UserNotificationListenerAccessStatus.Allowed
            if access == 1:
                self._has_access = True
                
                # Ilk calismada mevcut bildirimleri gorulmus isaretle
                notifs = await self._listener.get_notifications_async(1)
                for n in notifs:
                    self._seen_ids.add(n.id)
                return True
            else:
                print("[Notifications] Erisim reddedildi. Lutfen Windows Ayarlarindan izin verin.")
                return False
        except Exception as e:
            print(f"[Notifications] Initialize error: {e}")
            return False

    async def get_new_messages(self, target_apps: List[str] = None) -> List[Dict[str, str]]:
        if not self._has_access or self._listener is None:
            return []
            
        new_messages = []
        try:
            # 1 == NotificationKinds.Toast
            notifs = await self._listener.get_notifications_async(1)
            
            for n in notifs:
                if n.id in self._seen_ids:
                    continue
                
                self._seen_ids.add(n.id)
                
                try:
                    app_name = n.app_info.display_info.display_name
                    if target_apps and app_name not in target_apps:
                        continue
                        
                    texts = [t.text for t in n.notification.visual.bindings[0].get_text_elements()]
                    if len(texts) >= 2:
                        sender = texts[0]
                        message = " ".join(texts[1:])
                    elif len(texts) == 1:
                        sender = app_name
                        message = texts[0]
                    else:
                        continue
                        
                    new_messages.append({
                        "app": app_name,
                        "sender": sender,
                        "message": message
                    })
                except Exception as parse_e:
                    print(f"[Notifications] Parse error: {parse_e}")
                    
        except Exception as e:
            print(f"[Notifications] get_new_messages error: {e}")
            
        return new_messages

# Singleton instance
monitor = NotificationMonitor()
unread_notifications = []

async def fetch_and_store_notifications():
    global unread_notifications
    messages = await monitor.get_new_messages(target_apps=["WhatsApp", "Telegram Desktop", "Discord"])
    for msg in messages:
        unread_notifications.append(msg)
    return messages

def get_unread_notifications_text() -> str:
    global unread_notifications
    if not unread_notifications:
        return "Şu anda okunmamış yeni bir bildirim veya mesaj yok."
        
    lines = []
    for msg in unread_notifications:
        lines.append(f"Uygulama: {msg['app']}, Gonderen: {msg['sender']}, Mesaj: {msg['message']}")
    
    unread_notifications.clear() # Okunduktan sonra temizle
    return "\n".join(lines)

