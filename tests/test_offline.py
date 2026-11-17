from app.llm.offline import OfflineProvider, score_answer, track_for
from app.models import Context

ENTRY = {"keywords": ["index", "b-tree", "read", "write", "query plan", "selectivity"], "ideal": ""}


def test_track_detection():
    assert track_for("Backend Developer") == "backend"
    assert track_for("React Frontend Engineer") == "frontend"
    assert track_for("Full Stack Developer") == "fullstack"
    assert track_for("Data Analyst") == "data"
    assert track_for("DevOps Engineer") == "devops"
    assert track_for("QA Engineer") == "qa"
    assert track_for("Astronaut") == "general"


def test_good_answer_outscores_thin_answer():
    good = ("An index, usually a B-tree, speeds up read queries because the database avoids scanning the table. "
            "However it slows every write, so for example in my project I indexed only the selective columns and "
            "checked the query plan. First measure, then add the index, finally verify it helped by 40 percent.")
    thin = "It makes things faster."
    good_scores, _ = score_answer(ENTRY, good)
    thin_scores, missing = score_answer(ENTRY, thin)
    assert sum(good_scores.values()) > sum(thin_scores.values()) + 8
    assert good_scores["relevance"] >= 7
    assert thin_scores["depth"] <= 2
    assert "index" in missing


def test_scores_stay_in_range():
    for text in ["x", "um uh like basically " * 40, "word " * 900]:
        scores, _ = score_answer(ENTRY, text)
        assert all(1 <= v <= 10 for v in scores.values())


def test_plan_has_distinct_questions_and_a_behavioural_one():
    provider = OfflineProvider()
    ctx = Context(role="Backend Developer", level="junior", total=5, index=0, seed=42)
    plan = provider._plan(ctx)
    assert len(plan) == 5
    assert len({e["q"] for e in plan}) == 5
    behavioural = {e["q"] for e in provider._data["behavioral"]}
    assert any(e["q"] in behavioural for e in plan)


def test_plan_is_deterministic_for_a_seed():
    provider = OfflineProvider()
    a = provider._plan(Context(role="Data Analyst", level="mid", total=6, index=0, seed=7))
    b = provider._plan(Context(role="Data Analyst", level="mid", total=6, index=3, seed=7))
    assert [e["q"] for e in a] == [e["q"] for e in b]


def test_review_returns_sample_answer_and_next_question():
    provider = OfflineProvider()
    ctx = Context(role="Backend Developer", level="junior", total=3, index=0, seed=1)
    q = provider.first_question(ctx)
    evaluation, nxt = provider.review_answer(ctx, q, "I would use an index.", want_next=True)
    assert evaluation.sample_answer
    assert nxt is not None and nxt.text != q.text
    _, none_left = provider.review_answer(ctx, q, "I would use an index.", want_next=False)
    assert none_left is None

def test_report_never_lists_a_topic_as_both_strength_and_weakness():
    provider = OfflineProvider()
    for scores in ([6.7, 6.3, 6.9], [9, 8, 2], [3, 2, 4], [8, 9, 9]):
        history = [{"question": f"q{i}", "topic": f"Topic {i}", "answer": "a", "overall": s} for i, s in enumerate(scores)]
        ctx = Context(role="QA Engineer", level="junior", total=len(scores), index=len(scores), seed=1, history=history)
        report = provider.final_report(ctx)
        topics = lambda items: {i.split(":")[0] for i in items}
        assert not topics(report["strengths"]) & topics(report["weaknesses"]), scores
        assert report["practice_plan"] and report["summary"]