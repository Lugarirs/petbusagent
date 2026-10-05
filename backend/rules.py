"""Pet travel rules. Plain Python so it's testable; Google ADK agent wraps these later."""
from datetime import date, timedelta
from typing import Optional

ALLOWED_PETS = {"dog", "cat", "rabbit", "bird"}
MAX_PET_WEIGHT_KG = 15.0       # carrier-friendly limit for MVP
RABIES_VALID_DAYS = 365
HEALTH_CERT_VALID_DAYS = 10    # health certificate must be recent


def check_pet_documents(
    pet_type: Optional[str],
    weight_kg: Optional[float],
    rabies_date: Optional[date],
    health_cert_date: Optional[date],
    travel_date: date,
) -> tuple[bool, str]:
    if not pet_type or pet_type.lower() not in ALLOWED_PETS:
        return False, f"Pet type must be one of: {', '.join(sorted(ALLOWED_PETS))}."
    if weight_kg is None or weight_kg <= 0 or weight_kg > MAX_PET_WEIGHT_KG:
        return False, f"Pet weight must be between 0 and {MAX_PET_WEIGHT_KG} kg (in a carrier)."
    if not rabies_date:
        return False, "Rabies vaccination date is required."
    if rabies_date > travel_date:
        return False, "Vaccination date cannot be in the future."
    if travel_date - rabies_date > timedelta(days=RABIES_VALID_DAYS):
        return False, "Rabies vaccination is older than 1 year."
    if not health_cert_date:
        return False, "Vet health certificate date is required."
    if health_cert_date > travel_date or travel_date - health_cert_date > timedelta(days=HEALTH_CERT_VALID_DAYS):
        return False, f"Health certificate must be within {HEALTH_CERT_VALID_DAYS} days of travel."
    return True, "All documents valid."


def pet_price(base: float, premium_pct: int) -> float:
    return round(base * (1 + premium_pct / 100), 2)


# Refund policy (hours before departure -> % refunded). Waitlisted bookings always get 100%.
REFUND_TIERS = [(24, 100), (6, 50), (0, 0)]


def refund_pct(hours_before: float) -> int:
    for min_hours, pct in REFUND_TIERS:
        if hours_before >= min_hours:
            return pct
    return 0
