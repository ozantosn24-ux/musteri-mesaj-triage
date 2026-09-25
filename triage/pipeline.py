"""Uçtan uca akış: classify -> güvenlik katmanı -> decide -> reply -> Result.

triage.classify'a import ANINDA değil, çağrı ANINDA bağlanır (deferred import).
Böylece bu modül, triage/classify.py henüz yazılmamışken de import edilebilir;
sadece varsayılan extractor'la process() çağrıldığında gerekir.
"""
from __future__ import annotations

import dataclasses
from typing import Callable, Optional

from .decide import decide
from .knowledge import KnowledgeBase
from .models import Extraction, Intent, Message, Result
from .reply import build_reply

Extractor = Callable[[Message, KnowledgeBase], Extraction]


def process(msg: Message, kb: KnowledgeBase, extractor: Optional[Extractor] = None) -> Result:
    """Tek mesajı işler. extractor verilmezse triage.classify.classify kullanılır."""
    if extractor is None:
        from .classify import classify as extractor  # gecikmeli import

    ext = extractor(msg, kb)

    # Güvenlik katmanı: extractor (özellikle opsiyonel bir LLM) bir sağlık/güvenlik
    # niyetini ya da sipariş numarasını atlarsa, bu deterministik katman düzeltir.
    from .classify import extract_order_numbers, safety_intents

    guvenlik_niyetleri = safety_intents(msg.mesaj)
    yeni_niyetler = set(guvenlik_niyetleri) - set(ext.intents)
    # dict.fromkeys: sıra deterministik olsun (set birleşimi sırayı garanti etmez).
    ext.intents = list(dict.fromkeys([*ext.intents, *guvenlik_niyetleri]))
    if yeni_niyetler:
        ext.gerekceler.append("güvenlik katmanı: sağlık niyeti eklendi")

    # Sipariş numarası çıkarımında regex OTORİTEDİR (LLM'in yanlış/eksik
    # numara üretmesine karşı deterministik bir çapa).
    dogru_siparis_no = extract_order_numbers(msg.mesaj)
    if dogru_siparis_no != ext.entities.siparis_no:
        ext.gerekceler.append("güvenlik katmanı: sipariş numaraları regex ile düzeltildi")
    ext.entities.siparis_no = dogru_siparis_no

    # Sipariş no varsa ama SIPARIS_DURUMU niyeti eksikse: extractor (özellikle
    # bir LLM) atlamış olabilir. Sahiplik doğrulaması ATLANAMAZ, bu yüzden
    # niyet burada zorla eklenir (extractor'a güvenmeden).
    if dogru_siparis_no and Intent.SIPARIS_DURUMU not in ext.intents:
        ext.intents = list(dict.fromkeys([*ext.intents, Intent.SIPARIS_DURUMU]))
        ext.gerekceler.append(
            "güvenlik katmanı: sipariş no var ama SIPARIS_DURUMU niyeti eksikti, eklendi"
        )

    decision = decide(msg, ext, kb)
    yanit = build_reply(msg, ext, decision, kb)

    return Result(
        id=msg.id,
        kanal=msg.kanal,
        musteri_id=msg.musteri_id,
        mesaj=msg.mesaj,
        dil=ext.dil,
        intents=sorted(i.value for i in ext.intents),
        entities=dataclasses.asdict(ext.entities),
        oncelik=decision.oncelik.value,
        aksiyon=decision.aksiyon.value,
        ekip=decision.ekip,
        yanit_taslagi=yanit,
        gerekceler=[*ext.gerekceler, *decision.gerekceler],
        kaynaklar=decision.kaynaklar,
        eksik_bilgiler=decision.eksik_bilgiler,
    )


def process_all(messages: list[Message], kb: KnowledgeBase, extractor: Optional[Extractor] = None) -> list[Result]:
    return [process(m, kb, extractor) for m in messages]
