import os
from datetime import date
import requests
import streamlit as st

API = os.getenv("API_URL", "http://localhost:8000")
st.set_page_config(page_title="PetBus", page_icon="🐾", layout="centered")
st.title("🐾 PetBus")
st.caption("Travel with your pet. Book a pet-friendly seat.")

tab_book, tab_manage, tab_ai, tab_admin = st.tabs(["Book", "Manage", "Pet assistant", "Operator"])

with tab_book:
    trips = requests.get(f"{API}/trips", timeout=10).json()
    trip = st.selectbox("Trip", trips,
                        format_func=lambda t: f"{t['route']} · {t['departure'][:16]} · ₹{t['price']:.0f}")
    st.info(f"Seats left: {trip['seats_left']} · Pet seats left: {trip['pet_seats_left']} "
            f"· Pet fare ₹{trip['pet_price']:.0f}")
    if trip["pet_seats_left"] <= 0:
        st.warning(f"Pet compartment is full. You can join the waitlist ({trip['pet_waitlist']} waiting).")

    with st.expander("Rest stops on this trip"):
        for s in requests.get(f"{API}/trips/{trip['id']}/rest-stops", timeout=10).json():
            st.markdown(f"**{s['name']}** · {s['arrival']} to {s['departs']} ({s['duration_min']} min)  \n"
                        f"{'🐕 Pet walk area · ' if s['pet_walk_area'] else ''}"
                        f"{'💧 Water · ' if s['has_water'] else ''}{s['note'] or ''}")

    name = st.text_input("Your name")
    phone = st.text_input("Phone")
    has_pet = st.toggle("Travelling with a pet")

    pet = {}
    if has_pet:
        c1, c2 = st.columns(2)
        pet["pet_name"] = c1.text_input("Pet name")
        pet["pet_type"] = c2.selectbox("Type", ["dog", "cat", "rabbit", "bird"])
        pet["pet_weight_kg"] = st.number_input("Weight (kg)", 0.5, 50.0, 5.0)
        pet["rabies_vaccination_date"] = str(st.date_input("Rabies vaccination date", date.today()))
        pet["health_cert_date"] = str(st.date_input("Vet health certificate date", date.today()))
        if st.button("Check documents"):
            r = requests.post(f"{API}/pets/check-documents", json={
                "pet_type": pet["pet_type"], "weight_kg": pet["pet_weight_kg"],
                "rabies_vaccination_date": pet["rabies_vaccination_date"],
                "health_cert_date": pet["health_cert_date"],
                "travel_date": trip["departure"][:10]}).json()
            (st.success if r["valid"] else st.error)(r["message"])

    st.subheader("Drop point")
    c1, c2 = st.columns(2)
    lat = c1.number_input("Your home latitude", value=12.9716, format="%.4f")
    lng = c2.number_input("Your home longitude", value=77.5946, format="%.4f")
    pts = requests.get(f"{API}/trips/{trip['id']}/drop-points",
                       params={"lat": lat, "lng": lng}, timeout=10).json()
    drop = st.radio("Nearest stops", pts, format_func=lambda p:
                    f"{p['name']} · {p['distance_km']} km from home" +
                    (" ✅ close" if p["can_drop_near"] else ""))

    if st.button("Confirm booking", type="primary"):
        payload = {"trip_id": trip["id"], "passenger_name": name, "phone": phone,
                   "has_pet": has_pet, "drop_point_id": drop["id"], **pet}
        r = requests.post(f"{API}/bookings", json=payload, timeout=10)
        if r.ok:
            d = r.json()
            if d["status"] == "waitlisted":
                st.warning(f"You're #{d['waitlist_position']} on the pet waitlist. Ref #{d['id']}. "
                           "You'll be confirmed automatically if a pet seat frees up, or get a full refund.")
            else:
                st.success(f"Booked! Fare ₹{d['amount']:.0f}. Ref #{d['id']}")
                st.balloons()
        else:
            st.error(r.json().get("detail", "Booking failed"))

with tab_manage:
    st.markdown("**Refund policy:** 24h+ before departure 100% · 6 to 24h 50% · under 6h none · "
                "waitlisted bookings always 100%.")
    ref = st.number_input("Booking reference #", min_value=1, step=1)
    c1, c2 = st.columns(2)
    if c1.button("Look up"):
        r = requests.get(f"{API}/bookings/{int(ref)}", timeout=10)
        st.json(r.json()) if r.ok else st.error(r.json()["detail"])
    if c2.button("Cancel booking"):
        r = requests.post(f"{API}/bookings/{int(ref)}/cancel", timeout=10)
        if r.ok:
            d = r.json()
            st.success(f"Cancelled. Refund {d['refund_pct']}% = ₹{d['refund_amount']:.0f}")
            if d["promoted_booking_id"]:
                st.info(f"Waitlisted booking #{d['promoted_booking_id']} was moved to confirmed.")
        else:
            st.error(r.json()["detail"])

with tab_ai:
    st.caption("Powered by Google ADK + Gemini. Needs GOOGLE_API_KEY on the API server.")
    st.subheader("Verify a certificate")
    up = st.file_uploader("Vaccination or health certificate (photo)", type=["jpg", "jpeg", "png"])
    tdate = st.date_input("Travel date", date.today(), key="ai_date")
    if up and st.button("Verify with AI"):
        with st.spinner("Reading certificate..."):
            r = requests.post(f"{API}/agent/verify-certificate",
                              files={"file": (up.name, up.getvalue(), up.type)},
                              data={"travel_date": str(tdate)}, timeout=90)
        st.write(r.json().get("answer") if r.ok else r.json().get("detail"))
    st.subheader("Ask a question")
    q = st.text_input("e.g. How do I keep my dog calm on a night bus?")
    if q and st.button("Ask"):
        with st.spinner("Thinking..."):
            r = requests.post(f"{API}/agent/ask", json={"question": q}, timeout=60)
        st.write(r.json().get("answer") if r.ok else r.json().get("detail"))

with tab_admin:
    st.button("Refresh")
    rows = requests.get(f"{API}/bookings", timeout=10).json()
    live = [r for r in rows if r["status"] == "confirmed"]
    st.metric("Confirmed bookings", len(live))
    st.metric("Pet bookings", sum(1 for r in live if r["has_pet"]))
    st.metric("Pet waitlist", sum(1 for r in rows if r["status"] == "waitlisted"))
    st.metric("Revenue", f"₹{sum(r['amount'] for r in live):,.0f}")
    st.metric("Refunded", f"₹{sum(r['refund_amount'] for r in rows):,.0f}")
    st.dataframe(rows, use_container_width=True)
