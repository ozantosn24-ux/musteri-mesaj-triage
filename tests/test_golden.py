"""Uçtan uca golden test: pipeline.process_all(data/mesajlar.json) vs tests/golden.json.

worker A'nın triage/classify.py'sine bağımlıdır; henüz yoksa test ATLANIR
(kırmızı sayılmaz) — bu yüzden import en üstte, koşullu değil.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("triage.classify")

from triage.knowledge import KnowledgeBase  # noqa: E402
from triage.models import Message  # noqa: E402
from triage.pipeline import process_all  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def _load_golden() -> list[dict]:
    return json.loads((ROOT / "tests" / "golden.json").read_text(encoding="utf-8"))


def _load_messages() -> list[Message]:
    ham = json.loads((ROOT / "data" / "mesajlar.json").read_text(encoding="utf-8"))
    return [Message.from_dict(d) for d in ham]


def test_golden_matches():
    kb = KnowledgeBase.load(ROOT / "data")
    messages = _load_messages()
    results = process_all(messages, kb)
    golden_by_id = {g["id"]: g for g in _load_golden()}

    hatalar: list[str] = []
    for r in results:
        g = golden_by_id[r.id]
        if r.dil != g["dil"]:
            hatalar.append(f"id={r.id} dil: {r.dil!r} != {g['dil']!r}")
        if set(r.intents) != set(g["intents"]):
            hatalar.append(f"id={r.id} intents: {r.intents!r} != {g['intents']!r}")
        if r.oncelik != g["oncelik"]:
            hatalar.append(f"id={r.id} oncelik: {r.oncelik!r} != {g['oncelik']!r}")
        if r.aksiyon != g["aksiyon"]:
            hatalar.append(f"id={r.id} aksiyon: {r.aksiyon!r} != {g['aksiyon']!r}")
        if r.ekip != g["ekip"]:
            hatalar.append(f"id={r.id} ekip: {r.ekip!r} != {g['ekip']!r}")

    assert not hatalar, "\n".join(hatalar)
