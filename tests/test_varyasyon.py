"""Varyasyon seti üzerinde GÜVENLİK değişmezleri.

Sınıflandırma hata yapabilir; bu testler hatanın bu 20 mesajda güvenli tarafta kaldığını bekçiler:
- ACİL (P0, sağlık) beklenen hiçbir mesaj ACİL'den düşmez.
- Beklenmediği hâlde otomatik cevaplanan mesaj olmaz (şüphede insana gider).

Son iki test bekçilerin kendisini sınar (mutasyon): kural bozulduğunda bekçi gerçekten kırmızı vermeli.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from triage import decide as decide_mod
from triage.knowledge import KnowledgeBase
from triage.models import Action, Message
from triage.pipeline import process_all

ROWS = json.loads((Path(__file__).resolve().parent / "varyasyonlar.json").read_text(encoding="utf-8"))


def _results():
    return process_all([Message.from_dict(r) for r in ROWS], KnowledgeBase.load())


def _check_p0():
    for row, res in zip(ROWS, _results()):
        if row["beklenen"]["oncelik"] == "P0":
            assert res.oncelik == "P0", f"#{row['id']} ACİL (P0) bekleniyordu, {res.oncelik} çıktı"
            assert res.aksiyon == "human_escalation"


def _check_no_unexpected_auto():
    for row, res in zip(ROWS, _results()):
        if res.aksiyon == "auto_reply":
            assert row["beklenen"]["aksiyon"] == "auto_reply", f"#{row['id']} haksız yere otomatik cevaplandı"


def test_p0_hic_dusmez():
    _check_p0()


def test_beklenmeyen_otomatik_yanit_yok():
    _check_no_unexpected_auto()


def test_mutasyon_saglik_katmani_bozulursa_bekci_kirmizi(monkeypatch):
    # Sağlık katmanını kapat: bekçi bunu yakalamalı.
    monkeypatch.setattr("triage.classify.safety_intents", lambda text: set())
    with pytest.raises(AssertionError):
        _check_p0()


def test_mutasyon_herkese_otomatik_yanit_verilirse_bekci_kirmizi(monkeypatch):
    # Karar katmanı her şeyi otomatik cevaplasın: bekçi bunu yakalamalı.
    gercek = decide_mod.decide

    def hep_otomatik(msg, ext, kb):
        karar = gercek(msg, ext, kb)
        karar.aksiyon = Action.AUTO_REPLY
        return karar

    monkeypatch.setattr("triage.pipeline.decide", hep_otomatik)
    with pytest.raises(AssertionError):
        _check_no_unexpected_auto()
