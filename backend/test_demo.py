"""Smoke test: full Classroom Memory demo arc in DEMO mode via TestClient.

Run: python test_demo.py  (no network, no cloud account needed)
"""
import os
import sys
from pathlib import Path

os.environ["CLASSROOM_MODE"] = "demo"  # force demo regardless of .env
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi.testclient import TestClient
from app import app

c = TestClient(app)


def ok(r, label):
    assert r.status_code == 200, f"{label}: {r.status_code} {r.text[:200]}"
    return r.json()


h = ok(c.get("/api/health"), "health")
assert h["mode"] == "demo" and h["concepts"] == 22, h
print("health:", h)

s = ok(c.get("/api/students"), "students")
assert {x["id"] for x in s["students"]} == {"alice", "bob", "cara"}
print("students:", [(x["id"], x["avg_weight"], x["gaps"]) for x in s["students"]])

g = ok(c.get("/api/student/graph?student=alice"), "graph")
assert len(g["nodes"]) == 22 and g["next_step"], "graph shape"
reds = sum(1 for n in g["nodes"] if n["band"] == "red")
print(f"alice: {reds}/22 red, next_step={g['next_step']}")
assert reds == 22, "alice should start all red"

# frontier sanity: alice's first concepts must have no unmet prereqs
first = g["next_step"]
node = next(n for n in g["nodes"] if n["id"] == first)
assert node["requires"] == [] or all(
    next(n for n in g["nodes"] if n["id"] == r)["weight"] >= 0.35 for r in node["requires"]
), "frontier violated prereqs"

# quiz loop: answer correctly until the first concept goes green
q = ok(c.post("/api/quiz/next", json={"student": "alice"}), "quiz next")
assert not q["done"] and q["question"]["concept"] == first
import json as _json
curr = _json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "curriculum", "python.json"), encoding="utf-8"))
qbank = {cc["id"]: cc["questions"] for cc in curr["concepts"]}

concept = q["question"]["concept"]
weights = []
for i in range(3):
    # find the right answer from the curriculum (cursor-1 = question just served)
    text = q["question"]["text"]
    match = next(qq for qq in qbank[concept] if qq["q"] == text)
    a = ok(c.post("/api/quiz/answer", json={
        "student": "alice", "concept": concept, "answer_index": match["answer"]}), "answer")
    assert a["correct"], f"expected correct: {text}"
    weights.append(a["weight_after"])
    q = a["next"]
    if q["done"] or q["question"]["concept"] != concept:
        break
print(f"correct-answer progression on '{concept}': 0.2 -> {weights}")
assert weights[-1] > 0.75, "3 correct answers should reach green"

# wrong answer keeps a red node red
q2 = ok(c.post("/api/quiz/next", json={"student": "alice"}), "quiz next 2")
c2 = q2["question"]["concept"]
match = next(qq for qq in qbank[c2] if qq["q"] == q2["question"]["text"])
wrong = (match["answer"] + 1) % len(match["options"])
a2 = ok(c.post("/api/quiz/answer", json={
    "student": "alice", "concept": c2, "answer_index": wrong}), "wrong answer")
assert not a2["correct"] and a2["weight_after"] < a2["weight_before"]
print(f"wrong answer on '{c2}': {a2['weight_before']} -> {a2['weight_after']} (down, good)")

# teacher heatmap
hm = ok(c.get("/api/class/heatmap"), "heatmap")
rec = next(r for r in hm["concepts"] if r["id"] == "recursion")
print(f"heatmap: recursion red_pct={rec['red_pct']}%, teach_next={[t['id'] for t in hm['teach_next']]}")
assert rec["red_pct"] >= 50, "recursion should be a class-wide gap (cara+alice red)"

# decay view: cara's old greens go rusty with offset
gc0 = ok(c.get("/api/student/graph?student=cara&offset_days=0"), "cara now")
rusty0 = sum(1 for n in gc0["nodes"] if n["rusty"])
gc = ok(c.get("/api/student/graph?student=cara&offset_days=30"), "cara +30d")
rusty30 = sum(1 for n in gc["nodes"] if n["rusty"])
print(f"cara rusty nodes: {rusty0} at +0d -> {rusty30} at +30d")
assert rusty30 >= rusty0 and rusty0 > 0, "cara seeded 40d-old greens should be rusty"

# retire (forget) + guard
green_node = next(n["id"] for n in ok(c.get("/api/student/graph?student=alice"), "g")["nodes"]
                  if n["band"] == "green")
r1 = ok(c.post("/api/retire", json={"student": "alice", "concept": green_node}), "retire")
assert r1["ok"]
red_node = next(n["id"] for n in ok(c.get("/api/student/graph?student=alice"), "g")["nodes"]
                if n["band"] == "red")
r2 = ok(c.post("/api/retire", json={"student": "alice", "concept": red_node}), "retire red")
assert not r2["ok"], "must refuse retiring a red concept"
print(f"retire: {green_node} ok, {red_node} correctly refused")

# ask box
ans = ok(c.post("/api/ask", json={"student": "alice", "question": "explain closures to me"}), "ask")
assert "captured" in ans["answer"] or "Closures" in ans["answer"], ans
print("ask:", ans["answer"][:110])

# reset (transfer student)
ok(c.post("/api/reset-student", json={"student": "alice"}), "reset")
g3 = ok(c.get("/api/student/graph?student=alice"), "graph after reset")
assert sum(1 for n in g3["nodes"] if n["band"] == "red") == 22
print("reset: alice back to 22/22 red")

# ask the class (multi-dataset recall in cloud mode; deterministic here)
ca = ok(c.post("/api/class/ask", json={"question": "who knows recursion?"}), "class ask")
assert "Recursion" in ca["answer"] and "alice" in ca["answer"], ca
print("class ask:", ca["answer"][:100])

# teacher intervention workflow
ar = ok(c.post("/api/teacher/assign-review", json={"concept": "recursion"}), "assign review")
assert ar["ok"] and ar["assigned_count"] >= 2, ar
assert {s["student"] for s in ar["students"]} >= {"alice", "bob"}
print("assign review:", ar["message"], [(s["student"], s["band"]) for s in ar["students"]])

# enroll a new student (the "working product" feature)
e = ok(c.post("/api/student/add", json={"student": "Judge-One"}), "enroll")
assert e["ok"] and e["student"] == "judge-one", e
ge = ok(c.get("/api/student/graph?student=judge-one"), "new student graph")
assert sum(1 for n in ge["nodes"] if n["band"] == "red") == 22
dup = ok(c.post("/api/student/add", json={"student": "judge-one"}), "duplicate enroll")
assert not dup["ok"], "duplicate must be refused"
bad = ok(c.post("/api/student/add", json={"student": "x!"}), "bad name")
assert not bad["ok"], "invalid name must be refused"
print("enroll: judge-one added (22 red), duplicate + bad name refused")

# curriculum import: proves the product is not locked to Python
sample = {
    "domain": "math-demo",
    "title": "Math demo",
    "concepts": [
        {
            "id": "fractions",
            "name": "Fractions",
            "summary": "Parts of a whole and equivalent forms.",
            "requires": [],
            "questions": [
                {"q": "What is 1/2 + 1/2?", "options": ["1/4", "1", "2", "0"], "answer": 1}
            ],
        },
        {
            "id": "ratios",
            "name": "Ratios",
            "summary": "Comparing quantities multiplicatively.",
            "requires": ["fractions"],
            "questions": [
                {"q": "A 2:1 ratio means...", "options": ["equal parts", "two for every one", "one half", "unknown"], "answer": 1}
            ],
        },
    ],
}
imp = ok(c.post("/api/curriculum/import", json=sample), "import curriculum")
assert imp["ok"] and imp["domain"] == "math-demo" and imp["concepts"] == 2, imp
h2 = ok(c.get("/api/health"), "health after import")
assert h2["domain"] == "math-demo" and h2["concepts"] == 2, h2
bad_curr = c.post("/api/curriculum/import", json={
    "domain": "bad-demo", "title": "Bad", "concepts": [
        {"id": "a", "name": "A", "summary": "A", "requires": ["missing"],
         "questions": [{"q": "q", "options": ["a", "b"], "answer": 0}]}
    ],
})
assert bad_curr.status_code == 400, bad_curr.text
print("curriculum import: math-demo live, invalid prerequisite refused")
math_demo_path = Path(__file__).resolve().parent.parent / "curriculum" / "imported" / "math-demo.json"
if math_demo_path.exists():
    math_demo_path.unlink()

# 404 guard
assert c.get("/api/student/graph?student=nobody").status_code == 404

print("\nALL TRACK-B DEMO-MODE SMOKE TESTS PASSED")
