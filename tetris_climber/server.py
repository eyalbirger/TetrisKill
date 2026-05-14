#!/usr/bin/env python3
import socket
import threading
import json
import time
import struct

from constants import SERVER_HOST, SERVER_PORT, TICK_RATE
from database import init_db, register_user, verify_user, save_result, get_leaderboard
from game_logic import GameState


def send_msg(sock, data: dict):
    payload = json.dumps(data).encode()
    sock.sendall(struct.pack(">I", len(payload)) + payload)


def recv_msg(sock) -> dict | None:
    try:
        raw = _recvall(sock, 4)
        if not raw:
            return None
        length = struct.unpack(">I", raw)[0]
        data = _recvall(sock, length)
        return json.loads(data)
    except Exception:
        return None


def _recvall(sock, n):
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            return None
        buf += chunk
    return buf


class GameServer:
    def __init__(self):
        init_db()
        self.clients: dict[str, socket.socket] = {}   # role -> socket
        self.usernames: dict[str, str] = {}            # role -> username
        self.state = GameState()
        self.lock = threading.Lock()
        self.running = False

    def start(self):
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if hasattr(socket, "SO_REUSEPORT"):
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        server.bind((SERVER_HOST, SERVER_PORT))
        server.listen(5)
        print(f"Server listening on {SERVER_HOST}:{SERVER_PORT}")
        self.running = True

        while self.running:
            try:
                conn, addr = server.accept()
                print(f"Connection from {addr}")
                t = threading.Thread(target=self._handle_client, args=(conn,), daemon=True)
                t.start()
            except KeyboardInterrupt:
                break

        server.close()

    def _handle_client(self, conn: socket.socket):
        role = None
        username = None
        try:
            # Auth handshake
            msg = recv_msg(conn)
            if not msg:
                conn.close()
                return

            if msg.get("type") == "register":
                ok, err = register_user(msg["username"], msg["password"])
                send_msg(conn, {"type": "auth", "success": ok, "error": err})
                if not ok:
                    conn.close()
                    return
                username = msg["username"]
            elif msg.get("type") == "login":
                ok = verify_user(msg["username"], msg["password"])
                send_msg(conn, {"type": "auth", "success": ok, "error": "" if ok else "Invalid credentials"})
                if not ok:
                    conn.close()
                    return
                username = msg["username"]
            else:
                conn.close()
                return

            # Assign role
            with self.lock:
                if "builder" not in self.clients:
                    role = "builder"
                elif "climber" not in self.clients:
                    role = "climber"
                else:
                    send_msg(conn, {"type": "error", "message": "Game full"})
                    conn.close()
                    return
                self.clients[role] = conn
                self.usernames[role] = username

            send_msg(conn, {"type": "role", "role": role, "username": username})
            print(f"{username} joined as {role}")

            # Send leaderboard
            send_msg(conn, {"type": "leaderboard", "data": get_leaderboard()})

            # Start game when both players are ready
            with self.lock:
                if len(self.clients) == 2 and self.state.status == "waiting":
                    self.state.status = "playing"
                    self.state.start_time = time.time()
                    self._broadcast({"type": "start"})
                    self._broadcast({"type": "state", "data": self.state.to_dict()})
                    threading.Thread(target=self._game_loop, daemon=True).start()

            # Input loop
            while True:
                msg = recv_msg(conn)
                if not msg:
                    break
                self._handle_input(role, msg)

        except Exception as e:
            print(f"Client error: {e}")
        finally:
            print(f"{username} ({role}) disconnected")
            with self.lock:
                if role and role in self.clients:
                    del self.clients[role]
                if role and role in self.usernames:
                    del self.usernames[role]
            conn.close()

    def _handle_input(self, role: str, msg: dict):
        with self.lock:
            if msg.get("type") == "action" and role == "builder":
                self.state.apply_builder_action(msg.get("action", ""))
            elif msg.get("type") == "keys" and role == "climber":
                self.state.climber_keys = msg.get("keys", {})

    def _game_loop(self):
        interval = 1.0 / TICK_RATE
        while self.running:
            t0 = time.time()
            with self.lock:
                if self.state.status == "playing":
                    self.state.tick_update(time.time())

                state_dict = self.state.to_dict()
                status = self.state.status

            self._broadcast({"type": "state", "data": state_dict})

            if status in ("builder_wins", "climber_wins"):
                self._end_game(status)
                break

            elapsed = time.time() - t0
            sleep_for = interval - elapsed
            if sleep_for > 0:
                time.sleep(sleep_for)

    def _end_game(self, status: str):
        with self.lock:
            duration = self.state.duration
            builder_name = self.usernames.get("builder", "unknown")
            climber_name = self.usernames.get("climber", "unknown")

        if status == "builder_wins":
            winner_name, loser_name, winner_role = builder_name, climber_name, "builder"
        else:
            winner_name, loser_name, winner_role = climber_name, builder_name, "climber"

        save_result(winner_name, loser_name, winner_role, duration)
        lb = get_leaderboard()
        self._broadcast({
            "type": "game_over",
            "status": status,
            "winner": winner_name,
            "loser": loser_name,
            "duration": round(duration, 2),
            "leaderboard": lb,
        })

    def _broadcast(self, msg: dict):
        dead = []
        for role, sock in list(self.clients.items()):
            try:
                send_msg(sock, msg)
            except Exception:
                dead.append(role)
        for role in dead:
            self.clients.pop(role, None)


if __name__ == "__main__":
    GameServer().start()
