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
from triage.text import fold

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


# --- sağlık (güvenlik) katmanı: yanlış-pozitifler (masum kelimenin içine sızma) ---


@pytest.mark.parametrize(
    "text",
    [
        "Şişli'deki mağazanızdan aldım",   # ilçe adı, "sisli" != "şişlik"
        "yandex üzerinden ödeme yaptım",    # "yandex" içinde "yan" var ama uzantısı yok
        "bir yandan siparişimi bekliyorum, bir yandan da meraklıyım",
        "Yanda bir mağazanız var mı?",
        "Şişenin burnu biraz eğri duruyor.",  # burnu (şişenin ucu) != burn(ing)
        "kabarık saç istiyorum, ürün önerir misiniz?",  # kabarik != kabarcik/kabardi
        "switch atmadan önce fişi çekin",
        "kitchen serisi ürünleriniz var mı?",
        "kargo crash oldu diye duydum",
        "trash kutusuna düştü sanırım",
    ],
)
def test_safety_intents_yanlis_pozitif_yok(text):
    assert safety_intents(text) == set()


def test_safety_intents_peeling_urun_adi_semptom_degil():
    # "Tonik peeling var mı?" ürün türü sorusudur, cilt şikâyeti değil.
    assert safety_intents("Tonik peeling var mı?") == set()


# --- sağlık (güvenlik) katmanı: doğru-pozitifler ---


@pytest.mark.parametrize(
    "text",
    [
        "yüzüm yandı",
        "elim kızardı",
        "cildim şişti",
        "kaşıntı yaptı",
        "my skin is burning",
        "I have a rash on my arm",
        "it feels itchy",
        "cildim soyuldu",
        "Retinol serum cildimde yanma yaptı",  # 2. hakem: "yanma" formu
        "yüzüm yanıyor",                        # 2. hakem: "yanıyor" formu
    ],
)
def test_safety_intents_dogru_pozitif(text):
    assert safety_intents(text) == {Intent.SAGLIK_SIKAYETI}


def test_saglik_gerekce_eslesen_kelimeyi_adlandirir(kb):
    msg = Message(id=901, kanal="whatsapp", musteri_id=1, mesaj="yüzüm yandı")
    extraction = classify(msg, kb)
    assert Intent.SAGLIK_SIKAYETI in extraction.intents
    assert any("yandi" in g for g in extraction.gerekceler)


# --- spam: "takip" artık tek başına promosyon kelimesi değil ---


def test_spam_takip_numaram_spam_degil(kb):
    msg = Message(
        id=902, kanal="whatsapp", musteri_id=1,
        mesaj="takip numaram çalışmıyor, yurticikargo.com.tr/12345 linkine bakar mısınız?",
    )
    extraction = classify(msg, kb)
    assert Intent.SPAM not in extraction.intents


def test_spam_takipci_hala_spam(kb):
    # "takipci" (takipçi) hâlâ promosyon kelimesi; link + kelime spam sayılır.
    msg = Message(id=903, kanal="instagram", musteri_id=1, mesaj="takipçi kasmak ister misiniz? bit.ly/kazan")
    extraction = classify(msg, kb)
    assert Intent.SPAM in extraction.intents


# --- INDIRIM: bare "kod" artık indirim/kupon/promosyon/discount/coupon gerektirir ---


@pytest.mark.parametrize(
    "text",
    [
        "takip kodu çalışmıyor, yardım eder misiniz?",
        "posta kodu nedir?",
        "lot kodu ürünün üzerinde mi yazıyor?",
    ],
)
def test_indirim_bare_kod_yanlis_pozitif_yok(text, kb):
    msg = Message(id=904, kanal="whatsapp", musteri_id=1, mesaj=text)
    extraction = classify(msg, kb)
    assert Intent.INDIRIM not in extraction.intents


def test_indirim_mesaj_14_hala_indirim(messages, kb):
    extraction = _classify_id(14, messages, kb)
    assert Intent.INDIRIM in extraction.intents


# --- FIYAT vs KARGO_BILGISI: süre soruları fiyat değildir ---


def test_kargo_ne_kadar_surer_kargo_bilgisi_fiyat_degil(kb):
    msg = Message(id=905, kanal="whatsapp", musteri_id=1, mesaj="Kargo ne kadar sürer?")
    extraction = classify(msg, kb)
    assert Intent.KARGO_BILGISI in extraction.intents
    assert Intent.FIYAT not in extraction.intents


def test_retinol_kac_gun_kullanmaliyim_kargo_bilgisi_degil(kb):
    msg = Message(id=906, kanal="whatsapp", musteri_id=1, mesaj="Retinolü kaç gün kullanmalıyım?")
    extraction = classify(msg, kb)
    assert Intent.KARGO_BILGISI not in extraction.intents


def test_iade_suresi_kac_gun_kargo_bilgisi_degil(kb):
    # İade bağlamında "kaç gün" kargo/teslimat demek değildir.
    msg = Message(id=907, kanal="whatsapp", musteri_id=1, mesaj="İade süresi kaç gün?")
    extraction = classify(msg, kb)
    assert Intent.KARGO_BILGISI not in extraction.intents


def test_shipping_take_days_ingilizce_kargo_bilgisi(kb):
    msg = Message(id=908, kanal="whatsapp", musteri_id=1, mesaj="How many days does shipping usually take?")
    extraction = classify(msg, kb)
    assert Intent.KARGO_BILGISI in extraction.intents


# --- URUN_BILGISI: "kaç ml" ve "stok(ta)" da destekleyici kelimedir ---


def test_urun_bilgisi_kac_ml(kb):
    msg = Message(id=909, kanal="whatsapp", musteri_id=1, mesaj="Retinol serum kaç ml?")
    extraction = classify(msg, kb)
    assert Intent.URUN_BILGISI in extraction.intents


def test_urun_bilgisi_stokta(kb):
    msg = Message(id=910, kanal="instagram", musteri_id=1, mesaj="Nemlendirici stokta mı?")
    extraction = classify(msg, kb)
    assert Intent.URUN_BILGISI in extraction.intents


# --- extract_order_numbers: yeni kalıplar ---


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Sipariş numaram 45", [45]),
        ("Siparişimin numarası 45", [45]),
        ("45 no'lu siparişim geldi mi?", [45]),
        ("45 nolu siparişim geldi mi?", [45]),
        ("order number 45", [45]),
        ("order no. 45", [45]),
        ("order no 45", [45]),
        ("3 ve 12 numaralı siparişlerim nerede?", [3, 12]),
        ("3, 12 numaralı siparişlerim nerede?", [3, 12]),
    ],
)
def test_extract_order_numbers_yeni_kaliplar(text, expected):
    assert extract_order_numbers(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "Sipariş 3 gün önce verdim",       # sayı + süre eki -> sipariş no değil
        "Sipariş 2 hafta önce verdim",
        "67 numaralı telefon ile aradım",  # sayı + referans eki -> sipariş no değil
        "numaralı hat müsait değil",
        "Sipariş no: 3.5",                  # ondalık sayının tam kısmı
        "#100% indirim kazandınız",         # sayı + yüzde soneki
    ],
)
def test_extract_order_numbers_yeni_disariki_birakma(text):
    assert extract_order_numbers(text) == []


# --- text.fold: NFC normalizasyonu ---


def test_fold_nfc_ayristirilmis_i_noktali():
    # "İ" ayrıştırılmış biçimde: "I" (U+0049) + üstüne nokta (U+0307)
    ayristirilmis = "İndirim kodu var mı"
    assert fold(ayristirilmis) == fold("İndirim kodu var mı")


# --- detect_language: karışık dilde 3+ İngilizce stopword Türkçe harfe rağmen "en" ---


def test_detect_language_karisik_dil_ingilizce_agir_basar():
    assert detect_language("Hi, I'm Gökhan, where is my order #3?") == "en"


# --- match_products: alias sayı sonekiyle karışmasın ("spf" vs "spf30") ---


def test_match_products_spf_farkli_sayi_varyanti_eslesmez(kb):
    assert match_products("SPF30 fiyatı nedir?", kb) == []


def test_match_products_spf_bare_hala_eslesir(kb):
    assert match_products("SPF ürününüz var mı?", kb) == ["gunes_kremi_spf50"]
