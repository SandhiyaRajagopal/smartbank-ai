import pytest

from backend.app.services.loan_rules import assess_loan, calculate_emi, principal_for_emi


def test_emi_matches_standard_formula():
    # ₹1,00,000 at 12% p.a. for 12 months -> ₹8,884.88 (textbook value)
    assert calculate_emi(100_000, 12, 12) == pytest.approx(8884.88, abs=0.01)


def test_zero_interest_emi():
    assert calculate_emi(120_000, 0, 12) == 10_000


def test_invalid_tenure_rejected():
    with pytest.raises(ValueError):
        calculate_emi(100_000, 10, 0)


def test_principal_for_emi_is_inverse_of_emi():
    emi = calculate_emi(500_000, 11, 36)
    assert principal_for_emi(emi, 11, 36) == pytest.approx(500_000, rel=1e-6)


def test_good_profile_is_approved_at_best_rate():
    d = assess_loan("PERSONAL", 500_000, 36, monthly_income=125_000, existing_emis=0, credit_score=792)
    assert d.decision == "APPROVED"
    assert d.interest_rate == 11.0
    assert d.foir_after_loan < 0.5


def test_high_foir_is_conditional_with_lower_max_amount():
    d = assess_loan("PERSONAL", 300_000, 36, monthly_income=60_000, existing_emis=26_560, credit_score=702)
    assert d.decision == "CONDITIONAL"
    assert 50_000 <= d.max_eligible_amount < 300_000
    assert d.foir_after_loan > 0.5


def test_no_room_for_new_emi_is_declined():
    d = assess_loan("PERSONAL", 200_000, 36, monthly_income=50_000, existing_emis=25_000, credit_score=760)
    assert d.decision == "DECLINED"


@pytest.mark.parametrize("kwargs, reason", [
    (dict(kyc_status="PENDING", credit_score=800), "KYC"),
    (dict(credit_score=None), "No credit history"),
    (dict(credit_score=640), "below the minimum"),
    (dict(credit_score=780, missed_payments_12m=2), "missed payments"),
])
def test_hard_stops(kwargs, reason):
    d = assess_loan("PERSONAL", 100_000, 24, monthly_income=80_000, existing_emis=0, **kwargs)
    assert d.decision == "DECLINED"
    assert any(reason in r for r in d.reasons)


def test_tenure_is_capped_per_product():
    d = assess_loan("PERSONAL", 100_000, 120, monthly_income=80_000, existing_emis=0, credit_score=790)
    assert d.tenure_months == 60


def test_lower_score_gets_higher_rate():
    good = assess_loan("CAR", 500_000, 60, 150_000, 0, credit_score=790)
    fair = assess_loan("CAR", 500_000, 60, 150_000, 0, credit_score=700)
    assert fair.interest_rate > good.interest_rate


def test_unknown_loan_type():
    with pytest.raises(ValueError):
        assess_loan("BOAT", 1, 1, 1, 0, 800)
