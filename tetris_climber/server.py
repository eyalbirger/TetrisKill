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

            # Tell client which roles are still open, let them choose
            with self.lock:
                available = [r for r in ("builder", "climber") if r not in self.clients]
            if not available:
                send_msg(conn, {"type": "error", "message": "Game full"})
                conn.close()
                return
            send_msg(conn, {"type": "roles_available", "available": available})

            # Receive client's choice
            choice_msg = recv_msg(conn)
            if not choice_msg or choice_msg.get("type") != "choose_role":
                conn.close()
                return
            requested = choice_msg.get("role")

            with self.lock:
                # Re-check in case other client grabbed it first
                available_now = [r for r in ("builder", "climber") if r not in self.clients]
                if not available_now:
                    send_msg(conn, {"type": "error", "message": "Game full"})
                    conn.close()
                    return
                role = requested if requested in available_now else available_now[0]
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

            # Input loop — pass conn so role is looked up dynamically after flips
            while True:
                msg = recv_msg(conn)
                if not msg:
                    break
                self._handle_input(conn, msg)

        except Exception as e:
            print(f"Client error: {e}")
        finally:
            print(f"{username} disconnected")
            with self.lock:
                # Remove by socket identity — role may have flipped since connect
                for r in list(self.clients.keys()):
                    if self.clients.get(r) is conn:
                        del self.clients[r]
                        break
                for r in list(self.usernames.keys()):
                    if self.usernames.get(r) == username:
                        del self.usernames[r]
                        break
            conn.close()

    def _handle_input(self, conn: socket.socket, msg: dict):
        with self.lock:
            # Look up the current role for this socket — may have changed after a restart
            role = next((r for r, s in self.clients.items() if s is conn), None)
            if role is None:
                return
            t = msg.get("type")
            if t == "action" and role == "builder":
                self.state.apply_builder_action(msg.get("action", ""))
            elif t == "keys" and role == "climber":
                self.state.climber_keys = msg.get("keys", {})
            elif t == "restart":
                self._handle_restart()

    def _handle_restart(self):
        if self.state.status not in ("builder_wins", "climber_wins"):
            return
        # Flip roles: builder becomes climber and vice versa
        b_sock = self.clients.get("builder")
        c_sock = self.clients.get("climber")
        b_name = self.usernames.get("builder")
        c_name = self.usernames.get("climber")
        self.clients   = {}
        self.usernames = {}
        if b_sock: self.clients["climber"]   = b_sock; self.usernames["climber"]   = b_name
        if c_sock: self.clients["builder"]   = c_sock; self.usernames["builder"]   = c_name
        # Notify each client of their new role
        for role, sock in list(self.clients.items()):
            try:
                send_msg(sock, {"type": "role", "role": role, "username": self.usernames[role]})
            except Exception:
                pass
        self.state = GameState()
        self.state.status = "playing"
        self.state.start_time = time.time()
        self._broadcast({"type": "start"})
        self._broadcast({"type": "state", "data": self.state.to_dict()})
        threading.Thread(target=self._game_loop, daemon=True).start()

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
