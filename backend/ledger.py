"""SQLite mastery ledger for Classroom Memory.

This replaces the earlier cloud_state.json file. SQLite is intentionally the
default: it is durable, inspectable, and requires no setup for a hackathon judge.
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path


def now_ms() -> int:
    return int(time.time() * 1000)


class SQLiteLedger:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._connect() as conn:
            conn.executescript(
                """
                create table if not exists students (
                  id text primary key,
                  created_at integer not null
                );

                create table if not exists mastery (
                  student_id text not null,
                  concept_id text not null,
                  weight real not null,
                  updated_at integer not null,
                  retired integer not null default 0,
                  primary key (student_id, concept_id),
                  foreign key (student_id) references students(id) on delete cascade
                );

                create table if not exists seeded_datasets (
                  dataset_name text primary key,
                  student_id text not null,
                  curriculum_domain text not null,
                  seeded_at integer not null
                );

                create table if not exists interventions (
                  id integer primary key autoincrement,
                  concept_id text not null,
                  concept_name text not null,
                  created_at integer not null,
                  assigned_count integer not null,
                  status text not null
                );

                create table if not exists intervention_students (
                  intervention_id integer not null,
                  student_id text not null,
                  starting_band text not null,
                  starting_weight real not null,
                  status text not null,
                  primary key (intervention_id, student_id),
                  foreign key (intervention_id) references interventions(id)
                    on delete cascade
                );

                create table if not exists meta (
                  key text primary key,
                  value text not null
                );
                """
            )

    def sync_tenant(self, tenant: str) -> bool:
        """Record the active Cloud tenant. If it changed, the seeded_datasets rows
        point at datasets that live on a DIFFERENT tenant, so clear them: every
        student will re-seed lazily on the new tenant. Mastery weights are
        tenant-independent and kept. Returns True if the tenant changed."""
        with self._connect() as conn:
            row = conn.execute(
                "select value from meta where key = 'tenant'").fetchone()
            previous = row["value"] if row else None
            if previous == tenant:
                return False
            conn.execute("delete from seeded_datasets")
            conn.execute(
                "insert or replace into meta(key, value) values ('tenant', ?)",
                (tenant,))
        return True

    def student_ids(self) -> list[str]:
        with self._connect() as conn:
            rows = conn.execute("select id from students order by id").fetchall()
        return [r["id"] for r in rows]

    def load_states(self, default_states: dict[str, dict]) -> dict[str, dict]:
        """Load persisted states and fill missing concept rows from defaults."""
        states = {sid: {cid: rec.copy() for cid, rec in st.items()}
                  for sid, st in default_states.items()}
        with self._connect() as conn:
            for sid in self.student_ids():
                if sid not in states:
                    template = next(iter(default_states.values()))
                    states[sid] = {cid: rec.copy() for cid, rec in template.items()}
            for sid, state in states.items():
                conn.execute(
                    "insert or ignore into students(id, created_at) values (?, ?)",
                    (sid, now_ms()),
                )
                for cid, rec in state.items():
                    conn.execute(
                        """
                        insert or ignore into mastery
                          (student_id, concept_id, weight, updated_at, retired)
                        values (?, ?, ?, ?, ?)
                        """,
                        (sid, cid, rec["weight"], rec["updated_at"],
                         1 if rec["retired"] else 0),
                    )
            rows = conn.execute(
                "select student_id, concept_id, weight, updated_at, retired from mastery"
            ).fetchall()
        for row in rows:
            sid = row["student_id"]
            cid = row["concept_id"]
            if sid in states and cid in states[sid]:
                states[sid][cid].update(
                    weight=float(row["weight"]),
                    updated_at=int(row["updated_at"]),
                    retired=bool(row["retired"]),
                )
        return states

    def save_student(self, student: str, state: dict):
        with self._connect() as conn:
            conn.execute(
                "insert or ignore into students(id, created_at) values (?, ?)",
                (student, now_ms()),
            )
            for cid, rec in state.items():
                conn.execute(
                    """
                    insert into mastery(student_id, concept_id, weight, updated_at, retired)
                    values (?, ?, ?, ?, ?)
                    on conflict(student_id, concept_id) do update set
                      weight = excluded.weight,
                      updated_at = excluded.updated_at,
                      retired = excluded.retired
                    """,
                    (student, cid, rec["weight"], rec["updated_at"],
                     1 if rec["retired"] else 0),
                )

    def save_all(self, states: dict[str, dict]):
        for sid, state in states.items():
            self.save_student(sid, state)

    def seeded(self, domain: str | None = None) -> set[str]:
        with self._connect() as conn:
            if domain:
                rows = conn.execute(
                    "select dataset_name from seeded_datasets where curriculum_domain = ?",
                    (domain,),
                ).fetchall()
            else:
                rows = conn.execute("select dataset_name from seeded_datasets").fetchall()
        return {r["dataset_name"] for r in rows}

    def seeded_map(self, domain: str) -> dict[str, str]:
        """student_id -> the actual (possibly versioned) dataset name in use."""
        with self._connect() as conn:
            rows = conn.execute(
                "select student_id, dataset_name from seeded_datasets "
                "where curriculum_domain = ?",
                (domain,),
            ).fetchall()
        return {r["student_id"]: r["dataset_name"] for r in rows}

    def mark_seeded(self, dataset_name: str, student: str, domain: str):
        with self._connect() as conn:
            conn.execute(
                """
                insert or replace into seeded_datasets
                  (dataset_name, student_id, curriculum_domain, seeded_at)
                values (?, ?, ?, ?)
                """,
                (dataset_name, student, domain, now_ms()),
            )

    def unmark_seeded(self, dataset_name: str):
        with self._connect() as conn:
            conn.execute("delete from seeded_datasets where dataset_name = ?", (dataset_name,))

    def create_intervention(self, concept_id: str, concept_name: str,
                            assignments: list[dict]) -> dict:
        created = now_ms()
        with self._connect() as conn:
            cur = conn.execute(
                """
                insert into interventions
                  (concept_id, concept_name, created_at, assigned_count, status)
                values (?, ?, ?, ?, ?)
                """,
                (concept_id, concept_name, created, len(assignments), "assigned"),
            )
            intervention_id = cur.lastrowid
            for a in assignments:
                conn.execute(
                    """
                    insert into intervention_students
                      (intervention_id, student_id, starting_band, starting_weight, status)
                    values (?, ?, ?, ?, ?)
                    """,
                    (intervention_id, a["student"], a["band"], a["weight"], "assigned"),
                )
        return {
            "id": intervention_id,
            "concept": concept_id,
            "concept_name": concept_name,
            "created_at": created,
            "assigned_count": len(assignments),
            "students": assignments,
            "status": "assigned",
        }

    def recent_interventions(self, limit: int = 5) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                select id, concept_id, concept_name, created_at, assigned_count, status
                from interventions
                order by created_at desc
                limit ?
                """,
                (limit,),
            ).fetchall()
            out = []
            for row in rows:
                students = conn.execute(
                    """
                    select student_id, starting_band, starting_weight, status
                    from intervention_students
                    where intervention_id = ?
                    order by student_id
                    """,
                    (row["id"],),
                ).fetchall()
                out.append({
                    "id": row["id"],
                    "concept": row["concept_id"],
                    "concept_name": row["concept_name"],
                    "created_at": row["created_at"],
                    "assigned_count": row["assigned_count"],
                    "status": row["status"],
                    "students": [
                        {
                            "student": s["student_id"],
                            "band": s["starting_band"],
                            "weight": s["starting_weight"],
                            "status": s["status"],
                        }
                        for s in students
                    ],
                })
        return out

    def migrate_cloud_state_json(self, json_path: Path, concepts: dict):
        if not json_path.exists() or self.student_ids():
            return
        data = json.loads(json_path.read_text(encoding="utf-8"))
        students = data.get("students", {})
        for sid, state in students.items():
            filtered = {cid: rec for cid, rec in state.items() if cid in concepts}
            if filtered:
                self.save_student(sid, filtered)
        for sid in data.get("seeded", []):
            self.mark_seeded(f"student_{sid}", sid, "python")
