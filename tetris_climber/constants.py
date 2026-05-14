BOARD_COLS = 10
BOARD_ROWS = 20
CELL_SIZE = 32

WIN_ROW = 3  # Climber wins when reaching this row (0-indexed from top)

TICK_RATE = 60          # server ticks per second
FALL_TICKS_BASE = 48    # ticks between piece drops at level 1
LOCK_DELAY_TICKS = 30

GRAVITY = 0.6
JUMP_FORCE = -5.0
WALK_SPEED = 0.18
MAX_FALL_SPEED = 8.0
CLIMBER_WIDTH = 0.7     # in cells
CLIMBER_HEIGHT = 1.5

SERVER_HOST = "0.0.0.0"
SERVER_PORT = 55556
BUFFER_SIZE = 65536

COLORS = {
    "I": (0, 240, 240),
    "O": (240, 240, 0),
    "T": (160, 0, 240),
    "S": (0, 240, 0),
    "Z": (240, 0, 0),
    "J": (0, 0, 240),
    "L": (240, 160, 0),
    "ghost": (80, 80, 80),
    "empty": (20, 20, 30),
    "grid":  (40, 40, 55),
    "climber": (255, 140, 0),
    "win_line": (255, 255, 0),
}

TETROMINOES = {
    "I": [[0,0,0,0],[1,1,1,1],[0,0,0,0],[0,0,0,0]],
    "O": [[1,1],[1,1]],
    "T": [[0,1,0],[1,1,1],[0,0,0]],
    "S": [[0,1,1],[1,1,0],[0,0,0]],
    "Z": [[1,1,0],[0,1,1],[0,0,0]],
    "J": [[1,0,0],[1,1,1],[0,0,0]],
    "L": [[0,0,1],[1,1,1],[0,0,0]],
}

WALL_KICKS = {
    "normal": [
        [(0,0),(-1,0),(-1,1),(0,-2),(-1,-2)],
        [(0,0),(1,0),(1,-1),(0,2),(1,2)],
        [(0,0),(1,0),(1,1),(0,-2),(1,-2)],
        [(0,0),(-1,0),(-1,-1),(0,2),(-1,2)],
    ],
    "I": [
        [(0,0),(-2,0),(1,0),(-2,-1),(1,2)],
        [(0,0),(-1,0),(2,0),(-1,2),(2,-1)],
        [(0,0),(2,0),(-1,0),(2,1),(-1,-2)],
        [(0,0),(1,0),(-2,0),(1,-2),(-2,1)],
    ],
}
