# Classroom Memory

> Content apps give a class a syllabus. Cognee gives it a memory. Classroom Memory gives the teacher a plan.

Classroom Memory is a Cognee Cloud-powered classroom memory layer. It gives every student an isolated long-term memory, adaptive mastery graph, personal recall surface, and report card. It gives the teacher a class-level memory map that reads across all students, identifies the next concept to teach, and turns class-wide gaps into assigned interventions.

Most tools stop at showing you the gaps. This one reasons over the class memory and makes the decision:

> Instead of "the class is failing recursion," Classroom Memory says: "This week, teach functions. The class is failing recursion the hardest, but they are not ready for it yet. Functions is the foundation that unblocks it, and it opens up thirteen more concepts."

That is the difference between a dashboard and a memory that reasons.

By the numbers, on the live tenant: **12 private student memories, one dense class graph of roughly 290 relationship edges, a 22-concept prerequisite graph, and a 12-check verification that runs the full Cognee Cloud lifecycle against the real tenant.**

The project was built for Track B, Best Use of Cognee Cloud. It is designed as a working product prototype rather than a scripted demo: it has durable state, class setup, student enrollment, curriculum import, live cloud verification, and a teacher workflow that can be used end to end.

Live demo: https://classroom-memory.vercel.app/

Repository: https://github.com/RajdeepKushwaha5/ClassroomMemory

## Core Idea

Most education software stores content. Classroom Memory stores learning state.

A teacher does not only need another quiz or another chatbot. A teacher needs to know:

- what each student has mastered;
- what each student is forgetting;
- what each student is ready to learn next;
- what the whole class is stuck on;
- which students need targeted review;
- why the system is recommending a specific next lesson.

Classroom Memory treats those questions as a memory problem. Each student becomes a separate Cognee Cloud memory. The teacher view reads across those memories to produce a class heat map, a graph-reasoned teaching plan, and targeted interventions.

## What the Product Does

### Student Experience

- Select or enroll a student.
- Start an adaptive quiz.
- Watch the student's concept graph update live as answers change mastery.
- Ask the student's memory questions such as `explain closures to me`.
- See the next recommended concept and the graph reason behind it.
- Inspect the learning timeline, cloud memory contents, session log, and concept details.
- Generate a progress report from the student's own memory.
- Retire mastered concepts from active practice.
- Reset a student as a transfer-student or fresh-start workflow.

### Teacher Experience

- Ask a class-level question across the class memory.
- View a full class heat map over the same curriculum graph.
- See a graph-reasoned teaching plan that prioritizes concepts students are ready to learn, not merely the concepts with the highest raw failure rate.
- Assign review to every student who is red or rusty on a concept.
- Drill into an individual student's graph from the teacher page.
- Set up a class roster in one action.
- View students in a scrollable roster with current mastery summary.

### Curriculum Experience

- Use the built-in Python fundamentals curriculum.
- Import a new curriculum from JSON through the UI.
- Validate concept IDs, prerequisites, question structure, and answer indexes.
- Reset the class onto the imported curriculum after validation.

## Why Cognee Cloud Matters

The important architectural choice is not simply that the app is hosted or uses an AI memory API. The important choice is that the classroom is modeled as many memories, not one.

Classroom Memory uses Cognee Cloud in three layers:

1. **Private student memories**: each student has an isolated dataset such as `student_alice`.
2. **Shared class memory**: the teacher can query a dense class graph that summarizes all students and concepts.
3. **Intervention memory**: teacher-assigned reviews are written to `class_interventions`.

This structure makes the teacher view cloud-native. A single local graph can show one memory. This product needs many private memories and a teacher view that reads across them.

## Why a Graph, Not a Vector Database

Multi-tenancy is why this needs the cloud. Graph memory is why it needs Cognee specifically.

A vector database only knows that two things are similar. The entire product depends on a different relationship: one concept `requires` another. "Recursion requires functions" is not a similarity, it is a directed edge, and the teaching logic is impossible without it.

Cognee builds an actual knowledge graph from plain relationship sentences. When the app seeds a student with "learning recursion requires functions and conditionals," Cognee extracts the concepts as entities and the prerequisite as a real edge. Recall then does graph traversal, not keyword matching: ask a student's memory "what must I learn before decorators?" and it answers "functions and closures" by walking the edges to the nodes those edges point to.

That is why plain vector search or RAG would not have worked here. A vector hit finds similar text and misses the prerequisite structure. Cognee gives the graph, the extraction, and the hosted multi-tenant storage in one layer, which is exactly the combination this product needs.

## Cognee Cloud Lifecycle Usage

| Cognee capability | Product usage |
|---|---|
| `serve()` | Connects the backend to the authenticated Cognee Cloud tenant. The UI badge reports the live cloud connection state. |
| `remember()` | Seeds each student dataset with a relationship-rich curriculum document. Also writes mastery traces, progress snapshots, class overview memory, teaching-plan memory, and teacher interventions. |
| `remember(session_id=...)` | Stores quiz attempts as session memory so recent learning events can be attached to the current student session without forcing every attempt into permanent graph memory. |
| `remember(node_set=...)` | Tags memories as `curriculum`, `progress`, `mastery-trace`, `class-overview`, `teaching-plan`, or `teacher-intervention` so the cloud console shows structured memory activity. |
| `recall()` | Powers the student ask box, student report generation, class ask flow, and fallback multi-dataset class recall. |
| Multi-dataset recall | Supports the teacher's ability to query across multiple student datasets when the combined class graph is not used. |
| `forget()` | Deletes a student's active cloud dataset during reset and removes a mastered concept from active practice through the retire workflow. |
| `improve()` | Honest limitation: on the tenant used during the hackathon, Cognee Cloud's remote `improve()` endpoint returned 404, so mastery re-weighting runs app-side with the same feedback-weight semantics and is persisted in the SQLite ledger. The provider boundary is written so native cloud `improve()` drops in with no UI change the day the remote endpoint is available. Stating this plainly is deliberate: the goal was a working product, not a faked capability. |

## Product Architecture

```text
Browser SPA
  Student view
    mastery summary
    adaptive quiz
    personal ask box
    concept graph
    learning timeline
    report card
    cloud memory contents

  Teacher view
    class ask box
    graph-reasoned teaching plan
    intervention workflow
    student roster
    class heat map
    per-student drill-down

        REST/JSON

FastAPI backend
  CloudProvider
    Cognee Cloud through cognee.serve()
    async SDK bridged into sync FastAPI endpoints

  SQLite ledger
    students
    mastery weights
    seeded datasets
    interventions
    intervention_students
    tenant metadata

        Cognee SDK

Cognee Cloud tenant
  student_alice
  student_bob
  student_cara
  ...
  class_graph
  class_interventions
```

## Backend Design

The backend is a FastAPI application in `backend/app.py`. The `CloudProvider` handles the real Cognee Cloud integration and the SQLite persistence layer, and exposes a clean JSON API to the frontend.

### Main API Surface

| Endpoint | Purpose |
|---|---|
| `GET /api/health` | Cloud connection status, active curriculum, concept count, seeded students, ledger name. |
| `GET /api/students` | Roster with mastery counts and gap counts. |
| `GET /api/student/graph` | Student concept graph, frontier, next step, explainability, assignments, and session memory count. |
| `GET /api/student/timeline` | Learning history reconstructed from concept practice timestamps and decay state. |
| `GET /api/student/report` | Progress report generated from the student's own Cognee Cloud memory via recall. |
| `POST /api/quiz/next` | Next adaptive question for the student's graph frontier. |
| `POST /api/quiz/answer` | Updates mastery weight, session memory, cursor, graph state, and cloud traces. |
| `GET /api/class/heatmap` | Class-wide concept heat map with red, amber, green, and average mastery signals. |
| `GET /api/teacher/plan` | Graph-reasoned teaching plan ranked by readiness and downstream unlock value. |
| `POST /api/ask` | Student-level recall from that student's memory. |
| `POST /api/class/ask` | Teacher-level recall from the class graph or multiple student datasets. |
| `POST /api/teacher/assign-review` | Creates a targeted review assignment for red or rusty students. |
| `POST /api/student/add` | Adds one student with a fresh mastery graph. |
| `POST /api/class/setup` | Adds a roster of students in one action. |
| `POST /api/curriculum/import` | Validates and activates a new curriculum JSON. |
| `POST /api/retire` | Retires a mastered concept from active practice. |
| `POST /api/reset-student` | Resets local mastery and deletes the active cloud dataset when connected. |

## Mastery Model

Each concept has a floating mastery weight:

| Weight range | Band | Meaning |
|---|---|---|
| `< 0.35` | red | gap |
| `0.35` to `0.75` | amber | learning |
| `> 0.75` | green | mastered |

Correct answers move mastery upward:

```text
w = w + 0.35 * (1 - w)
```

Wrong answers move mastery downward:

```text
w = w - 0.15 * w
```

A fresh concept starts at `0.2`. Three correct answers move a concept from `0.2` to approximately `0.78`, which marks it green.

Mastered concepts can become rusty in the view layer after 14 days untouched. The top navigation includes an `age +30d` control so the demo can show forgetting without mutating the underlying timestamps.

## Graph-Native Learning Logic

The curriculum is not treated as a flat question bank. Each concept has prerequisites in `requires`, forming a directed concept graph.

The quiz chooses a student's frontier:

1. Ignore retired concepts.
2. Ignore already mastered concepts.
3. Keep concepts whose prerequisites are at least amber.
4. Prioritize amber concepts before opening new red concepts.

The student report explains this decision with:

- the frontier rule;
- the selected next concept;
- prerequisite readiness;
- the concept chain that led to the recommendation.

The teacher plan applies a class-level version of the same graph reasoning. It scores a concept higher when many students are stuck on it, those students are ready for it, and the concept unlocks many downstream concepts. This prevents the teacher plan from recommending advanced concepts before the class is prepared for their prerequisites.

## Data Persistence

Cloud mode uses `backend/mastery_ledger.sqlite`. The file is ignored by Git because it is runtime state.

SQLite stores:

- students;
- exact mastery weights;
- concept timestamps;
- retired flags;
- seeded Cognee datasets;
- tenant metadata;
- teacher interventions;
- intervention-student assignments.

The app previously supported `cloud_state.json`; the ledger contains a migration helper that can import that legacy file once if present.

## Cognee Dataset Strategy

### Student Datasets

Each student gets a dataset name:

```text
student_<student_id>
```

For imported non-Python curricula, the domain is included:

```text
student_<domain>_<student_id>
```

Each student seed is a relationship-rich document. It anchors the student as an entity, names the active course, describes every concept, and states prerequisite relationships as explicit sentences. This makes Cognee's graph extraction useful for both concept recall and student-specific progress recall.

### Class Graph

The teacher can use a combined class dataset:

```text
class_graph
```

This dataset is intentionally dense. It contains:

- student entities;
- concept entities;
- prerequisite relationships;
- one sentence per student-concept mastery relation;
- class-level progress signals.

The teacher's `ask the class` workflow prefers this combined class graph. If it is unavailable, the backend falls back to recall across seeded per-student datasets.

### Intervention Dataset

Teacher review assignments are written to:

```text
class_interventions
```

They are tagged with `teacher-intervention` and the active curriculum domain.

## Frontend Design

The frontend is a static browser app served from `frontend/`. It uses:

- `vis-network` for graph rendering;
- `lucide` for icons;
- plain JavaScript for state and API calls;
- CSS in `frontend/style.css`.

The main pages are:

- `student`: student mastery, quiz, graph, report, timeline, cloud memory contents;
- `teacher`: class ask, teaching plan, intervention workflow, roster, heat map;
- `about`: project explanation, architecture, product readiness, and proof points.

The student and teacher pages are intentionally arranged as stacked full-width work areas so the graph and reports have enough space during a live demo.

## Curriculum Format

The built-in curriculum lives at `curriculum/python.json`.

Each curriculum has:

```json
{
  "domain": "python",
  "title": "Python fundamentals -> async",
  "concepts": [
    {
      "id": "variables",
      "name": "Variables & assignment",
      "summary": "Names bound to objects; Python variables are references, not boxes.",
      "requires": [],
      "questions": [
        {
          "q": "After `a = [1]; b = a; b.append(2)`, what is `a`?",
          "options": ["[1]", "[1, 2]", "[2]", "error"],
          "answer": 1
        }
      ]
    }
  ]
}
```

The validator checks:

- domain format;
- non-empty title;
- non-empty concept list;
- valid concept IDs;
- duplicate concept IDs;
- required names and summaries;
- prerequisite references;
- question text;
- options;
- answer indexes.

Imported curriculum files are written under `curriculum/imported/`, which is ignored by Git as runtime state.

## Sample Class Data

The app seeds a class-sized roster with different mastery profiles so the teacher view is meaningful from the first second:

- `alice`: fresh student, all concepts red;
- `bob`: mid-progress;
- `cara`: advanced but rusty on older mastered concepts;
- additional students with varied progress patterns.

Recursion and async-related concepts are intentionally class-wide gaps so the teacher heat map and teaching plan are meaningful immediately.

## Running the Project

### Prerequisites

- Python 3.11
- FastAPI and Uvicorn available in the Python environment
- Cognee SDK available in the Python environment for cloud mode
- Browser with internet access for CDN-loaded frontend libraries

The commands below use the existing local virtual environment path used in this workspace:

```powershell
D:\cognee\.venv\Scripts\python.exe
```

Adjust that path if your Python environment is elsewhere.

### Configure and Run

Create `backend/.env`:

```env
CLASSROOM_MODE=cloud
COGNEE_CLOUD_URL=https://your-tenant.aws.cognee.ai
COGNEE_CLOUD_API_KEY=your_api_key
```

Run:

```powershell
cd D:\cognee-hack\track-b-classroom-memory\backend
D:\cognee\.venv\Scripts\python.exe -m uvicorn app:app --port 8002 --host 127.0.0.1
```

For a phone demo on the same network:

```powershell
cd D:\cognee-hack\track-b-classroom-memory\backend
D:\cognee\.venv\Scripts\python.exe -m uvicorn app:app --port 8002 --host 0.0.0.0
```

Then open:

```text
http://<your-LAN-IP>:8002
```

## Verification

### Product Logic Smoke Test

This validates the product's graph, mastery, and teaching logic deterministically:

```powershell
cd D:\cognee-hack\track-b-classroom-memory
D:\cognee\.venv\Scripts\python.exe backend\test_demo.py
```

This validates:

- health endpoint;
- class-sized roster;
- student graph shape;
- frontier explanation;
- quiz progression from red to green;
- wrong-answer downgrade;
- class heat map;
- graph-reasoned teaching plan;
- rusty decay view;
- retire guard;
- ask box;
- reset;
- direct quiz-answer cursor behavior;
- class ask;
- teacher intervention workflow;
- enrollment and validation;
- class setup;
- curriculum import and prerequisite validation;
- 404 guard.

### Live Cognee Cloud Verification

```powershell
cd D:\cognee-hack\track-b-classroom-memory
D:\cognee\.venv\Scripts\python.exe backend\verify_cloud.py
```

This validates against the configured tenant:

- `serve()` authentication and connection;
- `remember()` ingestion into a verification dataset;
- `recall()` answer from the cloud graph;
- dataset provenance on recall results;
- `remember(session_id=...)` session-memory write;
- `remember(node_set=...)` node-set tagging;
- one recall across multiple datasets;
- `forget()` dataset deletion;
- deterministic product arc from red to green;
- teacher heat-map signal;
- frontier explanation.

## Suggested Demo Flow

1. Start the app and show the `cognee cloud` badge.
2. Open Alice in the student view.
3. Answer three quiz questions correctly and show one concept move to mastered.
4. Point to the student report: next step, explanation, timeline, and cloud memory contents.
5. Ask Alice's memory: `explain closures to me`.
6. Generate a report card.
7. Switch to the teacher page.
8. Show the graph-reasoned teaching plan.
9. Ask the class: `who has mastered recursion?`
10. Assign review from a recommended class gap.
11. Drill into Alice from the teacher roster and return to the class heat map.
12. Open the Cognee Cloud console and show student datasets, `class_graph`, and `class_interventions`.
13. Run `backend\verify_cloud.py` for executable proof.

## Cloud Console Proof Points

In the Cognee Cloud console, the following should be visible after using the app in cloud mode:

- `student_alice`, `student_bob`, `student_cara`, and any enrolled students;
- curriculum memory tagged as `curriculum`;
- progress snapshots tagged as `progress`;
- mastery traces tagged as `mastery-trace`;
- the dense `class_graph` dataset;
- teacher intervention memory in `class_interventions`;
- search answers from a selected student dataset.

These are not frontend-only artifacts. They are written by the backend through the Cognee SDK.

## Project Structure

```text
track-b-classroom-memory/
  README.md
  backend/
    app.py              FastAPI app and REST endpoints
    providers.py        CloudProvider, mastery logic, Cognee Cloud integration
    ledger.py           SQLite persistence layer
    test_demo.py        Product logic smoke test
    verify_cloud.py     Live Cognee Cloud verification
  curriculum/
    python.json         Built-in prerequisite graph and quiz bank
  frontend/
    index.html          Student, teacher, about views and modals
    app.js              Frontend state, API calls, graph rendering, UI wiring
    style.css           Full visual system and responsive layouts
```

Runtime files ignored by Git:

- `backend/.env`
- `backend/mastery_ledger.sqlite`
- `backend/cloud_state.json`
- `curriculum/imported/`

## Engineering Notes

- The browser stores no mastery state.
- Cloud calls are async, while FastAPI endpoints are sync; CloudProvider runs Cognee calls on a dedicated background event loop.
- Slow or non-critical cloud writes use fire-and-forget wrappers so the UI stays responsive.
- Student reset handles Cognee's asynchronous dataset deletion by falling back to versioned dataset names when needed.
- Class setup and enrollment seed cloud datasets in the background.
- Teacher recommendations are computed from the prerequisite graph and class mastery state, then written back into class memory.

## Final Notes

Classroom Memory demonstrates Cognee Cloud as more than a retrieval layer. It uses Cognee as a durable, multi-tenant memory system for a real classroom workflow:

- one private memory per student;
- one teacher view across many memories;
- graph-native prerequisite reasoning;
- live recall from student and class memory;
- session memory for quiz attempts;
- durable mastery state;
- targeted teacher interventions;
- verifiable cloud datasets and traces.

The result is a planned, working project that can be run locally, verified automatically, demonstrated live, and extended into a production classroom pilot.
