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


class _BoardWithPiece:
    """
    Thin read-only view that makes the active falling piece solid for the
    climber's collision and crush checks, without touching the real board grid.
    """
    __slots__ = ("_board", "_cells")

    def __init__(self, board: "Board", piece_cells):
        self._board = board
        self._cells = frozenset(piece_cells)

    def cell_filled(self, col, row):
        if (col, row) in self._cells:
            return True
        return self._board.cell_filled(col, row)

    # Forward every other attribute (grid, is_valid, …) to the real board
    def __getattr__(self, name):
        return getattr(self._board, name)


class Climber:
    def __init__(self):
        self.x = BOARD_COLS / 2.0
        self.y = float(BOARD_ROWS)   # feet start on the floor (y = BOARD_ROWS)
        self.vx = 0.0
        self.vy = 0.0
        self.on_ground = False
        self.alive = True
        self.break_cooldown = 0
        self.on_wall = 0          # -1 = touching left wall, 0 = none, 1 = right wall
        self.wall_jump_lock = 0   # cooldown ticks to prevent chained wall jumps
        self.wj_vx = 0.0          # horizontal kick from last wall jump (persists briefly)

    # ── helpers ───────────────────────────────────────────────────────────────

    def _cols(self):
        half_w = CLIMBER_WIDTH / 2
        c0 = max(0, int(self.x - half_w + 0.001))
        c1 = min(BOARD_COLS - 1, int(self.x + half_w - 0.001))
        return range(c0, c1 + 1)

    def _body_rows(self):
        """Integer rows fully inside the body (excludes the floor row at feet)."""
        r0 = max(0, int(self.y - CLIMBER_HEIGHT + 0.001))
        r1 = min(BOARD_ROWS - 1, int(self.y - 0.001))
        return range(r0, r1 + 1)

    def _blocked(self, board, rows, cols):
        return any(board.cell_filled(c, r) for r in rows for c in cols)

    # ── movement ──────────────────────────────────────────────────────────────

    def _move_x(self, dx, board):
        if dx == 0:
            return
        new_x = self.x + dx
        half_w = CLIMBER_WIDTH / 2
        r0 = max(0, int(self.y - CLIMBER_HEIGHT + 0.001))
        r1 = min(BOARD_ROWS - 1, int(self.y - 0.001))
        body_rows = range(r0, r1 + 1)

        if dx > 0:
            edge_col = int(new_x + half_w)
            if edge_col >= BOARD_COLS:
                self.x = BOARD_COLS - half_w
                return
            if self._blocked(board, body_rows, [edge_col]):
                self.x = edge_col - half_w
            else:
                self.x = new_x
        else:
            edge_col = int(new_x - half_w)
            if edge_col < 0:
                self.x = half_w
                return
            if self._blocked(board, body_rows, [edge_col]):
                self.x = (edge_col + 1) + half_w
            else:
                self.x = new_x

    def _move_y(self, dy, board):
        new_y = self.y + dy
        cols = self._cols()

        if dy >= 0:  # falling / standing still
            # Sweep every row from current feet position to destination feet position.
            # This ensures we land on the TOP of any stack, not partway through it.
            start = int(self.y)
            end   = int(new_y)
            for row in range(start, min(BOARD_ROWS, end + 1)):
                if self._blocked(board, [row], cols):
                    self.y = float(row)
                    self.vy = 0.0
                    self.on_ground = True
                    return
            # Floor
            if new_y >= BOARD_ROWS:
                self.y = float(BOARD_ROWS)
                self.vy = 0.0
                self.on_ground = True
            else:
                self.y = new_y

        else:  # moving up
            curr_head_row = int(self.y - CLIMBER_HEIGHT)
            new_head_row  = int(new_y - CLIMBER_HEIGHT)
            for row in range(curr_head_row - 1, new_head_row - 1, -1):
                if 0 <= row < BOARD_ROWS and self._blocked(board, [row], cols):
                    if self.break_cooldown == 0:
                        # Mario-style: break every PLACED block the head bumps from below.
                        # Falling-piece cells pass cell_filled() but aren't in board.grid,
                        # so they register as a ceiling but don't get cleared.
                        cleared_any = False
                        for col in cols:
                            if board.grid[row][col]:
                                board.grid[row][col] = ""
                                cleared_any = True
                        if cleared_any:
                            self.break_cooldown = BREAK_COOLDOWN_TICKS
                    # Head bounces back regardless of whether a block was broken
                    self.y = float(row + 1) + CLIMBER_HEIGHT
                    self.vy = 0.0
                    return
            self.y = new_y

    # ── wall contact probe ────────────────────────────────────────────────────

    def _update_wall_contact(self, board):
        """
        Set self.on_wall by probing the column immediately outside each side of
        the climber's body.  Board borders produce an out-of-range column index
        and are therefore never detected — only actual blocks count.
        """
        body_rows = self._body_rows()
        half_w = CLIMBER_WIDTH / 2
        # Rightmost / leftmost columns currently occupied by the climber body
        c_right = min(BOARD_COLS - 1, int(self.x + half_w - 0.001))
        c_left  = max(0,              int(self.x - half_w + 0.001))
        right_col = c_right + 1   # column just beyond the right edge
        left_col  = c_left  - 1   # column just beyond the left  edge
        if right_col < BOARD_COLS and self._blocked(board, body_rows, [right_col]):
            self.on_wall = 1
        elif left_col >= 0 and self._blocked(board, body_rows, [left_col]):
            self.on_wall = -1
        else:
            self.on_wall = 0

    # ── main update ───────────────────────────────────────────────────────────

    def update(self, board, keys: dict):
        if not self.alive:
            return

        # Gravity & timers
        self.vy = min(self.vy + GRAVITY, MAX_FALL_SPEED)
        if self.break_cooldown > 0:
            self.break_cooldown -= 1
        if self.wall_jump_lock > 0:
            self.wall_jump_lock -= 1

        # Horizontal input — suppressed for the first 8 ticks after a wall jump
        # so the horizontal kick actually carries the climber away from the wall.
        if self.wall_jump_lock > 10:
            self.vx = self.wj_vx
        else:
            self.wj_vx = 0.0
            self.vx = 0.0
            if keys.get("left"):
                self.vx = -WALK_SPEED
            elif keys.get("right"):
                self.vx = WALK_SPEED

        # Regular jump
        if keys.get("jump") and self.on_ground:
            self.vy = JUMP_FORCE

        self.on_ground = False
        self._move_x(self.vx, board)

        # Detect adjacent blocks (not borders) for wall-jump eligibility
        self._update_wall_contact(board)

        # Wall jump: airborne + block wall contact + jump pressed + not in cooldown
        if (keys.get("jump") and not self.on_ground
                and self.on_wall != 0 and self.wall_jump_lock == 0):
            self.vy = WALL_JUMP_VY
            self.wj_vx = -self.on_wall * WALL_JUMP_VX
            self.vx = self.wj_vx
            self.on_wall = 0
            self.wall_jump_lock = 18

        self._move_y(self.vy, board)
        if self.on_ground:
            self.on_wall = 0

    # ── crush detection ───────────────────────────────────────────────────────

    def is_crushed(self, board: Board) -> bool:
        # A block crushes the climber only if it overlaps the body.
        # We deliberately exclude the feet row (row AT self.y) — a block landing
        # directly beneath the feet is not a crush, it's ground.
        return self._blocked(board, self._body_rows(), self._cols())

    def to_dict(self):
        return {"x": self.x, "y": self.y, "vx": self.vx, "vy": self.vy,
                "on_ground": self.on_ground, "alive": self.alive,
                "break_cooldown": self.break_cooldown,
                "on_wall": self.on_wall}

    @classmethod
    def from_dict(cls, d):
        c = cls()
        c.x, c.y, c.vx, c.vy = d["x"], d["y"], d["vx"], d["vy"]
        c.on_ground, c.alive = d["on_ground"], d["alive"]
        c.break_cooldown = d.get("break_cooldown", 0)
        c.on_wall = d.get("on_wall", 0)
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
        return max(MIN_FALL_INTERVAL, FALL_TICKS_BASE - (self.level - 1) * 5)

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
            self.status = "climber_wins"  # builder filled the board — climber wins

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

        # Build a board view where the falling piece is also solid, so the
        # climber collides with it just like placed blocks.
        collision_board = _BoardWithPiece(self.board, self.current_piece.cells())

        # Climber update (collides with placed blocks AND the falling piece)
        self.climber.update(collision_board, self.climber_keys)

        # Crush check: falling piece moving into the climber's body kills them
        if self.climber.alive and self.climber.is_crushed(collision_board):
            self.climber.alive = False
            self.status = "builder_wins"
            return

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
