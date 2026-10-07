import re
from collections.abc import Iterable

# Lightweight, explainable keyword rules for the MVP. These labels are signals,
# not claims of verified defects; evidence always links back to the source text.
ISSUE_PATTERNS: dict[str, tuple[str, ...]] = {
    "cooling_noise": (
        r"\b(noisy|loud fan|fan noise|coil whine|whining fan|rattling fan)\b|fan.{0,20}(?:noisy|loud|rattl)",
        r"кулер.{0,24}шум\w*|шум\w*.{0,24}кулер|шум\w* вентилятор|свист\w* дроссел\w*|гул\w*",
    ),
    "overheating": (
        r"\b(overheat(?:ing)?|runs? too hot|gets? hot|thermal throttling)\b",
        r"перегрев\w*|сильно гре\w*|троттлинг\w*",
    ),
    "battery_life": (
        r"\b(battery drain(?:s)?|short battery life|battery life|doesn't last)\b|battery.{0,24}(?:drain\w*|dies|short|low)",
        r"батаре\w* быстро разряж\w*|автономност\w*|аккумулятор\w* разряж\w*",
    ),
    "display": (
        r"\b(dead pixel|screen flicker|display bleed|screen burn)\b",
        r"бит\w* пиксел\w*|мерц\w* экран\w*|засвет\w*|выгорани\w* экран\w*",
    ),
    "reliability": (
        r"\b(stopped working|failed after|defective|keeps crashing|broken|crack(?:ed|ing)?)\b",
        r"перестал\w* работать|сломал\w*|брак\w*|част\w* завис\w*|неисправ\w*",
    ),
    "performance": (
        r"\b(slow|laggy|poor performance|stutter(?:ing)?)\b",
        r"тормоз\w*|лага\w*|низк\w* производительност\w*|фриз\w*",
    ),
}

NEGATIVE_WORDS = re.compile(
    r"\b(bad|poor|problem|issue|broken|disappoint(?:ed|ing)?|fail(?:ed|ure)?|noisy|hot|slow|crack(?:ed|ing)?)\b|"
    r"плох\w*|проблем\w*|сломал\w*|брак\w*|неудоб\w*|разочар\w*|шумн\w*|гре\w*|тормоз\w*",
    re.IGNORECASE,
)
POSITIVE_WORDS = re.compile(
    r"\b(great|excellent|love|reliable|quiet|fast|recommend)\b|"
    r"отличн\w*|прекрасн\w*|нрав\w*|тих\w*|быстр\w*|рекоменд\w*",
    re.IGNORECASE,
)
NEGATION = re.compile(r"\b(no|not|without|never)\b|\bне\b|нет|без", re.IGNORECASE)


def _has_negation_near(text: str, match: re.Match[str]) -> bool:
    prefix = text[max(0, match.start() - 32) : match.start()]
    # Don't let a negation in the previous clause flip the issue that follows.
    prefix = re.split(r"[,;.!?]|\\b(?:but|however|но)\\b", prefix, flags=re.IGNORECASE)[-1]
    return bool(NEGATION.search(prefix))


def analyze_review(text: str) -> dict[str, object]:
    """Return compact, auditable sentiment and issue tags without hidden reasoning."""
    lower = text.casefold()
    issues: list[dict[str, str]] = []
    for tag, patterns in ISSUE_PATTERNS.items():
        found: re.Match[str] | None = None
        for pattern in patterns:
            found = re.search(pattern, lower, re.IGNORECASE)
            if found:
                break
        if found:
            issue_sentiment = "positive" if _has_negation_near(lower, found) else "negative"
            issues.append({"tag": tag, "sentiment": issue_sentiment, "evidence": found.group(0)[:100]})

    negative_count = len(NEGATIVE_WORDS.findall(lower))
    positive_count = len(POSITIVE_WORDS.findall(lower))
    if negative_count > positive_count:
        sentiment = "negative"
    elif positive_count > negative_count:
        sentiment = "positive"
    elif issues:
        sentiment = "negative" if any(issue["sentiment"] == "negative" for issue in issues) else "positive"
    else:
        sentiment = "neutral"

    return {
        "sentiment": sentiment,
        "issues": issues,
        "issue_tags": list(dict.fromkeys(issue["tag"] for issue in issues)),
        "issue_sentiments": {issue["tag"]: issue["sentiment"] for issue in issues},
    }


def issue_summary(reviews: Iterable[object]) -> list[dict[str, object]]:
    aggregate: dict[str, dict[str, object]] = {}
    for review in reviews:
        tags = getattr(review, "issue_tags", []) or []
        issue_sentiments = getattr(review, "issue_sentiments", {}) or {}
        for tag in tags:
            bucket = aggregate.setdefault(tag, {"tag": tag, "mentions": 0, "negative": 0, "examples": []})
            bucket["mentions"] = int(bucket["mentions"]) + 1
            issue_sentiment = issue_sentiments.get(tag, getattr(review, "sentiment", "neutral"))
            if issue_sentiment == "negative":
                bucket["negative"] = int(bucket["negative"]) + 1
            examples = bucket["examples"]
            if len(examples) < 2:
                examples.append(getattr(review, "content", "")[:180])
    return sorted(aggregate.values(), key=lambda entry: int(entry["mentions"]), reverse=True)
