from datetime import datetime, timezone, timedelta
from decimal import Decimal
import pytest
from app.billing import billable_minutes, calculate_bill

def test_pricing_examples_and_surcharge():
    assert calculate_bill(Decimal("300"),120,120)["total"] == Decimal("350.00")
    assert calculate_bill(Decimal("300"),120,1)["total"] == Decimal("52.50")

def test_partial_minute_rounds_up_and_pause_excluded():
    start=datetime(2026,1,1,tzinfo=timezone.utc)
    assert billable_minutes(start,start+timedelta(seconds=61)) == 2
    assert billable_minutes(start,start+timedelta(seconds=600),300) == 5

def test_long_shift_keeps_selected_package_rate():
    result=calculate_bill(Decimal("500"),240,300)
    assert result["package_charge"] == Decimal("625.00")
    assert result["total"] == Decimal("675.00")

def test_bad_package_duration_rejected():
    with pytest.raises(ValueError): calculate_bill(Decimal("300"),0,1)
