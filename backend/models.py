from datetime import date, datetime
from typing import Optional
from pydantic import NaiveDatetime
from sqlmodel import SQLModel, Field


class Trip(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    route: str
    origin: str
    destination: str
    departure: NaiveDatetime
    price: float
    total_seats: int = 30
    pet_seats: int = 4
    pet_premium_pct: int = 40  # extra % charged for pet seat


class DropPoint(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    trip_id: int = Field(foreign_key="trip.id")
    name: str
    lat: float
    lng: float
    eta_offset_min: int  # minutes after departure


class RestStop(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    trip_id: int = Field(foreign_key="trip.id")
    name: str
    eta_offset_min: int       # minutes after departure
    duration_min: int = 15
    pet_walk_area: bool = True
    has_water: bool = True
    note: Optional[str] = None


class Booking(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    trip_id: int = Field(foreign_key="trip.id")
    passenger_name: str
    phone: str
    has_pet: bool = False
    pet_name: Optional[str] = None
    pet_type: Optional[str] = None
    pet_weight_kg: Optional[float] = None
    rabies_vaccination_date: Optional[date] = None
    health_cert_date: Optional[date] = None
    doc_status: str = "not_required"  # not_required | verified
    doc_note: Optional[str] = None
    drop_point_id: Optional[int] = None
    amount: float = 0
    status: str = "confirmed"  # confirmed | waitlisted | cancelled
    refund_amount: float = 0
    cancelled_at: Optional[NaiveDatetime] = None
    created_at: NaiveDatetime = Field(default_factory=datetime.utcnow)
