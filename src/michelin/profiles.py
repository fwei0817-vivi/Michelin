"""Local, explicitly scoped profile snapshots. No inferred allergies or implicit writes.

Scopes separate prototype households; they are NOT authentication. Deploy behind an
identity-aware gateway before storing real people's data. Transactions serialize revisions.
"""

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from michelin.schemas import DinerProfile


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
        return [{"revision": r, "profile": json.loads(b), "created_at": t} for r, b, t in rows]

    def list(self, scope: str):
        with self.connection() as db:
            rows = db.execute(
                "SELECT body FROM profiles p WHERE scope=? AND revision="
                "(SELECT MAX(revision) FROM profiles WHERE scope=p.scope AND person=p.person) "
                "ORDER BY person",
                (scope,),
            ).fetchall()
        return {p.id: p for (body,) in rows for p in [DinerProfile.model_validate_json(body)]}

    def save(self, scope: str, profile: DinerProfile, expected_revision: int):
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            current = db.execute(
                "SELECT COALESCE(MAX(revision), 0) FROM profiles WHERE scope=? AND person=?",
                (scope, profile.id),
            ).fetchone()[0]
            if current != expected_revision:
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
