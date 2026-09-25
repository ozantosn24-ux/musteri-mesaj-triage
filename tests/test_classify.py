from __future__ import annotations

import json
from pathlib import Path

import pytest

from triage.classify import (
    classify,
    detect_language,
    extract_order_numbers,
    extract_urls,
    match_products,
    safety_intents,
)
from triage.knowledge import KnowledgeBase
from triage.models import Intent, Message

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


@pytest.fixture(scope="module")
def kb() -> KnowledgeBase:
    return KnowledgeBase.load()


@pytest.fixture(scope="module")
def messages() -> dict[int, dict]:
    raw = json.loads((DATA_DIR / "mesajlar.json").read_text(encoding="utf-8"))
    return {m["id"]: m for m in raw}


@pytest.fixture(scope="module")
def golden() -> dict[int, dict]:
    raw = json.loads((Path(__file__).resolve().parent / "golden.json").read_text(encoding="utf-8"))
    return {g["id"]: g for g in raw}


def _classify_id(msg_id: int, messages: dict[int, dict], kb: KnowledgeBase):
    msg = Message.from_dict(messages[msg_id])
    return classify(msg, kb)


# --- golden.json ile tam eşleşme: dil + intent kümesi (15 mesajın hepsi) ---


@pytest.mark.parametrize("msg_id", range(1, 16))
def test_golden_dil_ve_intents(msg_id, messages, golden, kb):
    extraction = _classify_id(msg_id, messages, kb)
    expected = golden[msg_id]
    assert extraction.dil == expected["dil"], f"id={msg_id}"
    got_intents = {i.value for i in extraction.intents}
    assert got_intents == set(expected["intents"]), f"id={msg_id}: {got_intents} != {expected['intents']}"


# --- sipariş numarası ---


@pytest.mark.parametrize(
    "msg_id,expected",
    [(1, [12]), (2, [5]), (3, [9999]), (5, []), (6, [3]), (7, []), (8, [4]), (9, []), (10, []), (13, [])],
)
def test_extract_order_numbers_per_mesaj(msg_id, expected, messages):
    text = messages[msg_id]["mesaj"]
    assert extract_order_numbers(text) == expected


def test_order_number_birim_ve_yuzde_onekiyle_karistirilmaz():
    # "200 ml" bir sipariş no değil (message 13'ün gövdesi)
    assert extract_order_numbers("Tonik 200 ml mi?") == []
    # "%100" bir sipariş no değil (message 7'nin gövdesi)
    assert extract_order_numbers("%100 organik takipçi") == []
    # Aynı guard, sayı doğrudan bir sipariş kalıbına bitişik olsa da tutar
    assert extract_order_numbers("Sipariş no: 200 ml'lik ürün") == []
    assert extract_order_numbers("%100 nolu kampanyaya katıldım") == []


def test_order_number_generic_kaliplar():
    assert extract_order_numbers("order #3") == [3]
    assert extract_order_numbers("Sipariş no: 45") == [45]


# --- link çıkarımı ---


@pytest.mark.parametrize("msg_id", [i for i in range(1, 16) if i != 7])
def test_extract_urls_link_yok(msg_id, messages):
    assert extract_urls(messages[msg_id]["mesaj"]) == []


def test_extract_urls_mesaj_7(messages):
    assert extract_urls(messages[7]["mesaj"]) == ["bit.ly/takip-artir"]


# --- ürün eşleştirme ---


@pytest.mark.parametrize(
    "msg_id,expected",
    [
        (4, []),
        (8, ["gunes_kremi_spf50"]),
        (9, ["retinol_serum"]),
        (10, ["nemlendirici_krem"]),
        (11, ["c_vitamini_serum"]),
        (13, ["tonik"]),
    ],
)
def test_match_products_per_mesaj(msg_id, expected, messages, kb):
    assert match_products(messages[msg_id]["mesaj"], kb) == expected


def test_match_products_buyuk_harf_ve_ascii_varyanti(kb):
    assert match_products("GUNES KREMI NE KADAR", kb) == ["gunes_kremi_spf50"]


# --- sağlık (güvenlik) katmanı ---


def test_safety_intents_turkce():
    assert safety_intents("yüzüm yandı") == {Intent.SAGLIK_SIKAYETI}


def test_safety_intents_ingilizce():
    assert safety_intents("my skin is burning and red") == {Intent.SAGLIK_SIKAYETI}


def test_safety_intents_negatif():
    assert safety_intents("fiyat ne kadar") == set()


# --- çoklu niyet: spam + sağlık birlikte çıkabilmeli ---


def test_spam_ve_saglik_birlikte(kb):
    msg = Message(id=999, kanal="instagram", musteri_id=1, mesaj="Kazanmak ister misin? bit.ly/kazan-simdi ayrıca yüzüm kızardı")
    extraction = classify(msg, kb)
    assert Intent.SPAM in extraction.intents
    assert Intent.SAGLIK_SIKAYETI in extraction.intents


# --- dil tespiti ---


def test_detect_language_ingilizce(messages):
    assert detect_language(messages[6]["mesaj"]) == "en"


@pytest.mark.parametrize("msg_id", [i for i in range(1, 16) if i != 6])
def test_detect_language_turkce(msg_id, messages):
    assert detect_language(messages[msg_id]["mesaj"]) == "tr"


# --- gerekçeler boş olmamalı (audit izi) ---


@pytest.mark.parametrize("msg_id", [1, 4, 7])
def test_gerekceler_bos_degil(msg_id, messages, kb):
    extraction = _classify_id(msg_id, messages, kb)
    assert len(extraction.gerekceler) > 0
