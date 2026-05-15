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
SIDEBAR_W  = 300
WINDOW_W   = BOARD_PX_W + SIDEBAR_W
WINDOW_H   = BOARD_PX_H

# ── Light-mode UI palette ─────────────────────────────────────────────────────
UI = {
    "bg":           (238, 240, 248),   # main background
    "sidebar_bg":   (222, 226, 238),   # sidebar panel
    "card_bg":      (232, 236, 248),   # role / info card
    "card_hover":   (210, 216, 240),   # card on hover
    "card_taken":   (225, 226, 232),   # unavailable card
    "input_bg":     (250, 251, 255),   # text-field fill
    "text":         (22,  24,  40),    # primary text
    "text_dim":     (85,  90, 120),    # secondary text
    "text_faint":   (145, 150, 172),   # hint / controls text
    "accent":       (150, 100,   0),   # gold title (visible on light bg)
    "sep":          (185, 190, 208),   # divider lines
    "error":        (195,  35,  35),   # error messages
    "btn":          ( 42, 148,  70),   # submit button
    "btn_hover":    ( 32, 118,  55),
    "cooldown_bg":  (195, 198, 212),
    "cooldown_bar": (190,  50,  50),
}

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

# ── Sprite animation ──────────────────────────────────────────────────────────
# Source frame size (pixels in the PNG sheets)
_SRC_W, _SRC_H = 64, 80
# Display size — scale proportionally so height = 3 cells
_DSP_H = CELL_SIZE * 3          # 96 px
_DSP_W = _DSP_H * _SRC_W // _SRC_H  # 76 px  (preserves aspect ratio)

# (n_frames, anim_fps, asset_path)
_ANIM_DEF = {
    "idle":     (6,  7, "assets/stickman_idle.png"),
    "run":      (8, 14, "assets/stickman_run.png"),
    "jump":     (1,  1, "assets/stickman_jump.png"),
    "fall":     (1,  1, "assets/stickman_fall.png"),
    "death":    (8,  8, "assets/stickman_death.png"),
    "wallhold": (1,  1, "assets/stickman_wallhold.png"),
}

# Populated by load_sprites(); each entry: (fps, [(normal, flipped), ...])
_sprites: dict = {}
_facing_right = True
_death_start_frame: int | None = None


def load_sprites():
    """Load and pre-scale every animation strip. Call once after pygame.init()."""
    global _sprites
    for state, (n_frames, fps, path) in _ANIM_DEF.items():
        try:
            sheet = pygame.image.load(path).convert_alpha()
        except Exception as e:
            print(f"[sprites] could not load {path}: {e}")
            _sprites[state] = None
            continue
        pairs = []
        for i in range(n_frames):
            src  = pygame.Rect(i * _SRC_W, 0, _SRC_W, _SRC_H)
            cell = sheet.subsurface(src)
            norm = pygame.transform.smoothscale(cell, (_DSP_W, _DSP_H))
            flip = pygame.transform.flip(norm, True, False)
            pairs.append((norm, flip))
        _sprites[state] = (fps, pairs)


def _climber_anim_state(climber) -> str:
    if not climber.get("alive", True):
        return "death"
    on_wall = climber.get("on_wall", 0)
    on_ground = climber.get("on_ground", False)
    vy = climber.get("vy", 0)
    vx = climber.get("vx", 0)
    if not on_ground:
        if on_wall != 0:
            return "wallhold"
        return "fall" if vy > 0.02 else "jump"
    return "run" if abs(vx) > 0.01 else "idle"


def draw_climber(surf, climber, frame: int):
    global _facing_right, _death_start_frame

    cx = int(climber["x"] * CELL_SIZE)
    cy = int(climber["y"] * CELL_SIZE)

    # Track facing direction from horizontal velocity
    vx = climber.get("vx", 0)
    on_wall = climber.get("on_wall", 0)
    if vx > 0.01:
        _facing_right = True
    elif vx < -0.01:
        _facing_right = False
    elif on_wall == 1:   # pressing against right wall
        _facing_right = True
    elif on_wall == -1:  # pressing against left wall
        _facing_right = False

    state = _climber_anim_state(climber)

    # Track when death animation began
    if state == "death":
        if _death_start_frame is None:
            _death_start_frame = frame
    else:
        _death_start_frame = None

    # ── Sprite render ──────────────────────────────────────────────────────────
    entry = _sprites.get(state)
    if entry is None:
        # Fallback rectangle if asset failed to load
        h = int(CLIMBER_HEIGHT * CELL_SIZE)
        w = int(CLIMBER_WIDTH  * CELL_SIZE)
        pygame.draw.rect(surf, COLORS["climber"],
                         pygame.Rect(cx - w // 2, cy - h, w, h), border_radius=4)
        return

    fps, pairs = entry
    n = len(pairs)

    if state == "death":
        elapsed = frame - (_death_start_frame or frame)
        fi = min(elapsed * fps // 60, n - 1)   # play once, hold last frame
    else:
        fi = (frame * fps // 60) % n           # loop

    norm, flip = pairs[fi]
    img = norm if _facing_right else flip

    # Align bottom-centre of sprite to climber's foot position
    surf.blit(img, (cx - _DSP_W // 2, cy - _DSP_H))

def draw_sidebar(surf, font, small_font, state, role, username):
    ox = BOARD_PX_W + 10
    y = 10
    def text(s, f=None, color=None):
        nonlocal y
        img = (f or font).render(s, True, color or UI["text"])
        surf.blit(img, (ox, y))
        y += img.get_height() + 4

    text(f"Role: {role.upper()}", color=COLORS["climber"] if role=="climber" else (60,120,210))
    text(f"User: {username}", small_font, UI["text_dim"])
    y += 10
    text(f"Score: {state.get('score', 0)}")
    text(f"Lines: {state.get('lines', 0)}")
    text(f"Level: {state.get('level', 1)}")
    text(f"Time:  {state.get('duration', 0):.1f}s")
    y += 10

    # Next piece preview
    text("Next:", small_font, UI["text_dim"])
    next_p = state.get("next_piece")
    if next_p:
        for r, row in enumerate(next_p["matrix"]):
            for c, v in enumerate(row):
                if v:
                    rect = pygame.Rect(ox + c*18, y + r*18, 16, 16)
                    pygame.draw.rect(surf, COLORS[next_p["kind"]], rect)
                    pygame.draw.rect(surf, UI["sep"], rect, 1)
        y += len(next_p["matrix"]) * 18 + 8

    # Controls
    y += 10
    if role == "builder":
        controls = ["← → Move piece","↑ Rotate","↓ Hold to soft drop"]
    else:
        controls = ["← → / A D Walk","Space / ↑ / W Jump","Jump into block to break"]
        cd = state.get("climber", {}).get("break_cooldown", 0)
        if cd > 0:
            pct = cd / 30
            bar_w = SIDEBAR_W - 20
            pygame.draw.rect(surf, UI["cooldown_bg"],  pygame.Rect(ox, y, bar_w, 8))
            pygame.draw.rect(surf, UI["cooldown_bar"], pygame.Rect(ox, y, int(bar_w * pct), 8))
            y += 12
    text("Controls:", small_font, UI["text_faint"])
    for c in controls:
        text(c, small_font, UI["text_faint"])

def draw_leaderboard(surf, font, small_font, lb):
    surf.fill(UI["bg"])
    title_font = pygame.font.SysFont("monospace", 28, bold=True)
    y = 30
    def text(s, f=None, color=None, center=False):
        nonlocal y
        img = (f or font).render(s, True, color or UI["text"])
        x = WINDOW_W // 2 - img.get_width() // 2 if center else 30
        surf.blit(img, (x, y))
        y += img.get_height() + 4

    text("LEADERBOARD", title_font, UI["accent"], center=True)
    y += 10

    half = WINDOW_W // 2
    def col_board(entries, label, color, x_off):
        nonlocal y
        ly = y
        img = font.render(label, True, color)
        surf.blit(img, (x_off, ly)); ly += img.get_height() + 6
        header = small_font.render(f"{'#':<3} {'Name':<14} {'Best':>8} {'Wins':>5}", True, UI["text_dim"])
        surf.blit(header, (x_off, ly)); ly += header.get_height() + 2
        pygame.draw.line(surf, UI["sep"], (x_off, ly), (x_off + half - 40, ly)); ly += 4
        for i, e in enumerate(entries, 1):
            row_s = small_font.render(
                f"{i:<3} {e['name']:<14} {e['best_time']:>7.2f}s {e['wins']:>4}",
                True, UI["text"]
            )
            surf.blit(row_s, (x_off, ly)); ly += row_s.get_height() + 2
        return ly

    r1 = col_board(lb.get("builders", []), "BUILDERS", (60, 120, 210), 20)
    r2 = col_board(lb.get("climbers", []), "CLIMBERS", COLORS["climber"], half + 20)
    y = max(r1, r2) + 10

def draw_overlay(surf, font, message, sub=""):
    overlay = pygame.Surface((WINDOW_W, WINDOW_H), pygame.SRCALPHA)
    overlay.fill((255, 255, 255, 180))
    surf.blit(overlay, (0, 0))
    img = font.render(message, True, UI["accent"])
    surf.blit(img, (WINDOW_W//2 - img.get_width()//2, WINDOW_H//2 - 40))
    if sub:
        sf = pygame.font.SysFont("monospace", 18)
        img2 = sf.render(sub, True, UI["text_dim"])
        surf.blit(img2, (WINDOW_W//2 - img2.get_width()//2, WINDOW_H//2 + 10))

# ── Auth UI ───────────────────────────────────────────────────────────────────

def auth_screen(screen, font, small_font):
    fields = {"username": "", "password": ""}
    focused = "username"
    mode = "login"  # or "register"
    error = ""
    clock = pygame.time.Clock()

    while True:
        screen.fill(UI["bg"])
        title = font.render("TETRIS CLIMBER", True, UI["accent"])
        screen.blit(title, (WINDOW_W//2 - title.get_width()//2, 40))

        labels = {"login": "Login", "register": "Register"}
        mx, my = pygame.mouse.get_pos()

        # Mode tabs
        for i, (m, label) in enumerate(labels.items()):
            x = WINDOW_W//2 - 100 + i*120
            color = UI["accent"] if mode == m else UI["text_faint"]
            img = font.render(label, True, color)
            screen.blit(img, (x, 100))

        # Input fields
        for fi, (fname, fval) in enumerate(fields.items()):
            fy = 170 + fi * 70
            label_img = small_font.render(fname.capitalize() + ":", True, UI["text_dim"])
            screen.blit(label_img, (WINDOW_W//2 - 140, fy - 22))
            rect = pygame.Rect(WINDOW_W//2 - 140, fy, 280, 36)
            border_col = (70, 100, 200) if focused == fname else UI["sep"]
            pygame.draw.rect(screen, UI["input_bg"], rect, border_radius=4)
            pygame.draw.rect(screen, border_col, rect, 2, border_radius=4)
            display = fval if fname != "password" else "*" * len(fval)
            txt = small_font.render(display, True, UI["text"])
            screen.blit(txt, (rect.x + 8, rect.y + 8))

        # Submit button
        btn_rect = pygame.Rect(WINDOW_W//2 - 80, 330, 160, 40)
        btn_color = UI["btn_hover"] if btn_rect.collidepoint(mx, my) else UI["btn"]
        pygame.draw.rect(screen, btn_color, btn_rect, border_radius=6)
        btn_txt = font.render(mode.capitalize(), True, (255, 255, 255))
        screen.blit(btn_txt, (btn_rect.centerx - btn_txt.get_width()//2, btn_rect.y + 8))

        if error:
            err_img = small_font.render(error, True, UI["error"])
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

# ── Role selection screen ─────────────────────────────────────────────────────

def role_selection_screen(screen, font, small_font, available: list[str]) -> str:
    clock = pygame.time.Clock()
    ROLES = {
        "builder": {
            "color": (100, 180, 255),
            "desc1": "Place Tetris pieces to build the board.",
            "desc2": "Crush the Climber to win!",
            "key": "1",
        },
        "climber": {
            "color": COLORS["climber"],
            "desc1": "Jump and climb to the top of the board.",
            "desc2": "Reach the yellow line to win!",
            "key": "2",
        },
    }
    while True:
        screen.fill(UI["bg"])
        title = font.render("CHOOSE YOUR ROLE", True, UI["accent"])
        screen.blit(title, (WINDOW_W // 2 - title.get_width() // 2, 60))

        mx, my = pygame.mouse.get_pos()
        hovered = None

        for i, role in enumerate(("builder", "climber")):
            info = ROLES[role]
            taken = role not in available
            rx = WINDOW_W // 2 - 180
            ry = 140 + i * 160
            rect = pygame.Rect(rx, ry, 360, 130)

            if taken:
                bg, border, tc = UI["card_taken"], UI["sep"], UI["text_faint"]
            elif rect.collidepoint(mx, my):
                bg, border, tc = UI["card_hover"], info["color"], info["color"]
                hovered = role
            else:
                bg, border, tc = UI["card_bg"], UI["sep"], info["color"]

            pygame.draw.rect(screen, bg, rect, border_radius=10)
            pygame.draw.rect(screen, border, rect, 2, border_radius=10)

            lbl = font.render(
                f"[{info['key']}]  {role.upper()}" + ("  (taken)" if taken else ""),
                True, tc
            )
            screen.blit(lbl, (rect.x + 16, rect.y + 14))
            for j, line in enumerate((info["desc1"], info["desc2"])):
                desc_col = UI["text_faint"] if taken else UI["text_dim"]
                t = small_font.render(line, True, desc_col)
                screen.blit(t, (rect.x + 16, rect.y + 52 + j * 22))

        pygame.display.flip()
        clock.tick(60)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit(); sys.exit()
            if event.type == pygame.MOUSEBUTTONDOWN and hovered:
                return hovered
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_1 and "builder" in available:
                    return "builder"
                if event.key == pygame.K_2 and "climber" in available:
                    return "climber"


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
            try:
                with self.recv_lock:
                    self._handle(msg)
            except Exception as e:
                print(f"[client] handle error: {e}")

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
        elif t == "role":
            self.role = msg["role"]
        elif t == "start":
            self.state = {**self.state, "status": "playing"}
            self.game_over_info = None   # clear on restart


def main():
    host = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1"

    pygame.init()
    screen = pygame.display.set_mode((WINDOW_W, WINDOW_H))
    pygame.display.set_caption("Tetris Climber")
    font = pygame.font.SysFont("monospace", 22, bold=True)
    small_font = pygame.font.SysFont("monospace", 15)
    clock = pygame.time.Clock()
    load_sprites()

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
                screen.fill(UI["bg"])
                err = font.render(error, True, UI["error"])
                screen.blit(err, (WINDOW_W//2 - err.get_width()//2, WINDOW_H//2))
                pygame.display.flip()
                pygame.time.wait(2000)
                client = GameClient(host)
                continue
        except Exception as e:
            screen.fill(UI["bg"])
            err = font.render(f"Cannot connect: {e}", True, UI["error"])
            screen.blit(err, (WINDOW_W//2 - err.get_width()//2, WINDOW_H//2))
            pygame.display.flip()
            pygame.time.wait(2000)
            client = GameClient(host)
            continue

        # Role selection
        avail_msg = recv_msg(client.sock)
        if not avail_msg or avail_msg.get("type") != "roles_available":
            continue
        available = avail_msg["available"]
        if len(available) == 1:
            chosen = available[0]   # only one slot left, no choice needed
        else:
            chosen = role_selection_screen(screen, font, small_font, available)
        client.send({"type": "choose_role", "role": chosen})

        # Confirmed role from server
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
        screen.fill(UI["bg"])
        role_color = COLORS["climber"] if client.role == "climber" else (60, 120, 210)
        msg = font.render(f"You are the {client.role.upper()}", True, role_color)
        wait = small_font.render("Waiting for second player...", True, UI["text_faint"])
        screen.blit(msg, (WINDOW_W//2 - msg.get_width()//2, WINDOW_H//2 - 30))
        screen.blit(wait, (WINDOW_W//2 - wait.get_width()//2, WINDOW_H//2 + 10))

        pygame.display.flip()
        clock.tick(30)
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit(); sys.exit()

    # Climber held keys
    climber_keys = {"left": False, "right": False, "jump": False}
    jump_pressed = False

    # Builder held keys + DAS (Delayed Auto Shift)
    b_held = {"left": False, "right": False, "down": False}
    b_das  = {"left": 0,     "right": 0}
    DAS, ARR = 10, 2   # frames: initial delay, then repeat every ARR frames

    # Main game loop
    last_key_send = 0
    showing_gameover = False
    frame = 0

    while client.connected:
        playing = client.state.get("status") == "playing"

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit(); sys.exit()

            # ── Builder events ────────────────────────────────────────────────
            if client.role == "builder":
                if event.type == pygame.KEYDOWN and playing:
                    if event.key == pygame.K_LEFT:
                        client.send({"type": "action", "action": "left"})
                        b_held["left"] = True;  b_das["left"] = 0
                    elif event.key == pygame.K_RIGHT:
                        client.send({"type": "action", "action": "right"})
                        b_held["right"] = True; b_das["right"] = 0
                    elif event.key == pygame.K_UP:
                        client.send({"type": "action", "action": "rotate"})
                    elif event.key == pygame.K_DOWN:
                        b_held["down"] = True
                # KEYUP always processed so held state stays accurate when game ends
                if event.type == pygame.KEYUP:
                    if event.key == pygame.K_LEFT:  b_held["left"]  = False
                    if event.key == pygame.K_RIGHT: b_held["right"] = False
                    if event.key == pygame.K_DOWN:  b_held["down"]  = False

            # ── Climber events ────────────────────────────────────────────────
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

        # ── Builder auto-repeat (DAS/ARR) ─────────────────────────────────────
        if client.role == "builder" and playing:
            for direction in ("left", "right"):
                if b_held[direction]:
                    b_das[direction] += 1
                    d = b_das[direction]
                    if d > DAS and (d - DAS) % ARR == 0:
                        client.send({"type": "action", "action": direction})
                else:
                    b_das[direction] = 0
            if b_held["down"] and frame % 4 == 0:
                client.send({"type": "action", "action": "soft_drop"})

        # ── Climber key broadcast ─────────────────────────────────────────────
        if client.role == "climber" and playing:
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

        screen.fill(UI["bg"])

        if go_info and not showing_gameover:
            showing_gameover = True

        if state.get("board"):
            draw_board(screen, state["board"])
            draw_win_line(screen)
            if state.get("piece") and state.get("status") == "playing":
                draw_piece(screen, state["piece"], state.get("ghost_y"))
            if state.get("climber"):
                draw_climber(screen, state["climber"], frame)

        # Sidebar background
        pygame.draw.rect(screen, UI["sidebar_bg"], pygame.Rect(BOARD_PX_W, 0, SIDEBAR_W, WINDOW_H))
        draw_sidebar(screen, font, small_font, state, client.role, client.username)

        if state.get("status") == "waiting":
            draw_overlay(screen, font, "Waiting for opponent...")
        elif showing_gameover:
            # If game restarted (server cleared game_over_info), resume
            if go_info is None:
                showing_gameover = False
                # Clean slate for next game — clear every held state
                b_held["left"] = b_held["right"] = b_held["down"] = False
                b_das["left"]  = b_das["right"]  = 0
                climber_keys["left"] = climber_keys["right"] = climber_keys["jump"] = False
                jump_pressed = False
            else:
                you_won = go_info.get("winner", "") == client.username
                msg = "YOU WIN!" if you_won else "YOU LOSE"
                sub = (f"{go_info.get('winner','')} wins in {go_info.get('duration',0):.2f}s"
                       f"  |  R = play again   Q = quit")
                draw_overlay(screen, font, msg, sub)
                pressed = pygame.key.get_pressed()
                if pressed[pygame.K_r]:
                    client.send({"type": "restart"})
                if pressed[pygame.K_q]:
                    pygame.quit(); sys.exit()

        pygame.display.flip()
        clock.tick(60)
        frame += 1


if __name__ == "__main__":
    main()
