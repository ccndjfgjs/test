from types import SimpleNamespace

from src.services.review_analysis import analyze_review, issue_summary


def test_review_extracts_negative_technical_issue():
    result = analyze_review("The fan is noisy under load and the display has a dead pixel.")
    assert result["sentiment"] == "negative"
    assert set(result["issue_tags"]) == {"cooling_noise", "display"}


def test_review_negation_is_not_reported_as_a_defect():
    result = analyze_review("No overheating at all, and the laptop is quiet.")
    assert {issue["tag"] for issue in result["issues"]} == {"overheating"}
    assert result["issues"][0]["sentiment"] == "positive"


def test_russian_text_is_supported():
    result = analyze_review("Кулер очень шумный, а корпус сильно греется.")
    assert result["sentiment"] == "negative"
    assert "cooling_noise" in result["issue_tags"]
    assert "overheating" in result["issue_tags"]


def test_negation_does_not_bleed_across_clauses():
    result = analyze_review("No overheating, but the fan is noisy.")
    sentiments = result["issue_sentiments"]
    assert sentiments["overheating"] == "positive"
    assert sentiments["cooling_noise"] == "negative"


def test_issue_summary_uses_sentiment_per_issue():
    mixed = SimpleNamespace(
        issue_tags=["overheating", "cooling_noise"],
        issue_sentiments={"overheating": "positive", "cooling_noise": "negative"},
        sentiment="negative",
        content="No overheating, but the fan is noisy.",
    )
    summary = {entry["tag"]: entry for entry in issue_summary([mixed])}
    assert summary["overheating"]["negative"] == 0
    assert summary["cooling_noise"]["negative"] == 1
