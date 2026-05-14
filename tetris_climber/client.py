#!/usr/bin/env python3
import pygame
import socket
import threading
import json
import struct
import sys
import time

from constants import *

# ── Network helpers ───────────────────────────────────────────────────────────

def send_msg(sock, data: dict):
    payload = json.dumps(data).encode()
    sock.sendall(struct.pack(">I", len(payload)) + payload)

def recv_msg(sock) -> dict | None:
    try:
        raw = _recvall(sock, 4)
        if not raw:
            return None
        length = struct.unpack(">I", raw)[0]
        return json.loads(_recvall(sock, length))
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

# ── Drawing helpers ───────────────────────────────────────────────────────────

BOARD_PX_W = BOARD_COLS * CELL_SIZE
BOARD_PX_H = BOARD_ROWS * CELL_SIZE
SIDEBAR_W  = 200
WINDOW_W   = BOARD_PX_W + SIDEBAR_W
WINDOW_H   = BOARD_PX_H

def board_origin():
    return (0, 0)

def cell_rect(col, row):
    ox, oy = board_origin()
    return pygame.Rect(ox + col * CELL_SIZE, oy + row * CELL_SIZE, CELL_SIZE, CELL_SIZE)

def draw_board(surf, board_data):
    ox, oy = board_origin()
    bg = pygame.Rect(ox, oy, BOARD_PX_W, BOARD_PX_H)
    pygame.draw.rect(surf, COLORS["empty"], bg)
    for row in range(BOARD_ROWS):
        for col in range(BOARD_COLS):
            cell = board_data[row][col]
            r = cell_rect(col, row)
            if cell:
                pygame.draw.rect(surf, COLORS[cell], r)
                pygame.draw.rect(surf, (0, 0, 0), r, 1)
            else:
                pygame.draw.rect(surf, COLORS["grid"], r, 1)

def draw_piece(surf, piece, ghost_y=None, alpha=255):
    if ghost_y is not None:
        for x, y in _piece_cells(piece, 0, ghost_y - piece["y"]):
            if y >= 0:
                r = cell_rect(x, y)
                s = pygame.Surface((CELL_SIZE, CELL_SIZE), pygame.SRCALPHA)
                s.fill((*COLORS["ghost"], 80))
                surf.blit(s, r)
    for x, y in _piece_cells(piece, 0, 0):
        if y >= 0:
            r = cell_rect(x, y)
            pygame.draw.rect(surf, COLORS[piece["kind"]], r)
            pygame.draw.rect(surf, (0,0,0), r, 1)

def _piece_cells(piece, dx=0, dy=0):
    return [
        (piece["x"] + c + dx, piece["y"] + r + dy)
        for r, row in enumerate(piece["matrix"])
        for c, v in enumerate(row) if v
    ]

def draw_win_line(surf):
    y = WIN_ROW * CELL_SIZE
    pygame.draw.line(surf, COLORS["win_line"], (0, y), (BOARD_PX_W, y), 2)

def draw_climber(surf, climber):
    if not climber["alive"]:
        return
    cx = climber["x"] * CELL_SIZE
    cy = climber["y"] * CELL_SIZE
    h = CLIMBER_HEIGHT * CELL_SIZE
    w = CLIMBER_WIDTH * CELL_SIZE
    body = pygame.Rect(int(cx - w/2), int(cy - h), int(w), int(h))
    pygame.draw.rect(surf, COLORS["climber"], body, border_radius=4)
    # eyes
    eye_y = int(cy - h * 0.75)
    pygame.draw.circle(surf, (0,0,0), (int(cx - w*0.15), eye_y), 3)
    pygame.draw.circle(surf, (0,0,0), (int(cx + w*0.15), eye_y), 3)

def draw_sidebar(surf, font, small_font, state, role, username):
    ox = BOARD_PX_W + 10
    y = 10
    def text(s, f=None, color=(220,220,220)):
        nonlocal y
        img = (f or font).render(s, True, color)
        surf.blit(img, (ox, y))
        y += img.get_height() + 4

    text(f"Role: {role.upper()}", color=COLORS["climber"] if role=="climber" else (100,180,255))
    text(f"User: {username}", small_font)
    y += 10
    text(f"Score: {state.get('score', 0)}")
    text(f"Lines: {state.get('lines', 0)}")
    text(f"Level: {state.get('level', 1)}")
    text(f"Time:  {state.get('duration', 0):.1f}s")
    y += 10

    # Next piece preview
    text("Next:", small_font)
    next_p = state.get("next_piece")
    if next_p:
        for r, row in enumerate(next_p["matrix"]):
            for c, v in enumerate(row):
                if v:
                    rect = pygame.Rect(ox + c*18, y + r*18, 16, 16)
                    pygame.draw.rect(surf, COLORS[next_p["kind"]], rect)
        y += len(next_p["matrix"]) * 18 + 8

    # Controls
    y += 10
    if role == "builder":
        controls = ["← → Move","↑ Rotate","↓ Soft drop","Space Hard drop"]
    else:
        controls = ["← → Walk","Space / ↑ Jump"]
    text("Controls:", small_font, (150,150,150))
    for c in controls:
        text(c, small_font, (120,120,120))

def draw_leaderboard(surf, font, small_font, lb):
    surf.fill((15, 15, 25))
    title_font = pygame.font.SysFont("monospace", 28, bold=True)
    y = 30
    def text(s, f=None, color=(220,220,220), center=False):
        nonlocal y
        img = (f or font).render(s, True, color)
        x = WINDOW_W // 2 - img.get_width() // 2 if center else 30
        surf.blit(img, (x, y))
        y += img.get_height() + 4

    text("LEADERBOARD", title_font, (255,220,0), center=True)
    y += 10

    half = WINDOW_W // 2
    def col_board(entries, label, color, x_off):
        nonlocal y
        ly = y
        img = font.render(label, True, color)
        surf.blit(img, (x_off, ly)); ly += img.get_height() + 6
        header = small_font.render(f"{'#':<3} {'Name':<14} {'Best':>8} {'Wins':>5}", True, (160,160,160))
        surf.blit(header, (x_off, ly)); ly += header.get_height() + 2
        pygame.draw.line(surf, (80,80,80), (x_off, ly), (x_off + half - 40, ly)); ly += 4
        for i, e in enumerate(entries, 1):
            row_s = small_font.render(
                f"{i:<3} {e['name']:<14} {e['best_time']:>7.2f}s {e['wins']:>4}",
                True, (220,220,220)
            )
            surf.blit(row_s, (x_off, ly)); ly += row_s.get_height() + 2
        return ly

    r1 = col_board(lb.get("builders", []), "BUILDERS", (100,180,255), 20)
    r2 = col_board(lb.get("climbers", []), "CLIMBERS", COLORS["climber"], half + 20)
    y = max(r1, r2) + 10

def draw_overlay(surf, font, message, sub=""):
    overlay = pygame.Surface((WINDOW_W, WINDOW_H), pygame.SRCALPHA)
    overlay.fill((0,0,0,160))
    surf.blit(overlay, (0,0))
    img = font.render(message, True, (255,220,0))
    surf.blit(img, (WINDOW_W//2 - img.get_width()//2, WINDOW_H//2 - 40))
    if sub:
        sf = pygame.font.SysFont("monospace", 18)
        img2 = sf.render(sub, True, (200,200,200))
        surf.blit(img2, (WINDOW_W//2 - img2.get_width()//2, WINDOW_H//2 + 10))

# ── Auth UI ───────────────────────────────────────────────────────────────────

def auth_screen(screen, font, small_font):
    fields = {"username": "", "password": ""}
    focused = "username"
    mode = "login"  # or "register"
    error = ""
    clock = pygame.time.Clock()

    while True:
        screen.fill((15, 15, 25))
        title = font.render("TETRIS CLIMBER", True, (255, 220, 0))
        screen.blit(title, (WINDOW_W//2 - title.get_width()//2, 40))

        labels = {"login": "Login", "register": "Register"}
        mx, my = pygame.mouse.get_pos()

        # Mode tabs
        for i, (m, label) in enumerate(labels.items()):
            x = WINDOW_W//2 - 100 + i*120
            color = (255,220,0) if mode == m else (120,120,120)
            img = font.render(label, True, color)
            screen.blit(img, (x, 100))

        # Input fields
        for fi, (fname, fval) in enumerate(fields.items()):
            fy = 170 + fi * 70
            label_img = small_font.render(fname.capitalize() + ":", True, (180,180,180))
            screen.blit(label_img, (WINDOW_W//2 - 140, fy - 22))
            rect = pygame.Rect(WINDOW_W//2 - 140, fy, 280, 36)
            color = (255,255,255) if focused == fname else (100,100,120)
            pygame.draw.rect(screen, (30,30,45), rect)
            pygame.draw.rect(screen, color, rect, 2)
            display = fval if fname != "password" else "*" * len(fval)
            txt = small_font.render(display, True, (220,220,220))
            screen.blit(txt, (rect.x + 8, rect.y + 8))

        # Submit button
        btn_rect = pygame.Rect(WINDOW_W//2 - 80, 330, 160, 40)
        btn_color = (60,180,60) if btn_rect.collidepoint(mx, my) else (40,140,40)
        pygame.draw.rect(screen, btn_color, btn_rect, border_radius=6)
        btn_txt = font.render(mode.capitalize(), True, (255,255,255))
        screen.blit(btn_txt, (btn_rect.centerx - btn_txt.get_width()//2, btn_rect.y + 8))

        if error:
            err_img = small_font.render(error, True, (255, 80, 80))
            screen.blit(err_img, (WINDOW_W//2 - err_img.get_width()//2, 385))

        pygame.display.flip()
        clock.tick(60)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit(); sys.exit()
            if event.type == pygame.MOUSEBUTTONDOWN:
                for fi, fname in enumerate(fields):
                    fy = 170 + fi * 70
                    rect = pygame.Rect(WINDOW_W//2 - 140, fy, 280, 36)
                    if rect.collidepoint(event.pos):
                        focused = fname
                for i, m in enumerate(labels):
                    x = WINDOW_W//2 - 100 + i*120
                    img = font.render(labels[m], True, (255,255,255))
                    if pygame.Rect(x, 100, img.get_width(), img.get_height()).collidepoint(event.pos):
                        mode = m
                if btn_rect.collidepoint(event.pos):
                    return fields["username"], fields["password"], mode
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_TAB:
                    keys = list(fields.keys())
                    focused = keys[(keys.index(focused) + 1) % len(keys)]
                elif event.key == pygame.K_RETURN:
                    return fields["username"], fields["password"], mode
                elif event.key == pygame.K_BACKSPACE:
                    fields[focused] = fields[focused][:-1]
                elif event.unicode and len(fields[focused]) < 20:
                    fields[focused] += event.unicode

# ── Main game client ──────────────────────────────────────────────────────────

class GameClient:
    def __init__(self, host: str):
        self.host = host
        self.sock = None
        self.role = None
        self.username = None
        self.state = {}
        self.leaderboard = {}
        self.game_over_info = None
        self.recv_lock = threading.Lock()
        self.connected = False

    def connect(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.connect((self.host, SERVER_PORT))
        self.connected = True

    def send(self, data):
        try:
            send_msg(self.sock, data)
        except Exception:
            self.connected = False

    def start_recv(self):
        t = threading.Thread(target=self._recv_loop, daemon=True)
        t.start()

    def _recv_loop(self):
        while self.connected:
            msg = recv_msg(self.sock)
            if not msg:
                self.connected = False
                break
            with self.recv_lock:
                self._handle(msg)

    def _handle(self, msg):
        t = msg.get("type")
        if t == "state":
            self.state = msg["data"]
        elif t == "leaderboard":
            self.leaderboard = msg["data"]
        elif t == "game_over":
            self.game_over_info = msg
            if "leaderboard" in msg:
                self.leaderboard = msg["leaderboard"]
        elif t == "start":
            self.state = {**self.state, "status": "playing"}


def main():
    host = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1"

    pygame.init()
    screen = pygame.display.set_mode((WINDOW_W, WINDOW_H))
    pygame.display.set_caption("Tetris Climber")
    font = pygame.font.SysFont("monospace", 22, bold=True)
    small_font = pygame.font.SysFont("monospace", 15)
    clock = pygame.time.Clock()

    client = GameClient(host)

    # Auth loop
    while True:
        username, password, mode = auth_screen(screen, font, small_font)
        if not username or not password:
            continue
        try:
            client.connect()
            client.send({"type": mode, "username": username, "password": password})
            resp = recv_msg(client.sock)
            if not resp or not resp.get("success"):
                error = resp.get("error", "Connection failed") if resp else "No response"
                # Show error then retry
                screen.fill((15,15,25))
                err = font.render(error, True, (255,80,80))
                screen.blit(err, (WINDOW_W//2 - err.get_width()//2, WINDOW_H//2))
                pygame.display.flip()
                pygame.time.wait(2000)
                client = GameClient(host)
                continue
        except Exception as e:
            screen.fill((15,15,25))
            err = font.render(f"Cannot connect: {e}", True, (255,80,80))
            screen.blit(err, (WINDOW_W//2 - err.get_width()//2, WINDOW_H//2))
            pygame.display.flip()
            pygame.time.wait(2000)
            client = GameClient(host)
            continue

        # Get role
        role_msg = recv_msg(client.sock)
        if not role_msg or role_msg.get("type") != "role":
            continue
        client.role = role_msg["role"]
        client.username = role_msg["username"]

        # Get leaderboard
        lb_msg = recv_msg(client.sock)
        if lb_msg and lb_msg.get("type") == "leaderboard":
            client.leaderboard = lb_msg["data"]

        client.start_recv()
        break

    # Waiting screen
    while client.state.get("status") not in ("playing", "builder_wins", "climber_wins") and client.connected:
        screen.fill((15,15,25))
        role_color = COLORS["climber"] if client.role == "climber" else (100,180,255)
        msg = font.render(f"You are the {client.role.upper()}", True, role_color)
        wait = small_font.render("Waiting for second player...", True, (150,150,150))
        screen.blit(msg, (WINDOW_W//2 - msg.get_width()//2, WINDOW_H//2 - 30))
        screen.blit(wait, (WINDOW_W//2 - wait.get_width()//2, WINDOW_H//2 + 10))

        if client.leaderboard:
            draw_leaderboard(screen, font, small_font, client.leaderboard)

        pygame.display.flip()
        clock.tick(30)
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit(); sys.exit()

    # Key state for climber (held keys)
    climber_keys = {"left": False, "right": False, "jump": False}
    jump_pressed = False

    # Main game loop
    last_key_send = 0
    showing_gameover = False

    while client.connected:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit(); sys.exit()

            if client.role == "builder" and client.state.get("status") == "playing":
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_LEFT:
                        client.send({"type": "action", "action": "left"})
                    elif event.key == pygame.K_RIGHT:
                        client.send({"type": "action", "action": "right"})
                    elif event.key == pygame.K_UP:
                        client.send({"type": "action", "action": "rotate"})
                    elif event.key == pygame.K_DOWN:
                        client.send({"type": "action", "action": "soft_drop"})
                    elif event.key == pygame.K_SPACE:
                        client.send({"type": "action", "action": "hard_drop"})

            if client.role == "climber":
                if event.type == pygame.KEYDOWN:
                    if event.key in (pygame.K_LEFT, pygame.K_a):
                        climber_keys["left"] = True
                    elif event.key in (pygame.K_RIGHT, pygame.K_d):
                        climber_keys["right"] = True
                    elif event.key in (pygame.K_SPACE, pygame.K_UP, pygame.K_w):
                        climber_keys["jump"] = True
                        jump_pressed = True
                if event.type == pygame.KEYUP:
                    if event.key in (pygame.K_LEFT, pygame.K_a):
                        climber_keys["left"] = False
                    elif event.key in (pygame.K_RIGHT, pygame.K_d):
                        climber_keys["right"] = False
                    elif event.key in (pygame.K_SPACE, pygame.K_UP, pygame.K_w):
                        climber_keys["jump"] = False

        # Send climber keys at rate limit
        if client.role == "climber" and client.state.get("status") == "playing":
            now = time.time()
            if now - last_key_send > 1.0 / 30:
                client.send({"type": "keys", "keys": climber_keys})
                last_key_send = now
                if jump_pressed:
                    climber_keys["jump"] = False
                    jump_pressed = False

        # Render
        with client.recv_lock:
            state = dict(client.state)
            go_info = client.game_over_info

        screen.fill((15, 15, 25))

        if go_info and not showing_gameover:
            showing_gameover = True

        if state.get("board"):
            draw_board(screen, state["board"])
            draw_win_line(screen)
            if state.get("piece") and state.get("status") == "playing":
                draw_piece(screen, state["piece"], state.get("ghost_y"))
            if state.get("climber"):
                draw_climber(screen, state["climber"])

        # Sidebar background
        pygame.draw.rect(screen, (25, 25, 35), pygame.Rect(BOARD_PX_W, 0, SIDEBAR_W, WINDOW_H))
        draw_sidebar(screen, font, small_font, state, client.role, client.username)

        if state.get("status") == "waiting":
            draw_overlay(screen, font, "Waiting for opponent...")
        elif showing_gameover:
            winner = go_info.get("winner", "")
            status = go_info.get("status", "")
            you_won = winner == client.username
            msg = "YOU WIN!" if you_won else "YOU LOSE"
            sub = f"{winner} wins in {go_info.get('duration',0):.2f}s  |  Press Q to quit"
            draw_overlay(screen, font, msg, sub)
            keys = pygame.key.get_pressed()
            if keys[pygame.K_q]:
                pygame.quit(); sys.exit()

        pygame.display.flip()
        clock.tick(60)


if __name__ == "__main__":
    main()
