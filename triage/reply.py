"""Yanıt taslağı: her niyet için kısa, insan gibi görünen bir paragraf kurar.

Kural: metindeki her OLGU (durum, fiyat, içerik, kod, politika metni) yalnız
KnowledgeBase'den okunur; şablon sadece o değeri araya yerleştirir. Bilinmeyen
bir alan asla "hayır/yok" gibi kesin bir cevaba çevrilmez — nazikçe devredilir.
"""
from __future__ import annotations

from typing import Callable, Optional

from .decide import asked_product_fields, order_access
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
    if dil == "en":
        return ("For security reasons we can only share order details with the order owner. "
                 "Could you confirm the order number and the phone number or e-mail used for it?")
    return ("Güvenlik nedeniyle sipariş bilgilerini yalnızca sipariş sahibiyle paylaşabiliyoruz. "
            "Sipariş numarasını ve o siparişte kullanılan telefon/e-posta bilgisini teyit "
            "edebilir misiniz?")


def _siparis_durumu(msg: Message, ext: Extraction, kb: KnowledgeBase, dil: str) -> Optional[str]:
    if not ext.entities.siparis_no:
        if dil == "en":
            return "Could you share your order number so we can check its status?"
        return "Sipariş numaranızı paylaşırsanız durumunu hemen kontrol edebiliriz."

    owned, withheld = order_access(msg, ext, kb)
    lines = [_order_status_text(o, dil) for o in owned]
    if withheld:
        lines.append(_withheld_text(dil))
    return " ".join(lines)


# --- sağlık şikâyeti -------------------------------------------------------

def _saglik_sikayeti(msg: Message, ext: Extraction, kb: KnowledgeBase, dil: str) -> Optional[str]:
    policy = kb.get_policy("saglik") or {}
    ilk_mesaj = policy.get(f"ilk_mesaj_{dil}") or policy.get("ilk_mesaj_tr")
    istenecekler = policy.get("istenecekler") or []

    bits = [ilk_mesaj] if ilk_mesaj else []
    if dil == "en":
        bits.append("Our quality team will contact you as soon as possible.")
        if istenecekler:
            bits.append("Could you please share: " + ", ".join(istenecekler) + "?")
    else:
        bits.append("Kalite ekibimiz en kısa sürede sizinle iletişime geçecek.")
        if istenecekler:
            bits.append("Bize şu bilgileri paylaşabilir misiniz: " + ", ".join(istenecekler) + "?")
    return " ".join(bits)


# --- iade / hasar -----------------------------------------------------------

def _iade_hasar(msg: Message, ext: Extraction, kb: KnowledgeBase, dil: str) -> Optional[str]:
    policy = kb.get_policy("iade") or {}
    hasarli = policy.get("hasarli_urun")
    if dil == "en":
        detail = hasarli or ("Please share a photo and your order number so we can process "
                              "a free replacement or refund.")
        return ("We are sorry for the inconvenience. " + detail +
                " Could you send us a photo of the damage and your order number?")
    detail = hasarli or "Fotoğraf ve sipariş numaranızla ücretsiz değişim/iade sürecini başlatabiliriz."
    return ("Yaşadığınız sorun için üzgünüz. " + detail +
            " Ürünün fotoğrafını ve sipariş numaranızı paylaşabilir misiniz?")


# --- kargo bilgisi -----------------------------------------------------------

def _kargo_bilgisi(msg: Message, ext: Extraction, kb: KnowledgeBase, dil: str) -> Optional[str]:
    policy = kb.get_policy("kargo")
    if not policy:
        if dil == "en":
            return "We will confirm our current shipping carrier and delivery time and get back to you."
        return "Güncel kargo firması ve süresini teyit edip size döneceğiz."
    firma = policy.get("firma")
    sure = policy.get("sure_en") if dil == "en" else policy.get("sure")
    if dil == "en":
        return f"We ship with {firma}. Delivery usually takes {sure}."
    return f"Siparişleriniz {firma} ile gönderiliyor. Teslimat süresi genellikle {sure}."


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
                bits.append(_unknown_field_text(u["ad"], dil))
        return " ".join(bits)

    folded = fold(msg.mesaj)
    fiyat_listesi = kb.get_policy("fiyat_listesi") or {}
    if "fiyat listesi" in folded and fiyat_listesi.get("paylasilabilir"):
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
        liste = ", ".join(deger)
        if dil == "en":
            return f"{ad} is suitable for {liste} skin types."
        return f"{ad}, {liste} cilt tipleri için uygundur."
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

    asked = asked_product_fields(fold(msg.mesaj))
    bits = []
    for u in urunler:
        for alan in ("hacim_ml", "stokta", "cilt_tipleri", "alkol_icerir"):
            if alan in asked:
                metin = _urun_alan_metni(u, alan, dil)
                if metin:
                    bits.append(metin)
        if not any(alan in asked for alan in ("hacim_ml", "stokta", "cilt_tipleri", "alkol_icerir")):
            if dil == "en":
                bits.append(f"Could you clarify what you would like to know about {u['ad']}?")
            else:
                bits.append(f"{u['ad']} için tam olarak hangi bilgiyi merak ettiğinizi belirtebilir misiniz?")
    return " ".join(bits)


# --- politika ------------------------------------------------------------------

def _politika(msg: Message, ext: Extraction, kb: KnowledgeBase, dil: str) -> Optional[str]:
    folded = fold(msg.mesaj)
    if not any(k in folded for k in ("hayvan", "test", "vegan", "cruelty")):
        if dil == "en":
            return "We will confirm this policy question with our team and get back to you."
        return "Bu politika sorusunu ekibimizden teyit edip size döneceğiz."

    policy = kb.get_policy("hayvan_testi")
    if not policy:
        if dil == "en":
            return "We will confirm our animal-testing policy with our team and get back to you."
        return "Hayvan testi politikamızı ekibimizden teyit edip size döneceğiz."
    return policy.get(f"metin_{dil}") or policy.get("metin_tr")


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
