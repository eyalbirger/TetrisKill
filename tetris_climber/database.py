import sqlite3
import hashlib
import os
import time

DB_PATH = os.path.join(os.path.dirname(__file__), "leaderboard.db")


def _hash(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                winner_name TEXT NOT NULL,
                loser_name TEXT NOT NULL,
                winner_role TEXT NOT NULL,
                duration_seconds REAL NOT NULL,
                played_at REAL NOT NULL
            );
        """)


def register_user(username: str, password: str) -> tuple[bool, str]:
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                "INSERT INTO users (username, password_hash, created_at) VALUES (?,?,?)",
                (username, _hash(password), time.time())
            )
        return True, "ok"
    except sqlite3.IntegrityError:
        return False, "Username already taken"


def verify_user(username: str, password: str) -> bool:
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            "SELECT password_hash FROM users WHERE username=?", (username,)
        ).fetchone()
    return row is not None and row[0] == _hash(password)


def save_result(winner_name: str, loser_name: str, winner_role: str, duration_seconds: float):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT INTO results (winner_name, loser_name, winner_role, duration_seconds, played_at) VALUES (?,?,?,?,?)",
            (winner_name, loser_name, winner_role, duration_seconds, time.time())
        )


def get_leaderboard() -> dict:
    with sqlite3.connect(DB_PATH) as conn:
        builders = conn.execute("""
            SELECT winner_name, MIN(duration_seconds) as best_time, COUNT(*) as wins
            FROM results WHERE winner_role='builder'
            GROUP BY winner_name ORDER BY best_time ASC LIMIT 10
        """).fetchall()
        climbers = conn.execute("""
            SELECT winner_name, MIN(duration_seconds) as best_time, COUNT(*) as wins
            FROM results WHERE winner_role='climber'
            GROUP BY winner_name ORDER BY best_time ASC LIMIT 10
        """).fetchall()
    return {
        "builders": [{"name": r[0], "best_time": round(r[1], 2), "wins": r[2]} for r in builders],
        "climbers": [{"name": r[0], "best_time": round(r[1], 2), "wins": r[2]} for r in climbers],
    }
