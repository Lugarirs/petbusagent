"""Google ADK agent for pet travel.
Needs: pip install google-adk, and env GOOGLE_API_KEY (from Google AI Studio).
Imports are lazy so the rest of the API still runs without it.
"""
import os
import uuid
from datetime import date

from .rules import check_pet_documents

APP_NAME = "petbus"
MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

INSTRUCTION = """You are the PetBus assistant for pet-friendly bus travel in India.

When the user uploads a pet vaccination or health certificate image:
1. Read it and extract: pet type (if shown), weight (if shown), rabies vaccination date, and vet health certificate date.
2. Call verify_pet_documents with those values (dates as YYYY-MM-DD) and the travel date given by the user.
   If a value is not visible on the document, pass an empty string for it. Never guess dates.
3. Reply in 2-3 short sentences: what you read, whether it passes, and what to fix if not.

For general questions, answer briefly about travelling with pets by bus: carriers, vaccination, feeding before travel,
keeping pets calm. Rules differ by state and operator, so say so and never invent legal requirements.
If a question is unrelated to pet travel or PetBus, politely decline."""


def verify_pet_documents(
    pet_type: str,
    weight_kg: float,
    rabies_vaccination_date: str,
    health_cert_date: str,
    travel_date: str,
) -> dict:
    """Check a pet's travel documents against PetBus rules.

    Args:
        pet_type: dog, cat, rabbit or bird.
        weight_kg: pet weight in kilograms (use 0 if unknown).
        rabies_vaccination_date: date in YYYY-MM-DD, or empty string if not visible.
        health_cert_date: date in YYYY-MM-DD, or empty string if not visible.
        travel_date: date of travel in YYYY-MM-DD.

    Returns:
        A dict with 'valid' (bool) and 'message' (str).
    """
    def parse(s):
        try:
            return date.fromisoformat(s) if s else None
        except ValueError:
            return None

    ok, msg = check_pet_documents(
        pet_type, weight_kg, parse(rabies_vaccination_date),
        parse(health_cert_date), parse(travel_date) or date.today(),
    )
    return {"valid": ok, "message": msg}


_runner = None
_sessions = None


def _get_runner():
    global _runner, _sessions
    if _runner is None:
        from google.adk.agents import Agent
        from google.adk.runners import Runner
        from google.adk.sessions import InMemorySessionService

        agent = Agent(
            name="petbus_assistant",
            model=MODEL,
            description="Verifies pet documents and answers pet travel questions.",
            instruction=INSTRUCTION,
            tools=[verify_pet_documents],
        )
        _sessions = InMemorySessionService()
        _runner = Runner(agent=agent, app_name=APP_NAME, session_service=_sessions)
    return _runner, _sessions


async def run_agent(text: str, image_bytes: bytes | None = None, mime: str | None = None) -> str:
    from google.genai import types

    runner, sessions = _get_runner()
    session_id = uuid.uuid4().hex
    await sessions.create_session(app_name=APP_NAME, user_id="web", session_id=session_id)

    parts = [types.Part(text=text)]
    if image_bytes:
        parts.append(types.Part.from_bytes(data=image_bytes, mime_type=mime or "image/jpeg"))
    msg = types.Content(role="user", parts=parts)

    final = ""
    async for event in runner.run_async(user_id="web", session_id=session_id, new_message=msg):
        if event.is_final_response() and event.content and event.content.parts:
            final = "".join(p.text or "" for p in event.content.parts)
    return final or "Sorry, I could not produce an answer."
