from datetime import datetime

from backend.app.services.fraud_rules import TxnFeatures, score_transaction

DAYTIME = datetime(2026, 10, 1, 14, 30)
NIGHT = datetime(2026, 10, 1, 2, 10)


def features(**kw):
    base = dict(amount=1200, country="IN", timestamp=DAYTIME, category="GROCERIES", channel="UPI",
                avg_debit_amount=1500, known_categories={"GROCERIES", "FOOD"})
    return TxnFeatures(**{**base, **kw})


def test_normal_purchase_is_low_risk():
    r = score_transaction(features())
    assert (r.score, r.level, r.reasons) == (0, "LOW", [])


def test_foreign_night_large_purchase_is_high_risk():
    r = score_transaction(features(amount=48_500, country="AE", timestamp=NIGHT, category="SHOPPING"))
    assert r.level == "HIGH"
    assert r.score >= 60
    assert any("International" in x for x in r.reasons)
    assert any("unusual hour" in x for x in r.reasons)


def test_travel_notice_removes_foreign_penalty():
    without = score_transaction(features(country="AE"))
    with_notice = score_transaction(features(country="AE", travel_notice=True))
    assert without.score - with_notice.score == 25


def test_velocity_rule_detects_card_testing():
    r = score_transaction(features(txns_last_10_min=3))
    assert any("last 10 minutes" in x for x in r.reasons)
    assert r.score == 20


def test_high_risk_category_and_amount_ratio():
    r = score_transaction(features(amount=9_999, category="GIFT_CARDS"))  # ~6.7x average
    assert r.score == 40 and r.level == "MEDIUM"


def test_score_is_capped_at_100():
    r = score_transaction(features(amount=100_000, country="AE", timestamp=NIGHT, category="CRYPTO",
                                   txns_last_10_min=5))
    assert r.score == 100 and r.level == "HIGH"


def test_same_input_always_same_score():
    f = features(amount=20_000, country="US")
    assert score_transaction(f) == score_transaction(f)
