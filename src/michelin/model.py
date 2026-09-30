"""Replaceable extraction boundary. Replay is assistant-prepared output, NOT live inference.

Providers accept ExtractionRequest and return raw Menu JSON. All output is validated here
before business logic can consume it. Register a future live adapter in PROVIDERS with the
same interface; MICHELIN_EXTRACTION_PROVIDER selects it, without changing HTTP/UI contracts.
Replay performs exact (menu_id, input SHA-256) matching; it never recognizes arbitrary images.
"""

import base64
import hashlib
import json
import os
from pathlib import Path
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from michelin.schemas import Menu

PREPARED_DIR = Path(__file__).resolve().parents[2] / "data/prepared"


class ExtractionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    menu_id: str = Field(min_length=1, max_length=100)
    text: str | None = Field(default=None, max_length=100000)
    image_base64: str | None = Field(default=None, max_length=12000000)

    @model_validator(mode="after")
    def one_input(self):
        if (self.text is None) == (self.image_base64 is None):
            raise ValueError("Supply exactly one of text or image_base64")
        if self.text is not None and not self.text.strip():
            raise ValueError("Text must not be empty")
        if self.image_base64 is not None:
            try:
                image = base64.b64decode(self.image_base64, validate=True)
            except ValueError as exc:
                raise ValueError("Invalid base64 image") from exc
            if not image:
                raise ValueError("Image must not be empty")
        return self

    def input_hash(self):
        raw = (
            self.text.encode("utf-8")
            if self.text is not None
            else base64.b64decode(self.image_base64)
        )
        return hashlib.sha256(raw).hexdigest()


class ExtractionResponse(BaseModel):
    menu: Menu
    provider: str
    mode: Literal["prepared_replay", "live"]
    input_sha256: str
    source_url: str | None = None
    retrieved_at: str | None = None
    notice: str


class UnpreparedInput(ValueError):
    pass


class ExtractionProvider(Protocol):
    name: str
    mode: Literal["prepared_replay", "live"]

    def extract(self, request: ExtractionRequest) -> dict: ...


def prepared_catalog():
    return [json.loads(path.read_text()) for path in sorted(PREPARED_DIR.glob("*.json"))]


class ReplayProvider:
    name = "assistant-prepared"
    mode = "prepared_replay"

    def extract(self, request: ExtractionRequest) -> dict:
        for record in prepared_catalog():
            if (
                record["menu_id"] == request.menu_id
                and record["input_kind"] == ("text" if request.text is not None else "image")
                and record["input_sha256"] == request.input_hash()
            ):
                return record
        raise UnpreparedInput(
            "No prepared response matches this menu ID and exact input. "
            "Prepare a new response or select a known prepared input; no model was called."
        )


PROVIDERS = {"replay": ReplayProvider}


def get_extraction_provider() -> ExtractionProvider:
    name = os.environ.get("MICHELIN_EXTRACTION_PROVIDER", "replay")
    if name not in PROVIDERS:
        raise ValueError(
            f"Extraction provider {name!r} is not installed; no fallback or external call made."
        )
    return PROVIDERS[name]()


def extract(request: ExtractionRequest, provider: ExtractionProvider) -> ExtractionResponse:
    record = provider.extract(request)
    menu = Menu.model_validate(record["menu"])
    if menu.restaurant_id != request.menu_id:
        raise ValueError("Provider returned a different restaurant identity")
    if (
        not menu.dishes
        or len(menu.dishes) > 40
        or len({d.id for d in menu.dishes}) != len(menu.dishes)
    ):
        raise ValueError("Provider returned too many dishes or duplicate IDs")
    # Extraction is not human review. Even curated replay needs explicit UI review.
    menu.verified = False
    menu.preparation_mode = provider.mode
    return ExtractionResponse(
        menu=menu,
        provider=provider.name,
        mode=provider.mode,
        input_sha256=request.input_hash(),
        source_url=record.get("source_url"),
        retrieved_at=record.get("retrieved_at"),
        notice=(
            "Assistant-prepared response replay; no live model or OCR was run. "
            if provider.mode == "prepared_replay"
            else "Provider extraction requires review. "
        )
        + "Partial ingredient evidence; confirm unknown ingredients, cross-contact and fees.",
    )
