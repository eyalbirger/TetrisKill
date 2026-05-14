# Tetris Climber

Two-player networked game: **Builder** plays Tetris, **Climber** plays a platformer on the same board.

## Setup

```bash
pip install -r requirements.txt
```

## Running

**Server** (run once, on any machine):
```bash
python server.py
```

**Client** (run on each player's machine):
```bash
python client.py [server_ip]   # default: 127.0.0.1
```

First player to connect becomes the **Builder**, second becomes the **Climber**.

## Controls

| Builder         | Climber              |
|-----------------|----------------------|
| ← → Move piece  | ← → / A D Walk       |
| ↑ Rotate        | Space / ↑ / W Jump   |
| ↓ Soft drop     |                      |
| Space Hard drop |                      |

## Win Conditions

- **Climber wins** — reach the yellow line at the top of the board
- **Builder wins** — lock a Tetris piece on top of the Climber

## Leaderboard

Dual leaderboard stored in `leaderboard.db` (SQLite):
- **Builders** ranked by shortest win time
- **Climbers** ranked by shortest win time
