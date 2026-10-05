from datetime import datetime, timedelta, date
from typing import Optional
from fastapi import FastAPI, HTTPException, Depends, UploadFile, File, Form
from pydantic import BaseModel
from sqlmodel import SQLModel, Session, create_engine, select, func

from .models import Trip, DropPoint, RestStop, Booking
from .rules import check_pet_documents, pet_price, refund_pct

engine = create_engine("sqlite:///petbus.db", connect_args={"check_same_thread": False})
app = FastAPI(title="PetBus API", version="0.2.0")


def get_session():
    with Session(engine) as s:
        yield s


@app.on_event("startup")
def startup():
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        if s.exec(select(Trip)).first():
            return
        base = datetime.now().replace(hour=22, minute=0, second=0, microsecond=0) + timedelta(days=2)
        t = Trip(route="Chennai-Bangalore", origin="Chennai", destination="Bangalore",
                 departure=base, price=900)
        s.add(t); s.commit(); s.refresh(t)
        for name, lat, lng, off in [
            ("Koyambedu", 13.0694, 80.1948, 0),
            ("Poonamallee", 13.0473, 80.0945, 40),
            ("Krishnagiri", 12.5266, 78.2140, 240),
            ("Hosur", 12.7409, 77.8253, 300),
            ("Silk Board, Bangalore", 12.9177, 77.6238, 360),
            ("Majestic, Bangalore", 12.9767, 77.5713, 400),
        ]:
            s.add(DropPoint(trip_id=t.id, name=name, lat=lat, lng=lng, eta_offset_min=off))
        for name, off, dur, note in [
            ("Vellore highway stop", 120, 20, "Grass area for pets, water bowls available"),
            ("Krishnagiri food plaza", 240, 25, "Dinner break, shaded pet walking area"),
        ]:
            s.add(RestStop(trip_id=t.id, name=name, eta_offset_min=off, duration_min=dur, note=note))
        s.commit()


@app.get("/health")
def health():
    return {"ok": True}


# ---------- trips ----------
@app.get("/trips")
def list_trips(session: Session = Depends(get_session)):
    return [_trip_view(session, t) for t in session.exec(select(Trip)).all()]


def _count(session, trip_id, status="confirmed", pet_only=False):
    q = select(func.count()).select_from(Booking).where(Booking.trip_id == trip_id, Booking.status == status)
    if pet_only:
        q = q.where(Booking.has_pet == True)
    return session.exec(q).one()


def _trip_view(session: Session, t: Trip):
    pets = _count(session, t.id, pet_only=True)
    return {**t.model_dump(),
            "pet_seats_left": t.pet_seats - pets,
            "seats_left": t.total_seats - _count(session, t.id),
            "pet_waitlist": _count(session, t.id, "waitlisted", pet_only=True),
            "pet_price": pet_price(t.price, t.pet_premium_pct)}


@app.get("/trips/{trip_id}/drop-points")
def drop_points(trip_id: int, lat: Optional[float] = None, lng: Optional[float] = None,
                session: Session = Depends(get_session)):
    pts = session.exec(select(DropPoint).where(DropPoint.trip_id == trip_id)).all()
    res = []
    for p in pts:
        d = round(_km(lat, lng, p.lat, p.lng), 1) if lat is not None and lng is not None else None
        res.append({**p.model_dump(), "distance_km": d})
    if lat is not None and lng is not None:
        res.sort(key=lambda x: x["distance_km"])
        for r in res:
            r["can_drop_near"] = r["distance_km"] <= 5
    return res


@app.get("/trips/{trip_id}/rest-stops")
def rest_stops(trip_id: int, session: Session = Depends(get_session)):
    trip = session.get(Trip, trip_id)
    if not trip:
        raise HTTPException(404, "Trip not found")
    stops = session.exec(select(RestStop).where(RestStop.trip_id == trip_id)
                         .order_by(RestStop.eta_offset_min)).all()
    return [{**s.model_dump(),
             "arrival": (trip.departure + timedelta(minutes=s.eta_offset_min)).strftime("%d %b %H:%M"),
             "departs": (trip.departure + timedelta(minutes=s.eta_offset_min + s.duration_min)).strftime("%H:%M")}
            for s in stops]


def _km(lat1, lng1, lat2, lng2):
    from math import radians, sin, cos, asin, sqrt
    a = sin(radians(lat2 - lat1) / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(radians(lng2 - lng1) / 2) ** 2
    return 6371 * 2 * asin(sqrt(a))


# ---------- documents ----------
class DocCheckIn(BaseModel):
    pet_type: str
    weight_kg: float
    rabies_vaccination_date: Optional[date] = None
    health_cert_date: Optional[date] = None
    travel_date: date


@app.post("/pets/check-documents")
def check_docs(body: DocCheckIn):
    ok, msg = check_pet_documents(body.pet_type, body.weight_kg, body.rabies_vaccination_date,
                                  body.health_cert_date, body.travel_date)
    return {"valid": ok, "message": msg}


# ---------- bookings ----------
class BookingIn(BaseModel):
    trip_id: int
    passenger_name: str
    phone: str
    has_pet: bool = False
    pet_name: Optional[str] = None
    pet_type: Optional[str] = None
    pet_weight_kg: Optional[float] = None
    rabies_vaccination_date: Optional[date] = None
    health_cert_date: Optional[date] = None
    drop_point_id: Optional[int] = None


def _waitlist_position(session, b: Booking) -> Optional[int]:
    if b.status != "waitlisted":
        return None
    return session.exec(select(func.count()).select_from(Booking).where(
        Booking.trip_id == b.trip_id, Booking.status == "waitlisted",
        Booking.has_pet == True, Booking.created_at <= b.created_at)).one()


def _booking_view(session, b: Booking):
    return {**b.model_dump(), "waitlist_position": _waitlist_position(session, b)}


@app.post("/bookings")
def create_booking(b: BookingIn, session: Session = Depends(get_session)):
    trip = session.get(Trip, b.trip_id)
    if not trip:
        raise HTTPException(404, "Trip not found")
    if trip.departure <= datetime.now():
        raise HTTPException(409, "Trip already departed")
    view = _trip_view(session, trip)
    if view["seats_left"] <= 0:
        raise HTTPException(409, "Bus is full")

    amount, doc_status, note, status = trip.price, "not_required", None, "confirmed"
    if b.has_pet:
        ok, note = check_pet_documents(b.pet_type, b.pet_weight_kg, b.rabies_vaccination_date,
                                       b.health_cert_date, trip.departure.date())
        if not ok:
            raise HTTPException(422, f"Pet documents rejected: {note}")
        doc_status, amount = "verified", view["pet_price"]
        if view["pet_seats_left"] <= 0:  # compartment full -> waitlist, first come first served
            status = "waitlisted"

    booking = Booking(**b.model_dump(), amount=amount, doc_status=doc_status, doc_note=note, status=status)
    session.add(booking); session.commit(); session.refresh(booking)
    return _booking_view(session, booking)


@app.get("/bookings")
def all_bookings(session: Session = Depends(get_session)):
    rows = session.exec(select(Booking).order_by(Booking.created_at.desc())).all()
    return [_booking_view(session, r) for r in rows]


@app.get("/bookings/{booking_id}")
def get_booking(booking_id: int, session: Session = Depends(get_session)):
    b = session.get(Booking, booking_id)
    if not b:
        raise HTTPException(404, "Booking not found")
    return _booking_view(session, b)


def _promote_waitlist(session: Session, trip: Trip) -> Optional[int]:
    view = _trip_view(session, trip)
    if view["pet_seats_left"] <= 0 or view["seats_left"] <= 0:
        return None
    nxt = session.exec(select(Booking).where(
        Booking.trip_id == trip.id, Booking.status == "waitlisted", Booking.has_pet == True)
        .order_by(Booking.created_at)).first()
    if not nxt:
        return None
    nxt.status = "confirmed"
    session.add(nxt); session.commit()
    return nxt.id


@app.post("/bookings/{booking_id}/cancel")
def cancel_booking(booking_id: int, session: Session = Depends(get_session)):
    b = session.get(Booking, booking_id)
    if not b:
        raise HTTPException(404, "Booking not found")
    if b.status == "cancelled":
        raise HTTPException(409, "Already cancelled")
    trip = session.get(Trip, b.trip_id)
    hours = (trip.departure - datetime.now()).total_seconds() / 3600
    if hours <= 0:
        raise HTTPException(409, "Trip already departed")

    pct = 100 if b.status == "waitlisted" else refund_pct(hours)
    freed_pet_seat = b.status == "confirmed" and b.has_pet
    b.refund_amount = round(b.amount * pct / 100, 2)
    b.status, b.cancelled_at = "cancelled", datetime.utcnow()
    session.add(b); session.commit()

    promoted = _promote_waitlist(session, trip) if freed_pet_seat else None
    return {"booking_id": b.id, "refund_pct": pct, "refund_amount": b.refund_amount,
            "promoted_booking_id": promoted}


# ---------- Google ADK agent ----------
class AskIn(BaseModel):
    question: str


@app.post("/agent/ask")
async def agent_ask(body: AskIn):
    try:
        from .agent import run_agent
        return {"answer": await run_agent(body.question)}
    except Exception as e:
        raise HTTPException(503, f"AI assistant unavailable: {e}")


@app.post("/agent/verify-certificate")
async def agent_verify(file: UploadFile = File(...), travel_date: str = Form(...)):
    try:
        from .agent import run_agent
        data = await file.read()
        text = f"Verify this pet certificate. Travel date: {travel_date}."
        return {"answer": await run_agent(text, data, file.content_type)}
    except Exception as e:
        raise HTTPException(503, f"AI assistant unavailable: {e}")
