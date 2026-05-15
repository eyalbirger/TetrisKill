BOARD_COLS = 10
BOARD_ROWS = 20
CELL_SIZE = 32

WIN_ROW = 3  # Climber wins when reaching this row (0-indexed from top)

TICK_RATE = 60          # server ticks per second
FALL_TICKS_BASE = 48    # ticks between piece drops at level 1
MIN_FALL_INTERVAL = 8   # fastest a piece can fall (ticks) — caps momentum at ~7 cells/sec
LOCK_DELAY_TICKS = 30
BREAK_COOLDOWN_TICKS = 30  # ticks before climber can break another block

# All physics values are in cells/tick (position is in cells, 1 tick = 1/TICK_RATE seconds)
GRAVITY = 0.007          # cells/tick² — acceleration applied each tick
JUMP_FORCE = -0.22       # cells/tick — initial upward velocity (~3.5 cell peak height)
WALK_SPEED = 0.22        # cells/tick — horizontal speed
MAX_FALL_SPEED = 0.8     # cells/tick — terminal velocity
CLIMBER_WIDTH = 0.7      # cells
CLIMBER_HEIGHT = 1.5     # cells

SERVER_HOST = "0.0.0.0"
SERVER_PORT = 49200
BUFFER_SIZE = 65536

COLORS = {
    "I": (0, 240, 240),
    "O": (240, 240, 0),
    "T": (160, 0, 240),
    "S": (0, 240, 0),
    "Z": (240, 0, 0),
    "J": (0, 0, 240),
    "L": (240, 160, 0),
    "ghost": (160, 165, 180),
    "empty": (210, 215, 225),
    "grid":  (180, 185, 198),
    "climber": (255, 140, 0),
    "win_line": (200, 130, 0),
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
