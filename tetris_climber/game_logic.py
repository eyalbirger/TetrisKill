import random
import copy
from constants import *


def _rotate_matrix(matrix):
    return [list(row) for row in zip(*matrix[::-1])]


class Piece:
    def __init__(self, kind=None):
        self.kind = kind or random.choice(list(TETROMINOES.keys()))
        self.matrix = [row[:] for row in TETROMINOES[self.kind]]
        self.x = BOARD_COLS // 2 - len(self.matrix[0]) // 2
        self.y = 0
        self.rotation = 0

    def cells(self, dx=0, dy=0, matrix=None):
        m = matrix or self.matrix
        return [
            (self.x + c + dx, self.y + r + dy)
            for r, row in enumerate(m)
            for c, v in enumerate(row) if v
        ]

    def to_dict(self):
        return {"kind": self.kind, "x": self.x, "y": self.y,
                "rotation": self.rotation, "matrix": self.matrix}

    @classmethod
    def from_dict(cls, d):
        p = cls(d["kind"])
        p.x, p.y, p.rotation, p.matrix = d["x"], d["y"], d["rotation"], d["matrix"]
        return p


class Board:
    def __init__(self):
        self.grid = [["" for _ in range(BOARD_COLS)] for _ in range(BOARD_ROWS)]

    def is_valid(self, cells):
        for x, y in cells:
            if x < 0 or x >= BOARD_COLS or y >= BOARD_ROWS:
                return False
            if y >= 0 and self.grid[y][x]:
                return False
        return True

    def lock(self, piece):
        for x, y in piece.cells():
            if 0 <= y < BOARD_ROWS and 0 <= x < BOARD_COLS:
                self.grid[y][x] = piece.kind

    def clear_lines(self):
        new_grid = [row for row in self.grid if not all(row)]
        cleared = BOARD_ROWS - len(new_grid)
        self.grid = [["" for _ in range(BOARD_COLS)] for _ in range(cleared)] + new_grid
        return cleared

    def cell_filled(self, col, row):
        if row < 0:
            return False
        if row >= BOARD_ROWS:
            return True
        if col < 0 or col >= BOARD_COLS:
            return True
        return bool(self.grid[row][col])

    def to_list(self):
        return [row[:] for row in self.grid]

    @classmethod
    def from_list(cls, data):
        b = cls()
        b.grid = data
        return b


class Climber:
    def __init__(self):
        self.x = BOARD_COLS / 2.0   # float, center in cells
        self.y = float(BOARD_ROWS - 2)  # start near bottom
        self.vx = 0.0
        self.vy = 0.0
        self.on_ground = False
        self.alive = True

    def update(self, board: Board, keys: dict):
        if not self.alive:
            return

        # Horizontal input
        if keys.get("left"):
            self.vx = -WALK_SPEED * CELL_SIZE
        elif keys.get("right"):
            self.vx = WALK_SPEED * CELL_SIZE
        else:
            self.vx = 0.0

        # Jump
        if keys.get("jump") and self.on_ground:
            self.vy = JUMP_FORCE * CELL_SIZE

        # Gravity
        self.vy += GRAVITY * CELL_SIZE
        if self.vy > MAX_FALL_SPEED * CELL_SIZE:
            self.vy = MAX_FALL_SPEED * CELL_SIZE

        # Move X
        new_x = self.x + self.vx / TICK_RATE
        half_w = CLIMBER_WIDTH / 2
        left_col = int(new_x - half_w)
        right_col = int(new_x + half_w)
        top_row = int(self.y - CLIMBER_HEIGHT + 0.01)
        bot_row = int(self.y)
        x_blocked = (
            board.cell_filled(left_col, top_row) or board.cell_filled(left_col, bot_row) or
            board.cell_filled(right_col, top_row) or board.cell_filled(right_col, bot_row)
        )
        if not x_blocked and 0 < new_x < BOARD_COLS:
            self.x = new_x

        # Move Y
        new_y = self.y + self.vy / TICK_RATE
        self.on_ground = False

        if self.vy >= 0:  # falling
            feet_row = int(new_y)
            left_col_cur = int(self.x - half_w)
            right_col_cur = int(self.x + half_w - 0.01)
            if board.cell_filled(left_col_cur, feet_row) or board.cell_filled(right_col_cur, feet_row):
                # Land on top of block
                self.y = float(feet_row)
                self.vy = 0.0
                self.on_ground = True
            else:
                self.y = new_y
        else:  # moving up
            head_row = int(new_y - CLIMBER_HEIGHT)
            left_col_cur = int(self.x - half_w)
            right_col_cur = int(self.x + half_w - 0.01)
            if board.cell_filled(left_col_cur, head_row) or board.cell_filled(right_col_cur, head_row):
                self.y = float(head_row + 1) + CLIMBER_HEIGHT
                self.vy = 0.0
            else:
                self.y = new_y

        # Keep climber above floor
        if self.y >= BOARD_ROWS:
            self.y = float(BOARD_ROWS - 1)
            self.vy = 0.0
            self.on_ground = True

    def is_crushed(self, board: Board) -> bool:
        half_w = CLIMBER_WIDTH / 2
        cols = set(range(int(self.x - half_w), int(self.x + half_w) + 1))
        rows = set(range(int(self.y - CLIMBER_HEIGHT + 0.5), int(self.y) + 1))
        for col in cols:
            for row in rows:
                if 0 <= row < BOARD_ROWS and 0 <= col < BOARD_COLS:
                    if board.grid[row][col]:
                        return True
        return False

    def to_dict(self):
        return {"x": self.x, "y": self.y, "vx": self.vx, "vy": self.vy,
                "on_ground": self.on_ground, "alive": self.alive}

    @classmethod
    def from_dict(cls, d):
        c = cls()
        c.x, c.y, c.vx, c.vy = d["x"], d["y"], d["vx"], d["vy"]
        c.on_ground, c.alive = d["on_ground"], d["alive"]
        return c


class GameState:
    def __init__(self):
        self.board = Board()
        self.current_piece = Piece()
        self.next_piece = Piece()
        self.climber = Climber()
        self.score = 0
        self.lines = 0
        self.level = 1
        self.tick = 0
        self.lock_ticks = 0
        self.locking = False
        self.status = "waiting"   # waiting | playing | builder_wins | climber_wins
        self.start_time = None
        self.duration = 0.0
        self.builder_keys: dict = {}
        self.climber_keys: dict = {}

    def fall_interval(self):
        return max(1, FALL_TICKS_BASE - (self.level - 1) * 5)

    def _try_move(self, dx, dy):
        cells = self.current_piece.cells(dx, dy)
        if self.board.is_valid(cells):
            self.current_piece.x += dx
            self.current_piece.y += dy
            return True
        return False

    def _try_rotate(self):
        new_matrix = _rotate_matrix(self.current_piece.matrix)
        new_rot = (self.current_piece.rotation + 1) % 4
        kicks = WALL_KICKS["I"] if self.current_piece.kind == "I" else WALL_KICKS["normal"]
        kick_set = kicks[self.current_piece.rotation]
        for dx, dy in kick_set:
            cells = self.current_piece.cells(dx, -dy, new_matrix)
            if self.board.is_valid(cells):
                self.current_piece.x += dx
                self.current_piece.y -= dy
                self.current_piece.matrix = new_matrix
                self.current_piece.rotation = new_rot
                return True
        return False

    def _lock_piece(self):
        self.board.lock(self.current_piece)
        if self.climber.is_crushed(self.board):
            self.climber.alive = False
            self.status = "builder_wins"
            return
        cleared = self.board.clear_lines()
        if cleared:
            points = [0, 100, 300, 500, 800][cleared] * self.level
            self.score += points
            self.lines += cleared
            self.level = self.lines // 10 + 1
        self.current_piece = self.next_piece
        self.next_piece = Piece()
        self.locking = False
        self.lock_ticks = 0
        if not self.board.is_valid(self.current_piece.cells()):
            self.status = "builder_wins"

    def _ghost_y(self):
        dy = 0
        while self.board.is_valid(self.current_piece.cells(0, dy + 1)):
            dy += 1
        return self.current_piece.y + dy

    def apply_builder_action(self, action: str):
        if self.status != "playing":
            return
        if action == "left":
            self._try_move(-1, 0)
        elif action == "right":
            self._try_move(1, 0)
        elif action == "rotate":
            self._try_rotate()
        elif action == "soft_drop":
            if self._try_move(0, 1):
                self.score += 1
        elif action == "hard_drop":
            dy = 0
            while self._try_move(0, 1):
                dy += 1
                self.score += 2
            self._lock_piece()

    def tick_update(self, import_time):
        if self.status != "playing":
            return

        self.tick += 1
        self.duration = import_time - self.start_time

        # Climber update
        self.climber.update(self.board, self.climber_keys)

        # Check climber win
        if self.climber.y - CLIMBER_HEIGHT <= WIN_ROW:
            self.status = "climber_wins"
            return

        # Tetris gravity
        can_fall = self.board.is_valid(self.current_piece.cells(0, 1))
        if can_fall:
            self.locking = False
            self.lock_ticks = 0
            if self.tick % self.fall_interval() == 0:
                self._try_move(0, 1)
        else:
            self.locking = True
            self.lock_ticks += 1
            if self.lock_ticks >= LOCK_DELAY_TICKS:
                self._lock_piece()

    def to_dict(self):
        return {
            "board": self.board.to_list(),
            "piece": self.current_piece.to_dict(),
            "next_piece": self.next_piece.to_dict(),
            "ghost_y": self._ghost_y(),
            "climber": self.climber.to_dict(),
            "score": self.score,
            "lines": self.lines,
            "level": self.level,
            "status": self.status,
            "duration": round(self.duration, 2),
        }
