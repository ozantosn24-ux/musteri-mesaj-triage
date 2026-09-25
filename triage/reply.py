"""Yanıt taslağı: her niyet için kısa, insan gibi görünen bir paragraf kurar.

Kural: metindeki her OLGU (durum, fiyat, içerik, kod, politika metni) yalnız
KnowledgeBase'den okunur; şablon sadece o değeri araya yerleştirir. Bilinmeyen
bir alan asla "hayır/yok" gibi kesin bir cevaba çevrilmez — nazikçe devredilir.
"""
from __future__ import annotations

from typing import Callable, Optional

from .decide import (
    asked_product_fields,
    hasarli_urun_sorusu,
    istek_fiyat_listesi,
    kargo_ucret_soruluyor,
    order_access,
    politika_konulari,
    siparis_durum_disi_talep_kelimesi,
    tibbi_uygunluk_sorusu,
)
from .knowledge import KnowledgeBase
from .models import Action, Decision, Extraction, Intent, Message
from .text import fold

_STATUS_TR = {"kargoda": "kargoda", "hazirlaniyor": "hazırlanıyor", "teslim_edildi": "teslim edildi"}
_STATUS_EN = {"kargoda": "on the way", "hazirlaniyor": "being prepared", "teslim_edildi": "delivered"}

# (alan adı, tr etiketi, en etiketi) — "tahmini_teslim" bilerek "varış" diye
# çevrildi: bir siparişin KENDİ bilgisi "teslim" kelimesini yalnız gerçekten
# teslim edilmişse taşısın; başka siparişten sızıntı testleri buna göre kurulu.
_TARIH_ALANLARI = (
    ("kargoya_verilis", "Kargoya veriliş tarihi", "Shipped on"),
    ("tahmini_teslim", "Tahmini varış tarihi", "Estimated delivery"),
    ("tahmini_kargo", "Tahmini kargoya veriliş tarihi", "Estimated ship date"),
    ("teslim_tarihi", "Teslim tarihi", "Delivered on"),
)


def _greeting(dil: str) -> str:
    return "Merhaba," if dil == "tr" else "Hello,"


def _closing(dil: str) -> str:
    return "İyi günler dileriz." if dil == "tr" else "Best regards."


def _fallback_text(dil: str) -> str:
    if dil == "en":
        return "We received your message and will get back to you shortly."
    return "Mesajınızı aldık, en kısa sürede size dönüş yapacağız."


_ALAN_ETIKETI = {
    "alkol_icerir": ("alkol içeriği", "alcohol content"),
    "cilt_tipleri": ("uygun cilt tipleri", "suitable skin types"),
    "hacim_ml": ("hacim", "volume"),
    "stokta": ("stok durumu", "stock status"),
    "fiyat_tl": ("fiyat", "price"),
}


def _unknown_field_text(ad: str, dil: str, alan: str = "") -> str:
    tr_etiket, en_etiket = _ALAN_ETIKETI.get(alan, ("bu bilgi", "this detail"))
    if dil == "en":
        return f"We will confirm the {en_etiket} of {ad} with our product team and get back to you."
    return f"{ad} ürününün {tr_etiket} bilgisini ürün ekibimizden teyit edip size döneceğiz."


def _tarih(deger: str, dil: str) -> str:
    """2026-09-24 → 24.09.2026 (Türkçe). Beklenmeyen biçim olduğu gibi kalır."""
    parca = str(deger).split("-")
    if dil == "tr" and len(parca) == 3 and all(p.isdigit() for p in parca):
        return f"{parca[2]}.{parca[1]}.{parca[0]}"
    return str(deger)


# --- sipariş durumu -------------------------------------------------------

def _order_status_text(order: dict, dil: str) -> str:
    no = order["siparis_no"]
    durum = order.get("durum")
    firma = order.get("kargo_firmasi")
    takip = order.get("takip_no")

    if dil == "en":
        bits = [f"Order #{no} is {_STATUS_EN.get(durum, durum)}."]
        if firma:
            bits.append(f"Carrier: {firma}.")
        if takip:
            bits.append(f"Tracking number: {takip}.")
        for alan, _tr_etiket, en_etiket in _TARIH_ALANLARI:
            if order.get(alan):
                bits.append(f"{en_etiket}: {order[alan]}.")
        return " ".join(bits)

    bits = [f"{no} numaralı siparişiniz {_STATUS_TR.get(durum, durum)}."]
    if firma:
        bits.append(f"Kargo firması: {firma}.")
    if takip:
        bits.append(f"Takip numarası: {takip}.")
    for alan, tr_etiket, _en_etiket in _TARIH_ALANLARI:
        if order.get(alan):
            bits.append(f"{tr_etiket}: {_tarih(order[alan], 'tr')}.")
    return " ".join(bits)


def _withheld_text(dil: str) -> str:
    # Bulunamayan VE başkasına ait sipariş için AYNI (detaysız) metin — hangi
    # sebeple withheld olduğu asla sızmaz.
    if dil == "en":
        return ("We couldn't find an order with this number under your details. "
                "Could you share the order number and the phone number or e-mail used for the order?")
    return ("Bu numarayla size ait bir sipariş göremedik. Sipariş numaranızı ve siparişte "
            "kullandığınız telefon numarasını ya da e-posta adresini paylaşır mısınız?")


def _durum_disi_talep_text(dil: str) -> str:
    if dil == "en":
        return "We received your request; our team will get back to you about it shortly."
    return "Talebinizi aldık, ekibimiz bu konuda sizinle en kısa sürede iletişime geçecek."


def _durum_bilinmiyor_text(dil: str) -> str:
    if dil == "en":
        return "We will confirm the current status of your order with our team and get back to you."
    return "Siparişinizin güncel durumunu ekibimizden teyit edip size döneceğiz."


def _siparis_durumu(msg: Message, ext: Extraction, kb: KnowledgeBase, dil: str) -> Optional[str]:
    if not ext.entities.siparis_no:
        if dil == "en":
            return "Could you share your order number so we can check its status?"
        return "Sipariş numaranızı paylaşırsanız durumunu hemen kontrol edebiliriz."

    owned, withheld = order_access(msg, ext, kb)
    folded = fold(msg.mesaj)
    talep = siparis_durum_disi_talep_kelimesi(folded)

    lines: list[str] = []
    if talep:
        # Durum-dışı talep (iptal/adres/eksik vb.): sipariş durumu/takip no SIZDIRILMAZ.
        lines.append(_durum_disi_talep_text(dil))
    else:
        bilinen = [o for o in owned if o.get("durum") is not None]
        bilinmeyen = [o for o in owned if o.get("durum") is None]
        lines.extend(_order_status_text(o, dil) for o in bilinen)
        if bilinmeyen:
            # "durum" alanı None ise şablona asla basılmaz ("None" sızıntısı).
            lines.append(_durum_bilinmiyor_text(dil))
    if withheld:
        lines.append(_withheld_text(dil))
    return " ".join(lines)


# --- sağlık şikâyeti -------------------------------------------------------

def _saglik_sikayeti(msg: Message, ext: Extraction, kb: KnowledgeBase, dil: str) -> Optional[str]:
    policy = kb.get_policy("saglik") or {}
    ilk_mesaj = policy.get(f"ilk_mesaj_{dil}") or policy.get("ilk_mesaj_tr")
    istenecekler = (policy.get("istenecekler_en") if dil == "en" else policy.get("istenecekler")) or []

    if dil == "en":
        bits = ["We're sorry to hear this."]
        if ilk_mesaj:
            bits.append(ilk_mesaj)
        bits.append("Our quality team will contact you as soon as possible.")
        if istenecekler:
            bits.append("Could you please share: " + ", ".join(istenecekler) + "?")
    else:
        bits = ["Geçmiş olsun."]
        if ilk_mesaj:
            bits.append(ilk_mesaj)
        bits.append("Kalite ekibimiz en kısa sürede sizinle iletişime geçecek.")
        if istenecekler:
            bits.append("Bize şu bilgileri paylaşabilir misiniz: " + ", ".join(istenecekler) + "?")
    return " ".join(bits)


# --- iade / hasar -----------------------------------------------------------

def _iade_hasar(msg: Message, ext: Extraction, kb: KnowledgeBase, dil: str) -> Optional[str]:
    policy = kb.get_policy("iade") or {}
    folded = fold(msg.mesaj)

    if hasarli_urun_sorusu(folded):
        hasarli = policy.get("hasarli_urun_en") if dil == "en" else policy.get("hasarli_urun")
        if dil == "en":
            detail = hasarli or "Our team will let you know about the return process."
            return ("We are sorry for the inconvenience. " + detail +
                    " Could you send us a photo of the damage and your order number?")
        detail = hasarli or "İade sürecini ekibimiz size iletecek."
        return ("Yaşadığınız sorun için üzgünüz. " + detail +
                " Ürünün fotoğrafını ve sipariş numaranızı paylaşabilir misiniz?")

    # Hasar kelimesi yok: sıradan iade talebi, gerçek politikadaki süreyi kullan (uydurma yok).
    sure_gun = policy.get("sure_gun")
    if dil == "en":
        if sure_gun is not None:
            return (f"We are sorry to hear you would like to return the product. Our return period "
                    f"is {sure_gun} days. Could you share your order number so we can start the process?")
        return ("We will confirm our return process with our team and get back to you. "
                "Could you share your order number?")
    if sure_gun is not None:
        return (f"Ürünü iade etmek istemenize üzüldük. İade süremiz {sure_gun} gündür. "
                "Sipariş numaranızı paylaşırsanız süreci başlatabiliriz.")
    return "İade sürecini ekibimizden teyit edip size döneceğiz. Sipariş numaranızı paylaşabilir misiniz?"


# --- kargo bilgisi -----------------------------------------------------------

def _kargo_bilgisi(msg: Message, ext: Extraction, kb: KnowledgeBase, dil: str) -> Optional[str]:
    policy = kb.get_policy("kargo")
    if not policy:
        if dil == "en":
            return "We will confirm our current shipping carrier and delivery time and get back to you."
        return "Güncel kargo firması ve süresini teyit edip size döneceğiz."
    firma = policy.get("firma")
    sure = policy.get("sure_en") if dil == "en" else policy.get("sure")
    folded = fold(msg.mesaj)
    ucret_soruldu = kargo_ucret_soruluyor(folded, policy)
    if dil == "en":
        bits = [f"We ship with {firma}. Delivery usually takes {sure}."]
        if ucret_soruldu:
            bits.append("We will confirm the shipping fee and get back to you.")
        return " ".join(bits)
    bits = [f"Siparişleriniz {firma} ile gönderiliyor. Teslimat süresi genellikle {sure}."]
    if ucret_soruldu:
        bits.append("Kargo ücretini teyit edip size döneceğiz.")
    return " ".join(bits)


# --- fiyat -------------------------------------------------------------------

def _fiyat(msg: Message, ext: Extraction, kb: KnowledgeBase, dil: str) -> Optional[str]:
    urunler = [u for u in (kb.find_product(s) for s in ext.entities.urun) if u]

    if urunler:
        bits = []
        for u in urunler:
            fiyat = u.get("fiyat_tl")
            if fiyat is not None:
                bits.append(f"{u['ad']}: {fiyat} TL.")
            else:
                bits.append(_unknown_field_text(u["ad"], dil, "fiyat_tl"))
        return " ".join(bits)

    folded = fold(msg.mesaj)
    fiyat_listesi = kb.get_policy("fiyat_listesi") or {}
    if istek_fiyat_listesi(folded) and fiyat_listesi.get("paylasilabilir"):
        kalemler = [f"{u['ad']}: {u['fiyat_tl']} TL" for u in kb.products() if u.get("fiyat_tl") is not None]
        baslik = "Güncel fiyat listemiz: " if dil == "tr" else "Here is our current price list: "
        return baslik + "; ".join(kalemler) + "."

    if dil == "en":
        return "Could you let us know which product's price you would like to know?"
    return "Hangi ürünün fiyatını öğrenmek istediğinizi belirtebilir misiniz?"


# --- indirim -----------------------------------------------------------------

def _indirim(msg: Message, ext: Extraction, kb: KnowledgeBase, dil: str) -> Optional[str]:
    policy = kb.get_policy("indirim")
    if not policy or policy.get("aktif_kodlar") is None:
        if dil == "en":
            return "We will confirm our current discount codes with our team and get back to you."
        return "Güncel indirim kodlarını ekibimizden teyit edip size döneceğiz."
    kodlar = policy["aktif_kodlar"]
    if not kodlar:
        if dil == "en":
            return "We do not have an active discount code at the moment."
        return "Şu an aktif bir indirim kodumuz bulunmuyor."
    baslik = "Aktif indirim kodlarımız: " if dil == "tr" else "Our active discount codes: "
    return baslik + ", ".join(kodlar) + "."


# --- ürün bilgisi -------------------------------------------------------------

# cilt tipi TR->EN eşlemesi (reply İngilizce'yse Türkçe kelime asla kalmasın).
_CILT_TIPI_EN = {
    "normal": "normal",
    "kuru": "dry",
    "karma": "combination",
    "yağlı": "oily",
    "tüm cilt tipleri": "all skin types",
}


def _liste_baglacli(oge_listesi: list[str], baglac: str) -> str:
    """['normal','kuru','karma'], 've' -> 'normal, kuru ve karma'."""
    if len(oge_listesi) == 1:
        return oge_listesi[0]
    return ", ".join(oge_listesi[:-1]) + f" {baglac} " + oge_listesi[-1]


def _urun_alan_metni(u: dict, alan: str, dil: str) -> Optional[str]:
    ad = u["ad"]
    deger = u.get(alan)
    if deger is None:
        return _unknown_field_text(ad, dil, alan)

    if alan == "hacim_ml":
        return f"{ad} {deger} ml'dir." if dil == "tr" else f"{ad} is {deger} ml."
    if alan == "stokta":
        if dil == "en":
            return f"{ad} is in stock." if deger else f"{ad} is currently out of stock."
        return f"{ad} stoklarımızda var." if deger else f"{ad} şu anda stokta yok."
    if alan == "cilt_tipleri":
        if dil == "en":
            en_liste = [_CILT_TIPI_EN.get(x, x) for x in deger]
            if en_liste == ["all skin types"]:
                return f"{ad} is suitable for all skin types."
            return f"{ad} is suitable for {_liste_baglacli(en_liste, 'and')} skin types."
        if deger == ["tüm cilt tipleri"]:
            return f"{ad} tüm cilt tipleri için uygundur."
        return f"{ad} {_liste_baglacli(deger, 've')} ciltler için uygundur."
    if alan == "alkol_icerir":
        if dil == "en":
            return f"{ad} contains alcohol." if deger else f"{ad} does not contain alcohol."
        return f"{ad} alkol içerir." if deger else f"{ad} alkol içermez."
    return None


def _urun_bilgisi(msg: Message, ext: Extraction, kb: KnowledgeBase, dil: str) -> Optional[str]:
    urunler = [u for u in (kb.find_product(s) for s in ext.entities.urun) if u]
    if not urunler:
        if dil == "en":
            return "Could you let us know which product you are asking about?"
        return "Hangi ürünü sorduğunuzu belirtebilir misiniz?"

    folded = fold(msg.mesaj)
    if tibbi_uygunluk_sorusu(folded):
        # Tıbbi/hamilelik sorusu: cilt tipi/uygunluk cevabı VERİLMEZ.
        if dil == "en":
            return "This is a medical/pregnancy-related question; our quality team will confirm and get back to you."
        return "Bu tıbbi/hamilelik ile ilgili bir soru; kalite ekibimiz teyit edip size dönecek."

    asked = asked_product_fields(folded)
    bits = []
    for u in urunler:
        if not asked:
            # Ürün eşleşti ama tanınan bir alan sorulmuyor: uydurma yok, ürün ekibine devir.
            if dil == "en":
                bits.append(f"We will confirm this with our product team about {u['ad']} and get back to you.")
            else:
                bits.append(f"{u['ad']} hakkındaki bu soruyu ürün ekibimizden teyit edip size döneceğiz.")
            continue
        for alan in ("hacim_ml", "stokta", "cilt_tipleri", "alkol_icerir"):
            if alan in asked:
                metin = _urun_alan_metni(u, alan, dil)
                if metin:
                    bits.append(metin)
    return " ".join(bits)


# --- politika ------------------------------------------------------------------

def _diger_politika_teyit_text(dil: str) -> str:
    if dil == "en":
        return "We will confirm the other point you raised with our team and get back to you."
    return "Sorduğunuz diğer noktayı ekibimizden teyit edip size döneceğiz."


def _politika(msg: Message, ext: Extraction, kb: KnowledgeBase, dil: str) -> Optional[str]:
    folded = fold(msg.mesaj)
    konular = politika_konulari(folded)
    if not konular:
        if dil == "en":
            return "We will confirm this policy question with our team and get back to you."
        return "Bu politika sorusunu ekibimizden teyit edip size döneceğiz."

    bits = []
    if "hayvan" in konular:
        policy = kb.get_policy("hayvan_testi")
        if policy:
            bits.append(policy.get(f"metin_{dil}") or policy.get("metin_tr"))
        elif dil == "en":
            bits.append("We will confirm our animal-testing policy with our team and get back to you.")
        else:
            bits.append("Hayvan testi politikamızı ekibimizden teyit edip size döneceğiz.")

    if any(k != "hayvan" for k in konular):
        if bits:
            bits.append(_diger_politika_teyit_text(dil))
        elif dil == "en":
            bits.append("We will confirm this with our team and get back to you.")
        else:
            bits.append("Bu soruyu ekibimizden teyit edip size döneceğiz.")

    return " ".join(bits)


# --- bilinmiyor ------------------------------------------------------------------

def _bilinmiyor(msg: Message, ext: Extraction, kb: KnowledgeBase, dil: str) -> Optional[str]:
    if dil == "en":
        return "We want to make sure we understand your message correctly; our team will get back to you shortly."
    return "Mesajınızı doğru anladığımızdan emin olmak için ekibimiz sizinle en kısa sürede iletişime geçecek."


_BUILDER_SIRASI: list[Intent] = [
    Intent.SAGLIK_SIKAYETI,
    Intent.IADE_HASAR,
    Intent.SIPARIS_DURUMU,
    Intent.KARGO_BILGISI,
    Intent.FIYAT,
    Intent.INDIRIM,
    Intent.URUN_BILGISI,
    Intent.POLITIKA,
    Intent.BILINMIYOR,
]

_BUILDERS: dict[Intent, Callable[[Message, Extraction, KnowledgeBase, str], Optional[str]]] = {
    Intent.SAGLIK_SIKAYETI: _saglik_sikayeti,
    Intent.IADE_HASAR: _iade_hasar,
    Intent.SIPARIS_DURUMU: _siparis_durumu,
    Intent.KARGO_BILGISI: _kargo_bilgisi,
    Intent.FIYAT: _fiyat,
    Intent.INDIRIM: _indirim,
    Intent.URUN_BILGISI: _urun_bilgisi,
    Intent.POLITIKA: _politika,
    Intent.BILINMIYOR: _bilinmiyor,
}


def build_reply(msg: Message, ext: Extraction, decision: Decision, kb: KnowledgeBase) -> Optional[str]:
    """Karar karantina değilse, niyet başına bir bölüm içeren kısa bir taslak kurar."""
    if decision.aksiyon == Action.QUARANTINE:
        return None

    dil = ext.dil if ext.dil in ("tr", "en") else "tr"

    govde_parcalari = []
    for intent in _BUILDER_SIRASI:
        if intent in ext.intents:
            metin = _BUILDERS[intent](msg, ext, kb, dil)
            if metin:
                govde_parcalari.append(metin)

    govde = " ".join(govde_parcalari) if govde_parcalari else _fallback_text(dil)
    return f"{_greeting(dil)}\n\n{govde}\n\n{_closing(dil)}"
