import pytest

from app import grammar

CLEAN = ("I would limit requests per user and keep the counters in Redis. When a client goes over the limit, "
         "I return a 429 status with a Retry-After header. For example, in my project I limited login attempts "
         "to five per minute.")


def kinds(text):
    return [i["kind"] for i in grammar.analyze(text)["issues"]]


def test_well_formed_spoken_answer_scores_top_marks():
    result = grammar.analyze(CLEAN)
    assert result["issues"] == [] and result["score"] == 10


@pytest.mark.parametrize("text, expected_kind, fix", [
    ("He dont know the answer to that.", "agreement", "doesn't"),
    ("She have two years of experience.", "agreement", "has"),
    ("They was confused by the error.", "agreement", "were"),
    ("I is ready for the next question.", "agreement", "I am"),
    ("There is many ways to solve this.", "agreement", "there are many"),
    ("Last year I build a small web app.", "tense", "built"),
    ("Yesterday we deploy the change to staging.", "tense", "deployed"),
    ("We working on the search feature.", "tense", "are working"),
    ("I working on the project for months.", "tense", "am working"),
    ("We discuss about the design every week.", "usage", "discuss the"),
    ("It is more better than before.", "usage", "better"),
    ("I am agree with that approach.", "usage", "I agree"),
    ("I have worked here since 2 years.", "usage", "for 2 years"),
    ("He is a engineer at the company.", "article", "an engineer"),
    ("Me and my team worked on the API.", "usage", "My team and I"),
    ("I didn't have no time to test it.", "negation", "any"),
    ("The the cache was empty.", "repetition", "The cache"),
])
def test_each_rule_fires_with_a_helpful_fix(text, expected_kind, fix):
    issues = grammar.analyze(text)["issues"]
    assert any(i["kind"] == expected_kind and fix.lower() in i["suggestion"].lower() for i in issues), issues
    assert all(i["original"] and i["suggestion"] and i["note"] for i in issues)


def test_spelling_capitalisation_and_punctuation_are_ignored():
    text = "teh databse stores recrods in tabels and i use indxes to make serches faster and it works wel for us"
    assert kinds(text) == []
    assert grammar.analyze("I DID THIS PROJECT WITH MY TEAM AND WE SHIPPED IT")["issues"] == []


def test_casual_spoken_style_is_not_penalised():
    text = "im gonna be honest, i dont have much experience but i learned alot. basically i built a small api and it worked. kinda proud of it"
    result = grammar.analyze(text)
    assert result["issues"] == [] and result["score"] >= 8


def test_short_spoken_fragments_are_allowed_but_long_ones_are_flagged():
    assert "fragment" not in kinds("Great question. Kinda proud of it. I built the API and it worked well for us.")
    assert "fragment" in kinds("Because of the slow search. I measured the queries and added an index.")
    assert "fragment" in kinds("The slow performance of the whole application in production. Then I added an index to fix it.")
    # words like "query" can be nouns or verbs, so the rule gives them the benefit of the doubt


def test_run_on_sentences_are_flagged():
    chained = ("I measured the queries and then I added an index and then I added a cache and also I tested it and "
               "so the response time dropped and then we deployed it and everyone was happy with it.")
    assert "run-on" in kinds(chained)
    unpunctuated = "i would start by understanding the requirement then design the tables and the api and write the tests first and deploy it to a staging server and check the logs and monitor the errors and then roll it out slowly to all of the users while watching the metrics"
    assert kinds(unpunctuated).count("run-on") == 1


def test_no_false_alarm_on_common_good_patterns():
    for text in ["We use a university API with an hour of caching.", "That is e.g. a cache, i.e. a fast store, and so on.",
                 "It is what it is, and that that I said was true.", "I had had enough time to finish."]:
        assert kinds(text) == [], text


def test_more_errors_means_a_lower_score_and_the_score_is_bounded():
    clean = grammar.analyze(CLEAN)["score"]
    messy = grammar.analyze("Last year I build an api. He dont know why. We working on it since 2 years. There is many bugs.")["score"]
    assert messy < clean - 3
    for text in ["", "ok", "word " * 500]:
        assert 1 <= grammar.analyze(text)["score"] <= 10


def test_very_short_answers_cannot_score_high():
    assert grammar.analyze("It is fast.")["score"] <= 5


def test_issue_list_is_capped():
    text = " ".join(["He dont know it."] * 30)
    assert len(grammar.analyze(text)["issues"]) <= 8


def test_delivery_facts():
    d = grammar.delivery("Um, so basically I built an API. You know, it was kind of fast.")
    assert d["words"] == 14 and d["sentences"] == 2
    assert d["fillers"]["um"] == 1 and d["fillers"]["you know"] == 1 and d["filler_total"] == 4
    assert d["speaking_seconds"] >= 1 and d["pace"]
    long_answer = grammar.delivery("word " * 400)
    assert "Long" in long_answer["pace"]