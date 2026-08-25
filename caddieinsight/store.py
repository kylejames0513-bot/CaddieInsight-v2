"""SQLite persistence: users, bags, shots, and the Clubhouse.

One file, stdlib only. Every public method opens its own short-lived
connection, so the store is safe to share across request handlers without a
lock. Passwords are PBKDF2-HMAC-SHA256; nothing here needs a dependency.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime

from . import bag as bag_catalogue
from .distances import CarryNumber, carry_number
from .gapping import Rung

PBKDF2_ITERATIONS = 200_000

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    home_course TEXT NOT NULL DEFAULT '',
    share_bag INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS clubs (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    key TEXT NOT NULL,
    UNIQUE (user_id, key)
);
CREATE TABLE IF NOT EXISTS shots (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    club_key TEXT NOT NULL,
    carry REAL NOT NULL,
    note TEXT NOT NULL DEFAULT '',
    logged_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_shots_user_club ON shots(user_id, club_key);
CREATE TABLE IF NOT EXISTS posts (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    body TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS comments (
    id INTEGER PRIMARY KEY,
    post_id INTEGER NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    body TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS taps (
    post_id INTEGER NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    PRIMARY KEY (post_id, user_id)
);
"""


@dataclass(frozen=True)
class User:
    id: int
    email: str
    display_name: str
    home_course: str
    share_bag: bool
    created_at: datetime


@dataclass(frozen=True)
class Post:
    id: int
    user_id: int
    author: str
    body: str
    created_at: datetime
    taps: int = 0
    comments: int = 0
    tapped_by_me: bool = False
    author_shares_bag: bool = False


@dataclass(frozen=True)
class Comment:
    id: int
    post_id: int
    author: str
    body: str
    created_at: datetime


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode(), bytes.fromhex(salt), PBKDF2_ITERATIONS
    )
    return f"pbkdf2${PBKDF2_ITERATIONS}${salt}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, iterations, salt, expected = stored.split("$")
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), bytes.fromhex(salt), int(iterations)
        )
        return hmac.compare_digest(digest.hex(), expected)
    except (ValueError, TypeError):
        return False


def _parse_dt(value: str) -> datetime:
    return datetime.fromisoformat(value)


class Store:
    def __init__(self, path: str | os.PathLike[str] = "caddieinsight.db"):
        self.path = os.fspath(path)
        with self._connect() as db:
            db.executescript(SCHEMA)

    @contextmanager
    def _connect(self):
        db = sqlite3.connect(self.path)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
        try:
            yield db
            db.commit()
        finally:
            db.close()

    # ---- users -----------------------------------------------------------

    def create_user(
        self, email: str, display_name: str, password: str
    ) -> User:
        email = email.strip().lower()
        now = datetime.utcnow().isoformat()
        with self._connect() as db:
            cur = db.execute(
                "INSERT INTO users (email, display_name, password_hash,"
                " created_at) VALUES (?, ?, ?, ?)",
                (email, display_name.strip(), hash_password(password), now),
            )
            user_id = cur.lastrowid
        user = self.user_by_id(user_id)
        assert user is not None
        return user

    def _user_from_row(self, row: sqlite3.Row) -> User:
        return User(
            id=row["id"],
            email=row["email"],
            display_name=row["display_name"],
            home_course=row["home_course"],
            share_bag=bool(row["share_bag"]),
            created_at=_parse_dt(row["created_at"]),
        )

    def user_by_id(self, user_id: int) -> User | None:
        with self._connect() as db:
            row = db.execute(
                "SELECT * FROM users WHERE id = ?", (user_id,)
            ).fetchone()
        return self._user_from_row(row) if row else None

    def user_by_email(self, email: str) -> User | None:
        with self._connect() as db:
            row = db.execute(
                "SELECT * FROM users WHERE email = ?",
                (email.strip().lower(),),
            ).fetchone()
        return self._user_from_row(row) if row else None

    def authenticate(self, email: str, password: str) -> User | None:
        with self._connect() as db:
            row = db.execute(
                "SELECT * FROM users WHERE email = ?",
                (email.strip().lower(),),
            ).fetchone()
        if row and verify_password(password, row["password_hash"]):
            return self._user_from_row(row)
        return None

    def update_profile(
        self,
        user_id: int,
        display_name: str | None = None,
        home_course: str | None = None,
        share_bag: bool | None = None,
    ) -> None:
        with self._connect() as db:
            if display_name is not None:
                db.execute(
                    "UPDATE users SET display_name = ? WHERE id = ?",
                    (display_name.strip(), user_id),
                )
            if home_course is not None:
                db.execute(
                    "UPDATE users SET home_course = ? WHERE id = ?",
                    (home_course.strip(), user_id),
                )
            if share_bag is not None:
                db.execute(
                    "UPDATE users SET share_bag = ? WHERE id = ?",
                    (int(share_bag), user_id),
                )

    # ---- the bag ---------------------------------------------------------

    def set_bag(self, user_id: int, keys: list[str]) -> None:
        """Replace the user's bag with ``keys`` (catalogue keys)."""
        cleaned = []
        for key in keys:
            key = key.upper()
            if bag_catalogue.is_valid_key(key) and key not in cleaned:
                cleaned.append(key)
        with self._connect() as db:
            db.execute("DELETE FROM clubs WHERE user_id = ?", (user_id,))
            db.executemany(
                "INSERT INTO clubs (user_id, key) VALUES (?, ?)",
                [(user_id, key) for key in cleaned],
            )

    def add_club(self, user_id: int, key: str) -> None:
        key = key.upper()
        if not bag_catalogue.is_valid_key(key):
            raise KeyError(key)
        with self._connect() as db:
            db.execute(
                "INSERT OR IGNORE INTO clubs (user_id, key) VALUES (?, ?)",
                (user_id, key),
            )

    def remove_club(self, user_id: int, key: str) -> None:
        with self._connect() as db:
            db.execute(
                "DELETE FROM clubs WHERE user_id = ? AND key = ?",
                (user_id, key.upper()),
            )

    def bag_keys(self, user_id: int) -> list[str]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT key FROM clubs WHERE user_id = ?", (user_id,)
            ).fetchall()
        keys = [row["key"] for row in rows]
        return sorted(keys, key=lambda k: bag_catalogue.spec_for(k).rank)

    # ---- shots -----------------------------------------------------------

    def log_shots(
        self,
        user_id: int,
        club_key: str,
        carries: list[float],
        note: str = "",
        logged_at: datetime | None = None,
    ) -> int:
        club_key = club_key.upper()
        if not bag_catalogue.is_valid_key(club_key):
            raise KeyError(club_key)
        when = (logged_at or datetime.utcnow()).isoformat()
        rows = [
            (user_id, club_key, float(carry), note, when)
            for carry in carries
        ]
        with self._connect() as db:
            db.executemany(
                "INSERT INTO shots (user_id, club_key, carry, note,"
                " logged_at) VALUES (?, ?, ?, ?, ?)",
                rows,
            )
        return len(rows)

    def shots_for(
        self, user_id: int, club_key: str
    ) -> list[tuple[float, datetime]]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT carry, logged_at FROM shots"
                " WHERE user_id = ? AND club_key = ?"
                " ORDER BY logged_at DESC, id DESC",
                (user_id, club_key.upper()),
            ).fetchall()
        return [(row["carry"], _parse_dt(row["logged_at"])) for row in rows]

    def recent_shots(self, user_id: int, limit: int = 30) -> list[dict]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT club_key, carry, note, logged_at FROM shots"
                " WHERE user_id = ? ORDER BY logged_at DESC, id DESC"
                " LIMIT ?",
                (user_id, limit),
            ).fetchall()
        return [
            {
                "club_key": row["club_key"],
                "carry": row["carry"],
                "note": row["note"],
                "logged_at": _parse_dt(row["logged_at"]),
            }
            for row in rows
        ]

    def shot_count(self, user_id: int) -> int:
        with self._connect() as db:
            row = db.execute(
                "SELECT COUNT(*) AS n FROM shots WHERE user_id = ?",
                (user_id,),
            ).fetchone()
        return row["n"]

    # ---- the measured bag ------------------------------------------------

    def rungs(self, user_id: int, now: datetime | None = None) -> list[Rung]:
        """Every club in the bag with its carry number."""
        rungs = []
        for key in self.bag_keys(user_id):
            spec = bag_catalogue.spec_for(key)
            number: CarryNumber = carry_number(
                self.shots_for(user_id, key), now=now
            )
            rungs.append(
                Rung(key=key, label=spec.label, kind=spec.kind, number=number)
            )
        return rungs

    # ---- the clubhouse ---------------------------------------------------

    def create_post(self, user_id: int, body: str) -> int:
        with self._connect() as db:
            cur = db.execute(
                "INSERT INTO posts (user_id, body, created_at)"
                " VALUES (?, ?, ?)",
                (user_id, body.strip(), datetime.utcnow().isoformat()),
            )
            return cur.lastrowid

    def _post_from_row(self, row: sqlite3.Row) -> Post:
        return Post(
            id=row["id"],
            user_id=row["user_id"],
            author=row["author"],
            body=row["body"],
            created_at=_parse_dt(row["created_at"]),
            taps=row["taps"],
            comments=row["comments"],
            tapped_by_me=bool(row["tapped_by_me"]),
            author_shares_bag=bool(row["share_bag"]),
        )

    _POST_QUERY = """
        SELECT p.id, p.user_id, p.body, p.created_at,
               u.display_name AS author, u.share_bag,
               (SELECT COUNT(*) FROM taps t WHERE t.post_id = p.id) AS taps,
               (SELECT COUNT(*) FROM comments c WHERE c.post_id = p.id)
                   AS comments,
               EXISTS(SELECT 1 FROM taps t WHERE t.post_id = p.id
                      AND t.user_id = :viewer) AS tapped_by_me
        FROM posts p JOIN users u ON u.id = p.user_id
    """

    def feed(self, viewer_id: int, limit: int = 50) -> list[Post]:
        with self._connect() as db:
            rows = db.execute(
                self._POST_QUERY + " ORDER BY p.created_at DESC, p.id DESC"
                " LIMIT :limit",
                {"viewer": viewer_id, "limit": limit},
            ).fetchall()
        return [self._post_from_row(row) for row in rows]

    def post(self, post_id: int, viewer_id: int) -> Post | None:
        with self._connect() as db:
            row = db.execute(
                self._POST_QUERY + " WHERE p.id = :post_id",
                {"viewer": viewer_id, "post_id": post_id},
            ).fetchone()
        return self._post_from_row(row) if row else None

    def add_comment(self, post_id: int, user_id: int, body: str) -> int:
        with self._connect() as db:
            cur = db.execute(
                "INSERT INTO comments (post_id, user_id, body, created_at)"
                " VALUES (?, ?, ?, ?)",
                (post_id, user_id, body.strip(),
                 datetime.utcnow().isoformat()),
            )
            return cur.lastrowid

    def comments_for(self, post_id: int) -> list[Comment]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT c.id, c.post_id, c.body, c.created_at,"
                " u.display_name AS author"
                " FROM comments c JOIN users u ON u.id = c.user_id"
                " WHERE c.post_id = ? ORDER BY c.created_at, c.id",
                (post_id,),
            ).fetchall()
        return [
            Comment(
                id=row["id"],
                post_id=row["post_id"],
                author=row["author"],
                body=row["body"],
                created_at=_parse_dt(row["created_at"]),
            )
            for row in rows
        ]

    def toggle_tap(self, post_id: int, user_id: int) -> bool:
        """Tip of the cap on/off; returns the new state."""
        with self._connect() as db:
            existing = db.execute(
                "SELECT 1 FROM taps WHERE post_id = ? AND user_id = ?",
                (post_id, user_id),
            ).fetchone()
            if existing:
                db.execute(
                    "DELETE FROM taps WHERE post_id = ? AND user_id = ?",
                    (post_id, user_id),
                )
                return False
            db.execute(
                "INSERT INTO taps (post_id, user_id) VALUES (?, ?)",
                (post_id, user_id),
            )
            return True

    def shared_bags(self) -> list[User]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT * FROM users WHERE share_bag = 1"
                " ORDER BY display_name COLLATE NOCASE"
            ).fetchall()
        return [self._user_from_row(row) for row in rows]
