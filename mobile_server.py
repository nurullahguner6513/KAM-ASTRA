import asyncio
import websockets
import json
import threading

class MobileServer:
    def __init__(self, host="0.0.0.0", port=8765, on_message_callback=None):
        self.host = host
        self.port = port
        self.on_message_callback = on_message_callback
        self.loop = None
        self.server = None
        self.connected_clients = set()

    async def _handler(self, websocket):
        self.connected_clients.add(websocket)
        print(f"[MobileServer] Telefon baglandi: {websocket.remote_address}")
        try:
            async for message in websocket:
                if self.on_message_callback:
                    self.on_message_callback(message)
        except Exception as e:
            print(f"[MobileServer] Hata: {e}")
        finally:
            self.connected_clients.remove(websocket)
            print("[MobileServer] Telefon baglantisi koptu.")

    async def _start_server(self):
        print(f"[MobileServer] Sunucu calisiyor -> ws://{self.host}:{self.port}")
        self.server = await websockets.serve(self._handler, self.host, self.port)
        await asyncio.Future()  # Sonsuza kadar calis

    def _run_thread(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self._start_server())

    def start(self):
        t = threading.Thread(target=self._run_thread, daemon=True)
        t.start()
        return t

    def send_message(self, message: dict):
        if not self.loop or not self.connected_clients:
            return False
        
        async def _send():
            msg_str = json.dumps(message)
            for client in list(self.connected_clients):
                try:
                    await client.send(msg_str)
                except Exception as e:
                    print(f"[MobileServer] Gonderim hatasi: {e}")
                    
        asyncio.run_coroutine_threadsafe(_send(), self.loop)
        return True

# Test
if __name__ == "__main__":
    def on_msg(msg):
        print("Telefondan Gelen:", msg)
    server = MobileServer(on_message_callback=on_msg)
    server.start()
    input("Cikmak icin Enter'a basin...\n")
