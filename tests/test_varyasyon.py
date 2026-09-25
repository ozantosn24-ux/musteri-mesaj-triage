"""Varyasyon seti üzerinde GÜVENLİK değişmezleri.

Sınıflandırma hata yapabilir; bu testler hatanın her zaman güvenli tarafta kaldığını bekçiler:
- P0 (sağlık) beklenen hiçbir mesaj P0'dan düşmez.
- Beklenmediği hâlde otomatik cevaplanan mesaj olmaz (şüphede insana gider).
"""
from __future__ import annotations

import json
from pathlib import Path

from triage.knowledge import KnowledgeBase
from triage.models import Message
from triage.pipeline import process_all

ROWS = json.loads((Path(__file__).resolve().parent / "varyasyonlar.json").read_text(encoding="utf-8"))


def _results():
    return process_all([Message.from_dict(r) for r in ROWS], KnowledgeBase.load())


def test_p0_hic_dusmez():
    for row, res in zip(ROWS, _results()):
        if row["beklenen"]["oncelik"] == "P0":
            assert res.oncelik == "P0", f"#{row['id']} P0 bekleniyordu, {res.oncelik} çıktı"
            assert res.aksiyon == "human_escalation"


def test_beklenmeyen_otomatik_yanit_yok():
    for row, res in zip(ROWS, _results()):
        if res.aksiyon == "auto_reply":
            assert row["beklenen"]["aksiyon"] == "auto_reply", f"#{row['id']} haksız yere otomatik cevaplandı"
