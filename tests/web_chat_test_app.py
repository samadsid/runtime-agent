from typing import Annotated
from uuid import UUID, uuid4

from fastapi import FastAPI, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field


class RequestBody(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    conversation_id: UUID | None = None


app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:4173"],
    allow_credentials=False,
    allow_methods=["POST", "OPTIONS"],
    allow_headers=["Content-Type", "X-Request-Id", "X-Dev-Customer-Id"],
)


@app.get("/health")
async def health() -> dict[str, bool]:
    return {"ok": True}


@app.post("/chat")
async def chat(
    body: RequestBody,
    request_id: Annotated[UUID, Header(alias="X-Request-Id")],
) -> dict[str, str]:
    del request_id
    conversation_id = body.conversation_id or uuid4()
    reply = (
        "Available products:\n\n1. Chicken Breast - ₹320.00/kg"
        if body.conversation_id is None
        else "Continued the same conversation."
    )
    return {"conversation_id": str(conversation_id), "reply": reply}
