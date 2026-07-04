"""Classroom Memory: FastAPI backend (TRACK-B.md §5).

Run (demo mode, zero deps beyond fastapi/uvicorn):
    cd track-b-classroom-memory/backend
    uvicorn app:app --port 8002

CLASSROOM_MODE=demo (default) | cloud (after Day-1 Cloud verification).
"""

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from providers import make_provider


def _load_env():
    """Minimal .env loader: real env vars win over file values."""
    env_path = Path(__file__).resolve().parent / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())


_load_env()
MODE = os.environ.get("CLASSROOM_MODE", "demo")

app = FastAPI(title="Classroom Memory")
provider = make_provider(MODE)


@app.on_event("shutdown")
def close_provider():
    provider.close()


class AnswerBody(BaseModel):
    student: str
    concept: str
    answer_index: int


class AskBody(BaseModel):
    student: str
    question: str


class StudentBody(BaseModel):
    student: str


class RetireBody(BaseModel):
    student: str
    concept: str


class AssignReviewBody(BaseModel):
    concept: str


def _guard(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except KeyError as err:
        raise HTTPException(status_code=404, detail=str(err))


@app.get("/api/health")
def health():
    return provider.health()


@app.get("/api/students")
def students():
    return provider.students()


@app.get("/api/student/graph")
def student_graph(student: str, offset_days: int = 0):
    return _guard(provider.student_graph, student, offset_days)


@app.post("/api/quiz/next")
def quiz_next(body: StudentBody):
    return _guard(provider.quiz_next, body.student)


@app.post("/api/quiz/answer")
def quiz_answer(body: AnswerBody):
    return _guard(provider.quiz_answer, body.student, body.concept, body.answer_index)


@app.get("/api/class/heatmap")
def class_heatmap(offset_days: int = 0):
    return provider.class_heatmap(offset_days)


@app.post("/api/retire")
def retire(body: RetireBody):
    return _guard(provider.retire, body.student, body.concept)


@app.post("/api/reset-student")
def reset_student(body: StudentBody):
    return _guard(provider.reset_student, body.student)


@app.post("/api/ask")
def ask(body: AskBody):
    return _guard(provider.ask, body.student, body.question)


class ClassAskBody(BaseModel):
    question: str


@app.post("/api/class/ask")
def class_ask(body: ClassAskBody):
    return provider.class_ask(body.question)


@app.post("/api/student/add")
def add_student(body: StudentBody):
    return provider.add_student(body.student)


@app.get("/api/curricula")
def curricula():
    return provider.curricula()


@app.post("/api/curriculum/import")
def import_curriculum(body: dict):
    try:
        return provider.import_curriculum(body)
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err))


@app.post("/api/teacher/assign-review")
def assign_review(body: AssignReviewBody):
    return _guard(provider.assign_review, body.concept)


FRONTEND = Path(__file__).resolve().parent.parent / "frontend"
if FRONTEND.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND), html=True), name="frontend")
