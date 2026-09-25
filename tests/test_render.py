"""render.py testleri: XSS kaçışı + (varsa) karşı-olgusal bilgi boşluğu hesabı."""
from __future__ import annotations

import pytest

from triage.knowledge import KnowledgeBase
from triage.models import Result
from triage.render import knowledge_gap_report, write_reports


def _entities(siparis_no=None, urun=None, url=None) -> dict:
    return {"siparis_no": siparis_no or [], "urun": urun or [], "url": url or []}


def _sample_results() -> list[Result]:
    # P0 human_escalation — mesajda XSS denemesi (<script>).
    r_health = Result(
        id=4,
        kanal="instagram",
        musteri_id=14,
        mesaj="Dün aldığım serumu kullandım <script>alert(1)</script> yüzüm yandı",
        dil="tr",
        intents=["saglik_sikayeti"],
        entities=_entities(),
        oncelik="P0",
        aksiyon="human_escalation",
        ekip="kalite",
        yanit_taslagi="Ürünü kullanmayı hemen bırakmanızı rica ederiz.",
        gerekceler=["cilt reaksiyonu bildirildi"],
        kaynaklar=["politikalar.json#saglik"],
        eksik_bilgiler=[],
    )
    # auto_reply — gerekçede XSS denemesi (<img onerror>).
    r_auto = Result(
        id=2,
        kanal="whatsapp",
        musteri_id=5,
        mesaj="5 numaralı siparişimin durumu nedir acaba?",
        dil="tr",
        intents=["siparis_durumu"],
        entities=_entities(siparis_no=[5]),
        oncelik="P2",
        aksiyon="auto_reply",
        ekip=None,
        yanit_taslagi="Siparişiniz kargoda, tahmini teslim 2026-09-26.",
        gerekceler=["<img src=x onerror=alert(1)> siparis 5 kargoda"],
        kaynaklar=["siparisler.json#5"],
        eksik_bilgiler=[],
    )
    # quarantine — yanıt yok (yanit_taslagi None).
    r_quarantine = Result(
        id=7,
        kanal="instagram",
        musteri_id=27,
        mesaj="Takipçi kasmak ister misiniz? %100 organik takipçi: bit.ly/takip-artir",
        dil="tr",
        intents=["spam"],
        entities=_entities(url=["bit.ly/takip-artir"]),
        oncelik="P3",
        aksiyon="quarantine",
        ekip=None,
        yanit_taslagi=None,
        gerekceler=["spam: takipçi satışı + kısaltılmış link"],
        kaynaklar=[],
        eksik_bilgiler=[],
    )
    return [r_health, r_auto, r_quarantine]


def test_write_reports_escapes_xss_and_has_required_sections(tmp_path):
    kb = KnowledgeBase.load()
    results = _sample_results()

    paths = write_reports(results, kb, tmp_path)

    panel_html = paths["panel"].read_text(encoding="utf-8")
    rapor_md = paths["rapor"].read_text(encoding="utf-8")

    # Mesajdaki <script> kaçırılmış olmalı, ham hali panelde YER ALMAMALI.
    assert "&lt;script&gt;" in panel_html
    assert "<script>alert" not in panel_html
    # Gerekçedeki <img onerror> de kaçırılmış olmalı.
    assert "<img src=x" not in panel_html

    assert paths["rapor"].exists()
    assert "Onay Kuyruğu" in rapor_md

    assert "P0" in panel_html


def test_knowledge_gap_report_counterfactual():
    pytest.importorskip("triage.pipeline")
    pytest.importorskip("triage.classify")

    import json
    from pathlib import Path

    from triage.pipeline import process_all

    kb = KnowledgeBase.load()
    mesajlar = json.loads((Path(__file__).resolve().parent.parent / "data" / "mesajlar.json").read_text(encoding="utf-8"))
    results = process_all(mesajlar, kb)

    gap = knowledge_gap_report(results, kb)

    assert "urun:tonik:alkol_icerir" in gap["eksik_alanlar"]
    assert 13 in gap["donusecek_mesajlar"]
    assert 4 not in gap["donusecek_mesajlar"]
    assert 1 not in gap["donusecek_mesajlar"]
    assert gap["etiket"] == "varsayımsal tahmin"
