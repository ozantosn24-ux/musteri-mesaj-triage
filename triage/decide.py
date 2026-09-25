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

# Hamilelik/emzirme/ilaç-tedavi gibi TIBBİ uygunluk soruları cilt tipi sorusu
# SANILMAMALI ("hamilelikte uygun mu" içinde "uygun" geçer ama bu bir cilt tipi
# sorusu değildir) — veride yok, doktora/kaliteye devredilir.
_TIBBI_UYGUNLUK_ANAHTAR = ("hamile", "gebe", "emzir", "bebek", "cocuk", "ilac",
                            "tedavi", "hastalik", "pregnan", "breastfeed")

# Politika sorusu alt-konuları (fold edilmiş metinle karşılaştırılır). "hayvan"
# konusu ("hayvan"/"animal"/"cruelty") politikalar.json#hayvan_testi ile karşılanır;
# diğerleri veride YOK, insana devredilir.
_POLITIKA_KONU_ANAHTARLARI: dict[str, tuple[str, ...]] = {
    "hayvan": ("hayvan", "animal", "cruelty"),
    "vegan": ("vegan",),
    "dermatolojik_test": ("dermatolojik",),
    "helal": ("helal", "halal"),
}

# Sipariş DURUMU sorulduğunu gösteren kelimeler — bunlardan biri yoksa ya da
# mesaj durum-dışı bir talep içeriyorsa, sahip olunan siparişte bile otomatik
# yanıt VERİLMEZ (§A).
_SIPARIS_DURUM_SOZ = ("nerede", "nerde", "durum", "ne zaman", "gelir", "gelmedi", "geldi",
                       "ulasmadi", "ulasir", "ulasti", "kargo", "kargoya", "teslim", "takip",
                       "verildi", "gonderildi",
                       "where", "status", "when", "arrive", "ship", "track", "deliver", "check")
# Durum sorusu gibi görünse de insan isteyen talep/şikâyet ("takip numaram çalışmıyor").
_SIPARIS_TALEP_SOZ = ("iptal", "adres", "eksik", "degistir", "yanlis",
                       "calismiyor", "gorunmuyor", "acilmiyor",
                       "cancel", "address", "missing", "wrong", "not working")

# Kargo ücreti soruluyor mu? (veride YOK; eklenirse otomatik auto_reply'e döner.)
_KARGO_UCRET_ANAHTAR = ("ucret", "fee", "cost")

# Fiziksel hasar kelimeleri. "hasarsız" gibi olumsuz ekli biçimler SAYILMAZ
# (aşağıdaki regex bunları önce metinden çıkarır).
_HASAR_KELIMELERI = ("ezik", "hasar", "kirik", "bozuk", "damaged", "broken")
_HASAR_OLUMSUZ_EKI = re.compile(r"(?:ezik|hasar|kirik|bozuk)siz")


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


# "var mı"dan önceki kelime ürün kategorisi ya da iyelik ekli bir ad ise ("serumunuz") stok sorusudur.
_URUNE_BAGLI_VAR_MI = (
    r"\b(\w+(unuz|uniz|nuz|niz)|serum\w*|krem\w*|tonik\w*|toner|nemlendirici\w*|"
    r"gunes kremi\w*|retinol\w*|vitamini\w*)\s+var mi"
)


def asked_product_fields(folded_mesaj: str) -> set[str]:
    """Katlanmış (fold edilmiş) mesaj metninde hangi ürün alanları soruluyor?

    reply.py da aynı fonksiyonu kullanır ki "ne soruldu" mantığı tek yerde kalsın.
    """
    fields: set[str] = set()
    # Stok sorusu: "stok" kelimesi ya da ÜRÜNE bağlı "var mı" ("serumunuz var mı", "tonik var mı").
    # "peeling var mı", "paraben var mı" gibi başka bir şeye bağlı "var mı" içerik sorusudur, stok değil.
    if "stok" in folded_mesaj or re.search(_URUNE_BAGLI_VAR_MI, folded_mesaj):
        fields.add("stokta")
    if any(k in folded_mesaj for k in _CILT_ANAHTAR):
        fields.add("cilt_tipleri")
    if "alkol" in folded_mesaj:
        fields.add("alkol_icerir")
    # "nemlendirici" içinde de "ml" geçer; yalnız ayrı kelime ya da sayı + ml say.
    if re.search(r"\d\s*ml\b|\bml\b", folded_mesaj):
        fields.add("hacim_ml")
    return fields


def tibbi_uygunluk_sorusu(folded_mesaj: str) -> bool:
    """Hamilelik/emzirme/ilaç-tedavi gibi tıbbi bir uygunluk sorusu mu?

    Bu bilgi ürün verisinde YOK; cilt tipi alanıyla karıştırılmaz — kalite
    ekibine devredilir. decide.py ve reply.py aynı kontrolü paylaşır.
    """
    return any(k in folded_mesaj for k in _TIBBI_UYGUNLUK_ANAHTAR)


def politika_konulari(folded_mesaj: str) -> list[str]:
    """Mesajda geçen politika alt-konuları (tekrarsız, sabit sırayla).

    "hayvan" konusu (hayvan/animal/cruelty) politikalar.json#hayvan_testi ile
    karşılanabilir; diğerleri (vegan, dermatolojik_test, helal) ya da genel
    "test edildi mi" (hayvan/dermatolojik olmadan) veride YOK — insana devredilir.
    decide.py ve reply.py aynı fonksiyonu kullanır (tek yerde tutulan mantık).
    """
    konular = [konu for konu, anahtarlar in _POLITIKA_KONU_ANAHTARLARI.items()
               if any(k in folded_mesaj for k in anahtarlar)]
    if "test" in folded_mesaj and "hayvan" not in konular and "dermatolojik_test" not in konular:
        konular.append("test_belirsiz")
    return konular


def istek_fiyat_listesi(folded_mesaj: str) -> bool:
    """Mesaj, ürün adı vermeden GENEL fiyat listesi mi istiyor?"""
    return "fiyat listesi" in folded_mesaj


def siparis_durum_disi_talep_kelimesi(folded_mesaj: str) -> Optional[str]:
    """Sahip olunan bir siparişte otomatik yanıt yalnız DURUM soruluyorsa verilir.

    Mesaj durum-dışı bir talep içeriyorsa (iptal/adres/eksik/değiştir/yanlış ürün)
    eşleşen kelimeyi döndürür; hiç durum kelimesi de yoksa "durum kelimesi yok"
    döner; ikisi de yoksa (yalnız durum soruluyorsa) None döner.
    """
    talep_hit = next((k for k in _SIPARIS_TALEP_SOZ if k in folded_mesaj), None)
    if talep_hit:
        return talep_hit
    if not any(k in folded_mesaj for k in _SIPARIS_DURUM_SOZ):
        return "durum kelimesi yok"
    return None


def kargo_ucret_soruluyor(folded_mesaj: str, policy: Optional[dict]) -> bool:
    """Kargo ücreti mi soruluyor VE veride yok mu? (varsa otomatik auto_reply kalır.)"""
    policy = policy or {}
    return any(k in folded_mesaj for k in _KARGO_UCRET_ANAHTAR) and policy.get("ucret_tl") is None


def hasarli_urun_sorusu(folded_mesaj: str) -> bool:
    """Fiziksel hasar kelimesi geçiyor mu? "hasarsız" gibi olumsuz ekli biçim SAYILMAZ."""
    temiz = _HASAR_OLUMSUZ_EKI.sub("", folded_mesaj)
    return any(k in temiz for k in _HASAR_KELIMELERI)


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
        folded = fold(msg.mesaj)
        talep = siparis_durum_disi_talep_kelimesi(folded)
        if talep:
            # Durum-dışı talep (iptal/adres/eksik/değiştir vb.) OTOMATİK yanıtlanmaz.
            parts.append(_Part(Action.HUMAN_ESCALATION, Priority.P1, "destek",
                                reasons=[f"sipariş hakkında durum dışı talep ({talep}) → insan"]))
        else:
            # "durum" alanı bilinmiyorsa uydurulmaz; o sipariş NEEDS_VERIFICATION'a gider.
            bilinen = [o for o in owned if o.get("durum") is not None]
            bilinmeyen = [o for o in owned if o.get("durum") is None]
            if bilinen:
                sources = [f"siparisler.json#{o['siparis_no']}" for o in bilinen]
                parts.append(_Part(Action.AUTO_REPLY, Priority.P2, None, sources=sources))
            if bilinmeyen:
                missing = [f"siparis:{o['siparis_no']}:durum" for o in bilinmeyen]
                parts.append(_Part(Action.NEEDS_VERIFICATION, Priority.P2, "destek", missing=missing))

    return parts


def _part_kargo(msg: Message, kb: KnowledgeBase) -> _Part:
    folded = fold(msg.mesaj)
    policy = kb.get_policy("kargo")
    if not policy:
        return _Part(Action.HUMAN_ESCALATION, Priority.P3, "destek", missing=["politika:kargo"])
    if kargo_ucret_soruluyor(folded, policy):
        # Taşıyıcı/süre biliniyor, ücret veride yok: kısmen paylaşılır + devredilir.
        return _Part(Action.HUMAN_ESCALATION, Priority.P3, "destek",
                      sources=["politikalar.json#kargo"], missing=["politika:kargo:ucret"])
    return _Part(Action.AUTO_REPLY, Priority.P3, None, sources=["politikalar.json#kargo"])


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
    if istek_fiyat_listesi(folded) and fiyat_listesi.get("paylasilabilir"):
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

    folded = fold(msg.mesaj)
    if tibbi_uygunluk_sorusu(folded):
        # "Hamilelikte uygun mu" bir cilt tipi sorusu DEĞİL, tıbbi bir sorudur;
        # veride yok, ürün ekibi değil kalite ekibi devralır.
        return [_Part(Action.HUMAN_ESCALATION, Priority.P2, "kalite",
                       reasons=["tıbbi/hamilelik uygunluğu veride yok → kalite ekibi"])]

    asked = asked_product_fields(folded)
    parts: list[_Part] = []
    for u in urunler:
        if not asked:
            # Ürün eşleşti ama tanınan bir alan (stok/cilt/alkol/hacim) soruluyor
            # değil (ör. "paraben var mı?", "hamilelikte..." gibi veride olmayan
            # bir soru) — uydurulmaz, ürün ekibine devredilir.
            parts.append(_Part(Action.HUMAN_ESCALATION, Priority.P3, "urun",
                                reasons=["sorulan ürün bilgisi veride yok/tanınmadı → ürün ekibi"]))
            continue
        eksik_alanlar = [alan for alan in asked if u.get(alan) is None]
        bilinen_alanlar = [alan for alan in asked if alan not in eksik_alanlar]
        if eksik_alanlar:
            # Bilinen alan varsa kaynağı da eklenir (kısmen yanıtlanan sorunun
            # kanıtı defterde de görünsün).
            kaynaklar = [f"urunler.json#{u['slug']}"] if bilinen_alanlar else []
            parts.append(_Part(Action.HUMAN_ESCALATION, Priority.P3, "urun",
                                missing=[f"urun:{u['slug']}:{alan}" for alan in eksik_alanlar],
                                sources=kaynaklar))
        else:
            parts.append(_Part(Action.AUTO_REPLY, Priority.P3, None,
                                sources=[f"urunler.json#{u['slug']}"]))
    return parts


def _part_politika(msg: Message, kb: KnowledgeBase) -> _Part:
    folded = fold(msg.mesaj)
    konular = politika_konulari(folded)
    if not konular:
        # Hiçbir tanınan alt-konu yok; "bilinmiyor" gibi insana devredilir.
        return _Part(Action.HUMAN_ESCALATION, Priority.P3, "destek",
                      reasons=["tanımlanmayan politika sorusu"])

    diger_konular = [k for k in konular if k != "hayvan"]

    if "hayvan" not in konular:
        # Yalnız kapsanmayan konu(lar) soruluyor (vegan/dermatolojik/helal/genel test).
        return _Part(Action.HUMAN_ESCALATION, Priority.P3, "destek",
                      missing=[f"politika:{k}" for k in konular],
                      reasons=[f"kapsanmayan politika konusu: {k}" for k in konular])

    if not kb.get_policy("hayvan_testi"):
        return _Part(Action.HUMAN_ESCALATION, Priority.P3, "destek",
                      missing=["politika:hayvan_testi"] + [f"politika:{k}" for k in diger_konular],
                      reasons=[f"kapsanmayan politika konusu: {k}" for k in diger_konular])

    if diger_konular:
        # Hayvan testi metni paylaşılabilir AMA mesaj kapsanmayan başka bir
        # konu da soruyor (ör. vegan) — o kısım insana devredilir.
        return _Part(Action.HUMAN_ESCALATION, Priority.P3, "destek",
                      sources=["politikalar.json#hayvan_testi"],
                      missing=[f"politika:{k}" for k in diger_konular],
                      reasons=[f"kapsanmayan politika konusu: {k}" for k in diger_konular])

    return _Part(Action.AUTO_REPLY, Priority.P3, None, sources=["politikalar.json#hayvan_testi"])


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
    # Aynı mantık BİLİNMİYOR dışında herhangi bir GERÇEK niyet için de geçerli:
    # spam + gerçek talep varsa karantinaya atılıp sessizce kaybolmaz, insana gider.
    if Intent.SPAM in ext.intents:
        if Intent.SAGLIK_SIKAYETI in ext.intents:
            extra_reasons.append("spam şüphesi var ama sağlık şikâyeti öncelikli")
        elif set(ext.intents) - {Intent.SPAM, Intent.BILINMIYOR}:
            parts.append(_Part(Action.HUMAN_ESCALATION, Priority.P3, "destek",
                                reasons=["spam işareti var ama gerçek bir talep de var → insan"]))
        else:
            parts.append(_Part(Action.QUARANTINE, Priority.P3, None))

    if Intent.SAGLIK_SIKAYETI in ext.intents:
        parts.append(_part_saglik(kb))
    if Intent.IADE_HASAR in ext.intents:
        parts.append(_part_iade(kb))
    if Intent.SIPARIS_DURUMU in ext.intents:
        parts.extend(_part_siparis(msg, ext, kb))
    if Intent.KARGO_BILGISI in ext.intents:
        parts.append(_part_kargo(msg, kb))
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
