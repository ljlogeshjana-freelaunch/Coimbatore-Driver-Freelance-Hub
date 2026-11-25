from datetime import datetime, timezone
from decimal import Decimal, ROUND_CEILING, ROUND_HALF_UP

CENT = Decimal("0.01")

def billable_minutes(started_at: datetime, ended_at: datetime, paused_seconds: int = 0) -> int:
    """Count active elapsed time, excluding completed and currently-open pauses."""
    elapsed = max(0, int((ended_at - started_at).total_seconds()) - max(0, paused_seconds))
    return (elapsed + 59) // 60

def calculate_bill(package_price: Decimal, duration_minutes: int, minutes: int,
                   surcharge: Decimal = Decimal("50.00")) -> dict:
    if duration_minutes <= 0 or minutes < 0 or package_price < 0 or surcharge < 0:
        raise ValueError("Invalid package or time values")
    rate = package_price / Decimal(duration_minutes)
    charge = (rate * Decimal(minutes)).quantize(CENT, rounding=ROUND_HALF_UP)
    total = (charge + surcharge).quantize(CENT, rounding=ROUND_HALF_UP)
    return {"rate_per_minute": rate, "billable_minutes": minutes,
            "package_charge": charge, "surcharge": surcharge, "total": total}
