# 🎓 Classroom Memory

**A school that remembers. Every student gets an isolated Cognee Cloud memory,
adaptive mastery graph, and personal recall surface; the teacher gets a live heat map
of where the whole class is forgetting.**

Built for **The Hangover Part AI** hackathon · Track: **Best Use of Cognee Cloud** ·
Solo build, Jun–Jul 2026.

---

## The unsolved problem

In classrooms across India and much of the world, one teacher faces 40 to 60
students. Personal attention is mathematically impossible: no human can hold 60
individual mastery states in their head. So struggling students stay invisible
until exam day, and each year's gaps compound into the next year's failures.

EdTech attacked the wrong half of the problem. It digitized *content*: videos,
question banks, lectures at scale. What was never built is *memory* at scale: a
system that knows what each individual child actually knows, what they are
forgetting, and what they are ready to learn next, and that shows the teacher
where the whole class is silently failing.

That is a memory problem, not a content problem. So we built the school out of a
memory layer.

## The solution

- **One Cognee Cloud dataset per student.** Each student's mastery state lives in an
  isolated, hosted memory dataset: not in localStorage, not in a browser session, not
  on one device. Cognee Cloud owns long-term recall and learning traces; the backend
  stores exact quiz mastery weights until remote `improve()` is available.
- **A concept graph, not a question bank.** 22 Python concepts with `requires`
  prerequisite edges. The quiz engine picks your **frontier**: the gap whose
  prerequisites you already hold: by *graph traversal*, not similarity search. That's
  the "not just RAG" difference.
- **Explainable graph choices.** The student report shows *why* a concept is next:
  the frontier rule, prerequisite readiness, and the graph chain behind the
  recommendation. The teacher heat map also shows why a review was selected.
- **Mastery that moves like memory.** Correct answers push a concept red → amber →
  green on screen, live. Untouched concepts decay to *rusty*. Mastered ones can be
  **retired** (a real `forget()`), and a transfer student is one real dataset deletion.
- **The teacher heat map (the part no single-user app can do).** The teacher reads
  *across* all student datasets: "70% of the class is red on recursion: teach that
  Thursday." Per-student drill-down included. This cross-dataset aggregation over
  isolated per-student memories is exactly why this project needs **Cloud**, not a
  local instance.
- **Not hardcoded to three students or one subject.** The app can enroll a new student,
  import a new curriculum JSON, create a fresh memory path, quiz from zero, and seed
  Cognee datasets lazily on first recall.
- **Teacher intervention workflow.** The heat map is actionable: assign review to every
  student who is red or rusty on a concept, and persist that intervention in SQLite.
- **Class-sized setup.** A teacher can paste a roster and create many isolated student
  memories at once. The sample data also includes a believable multi-student classroom,
  not just three demo accounts.

## Why this needs the Cloud, not a local instance

This is the heart of the submission, so it is worth stating plainly.

The easy way to use a memory layer is to put everything into **one big graph**.
That is impressive to look at, but it does not need the Cloud: a single graph runs
just as well on a laptop.

A classroom is the opposite shape. It is **many private memories — one isolated
dataset per student — with a teacher who reads across all of them**, plus a combined
class graph that no individual student can see. That is a multi-tenant memory
problem, and it is structurally impossible on a single-user, single-writer local
instance. It is exactly what a hosted, multi-tenant memory layer is for.

So when the question is "why Cognee Cloud instead of local Cognee?", the answer here
is not "convenience" or "hosting." It is that the product's *architecture* — private
per-student memories plus cross-student teacher reads — cannot exist without it.

| Need | Why a local instance can't | What Cloud provides |
|---|---|---|
| Private, isolated memory per student | Single-writer, single principal | One hosted dataset per student |
| Teacher reads across every student at once | No multi-dataset tenancy | One tenant, many datasets, read across them |
| A combined class graph over private memories | Nothing to aggregate across | A shared `class_graph` dataset alongside the private ones |
| Same memory on any device, any day | State bound to one machine | `cognee.serve()` from anywhere |

## How it uses the memory lifecycle

| Capability | Where it runs, for real |
|---|---|
| `remember()` | Curriculum seeded into each student's Cloud dataset (one combined-document ingest, once); learning traces written when a concept is mastered, visible as activity in the Cognee Cloud console |
| `remember(session_id=…)` | Every quiz answer is written to Cognee session memory as fast learning context. This uses Cognee's session-memory model without forcing every attempt into permanent graph memory. |
| `remember(node_set=…)` | Every write is tagged (`curriculum`, `mastery-trace`): NodeSets become first-class graph nodes inside each student's memory |
| `recall()` | The student **ask box**: free questions answered from the student's own cloud graph, with dataset provenance (measured ~7s warm); the current learning session is also passed as context when available |
| **multi-dataset `recall()`** | The teacher's **ask the class** box: ONE recall spanning every student's dataset at once, results labeled per student. This is the cross-student moat running through Cognee itself, not app code |
| `forget()` | **Retire** a mastered concept; **reset student** = real `forget(dataset=…)` on the tenant (measured ~2s) |
| `improve()` | **Honesty note:** Cognee Cloud's remote API still returns 404 for `improve()` on this tenant (re-probed 2026-07-04), so mastery re-weighting runs app-layer and is persisted server-side. The UI still exposes the improve lifecycle honestly; the provider boundary is ready when Cloud exposes it remotely. |

**No client-side LLM key is needed.** `recall()` answers are generated server-side by
Cognee Cloud; quiz questions are curated in `curriculum/python.json`, deterministic by
design so the demo cannot die on a quota error.

Everything above was verified against a live tenant: see **Verification** below.

## Architecture

```
Browser SPA (student / teacher role toggle)
  student: mastery graph (vis-network) · quiz card · next-step · ask box
  teacher: class heat map · "teach this next" · per-student drill-down
        │ REST/JSON
FastAPI backend: provider pattern
  DemoProvider   deterministic, zero-network (unbreakable demo fallback)
  CloudProvider  real Cognee Cloud via cognee.serve(); async SDK bridged to
                 sync endpoints on a dedicated event-loop thread
  SQLite ledger  exact mastery weights, enrolled students, seeded datasets,
                 teacher interventions
        ├─ SQLite: exact weights, rosters, interventions
        │
        └─ cognee SDK
Cognee Cloud tenant:
  dataset per student (student_alice, student_bob, student_cara, ...)
  session memory for quiz attempts
  class_interventions dataset for teacher-assigned reviews
```

## Product readiness

This is designed as a working pilot, not just a staged hackathon clip.

- **Reusable curriculum model:** import a subject from the UI or add a JSON file with
  concepts, prerequisites, summaries, and quiz questions.
- **Real enrollment path:** the UI can add a new student; cloud mode creates their
  dataset lazily on first recall.
- **Durable mastery ledger:** cloud mode uses `backend/mastery_ledger.sqlite`, not a
  JSON blob, for exact mastery weights, enrolled students, seeded datasets, and
  teacher interventions.
- **Actionable teacher loop:** the teacher can assign review to everyone red or rusty
  on a concept; the assignment is persisted and can be shown in the product demo.
- **Append-only agent safety:** normal AI-facing flows can remember, recall, and
  confirm learning; destructive full wipes are not exposed as autonomous agent tools.
  Dataset reset remains a deliberate human action in the UI.
- **Deterministic fallback:** `CLASSROOM_MODE=demo` runs the exact same UI offline, so
  teachers and judges can try the product without cloud credentials.
- **Cloud-verifiable:** `backend/verify_cloud.py` asserts `serve()`, `remember()`,
  `recall()` with dataset provenance, multi-dataset recall, `forget()`, and the product
  quiz arc.
- **Graph-extraction-aware seeding:** the memory seed is written for the knowledge
  graph, not just for reading. An identity sentence anchors each student as an
  entity in their own memory ("this is the personal learning memory of alice"),
  and every prerequisite is stated as an explicit relationship sentence, because
  GraphRAG quality follows relationship-rich input.
- **Production path:** move the SQLite mastery ledger to managed Postgres if
  multi-school scale requires it, add school auth/RBAC, add richer
  curriculum authoring, an MCP server so coding agents and tutors can query the
  class memory directly, and native Cloud `improve()` when the remote endpoint is
  exposed.

## Why memory + education is the right bet

This is not a speculative pairing. Cognee's own team has described working with
the University of Wyoming on individualized education plans (IEPs), where feeding
prior context back into the planning flow measurably increased successful plan
creation. Education is memory work: what a learner already knows is the context
every next decision needs. Classroom Memory applies that same thesis at the
classroom level, with one hosted memory per student.

## Run it

```powershell
cd backend
copy .env.example .env       # fill in COGNEE_CLOUD_URL + COGNEE_CLOUD_API_KEY
D:\cognee\.venv\Scripts\python.exe -m uvicorn app:app --port 8002 --host 0.0.0.0
# open http://127.0.0.1:8002   (phone demo: http://<your-LAN-IP>:8002)
```

No Cloud account? `CLASSROOM_MODE=demo` in `.env` runs the identical UI fully offline.

## Verification (one command)

```powershell
cd backend
D:\cognee\.venv\Scripts\python.exe verify_cloud.py
```

Proves on the live tenant: `serve()` auth → `remember()` ingestion → `recall()` with a
correct answer **and dataset provenance** → multi-dataset class recall →
`forget()` deletion → the red→green quiz arc → the class-gap heat map. Exits non-zero
on any failure.

## Cloud console proof to record

For the final video, open the Cognee Cloud console (platform.cognee.ai) after
running the app. Each student is a real named dataset with its own extracted
knowledge graph, exactly like any Cognee dataset, just one per student instead
of one shared `main_dataset`:

1. In the dataset dropdown, `student_alice`, `student_bob`, `student_cara` exist.
2. Select `student_alice` and open **Knowledge Graph**. Cognee extracted the
   course concepts as entities and the prerequisite `requires` relationships as
   edges, from the seed document our app wrote. Click a node to see its source
   chunk, provenance (`extract_graph_from_data` / `cognify_pipeline`), and
   relations.
3. A mastered concept adds a `mastery-trace` node linking the student to the
   concept and to what it unlocks; the graph grows as the class learns.
4. Assigning review writes to the `class_interventions` dataset with
   `teacher-intervention` tags.

That the graph is real is provable without the console: `recall()` answers
prerequisite questions by traversing those edges. Ask a student "what must I
learn before decorators?" and the answer ("Functions and Closures") comes from
the graph, not keyword matching.

## Honest limitations

- Cloud `improve()` is not exposed remotely today (verified 404): mastery weighting is
  app-layer; the semantics mirror Cognee's feedback-weight design.
- Student/teacher roles are enforced by the app server over per-student datasets
  (isolation and cross-dataset reads are real; native Cloud RBAC was not exercised).
- Curriculum import is JSON-based; the next product step is a visual authoring flow for
  non-technical teachers.

## Disclosure

Built with AI pair-programming assistance (Claude). All memory is powered by Cognee
Cloud; all Cognee behavior claimed above was verified against a live tenant, with
timings, on 2026-07-03/04.
