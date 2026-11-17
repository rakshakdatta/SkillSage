"""Grammar = proper sentence formation, judged as SPOKEN English.

Answers are written the way a candidate would speak, so this deliberately ignores spelling,
capitalisation, punctuation style and casual spoken forms ("gonna", contractions). It looks for
structural problems an interviewer would notice:

  * incomplete sentences (fragments) and run-on sentences
  * subject-verb agreement   ("he don't", "they was")
  * tense consistency        ("last year I build ...")
  * missing helping verbs    ("we working on ...")
  * word usage               ("discuss about", "more better")
  * a/an, double negatives, repeated words

The rules are conservative: a missed error is better than a false alarm.
"""
from __future__ import annotations

import re

WPM = 130                      # typical speaking pace, used for the "speaking time" estimate

FILLERS = ("um", "umm", "uh", "uhh", "er", "you know", "i mean", "kind of", "sort of", "basically",
           "actually", "literally", "honestly", "or something", "and stuff")

_PAST = {"go": "went", "build": "built", "make": "made", "work": "worked", "do": "did", "use": "used",
         "see": "saw", "take": "took", "create": "created", "write": "wrote", "learn": "learned",
         "develop": "developed", "implement": "implemented", "fix": "fixed", "design": "designed", "lead": "led",
         "deploy": "deployed", "test": "tested", "add": "added", "change": "changed", "update": "updated",
         "finish": "finished", "complete": "completed", "start": "started", "run": "ran", "send": "sent",
         "give": "gave", "get": "got", "find": "found", "decide": "decided", "migrate": "migrated",
         "release": "released", "review": "reviewed", "plan": "planned", "solve": "solved", "meet": "met",
         "ship": "shipped", "join": "joined"}
# ("have" is left out on purpose: "last year I have worked" would get a wrong fix.)
_AUX = {"is", "are", "was", "were", "am", "be", "been", "being", "have", "has", "had", "do", "does", "did",
        "will", "would", "can", "could", "should", "may", "might", "must", "shall", "'s", "'re", "'m", "'ve", "'ll", "'d"}

_VERBS = set("""use build make create write test deploy design handle store check add run fix learn work help lead manage
implement improve reduce increase ensure return send get give take keep set call need want think know see find show move
change include develop analyze analyse optimize optimise measure monitor validate scale cache index query hash issue limit
split review explain discuss solve decide plan start finish join connect access read load parse render apply prefer
choose try say tell ask become seem feel mean believe understand support provide require allow prevent avoid collect built made went saw took wrote led found got gave knew began ran kept sent held brought thought told felt left met paid sat stood won
count compare combine break turn open close delete update remove replace maintain release ship own divide""".split())

_SUBORDINATORS = {"because", "although", "though", "whereas", "which", "whose", "unless", "whenever", "wherever"}

_NOT_REPEATS = {"that", "had", "very", "so", "no", "really", "bye", "well", "many", "much"}

_PROGRESSIVE = {"working", "doing", "building", "learning", "using", "developing", "trying", "going", "making",
                "testing", "studying", "looking", "writing", "creating", "handling", "managing"}

_PRONOUN_AUX = {"i": "am", "we": "are", "they": "are", "you": "are"}

_ARTICLE_EXCEPTIONS = ("uni", "use", "usu", "usa", "uti", "uto", "uk", "eu", "one", "once", "ubi", "ura", "uro")

_ABBREV = re.compile(r"\b(e\.g|i\.e|etc|vs|approx|mr|mrs|dr)\.", re.IGNORECASE)


def _plain(text: str) -> str:
    return _ABBREV.sub(lambda m: m.group(0).replace(".", ""), text)


def _sentences(text: str) -> list:
    parts = re.split(r"(?<=[.!?])\s+|\n+", _plain(text).strip())
    return [p.strip() for p in parts if p.strip()]


def _words(text: str) -> list:
    return [w.rstrip(".-") for w in re.findall(r"[A-Za-z0-9][A-Za-z0-9'+#.\-]*", text)]


def _snippet(text: str, start: int, end: int, replacement: str, pad: int = 26) -> tuple:
    """Show the mistake with a little surrounding context, before and after the fix."""
    left_from = max(0, start - pad)
    left = text[left_from:start]
    if left_from > 0 and " " in left:
        left = "…" + left[left.index(" ") + 1:]
    right_to = min(len(text), end + pad)
    right = text[end:right_to]
    if right_to < len(text) and " " in right:
        right = right[:right.rindex(" ")] + "…"
    before = " ".join((left + text[start:end] + right).split())
    after = " ".join((left + replacement + right).split())
    return before, after


def _same_case(src: str, repl: str) -> str:
    return repl[:1].upper() + repl[1:] if src[:1].isupper() else repl


def _has_verb(words: list) -> bool:
    for w in words:
        lw = w.lower()
        if lw in _AUX or lw in _VERBS or (len(lw) > 4 and lw.endswith(("ed", "ing"))):
            return True
    return False


# (pattern, replacement(match) -> str, explanation, kind)
_RULES = [
    (re.compile(r"\b(he|she|it)\s+(?:don't|dont|do not)\b", re.I), lambda m: f"{m[1]} doesn't",
     "With he, she and it, use 'doesn't'.", "agreement"),
    (re.compile(r"\b(he|she|it)\s+have\b", re.I), lambda m: f"{m[1]} has",
     "With he, she and it, use 'has'.", "agreement"),
    (re.compile(r"\b(he|she|it)\s+are\b", re.I), lambda m: f"{m[1]} is",
     "With he, she and it, use 'is'.", "agreement"),
    (re.compile(r"\b(we|they|you)\s+was\b", re.I), lambda m: f"{m[1]} were",
     "With we, they and you, use 'were'.", "agreement"),
    (re.compile(r"\bi\s+(?:is|are)\b", re.I), lambda m: "I am",
     "With 'I', use 'am'.", "agreement"),
    (re.compile(r"\bthere\s+is\s+(many|several|multiple|few|two|three|four|five|\d+)\b", re.I),
     lambda m: f"there are {m[1]}", "Use 'there are' before plural things.", "agreement"),
    (re.compile(r"\bpeople\s+(is|was)\b", re.I),
     lambda m: "people " + ("are" if m[1].lower() == "is" else "were"), "'People' is plural.", "agreement"),
    (re.compile(r"\bi\s+am\s+agree\b", re.I), lambda m: "I agree",
     "Say 'I agree' (no 'am').", "usage"),
    (re.compile(r"\bmore\s+(better|easier|faster|simpler|cheaper|bigger|cleaner)\b", re.I), lambda m: m[1],
     "'Better' is already a comparison, so drop 'more'.", "usage"),
    (re.compile(r"\bmost\s+(easiest|best|biggest|fastest|simplest|hardest)\b", re.I), lambda m: m[1],
     "Don't use 'most' with a word that already means 'most'.", "usage"),
    (re.compile(r"\bcan\s+able\s+to\b", re.I), lambda m: "can",
     "Say 'can' or 'is able to', not both.", "usage"),
    (re.compile(r"\bdiscuss\s+about\b", re.I), lambda m: "discuss",
     "'Discuss' needs no 'about'.", "usage"),
    (re.compile(r"\b(revert|return)\s+back\b", re.I), lambda m: m[1],
     "'Back' is already part of the meaning.", "usage"),
    (re.compile(r"\bcope\s+up\s+with\b", re.I), lambda m: "cope with",
     "Say 'cope with'.", "usage"),
    (re.compile(r"\bemphasi[sz]e\s+on\b", re.I), lambda m: "emphasize",
     "'Emphasize' needs no 'on'.", "usage"),
    (re.compile(r"\bsince\s+(\d+|a|one|two|three|four|five|six|seven|eight|nine|ten)\s+(years?|months?|weeks?|days?)\b", re.I),
     lambda m: f"for {m[1]} {m[2]}", "Use 'for' with a length of time, and 'since' with a starting point.", "usage"),
    (re.compile(r"\b(don't|doesn't|didn't|can't|won't|cannot|haven't|hasn't)\s+(?:\w+\s+){0,2}?(no|nothing|nobody|nowhere)\b", re.I),
     None, "Avoid double negatives: use 'any', 'anything' or 'anyone' after a negative.", "negation"),
]


def _regex_issues(text: str) -> list:
    hits = []
    for pattern, repl, note, kind in _RULES:
        for m in pattern.finditer(text):
            if repl is None:                      # double negative: show the advice, not a rewrite
                fixed = m.group(0).rsplit(None, 1)[0] + " " + {"no": "any", "nothing": "anything", "nobody": "anyone", "nowhere": "anywhere"}[m.group(2).lower()]
            else:
                fixed = _same_case(m.group(0), repl(m))
            hits.append((m.start(), m.end(), fixed, note, kind))
    return hits


def _function_issues(text: str) -> list:
    hits = []

    # a / an
    for m in re.finditer(r"\b([Aa])\s+([A-Za-z]+)", text):
        word = m.group(2)
        if word[0].lower() in "aeiou" and not word.lower().startswith(_ARTICLE_EXCEPTIONS) and not word.isupper():
            hits.append((m.start(1), m.end(2), _same_case(m.group(1), "an") + " " + word,
                         "Use 'an' before a vowel sound.", "article"))

    # "me and my team worked ..." -> "my team and I worked ..."
    for m in re.finditer(r"\b([Mm])e and my (\w+)\b(?=\s+(?:worked|built|made|did|decided|created|developed|started|were|have|had|led|designed|tested|deployed|used|wrote|found|learned|finished|completed))", text):
        fixed = ("My" if m.group(1) == "M" else "my") + f" {m.group(2)} and I"
        hits.append((m.start(), m.end(), fixed, "Put yourself last and use 'I' as the subject.", "usage"))

    # missing helping verb: "we working on" -> "we are working on"
    for m in re.finditer(r"\b(I|we|they|you)\s+(\w+ing)\b", text, re.I):
        if m.group(2).lower() in _PROGRESSIVE:
            aux = _PRONOUN_AUX[m.group(1).lower()]
            hits.append((m.start(), m.end(), f"{m.group(1)} {aux} {m.group(2)}",
                         "Add a helping verb ('am', 'are') before an -ing verb.", "tense"))

    # past-time marker with a present-tense verb: "last year I build ..." -> "built"
    for m in re.finditer(r"\b(yesterday|last\s+(?:week|month|year|semester|summer)|\d+\s+(?:days?|weeks?|months?|years?)\s+ago)\b[^.!?\n]{0,40}?\b(I|we|they|he|she)\s+(" + "|".join(_PAST) + r")\b", text, re.I):
        verb = m.group(3)
        hits.append((m.start(3), m.end(3), _PAST[verb.lower()],
                     f"'{m.group(1)}' points to the past, so use the past tense.", "tense"))

    # repeated word (a false start)
    for m in re.finditer(r"\b([A-Za-z']+)\s+\1\b", text, re.I):
        if m.group(1).lower() not in _NOT_REPEATS:
            hits.append((m.start(), m.end(), m.group(1), "Repeated word. Say it once.", "repetition"))
    return hits


def _sentence_issues(text: str) -> list:
    """Fragments and run-ons. These have no exact fix, so the 'suggestion' is advice."""
    issues = []
    sentences = _sentences(text)
    total_words = len(_words(text))

    fragments = 0
    for s in sentences:
        words = _words(s)
        n = len(words)
        if n < 3 or "?" in s or s.count(",") >= 2:
            continue
        lead = words[0].lower()
        no_verb = not _has_verb(words)
        dangling = lead in _SUBORDINATORS and n <= 8
        if ((no_verb and 5 <= n <= 14) or dangling) and fragments < 2:
            fragments += 1
            issues.append({
                "original": " ".join(words[:12]) + ("…" if n > 12 else ""),
                "suggestion": "Add what the subject does or is, so this becomes a full sentence.",
                "note": "This reads like an incomplete sentence." if no_verb else f"A sentence starting with '{lead}' needs a main clause too.",
                "kind": "fragment"})

    no_breaks = total_words >= 45 and not re.search(r"[.!?\n]", text)
    long_flagged = 2 if no_breaks else 0       # the whole-answer note below covers it
    for s in sentences:
        words = _words(s)
        n = len(words)
        joins = len(re.findall(r"\b(and|so|then|also)\b", s, re.I))
        if (n >= 36 or (n >= 24 and joins >= 4)) and long_flagged < 2:
            long_flagged += 1
            issues.append({
                "original": " ".join(words[:12]) + "…",
                "suggestion": "Split this into two or three shorter sentences, one idea each.",
                "note": "Very long sentence that chains many ideas together." if n < 36 else "Very long sentence: it is easy to lose the listener.",
                "kind": "run-on"})

    if no_breaks:
        issues.append({
            "original": " ".join(_words(text)[:12]) + "…",
            "suggestion": "Break the answer into separate sentences, each carrying one point.",
            "note": "The whole answer is a single sentence.",
            "kind": "run-on"})
    return issues


def analyze(text: str) -> dict:
    """Return {'score': 1-10, 'issues': [...]} for an answer."""
    text = (text or "").strip()
    words = _words(text)
    n = len(words)

    spans = sorted(_regex_issues(text) + _function_issues(text), key=lambda h: h[0])
    issues, last_end = [], -1
    for start, end, fixed, note, kind in spans:
        if start < last_end:
            continue                                   # overlaps an issue we already reported
        last_end = end
        before, after = _snippet(text, start, end, fixed)
        issues.append({"original": before, "suggestion": after, "note": note, "kind": kind})
    issues += _sentence_issues(text)

    penalty = sum(0.5 if i["kind"] == "repetition" else 1.0 for i in issues)
    sentences = _sentences(text)
    avg = n / max(1, len(sentences))
    base = 10 if n >= 40 and 7 <= avg <= 26 else 9
    score = base - min(7.0, penalty)
    if n < 12:
        score = min(score, 5)        # too little to judge a full sentence structure
    if n < 6:
        score = min(score, 3)
    return {"score": max(1, min(10, round(score))), "issues": issues[:8]}


def delivery(text: str) -> dict:
    """Plain facts about how the answer would sound (these do not change the grammar score)."""
    text = (text or "").strip()
    words = _words(text)
    low = " " + re.sub(r"[^a-z' ]", " ", text.lower()) + " "
    fillers = {}
    for f in FILLERS:
        count = len(re.findall(rf"(?<![a-z']){re.escape(f)}(?![a-z'])", low))
        if count:
            fillers[f] = count
    sentences = _sentences(text)
    seconds = round(len(words) / WPM * 60)
    if seconds < 20:
        pace = "Short. Aim for roughly 45 to 90 seconds spoken."
    elif seconds > 150:
        pace = "Long. Try to stay under about two minutes."
    else:
        pace = "Good length for a spoken answer."
    return {"words": len(words), "sentences": len(sentences),
            "avg_sentence_words": round(len(words) / max(1, len(sentences)), 1),
            "fillers": fillers, "filler_total": sum(fillers.values()),
            "speaking_seconds": seconds, "pace": pace}