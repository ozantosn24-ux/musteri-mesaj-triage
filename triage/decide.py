"""Karar katmanı: her niyeti bağımsız değerlendirir, sonra en sert sonucu birleştirir.

decide() SAF bir fonksiyondur — global durum tutmaz, aynı (msg, ext, kb) girdisi
her zaman aynı Decision'ı üretir. Bu yüzden kb.filled(...) ile karşı-olgusal
("bu alan bilinseydi karar ne olurdu") hesabı, decide()'ı değiştirmeden çalışır.

Kural: olgu (fiyat, stok, sipariş durumu...) yalnız KnowledgeBase'den okunur.
Bir alan yok/None ise "bilinmiyor"dur; bu asla olumsuz cevaba çevrilmez, insana
devredilir (eksik_bilgiler alanına yazılır).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from .knowledge import KnowledgeBase
from .models import (
    ACTION_SEVERITY,
    PRIORITY_RANK,
    Action,
    Decision,
    Extraction,
    Intent,
    Message,
    Priority,
)
from .text import fold

# Ürün bilgisi sorularında hangi alanın soruldığunu anlamak için anahtar kelimeler
# (fold edilmiş metinle karşılaştırılır, bu yüzden zaten ASCII/küçük harf).
_CILT_ANAHTAR = ("cilt", "kuru", "yagli", "karma", "hassas", "uygun")
_HAYVAN_TESTI_ANAHTAR = ("hayvan", "test", "vegan", "cruelty")


@dataclass
class _Part:
    """Tek bir niyetin ürettiği kısmi karar. decide() bunları birleştirir."""

    action: Action
    priority: Priority
    ekip: Optional[str]
    reasons: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)


def order_access(msg: Message, ext: Extraction, kb: KnowledgeBase) -> tuple[list[dict], list[int]]:
    """Mesajdaki sipariş numaralarını sahiplik açısından ikiye ayırır.

    owned: bulunan VE mesajı yazan müşteriye (msg.musteri_id) ait siparişler —
    detayı paylaşmak güvenli.
    withheld: bulunamayan YA DA başka müşteriye ait numaralar — hiçbir detayı
    paylaşılmaz. İkisi ayrı sebeple withheld'e girer ama reply.py için aynı
    (nötr, detaysız) metin kullanılır; decide.py sebep metni için ayrıca bakar.
    """
    owned: list[dict] = []
    withheld: list[int] = []
    for no in ext.entities.siparis_no:
        order = kb.find_order(no)
        if order is None or int(order.get("musteri_id", -1)) != int(msg.musteri_id):
            withheld.append(no)
        else:
            owned.append(order)
    return owned, withheld


def asked_product_fields(folded_mesaj: str) -> set[str]:
    """Katlanmış (fold edilmiş) mesaj metninde hangi ürün alanları soruluyor?

    reply.py da aynı fonksiyonu kullanır ki "ne soruldu" mantığı tek yerde kalsın.
    """
    fields: set[str] = set()
    # "alkol var mı" içerik sorusudur, stok sorusu değil: içerik kelimesine bağlı "var mı"yı düşür.
    stok_metni = re.sub(r"(alkol|paraben|parfum|koku|icerig)\w*\s+var mi", "", folded_mesaj)
    if "var mi" in stok_metni:
        fields.add("stokta")
    if any(k in folded_mesaj for k in _CILT_ANAHTAR):
        fields.add("cilt_tipleri")
    if "alkol" in folded_mesaj:
        fields.add("alkol_icerir")
    # "nemlendirici" içinde de "ml" geçer; yalnız ayrı kelime ya da sayı + ml say.
    if re.search(r"\d\s*ml\b|\bml\b", folded_mesaj):
        fields.add("hacim_ml")
    return fields


def _part_saglik(kb: KnowledgeBase) -> _Part:
    policy = kb.get_policy("saglik") or {}
    ekip = policy.get("ekip") or "kalite"
    return _Part(Action.HUMAN_ESCALATION, Priority.P0, ekip, sources=["politikalar.json#saglik"])


def _part_iade(kb: KnowledgeBase) -> _Part:
    if kb.get_policy("iade"):
        return _Part(Action.HUMAN_ESCALATION, Priority.P1, "iade", sources=["politikalar.json#iade"])
    return _Part(Action.HUMAN_ESCALATION, Priority.P1, "iade", missing=["politika:iade"])


def _part_siparis(msg: Message, ext: Extraction, kb: KnowledgeBase) -> list[_Part]:
    numaralar = ext.entities.siparis_no
    if not numaralar:
        return [_Part(Action.NEEDS_VERIFICATION, Priority.P2, "destek",
                       reasons=["sipariş numarası verilmedi"])]

    parts: list[_Part] = []
    owned, withheld = order_access(msg, ext, kb)

    if withheld:
        reasons = []
        for no in withheld:
            if kb.find_order(no) is None:
                reasons.append(f"sipariş {no} bulunamadı")
            else:
                reasons.append(f"sipariş {no} bu müşteriye ait değil; bilgi paylaşılmadı")
        parts.append(_Part(Action.NEEDS_VERIFICATION, Priority.P1, "destek", reasons=reasons))

    if owned:
        sources = [f"siparisler.json#{o['siparis_no']}" for o in owned]
        parts.append(_Part(Action.AUTO_REPLY, Priority.P2, None, sources=sources))

    return parts


def _part_kargo(kb: KnowledgeBase) -> _Part:
    if kb.get_policy("kargo"):
        return _Part(Action.AUTO_REPLY, Priority.P3, None, sources=["politikalar.json#kargo"])
    return _Part(Action.HUMAN_ESCALATION, Priority.P3, "destek", missing=["politika:kargo"])


def _part_fiyat(msg: Message, ext: Extraction, kb: KnowledgeBase) -> list[_Part]:
    urunler = [u for u in (kb.find_product(s) for s in ext.entities.urun) if u]

    if urunler:
        parts: list[_Part] = []
        for u in urunler:
            if u.get("fiyat_tl") is not None:
                parts.append(_Part(Action.AUTO_REPLY, Priority.P3, None,
                                    sources=[f"urunler.json#{u['slug']}"]))
            else:
                parts.append(_Part(Action.HUMAN_ESCALATION, Priority.P3, "urun",
                                    missing=[f"urun:{u['slug']}:fiyat_tl"]))
        return parts

    # Ürün adı geçmiyor: fiyat listesi mi isteniyor?
    folded = fold(msg.mesaj)
    fiyat_listesi = kb.get_policy("fiyat_listesi") or {}
    if "fiyat listesi" in folded and fiyat_listesi.get("paylasilabilir"):
        sources = ["politikalar.json#fiyat_listesi"] + [f"urunler.json#{u['slug']}" for u in kb.products()]
        return [_Part(Action.AUTO_REPLY, Priority.P3, None, sources=sources,
                       reasons=["fiyat listesi paylaşılabilir"])]

    return [_Part(Action.NEEDS_VERIFICATION, Priority.P3, "destek",
                   reasons=["hangi ürünün fiyatı sorulduğu belirsiz"])]


def _part_indirim(kb: KnowledgeBase) -> _Part:
    policy = kb.get_policy("indirim")
    if not policy or policy.get("aktif_kodlar") is None:
        return _Part(Action.HUMAN_ESCALATION, Priority.P3, "destek",
                      missing=["politika:indirim:aktif_kodlar"])
    if not policy["aktif_kodlar"]:
        return _Part(Action.AUTO_REPLY, Priority.P3, None, sources=["politikalar.json#indirim"],
                      reasons=["aktif kod yok, kod uydurulmadı"])
    return _Part(Action.AUTO_REPLY, Priority.P3, None, sources=["politikalar.json#indirim"],
                  reasons=["aktif kodlar paylaşıldı"])


def _part_urun_bilgisi(msg: Message, ext: Extraction, kb: KnowledgeBase) -> list[_Part]:
    urunler = [u for u in (kb.find_product(s) for s in ext.entities.urun) if u]
    if not urunler:
        return [_Part(Action.NEEDS_VERIFICATION, Priority.P3, "destek",
                       reasons=["hangi ürün soruluyor belirsiz"])]

    asked = asked_product_fields(fold(msg.mesaj))
    parts: list[_Part] = []
    for u in urunler:
        eksik_alanlar = [alan for alan in asked if u.get(alan) is None]
        if eksik_alanlar:
            parts.append(_Part(Action.HUMAN_ESCALATION, Priority.P3, "urun",
                                missing=[f"urun:{u['slug']}:{alan}" for alan in eksik_alanlar]))
        else:
            parts.append(_Part(Action.AUTO_REPLY, Priority.P3, None,
                                sources=[f"urunler.json#{u['slug']}"]))
    return parts


def _part_politika(msg: Message, kb: KnowledgeBase) -> _Part:
    folded = fold(msg.mesaj)
    if not any(k in folded for k in _HAYVAN_TESTI_ANAHTAR):
        # Spesifikasyon yalnız hayvan-testi alt-durumunu tanımlıyor; başka
        # politika sorusu tanımsız kalır, "bilinmiyor" gibi insana devredilir.
        return _Part(Action.HUMAN_ESCALATION, Priority.P3, "destek",
                      reasons=["tanımlanmayan politika sorusu"])
    if kb.get_policy("hayvan_testi"):
        return _Part(Action.AUTO_REPLY, Priority.P3, None, sources=["politikalar.json#hayvan_testi"])
    return _Part(Action.HUMAN_ESCALATION, Priority.P3, "destek", missing=["politika:hayvan_testi"])


def _merge(parts: list[_Part], extra_reasons: list[str]) -> Decision:
    severity_to_action = {v: k for k, v in ACTION_SEVERITY.items()}
    rank_to_priority = {v: k for k, v in PRIORITY_RANK.items()}

    max_severity = max(ACTION_SEVERITY[p.action] for p in parts)
    top_action = severity_to_action[max_severity]

    min_rank = min(PRIORITY_RANK[p.priority] for p in parts)
    top_priority = rank_to_priority[min_rank]

    # ekip, en sert aksiyonu üreten parça(lar)dan gelir; birden fazlaysa
    # bunlar arasında en acil önceliğe sahip olan seçilir (deterministik).
    en_sert_parcalar = sorted(
        (p for p in parts if ACTION_SEVERITY[p.action] == max_severity),
        key=lambda p: PRIORITY_RANK[p.priority],
    )
    ekip = en_sert_parcalar[0].ekip

    return Decision(
        aksiyon=top_action,
        oncelik=top_priority,
        ekip=ekip,
        gerekceler=[r for p in parts for r in p.reasons] + extra_reasons,
        kaynaklar=[s for p in parts for s in p.sources],
        eksik_bilgiler=[m for p in parts for m in p.missing],
    )


def decide(msg: Message, ext: Extraction, kb: KnowledgeBase) -> Decision:
    """Her niyeti bağımsız değerlendirir, sonra en sert aksiyon/en acil önceliğe göre birleştirir."""
    parts: list[_Part] = []
    extra_reasons: list[str] = []

    # SPAM istisnası: sağlık şikâyeti varsa spam görmezden gelinir. Bu ÖNEMLİ,
    # çünkü QUARANTINE, HUMAN_ESCALATION'dan daha sert sayılıyor (ACTION_SEVERITY);
    # istisna olmasaydı bir sağlık şikâyeti "spam" etiketiyle sessizce yanıtsız kalabilirdi.
    if Intent.SPAM in ext.intents:
        if Intent.SAGLIK_SIKAYETI in ext.intents:
            extra_reasons.append("spam şüphesi var ama sağlık şikâyeti öncelikli")
        else:
            parts.append(_Part(Action.QUARANTINE, Priority.P3, None))

    if Intent.SAGLIK_SIKAYETI in ext.intents:
        parts.append(_part_saglik(kb))
    if Intent.IADE_HASAR in ext.intents:
        parts.append(_part_iade(kb))
    if Intent.SIPARIS_DURUMU in ext.intents:
        parts.extend(_part_siparis(msg, ext, kb))
    if Intent.KARGO_BILGISI in ext.intents:
        parts.append(_part_kargo(kb))
    if Intent.FIYAT in ext.intents:
        parts.extend(_part_fiyat(msg, ext, kb))
    if Intent.INDIRIM in ext.intents:
        parts.append(_part_indirim(kb))
    if Intent.URUN_BILGISI in ext.intents:
        parts.extend(_part_urun_bilgisi(msg, ext, kb))
    if Intent.POLITIKA in ext.intents:
        parts.append(_part_politika(msg, kb))
    if Intent.BILINMIYOR in ext.intents:
        parts.append(_Part(Action.HUMAN_ESCALATION, Priority.P3, "destek"))

    if not parts:
        # Niyet hiç çıkarılamadıysa "sorun yok" denmez, insana devredilir.
        parts.append(_Part(Action.HUMAN_ESCALATION, Priority.P3, "destek",
                            reasons=["niyet belirlenemedi"]))

    return _merge(parts, extra_reasons)
