"""Veri sözleşmesi: tüm modüller bu tipleri paylaşır.

Akış: Message --classify--> Extraction --decide--> Decision --reply--> Result
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Optional


class Intent(str, Enum):
    SIPARIS_DURUMU = "siparis_durumu"
    IADE_HASAR = "iade_hasar"
    SAGLIK_SIKAYETI = "saglik_sikayeti"
    URUN_BILGISI = "urun_bilgisi"
    FIYAT = "fiyat"
    INDIRIM = "indirim"
    KARGO_BILGISI = "kargo_bilgisi"
    POLITIKA = "politika"
    SPAM = "spam"
    BILINMIYOR = "bilinmiyor"


class Action(str, Enum):
    AUTO_REPLY = "auto_reply"                  # taslak doğrudan gönderilebilir (yine de kuyrukta görünür)
    NEEDS_VERIFICATION = "needs_verification"  # müşteriden/ekipten doğrulama gerekir
    HUMAN_ESCALATION = "human_escalation"      # insan temsilci devralır
    QUARANTINE = "quarantine"                  # yanıt verilmez (spam)


# Çoklu niyette en sert aksiyon kazanır.
ACTION_SEVERITY = {
    Action.AUTO_REPLY: 0,
    Action.NEEDS_VERIFICATION: 1,
    Action.HUMAN_ESCALATION: 2,
    Action.QUARANTINE: 3,
}


class Priority(str, Enum):
    P0 = "P0"  # sağlık / güvenlik: hemen
    P1 = "P1"  # şikâyet, iade, doğrulanamayan sipariş
    P2 = "P2"  # olağan sipariş sorusu
    P3 = "P3"  # bilgi sorusu, spam


PRIORITY_RANK = {Priority.P0: 0, Priority.P1: 1, Priority.P2: 2, Priority.P3: 3}


@dataclass
class Message:
    id: int
    kanal: str
    musteri_id: int
    mesaj: str

    @classmethod
    def from_dict(cls, d: dict) -> "Message":
        return cls(id=int(d["id"]), kanal=str(d["kanal"]), musteri_id=int(d["musteri_id"]), mesaj=str(d["mesaj"]))


@dataclass
class Entities:
    siparis_no: list[int] = field(default_factory=list)  # mesajda geçen sipariş numaraları (sırayla, tekrarsız)
    urun: list[str] = field(default_factory=list)        # eşleşen ürün slug'ları (knowledge.urunler[].slug)
    url: list[str] = field(default_factory=list)


@dataclass
class Extraction:
    """classify (kural) ya da llm (opsiyonel) çıktısı. Olgu İÇERMEZ, yalnız anlama."""
    dil: str                      # "tr" | "en"
    intents: list[Intent]
    entities: Entities
    gerekceler: list[str] = field(default_factory=list)


@dataclass
class Decision:
    """decide() çıktısı. Taslak metni burada değil, reply.py'de kurulur."""
    aksiyon: Action
    oncelik: Priority
    ekip: Optional[str]                 # "destek" | "kalite" | "iade" | "urun" | None
    gerekceler: list[str] = field(default_factory=list)
    kaynaklar: list[str] = field(default_factory=list)       # "siparisler.json#5", "politikalar.json#kargo" ...
    eksik_bilgiler: list[str] = field(default_factory=list)  # bilinmeyen yüzünden devir: "urun:tonik:alkol_icerir", "politika:hayvan_testi"


@dataclass
class Result:
    id: int
    kanal: str
    musteri_id: int
    mesaj: str
    dil: str
    intents: list[str]
    entities: dict
    oncelik: str
    aksiyon: str
    ekip: Optional[str]
    yanit_taslagi: Optional[str]
    gerekceler: list[str]
    kaynaklar: list[str]
    eksik_bilgiler: list[str]

    def to_dict(self) -> dict:
        return asdict(self)
