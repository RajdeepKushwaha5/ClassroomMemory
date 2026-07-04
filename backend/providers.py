"""Classroom Memory providers.

ClassroomProvider is the interface; DemoProvider is the deterministic zero-dependency
implementation (TRACK-B.md §5: mandatory, byte-identical shapes to CloudProvider).
CloudProvider (real Cognee Cloud via cognee.serve) is added once Cloud credentials are
verified: it must return the exact same response shapes.

Mastery model (TRACK-B.md §3 F2):
  weight < 0.35        -> "red"    (gap)
  0.35 <= weight <= .75-> "amber"  (learning)
  weight > 0.75        -> "green"  (mastered)
Decay is VIEW-LAYER only (offset_days), same design as Track A's decay clock.
"""

from __future__ import annotations

import json
import re
import time
import uuid
from pathlib import Path

from ledger import SQLiteLedger

STUDENT_NAME_RE = re.compile(r"^[a-z][a-z0-9_-]{1,15}$")
CURRICULUM_ID_RE = re.compile(r"^[a-z][a-z0-9_-]{1,40}$")

CURRICULUM_PATH = Path(__file__).resolve().parent.parent / "curriculum" / "python.json"
CURRICULUM_DIR = CURRICULUM_PATH.parent
IMPORTED_CURRICULUM_DIR = CURRICULUM_DIR / "imported"

RED_MAX = 0.35
GREEN_MIN = 0.75
LEARN_ALPHA = 0.35          # correct answer: w += alpha * (1 - w)  (3 corrects: .2 -> .78)
WRONG_FACTOR = 0.15         # wrong answer:   w -= factor * w
RUSTY_AFTER_DAYS = 14       # untouched this long -> "rusty" flag in the view layer
DAY_MS = 86_400_000


def now_ms() -> int:
    return int(time.time() * 1000)


def band(weight: float) -> str:
    if weight < RED_MAX:
        return "red"
    if weight > GREEN_MIN:
        return "green"
    return "amber"


def load_curriculum() -> dict:
    with open(CURRICULUM_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def validate_curriculum(payload: dict) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("curriculum must be a JSON object")
    domain = str(payload.get("domain", "")).strip().lower()
    title = str(payload.get("title", "")).strip()
    concepts = payload.get("concepts")
    if not CURRICULUM_ID_RE.match(domain):
        raise ValueError("domain must be lowercase letters, digits, - or _")
    if not title:
        raise ValueError("title is required")
    if not isinstance(concepts, list) or not concepts:
        raise ValueError("concepts must be a non-empty list")

    ids: set[str] = set()
    for c in concepts:
        cid = str(c.get("id", "")).strip().lower()
        if not CURRICULUM_ID_RE.match(cid):
            raise ValueError(f"invalid concept id: {cid!r}")
        if cid in ids:
            raise ValueError(f"duplicate concept id: {cid}")
        ids.add(cid)
        if not str(c.get("name", "")).strip():
            raise ValueError(f"{cid}: name is required")
        if not str(c.get("summary", "")).strip():
            raise ValueError(f"{cid}: summary is required")
        if not isinstance(c.get("requires", []), list):
            raise ValueError(f"{cid}: requires must be a list")
        questions = c.get("questions")
        if not isinstance(questions, list) or not questions:
            raise ValueError(f"{cid}: at least one question is required")
        for q in questions:
            options = q.get("options")
            answer = q.get("answer")
            if not str(q.get("q", "")).strip():
                raise ValueError(f"{cid}: question text is required")
            if not isinstance(options, list) or len(options) < 2:
                raise ValueError(f"{cid}: question needs at least two options")
            if not isinstance(answer, int) or answer < 0 or answer >= len(options):
                raise ValueError(f"{cid}: answer index is out of range")

    for c in concepts:
        cid = c["id"]
        for req in c.get("requires", []):
            if req not in ids:
                raise ValueError(f"{cid}: unknown prerequisite {req}")

    clean = {
        "domain": domain,
        "title": title,
        "concepts": [],
    }
    for c in concepts:
        clean["concepts"].append({
            "id": str(c["id"]).strip().lower(),
            "name": str(c["name"]).strip(),
            "summary": str(c["summary"]).strip(),
            "requires": [str(r).strip().lower() for r in c.get("requires", [])],
            "questions": [
                {
                    "q": str(q["q"]).strip(),
                    "options": [str(o) for o in q["options"]],
                    "answer": int(q["answer"]),
                }
                for q in c["questions"]
            ],
        })
    return clean


class ClassroomProvider:
    """Interface: every method returns plain JSON-serializable dicts."""

    def health(self) -> dict: ...
    def students(self) -> dict: ...
    def student_graph(self, student: str, offset_days: int = 0) -> dict: ...
    def quiz_next(self, student: str) -> dict: ...
    def quiz_answer(self, student: str, concept: str, answer_index: int) -> dict: ...
    def class_heatmap(self, offset_days: int = 0) -> dict: ...
    def retire(self, student: str, concept: str) -> dict: ...
    def reset_student(self, student: str) -> dict: ...
    def ask(self, student: str, question: str) -> dict: ...
    def class_ask(self, question: str) -> dict: ...
    def add_student(self, student: str) -> dict: ...
    def curricula(self) -> dict: ...
    def import_curriculum(self, payload: dict) -> dict: ...
    def assign_review(self, concept: str) -> dict: ...
    def close(self) -> None: ...


class DemoProvider(ClassroomProvider):
    """Deterministic in-memory implementation. No network, no LLM, no Cognee.

    Seeds three students (TRACK-B.md §5): alice fresh, bob mid-progress,
    cara advanced-but-rusty: so the teacher heat map is interesting immediately.
    """

    def __init__(self):
        self.curriculum = load_curriculum()
        self.concepts = {c["id"]: c for c in self.curriculum["concepts"]}
        self._states: dict[str, dict] = {}
        self._question_cursor: dict[tuple[str, str], int] = {}
        self._sessions: dict[str, dict] = {}
        self._seed_all()

    # ---------- seeding ----------

    def _fresh_state(self) -> dict:
        t = now_ms()
        return {
            cid: {"weight": 0.2, "updated_at": t, "retired": False}
            for cid in self.concepts
        }

    def _seed_all(self):
        t = now_ms()
        self._states["alice"] = self._fresh_state()

        bob = self._fresh_state()
        # a believable mid-course gradient: solid basics, fading middle, red frontier
        for cid, w in [
            ("variables", 0.92), ("data-types", 0.88), ("strings", 0.84),
            ("lists", 0.86), ("conditionals", 0.8),
            ("dicts", 0.62), ("loops", 0.58), ("functions", 0.66),
            ("scope", 0.48), ("comprehensions", 0.44), ("exceptions", 0.4),
        ]:
            if cid in bob:
                bob[cid].update(weight=w)
        self._states["bob"] = bob

        cara = self._fresh_state()
        old = t - 40 * DAY_MS  # long-untouched -> rusty in the view layer
        for cid in self.concepts:
            cara[cid].update(weight=0.85, updated_at=old)
        for cid in ["async-await", "asyncio-tasks", "recursion"]:
            if cid in cara:
                cara[cid].update(weight=0.3, updated_at=t)
        self._states["cara"] = cara

    # ---------- core reads ----------

    def health(self) -> dict:
        return {
            "mode": "demo",
            "cloud_connected": False,
            "domain": self.curriculum["domain"],
            "title": self.curriculum["title"].replace("→", "->"),
            "concepts": len(self.concepts),
            "students": sorted(self._states),
            "ledger": "memory",
        }

    def students(self) -> dict:
        out = []
        for sid, state in sorted(self._states.items()):
            weights = [c["weight"] for c in state.values() if not c["retired"]]
            avg = sum(weights) / len(weights) if weights else 0.0
            out.append({
                "id": sid,
                "avg_weight": round(avg, 3),
                "mastered": sum(1 for c in state.values() if band(c["weight"]) == "green"),
                "gaps": sum(1 for c in state.values() if band(c["weight"]) == "red"),
                "total": len(state),
            })
        return {"students": out}

    def _view_concept(self, cid: str, rec: dict, offset_days: int) -> dict:
        virtual_now = now_ms() + offset_days * DAY_MS
        age_days = max(0, (virtual_now - rec["updated_at"]) / DAY_MS)
        rusty = (not rec["retired"] and band(rec["weight"]) == "green"
                 and age_days >= RUSTY_AFTER_DAYS)
        c = self.concepts[cid]
        return {
            "id": cid,
            "name": c["name"],
            "summary": c["summary"],
            "requires": c["requires"],
            "weight": round(rec["weight"], 3),
            "band": band(rec["weight"]),
            "rusty": rusty,
            "retired": rec["retired"],
            "age_days": round(age_days, 1),
        }

    def student_graph(self, student: str, offset_days: int = 0) -> dict:
        state = self._require(student)
        nodes = [self._view_concept(cid, rec, offset_days) for cid, rec in state.items()]
        edges = [
            {"from": req, "to": cid, "type": "requires"}
            for cid, c in self.concepts.items() for req in c["requires"]
        ]
        frontier = self._frontier(student)
        return {
            "student": student,
            "nodes": nodes,
            "edges": edges,
            "frontier": frontier,
            "next_step": frontier[0] if frontier else None,
        }

    # ---------- frontier + quiz ----------

    def _frontier(self, student: str) -> list[str]:
        """Concepts whose prerequisites are all >= amber but which are not yet green.
        This is the graph-native 'what should you learn next' decision (TRACK-B.md F3)."""
        state = self._require(student)
        out = []
        for cid, c in self.concepts.items():
            rec = state[cid]
            if rec["retired"] or band(rec["weight"]) == "green":
                continue
            if all(state[r]["weight"] >= RED_MAX for r in c["requires"]):
                out.append(cid)
        # Finish in-progress (amber) concepts before opening new reds: this gives the
        # demo its red -> amber -> green progression on a single node.
        out.sort(key=lambda cid: (
            0 if band(state[cid]["weight"]) == "amber" else 1,
            state[cid]["weight"],
            cid,
        ))
        return out

    def quiz_next(self, student: str) -> dict:
        frontier = self._frontier(student)
        if not frontier:
            return {"student": student, "done": True, "question": None,
                    "message": "All frontier concepts mastered: nothing left to drill."}
        cid = frontier[0]
        questions = self.concepts[cid]["questions"]
        cursor = self._question_cursor.get((student, cid), 0)
        q = questions[cursor % len(questions)]
        self._question_cursor[(student, cid)] = cursor + 1
        session = self._sessions.setdefault(student, {"id": str(uuid.uuid4()), "answers": []})
        return {
            "student": student,
            "done": False,
            "session_id": session["id"],
            "concept": self._view_concept(cid, self._require(student)[cid], 0),
            "question": {"text": q["q"], "options": q["options"], "concept": cid},
        }

    def quiz_answer(self, student: str, concept: str, answer_index: int) -> dict:
        state = self._require(student)
        if concept not in self.concepts:
            raise KeyError(f"unknown concept: {concept}")
        questions = self.concepts[concept]["questions"]
        cursor = max(0, self._question_cursor.get((student, concept), 1) - 1)
        q = questions[cursor % len(questions)]
        correct = answer_index == q["answer"]

        rec = state[concept]
        before = rec["weight"]
        if correct:
            rec["weight"] = min(1.0, rec["weight"] + LEARN_ALPHA * (1 - rec["weight"]))
        else:
            rec["weight"] = max(0.05, rec["weight"] - WRONG_FACTOR * rec["weight"])
        rec["updated_at"] = now_ms()

        session = self._sessions.setdefault(student, {"id": str(uuid.uuid4()), "answers": []})
        session["answers"].append({"concept": concept, "correct": correct, "ts": rec["updated_at"]})

        return {
            "student": student,
            "concept": self._view_concept(concept, rec, 0),
            "correct": correct,
            "correct_option": q["options"][q["answer"]],
            "weight_before": round(before, 3),
            "weight_after": round(rec["weight"], 3),
            "next": self.quiz_next(student),
        }

    # ---------- teacher ----------

    def class_heatmap(self, offset_days: int = 0) -> dict:
        rows = []
        for cid, c in self.concepts.items():
            views = [
                self._view_concept(cid, state[cid], offset_days)
                for state in self._states.values()
            ]
            n = len(views)
            reds = sum(1 for v in views if v["band"] == "red")
            ambers = sum(1 for v in views if v["band"] == "amber" or v["rusty"])
            greens = sum(1 for v in views if v["band"] == "green" and not v["rusty"])
            rows.append({
                "id": cid,
                "name": c["name"],
                "requires": c["requires"],
                "red_pct": round(100 * reds / n),
                "amber_pct": round(100 * ambers / n),
                "green_pct": round(100 * greens / n),
                "avg_weight": round(sum(v["weight"] for v in views) / n, 3),
            })
        rows.sort(key=lambda r: (-r["red_pct"], r["avg_weight"]))
        teach_next = [r for r in rows if r["red_pct"] >= 50][:3]
        return {"concepts": rows, "teach_next": teach_next,
                "students": self.students()["students"]}

    # ---------- lifecycle: forget / reset / ask ----------

    def retire(self, student: str, concept: str) -> dict:
        rec = self._require(student)[concept]
        if band(rec["weight"]) != "green":
            return {"ok": False, "reason": "only mastered (green) concepts can be retired"}
        rec["retired"] = True
        return {"ok": True, "student": student, "concept": concept}

    def reset_student(self, student: str) -> dict:
        self._states[student] = self._fresh_state()
        self._sessions.pop(student, None)
        self._question_cursor = {
            k: v for k, v in self._question_cursor.items() if k[0] != student
        }
        return {"ok": True, "student": student}

    def add_student(self, student: str) -> dict:
        """Enroll a new student. Their memory starts fresh; in cloud mode their
        Cognee dataset is created on their first ask/quiz (lazy seed)."""
        sid = student.strip().lower()
        if not STUDENT_NAME_RE.match(sid):
            return {"ok": False,
                    "reason": "name must be 2-16 chars: letters, digits, - or _ "
                              "(starting with a letter)"}
        if sid in self._states:
            return {"ok": False, "reason": f"{sid} is already enrolled"}
        self._states[sid] = self._fresh_state()
        return {"ok": True, "student": sid}

    # ---------- curriculum + teacher action ----------

    def curricula(self) -> dict:
        items = []
        for path in [CURRICULUM_PATH, *sorted(IMPORTED_CURRICULUM_DIR.glob("*.json"))]:
            try:
                data = validate_curriculum(json.loads(path.read_text(encoding="utf-8")))
            except Exception:
                continue
            items.append({
                "domain": data["domain"],
                "title": data["title"],
                "concepts": len(data["concepts"]),
                "active": data["domain"] == self.curriculum["domain"],
                "source": "builtin" if path == CURRICULUM_PATH else "imported",
            })
        return {"active": self.curriculum["domain"], "curricula": items}

    def import_curriculum(self, payload: dict) -> dict:
        clean = validate_curriculum(payload)
        IMPORTED_CURRICULUM_DIR.mkdir(parents=True, exist_ok=True)
        path = IMPORTED_CURRICULUM_DIR / f"{clean['domain']}.json"
        path.write_text(json.dumps(clean, indent=2), encoding="utf-8")
        self.curriculum = clean
        self.concepts = {c["id"]: c for c in clean["concepts"]}
        self._states = {}
        self._question_cursor = {}
        self._sessions = {}
        self._seed_all()
        return {"ok": True, "domain": clean["domain"], "title": clean["title"],
                "concepts": len(clean["concepts"])}

    def assign_review(self, concept: str) -> dict:
        if concept not in self.concepts:
            raise KeyError(f"unknown concept: {concept}")
        assignments = []
        for sid, state in sorted(self._states.items()):
            view = self._view_concept(concept, state[concept], 0)
            if view["band"] == "red" or view["rusty"]:
                assignments.append({
                    "student": sid,
                    "band": "rusty" if view["rusty"] else view["band"],
                    "weight": view["weight"],
                })
        c = self.concepts[concept]
        return {
            "ok": True,
            "concept": concept,
            "concept_name": c["name"],
            "assigned_count": len(assignments),
            "students": assignments,
            "message": f"Assigned {c['name']} review to {len(assignments)} student(s).",
        }

    def close(self) -> None:
        return None

    def class_ask(self, question: str) -> dict:
        """Teacher asks across ALL students' memories. Demo mode answers
        deterministically from every student's mastery state; CloudProvider overrides
        this with a real multi-dataset cognee recall()."""
        ql = question.lower()
        hits = [
            (cid, c) for cid, c in self.concepts.items()
            if cid.replace("-", " ") in ql or c["name"].lower() in ql
        ]
        if not hits:
            hm = self.class_heatmap()
            worst = hm["concepts"][0]
            return {"answer":
                    f"Biggest class-wide gap right now: {worst['name']} "
                    f"({worst['red_pct']}% of the class is red on it).",
                    "datasets": sorted(self._states), "cloud": False}
        parts = []
        for cid, c in hits:
            status = ", ".join(
                f"{sid}: {band(state[cid]['weight'])}"
                for sid, state in sorted(self._states.items()))
            parts.append(f"{c['name']}: {status}.")
        return {"answer": " ".join(parts), "datasets": sorted(self._states),
                "cloud": False}

    def ask(self, student: str, question: str) -> dict:
        """Demo mode: deterministic answer assembled from curriculum summaries of the
        concepts mentioned in the question, grounded in the student's own mastery."""
        state = self._require(student)
        ql = question.lower()
        hits = [
            self._view_concept(cid, state[cid], 0)
            for cid, c in self.concepts.items()
            if cid.replace("-", " ") in ql or c["name"].lower() in ql
        ]
        if not hits:
            frontier = self._frontier(student)
            nxt = self.concepts[frontier[0]]["name"] if frontier else "nothing: all done"
            return {"student": student, "answer":
                    f"I don't have that concept in this curriculum. Your next step is: {nxt}.",
                    "sources": []}
        parts = []
        for h in hits:
            status = {"red": "a gap for you", "amber": "in progress",
                      "green": "mastered"}[h["band"]]
            parts.append(f"{h['name']}: {h['summary']} (currently {status})")
        return {"student": student, "answer": " ".join(parts), "sources": hits}

    # ---------- utils ----------

    def _require(self, student: str) -> dict:
        if student not in self._states:
            raise KeyError(f"unknown student: {student}")
        return self._states[student]


class CloudProvider(DemoProvider):
    """Real Cognee Cloud. Verified 2026-07-03 against the user's tenant:
    serve 1.6s, remember ~16s (full ingestion pipeline), recall ~3.4s, forget ~2s.

    Design (TRACK-B.md §3 F5 honesty policy):
    - one Cloud DATASET per student (`student_<id>`), seeded once with the combined
      curriculum document (a single remember() call: per-concept calls would take
      ~6 min/student at measured latency);
    - ask() -> real recall() scoped to the student's dataset;
    - reset_student() -> real forget(dataset=...) then re-seed lazily;
    - quiz traces (concept mastered) -> fire-and-forget remember() so the Cloud
      console shows real learning activity;
    - mastery weights are maintained app-layer and persisted to SQLite
      (explicit-weights fallback; improve()-parity still ⚠️ unverified on Cloud).

    Cognee's API is async; FastAPI endpoints here are sync: so all cognee calls run
    on a dedicated background event loop thread (run_coroutine_threadsafe)."""

    LEDGER_PATH = Path(__file__).resolve().parent / "mastery_ledger.sqlite"
    LEGACY_STATE_PATH = Path(__file__).resolve().parent / "cloud_state.json"

    def __init__(self, url: str, api_key: str):
        super().__init__()
        import asyncio
        import threading

        self._asyncio = asyncio
        self._url = url
        self._loop = asyncio.new_event_loop()
        threading.Thread(target=self._loop.run_forever, daemon=True).start()

        import cognee
        self._cognee = cognee

        self._connected = False
        try:
            self._call(cognee.serve(url=url, api_key=api_key), timeout=30)
            self._connected = True
        except Exception as err:  # demo shapes still work; badge shows offline cloud
            print(f"[cloud] serve() failed, falling back to local state: {err}")

        self._seeded: set[str] = set()
        self._ledger = SQLiteLedger(self.LEDGER_PATH)
        self._load_state()

    # ---------- async bridge ----------

    def _call(self, coro, timeout=60):
        fut = self._asyncio.run_coroutine_threadsafe(coro, self._loop)
        return fut.result(timeout)

    def _fire_and_forget(self, coro):
        async def safe():
            try:
                await coro
            except Exception as err:
                print(f"[cloud] background write failed (non-fatal): {err}")
        self._asyncio.run_coroutine_threadsafe(safe(), self._loop)

    # ---------- state persistence (weights survive restarts) ----------

    def _load_state(self):
        self._ledger.migrate_cloud_state_json(self.LEGACY_STATE_PATH, self.concepts)
        self._states = self._ledger.load_states(self._states)
        self._seeded = self._ledger.seeded(self.curriculum["domain"])

    def _save_state(self):
        self._ledger.save_all(self._states)

    # ---------- cloud dataset per student ----------

    def _dataset(self, student: str) -> str:
        domain = self.curriculum["domain"]
        if domain == "python":
            return f"student_{student}"
        safe_domain = re.sub(r"[^a-z0-9_-]", "_", domain.lower())
        return f"student_{safe_domain}_{student}"

    def _curriculum_doc(self) -> str:
        lines = [f"{self.curriculum['title']}: course concepts:"]
        for c in self.curriculum["concepts"]:
            req = f" Requires: {', '.join(c['requires'])}." if c["requires"] else ""
            lines.append(f"{c['name']}: {c['summary']}{req}")
        return "\n".join(lines)

    def ensure_seeded(self, student: str):
        self._require(student)
        dataset = self._dataset(student)
        if not self._connected or dataset in self._seeded:
            return
        # node_set tags become first-class NodeSet graph nodes (probed OK 2026-07-04)
        self._call(self._cognee.remember(
            self._curriculum_doc(), dataset_name=dataset,
            node_set=["curriculum", self.curriculum["domain"]]), timeout=120)
        self._seeded.add(dataset)
        self._ledger.mark_seeded(dataset, student, self.curriculum["domain"])

    # ---------- overrides ----------

    def health(self) -> dict:
        base = super().health()
        base.update(mode="cloud", cloud_connected=self._connected,
                    tenant=self._url.split("//")[-1].split(".")[0],
                    seeded=sorted(d.replace("student_", "") for d in self._seeded),
                    ledger=str(self.LEDGER_PATH.name))
        return base

    def ask(self, student: str, question: str) -> dict:
        self._require(student)
        if self._connected:
            try:
                self.ensure_seeded(student)
                res = self._call(self._cognee.recall(
                    question, datasets=[self._dataset(student)]), timeout=45)
                items = res if isinstance(res, list) else [res]
                text = next((str(i.get("text")) for i in items
                             if isinstance(i, dict) and i.get("text")), None)
                if text:
                    return {"student": student, "answer": text, "cloud": True,
                            "sources": [{"dataset": self._dataset(student),
                                         "kind": i.get("kind", "graph_completion")}
                                        for i in items if isinstance(i, dict)][:3]}
            except Exception as err:
                print(f"[cloud] recall failed, using local answer: {err}")
        out = super().ask(student, question)
        out["cloud"] = False
        return out

    def quiz_answer(self, student: str, concept: str, answer_index: int) -> dict:
        res = super().quiz_answer(student, concept, answer_index)
        self._save_state()
        # When a concept crosses into green, write a real learning trace to the
        # student's Cloud dataset (visible in the Cognee Cloud console: demo beat).
        if self._connected and res["concept"]["band"] == "green" and res["correct"]:
            self._fire_and_forget(self._cognee.remember(
                f"{student} mastered the concept '{res['concept']['name']}' "
                f"(mastery {res['weight_after']:.2f}).",
                dataset_name=self._dataset(student),
                node_set=["mastery-trace"]))
        return res

    def retire(self, student: str, concept: str) -> dict:
        out = super().retire(student, concept)
        if out.get("ok"):
            self._ledger.save_student(student, self._states[student])
            if self._connected:
                self._fire_and_forget(self._cognee.remember(
                    f"{student} retired mastered concept '{concept}' from active practice.",
                    dataset_name=self._dataset(student)))
        return out

    def class_ask(self, question: str) -> dict:
        """The teacher's cross-student question: ONE cognee recall() spanning every
        student's dataset (multi-dataset retrieval probed live 2026-07-04). Results
        come back per dataset, which is exactly the per-student shape a teacher needs."""
        if self._connected:
            try:
                for sid in sorted(self._states):
                    self.ensure_seeded(sid)
                datasets = [self._dataset(s) for s in sorted(self._states)]
                res = self._call(self._cognee.recall(
                    question, datasets=datasets, top_k=8), timeout=60)
                items = res if isinstance(res, list) else [res]
                per_student = []
                for i in items:
                    if not isinstance(i, dict) or not i.get("text"):
                        continue
                    ds = str(i.get("dataset_name", ""))
                    who = ds.replace("student_", "") or "class"
                    per_student.append({"student": who, "text": str(i["text"])})
                if per_student:
                    answer = "  ".join(
                        f"[{p['student']}] {p['text']}" for p in per_student)
                    return {"answer": answer, "per_student": per_student,
                            "datasets": datasets, "cloud": True}
            except Exception as err:
                print(f"[cloud] class recall failed, using local answer: {err}")
        out = super().class_ask(question)
        out["cloud"] = False
        return out

    def reset_student(self, student: str) -> dict:
        dataset = self._dataset(student)
        if self._connected and dataset in self._seeded:
            try:
                self._call(self._cognee.forget(dataset=dataset), timeout=45)
                self._seeded.discard(dataset)
                self._ledger.unmark_seeded(dataset)
            except Exception as err:
                print(f"[cloud] forget failed (continuing with local reset): {err}")
        out = super().reset_student(student)
        self._ledger.save_student(student, self._states[student])
        return out

    def add_student(self, student: str) -> dict:
        out = super().add_student(student)
        if out.get("ok"):
            self._ledger.save_student(out["student"], self._states[out["student"]])
        return out

    def import_curriculum(self, payload: dict) -> dict:
        out = super().import_curriculum(payload)
        self._ledger.save_all(self._states)
        self._seeded = self._ledger.seeded(self.curriculum["domain"])
        return out

    def assign_review(self, concept: str) -> dict:
        out = super().assign_review(concept)
        if out.get("ok"):
            out["intervention"] = self._ledger.create_intervention(
                out["concept"], out["concept_name"], out["students"])
            if self._connected and out["students"]:
                names = ", ".join(s["student"] for s in out["students"])
                self._fire_and_forget(self._cognee.remember(
                    f"Teacher assigned review for '{out['concept_name']}' to: {names}.",
                    dataset_name="class_interventions",
                    node_set=["teacher-intervention", self.curriculum["domain"]]))
        out["recent"] = self._ledger.recent_interventions()
        return out

    def close(self) -> None:
        if not getattr(self, "_loop", None):
            return

        async def close_telemetry():
            try:
                import cognee.shared.utils as utils

                session = getattr(utils, "_telemetry_session", None)
                if session and not session.closed:
                    await session.close()
                utils._telemetry_session = None
                utils._telemetry_session_loop = None
            except Exception:
                pass

        if self._connected:
            try:
                self._call(self._cognee.disconnect(), timeout=20)
            except Exception as err:
                print(f"[cloud] disconnect failed during shutdown: {err}")

        try:
            self._call(close_telemetry(), timeout=10)
        except Exception:
            pass

        try:
            self._loop.call_soon_threadsafe(self._loop.stop)
        except Exception:
            pass


def make_provider(mode: str) -> ClassroomProvider:
    if mode == "demo":
        return DemoProvider()
    if mode == "cloud":
        import os
        url = os.environ.get("COGNEE_CLOUD_URL", "")
        key = os.environ.get("COGNEE_CLOUD_API_KEY", "")
        if not url or not key:
            raise RuntimeError("CLASSROOM_MODE=cloud needs COGNEE_CLOUD_URL and "
                               "COGNEE_CLOUD_API_KEY in backend/.env")
        return CloudProvider(url, key)
    raise ValueError(f"unknown CLASSROOM_MODE: {mode}")
