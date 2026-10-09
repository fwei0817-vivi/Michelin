"""Local, explicitly scoped profile snapshots. No inferred allergies or implicit writes.

Scopes separate prototype households; they are NOT authentication. Deploy behind an
identity-aware gateway before storing real people's data. Transactions serialize revisions.
"""

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from michelin.schemas import DinerProfile

LEGACY = {"max_spice", "likes", "dislikes"}


def _current(raw: dict) -> dict:
    """A stored body in today's shape (older bodies are migrated on read)."""
    try:
        return DinerProfile.model_validate(raw).model_dump(mode="json")
    except ValueError:
        return raw


class ProfileStore:
    def __init__(self, path: Path):
        self.path = path

    @contextmanager
    def connection(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path, timeout=10) as db:
            db.execute("""CREATE TABLE IF NOT EXISTS profiles (
                scope TEXT NOT NULL, person TEXT NOT NULL, revision INTEGER NOT NULL,
                body TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT
                (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
                PRIMARY KEY(scope, person, revision))""")
            yield db

    def history(self, scope: str, person: str):
        with self.connection() as db:
            rows = db.execute(
                "SELECT revision, body, created_at FROM profiles WHERE scope=? AND person=? "
                "ORDER BY revision",
                (scope, person),
            ).fetchall()
        return [
            {"revision": r, "profile": _current(json.loads(b)), "created_at": t} for r, b, t in rows
        ]

    def migrate(self) -> int:
        """Rewrite saved people whose latest record predates the free-text taste note
        (heat/likes/dislikes fields) as a new revision in the current shape. Idempotent."""
        changed = 0
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            rows = db.execute(
                "SELECT scope, person, revision, body FROM profiles p WHERE revision="
                "(SELECT MAX(revision) FROM profiles WHERE scope=p.scope AND person=p.person)"
            ).fetchall()
            for scope, person, revision, body in rows:
                raw = json.loads(body)
                if not LEGACY & raw.keys():
                    continue
                new = DinerProfile.model_validate(raw).model_dump_json()
                db.execute(
                    "INSERT INTO profiles(scope, person, revision, body) VALUES (?, ?, ?, ?)",
                    (scope, person, revision + 1, new),
                )
                changed += 1
        return changed

    def list(self, scope: str):
        with self.connection() as db:
            rows = db.execute(
                "SELECT body FROM profiles p WHERE scope=? AND revision="
                "(SELECT MAX(revision) FROM profiles WHERE scope=p.scope AND person=p.person) "
                "ORDER BY person",
                (scope,),
            ).fetchall()
        return {p.id: p for (body,) in rows for p in [DinerProfile.model_validate_json(body)]}

    def save(self, scope: str, profile: DinerProfile, expected_revision: int | None):
        """Append a revision. With expected_revision None the latest record is replaced
        (upsert): there is one current record per person, edited in place by the app."""
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            current = db.execute(
                "SELECT COALESCE(MAX(revision), 0) FROM profiles WHERE scope=? AND person=?",
                (scope, profile.id),
            ).fetchone()[0]
            if expected_revision is not None and current != expected_revision:
                raise ValueError("Profile revision changed; reload before saving.")
            db.execute(
                "INSERT INTO profiles(scope, person, revision, body) VALUES (?, ?, ?, ?)",
                (scope, profile.id, current + 1, profile.model_dump_json()),
            )
        return current + 1

    def delete(self, scope: str, person: str):
        with self.connection() as db:
            return (
                db.execute(
                    "DELETE FROM profiles WHERE scope=? AND person=?", (scope, person)
                ).rowcount
                > 0
            )
