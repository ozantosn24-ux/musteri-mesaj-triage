"""decide()/build_reply() birim testleri.

classify'a BAĞIMLI DEĞİL: Extraction nesneleri elle kurulur, bu yüzden
worker A'nın triage/classify.py'si henüz yazılmamışken de çalışır.
"""
from __future__ import annotations

from triage.decide import decide
from triage.knowledge import KnowledgeBase
from triage.models import Action, Entities, Extraction, Intent, Message, Priority
from triage.reply import build_reply


def _kb() -> KnowledgeBase:
    return KnowledgeBase.load()


def _msg(musteri_id: int, mesaj: str = "test mesajı") -> Message:
    return Message(id=1, kanal="whatsapp", musteri_id=musteri_id, mesaj=mesaj)


def _ext(intents, siparis_no=None, urun=None, dil="tr") -> Extraction:
    return Extraction(
        dil=dil,
        intents=list(intents),
        entities=Entities(siparis_no=list(siparis_no or []), urun=list(urun or [])),
    )


def test_order_owner_mismatch_no_leak():
    kb = _kb()
    msg = _msg(musteri_id=7, mesaj="12 numaralı siparişim nerede?")
    ext = _ext([Intent.SIPARIS_DURUMU], siparis_no=[12])

    decision = decide(msg, ext, kb)
    assert decision.aksiyon == Action.NEEDS_VERIFICATION
    assert decision.oncelik == Priority.P1
    assert decision.ekip == "destek"

    reply = build_reply(msg, ext, decision, kb)
    assert "teslim" not in reply
    assert "YK3000000012" not in reply
    assert "2026-09-18" not in reply


def test_order_not_found_no_status_word():
    kb = _kb()
    msg = _msg(musteri_id=22, mesaj="9999 numaralı siparişim hâlâ elime ulaşmadı")
    ext = _ext([Intent.SIPARIS_DURUMU], siparis_no=[9999])

    decision = decide(msg, ext, kb)
    assert decision.aksiyon == Action.NEEDS_VERIFICATION
    assert decision.oncelik == Priority.P1

    reply = build_reply(msg, ext, decision, kb)
    for kelime in ("kargoda", "hazırlanıyor", "teslim edildi"):
        assert kelime not in reply


def test_multi_order_owned_and_withheld_do_not_mix():
    kb = _kb()
    msg = _msg(musteri_id=3, mesaj="3 ve 12 numaralı siparişlerim nerede?")
    ext = _ext([Intent.SIPARIS_DURUMU], siparis_no=[3, 12])

    decision = decide(msg, ext, kb)
    assert decision.aksiyon == Action.NEEDS_VERIFICATION

    reply = build_reply(msg, ext, decision, kb)
    assert "YK3000000003" in reply
    assert "YK3000000012" not in reply
    assert "teslim" not in reply


def test_health_complaint_is_p0_human_no_medical_advice():
    kb = _kb()
    msg = _msg(musteri_id=14, mesaj="Dün aldığım serumu kullandım, yüzüm yandı ve kızardı.")
    ext = _ext([Intent.SAGLIK_SIKAYETI])

    decision = decide(msg, ext, kb)
    assert decision.aksiyon == Action.HUMAN_ESCALATION
    assert decision.oncelik == Priority.P0
    assert decision.ekip == "kalite"

    reply = build_reply(msg, ext, decision, kb)
    for yasakli in ("krem sür", "kortizon", "ilaç", "antihistamin", "merhem"):
        assert yasakli not in reply
    assert "lot" in reply


def test_spam_with_health_ignores_quarantine():
    kb = _kb()
    msg = _msg(musteri_id=1, mesaj="Takipçi kasmak ister misiniz, ayrıca yüzüm de yandı")
    ext = _ext([Intent.SPAM, Intent.SAGLIK_SIKAYETI])

    decision = decide(msg, ext, kb)
    assert decision.aksiyon == Action.HUMAN_ESCALATION
    assert decision.oncelik == Priority.P0
    assert "spam şüphesi var ama sağlık şikâyeti öncelikli" in decision.gerekceler


def test_spam_alone_is_quarantine_with_no_reply():
    kb = _kb()
    msg = _msg(musteri_id=27, mesaj="Takipçi kasmak ister misiniz? bit.ly/takip-artir")
    ext = _ext([Intent.SPAM])

    decision = decide(msg, ext, kb)
    assert decision.aksiyon == Action.QUARANTINE
    assert decision.oncelik == Priority.P3
    assert build_reply(msg, ext, decision, kb) is None


def test_tonik_alcohol_unknown_escalates_and_counterfactual_resolves():
    kb = _kb()
    msg = _msg(musteri_id=9, mesaj="Tonik 200 ml mi? İçeriğinde alkol var mı?")
    ext = _ext([Intent.URUN_BILGISI], urun=["tonik"])

    decision = decide(msg, ext, kb)
    assert decision.aksiyon == Action.HUMAN_ESCALATION
    assert decision.ekip == "urun"
    assert "urun:tonik:alkol_icerir" in decision.eksik_bilgiler

    reply = build_reply(msg, ext, decision, kb)
    assert "200 ml" in reply

    # Karşı-olgusal: alan biliniyor olsaydı (kb.filled) karar auto_reply'a döner.
    filled_kb = kb.filled(decision.eksik_bilgiler)
    filled_decision = decide(msg, ext, filled_kb)
    assert filled_decision.aksiyon == Action.AUTO_REPLY


def test_indirim_empty_codes_is_known_auto_reply():
    kb = _kb()
    msg = _msg(musteri_id=10, mesaj="İndirim kodunuz var mı?")
    ext = _ext([Intent.INDIRIM])

    decision = decide(msg, ext, kb)
    assert decision.aksiyon == Action.AUTO_REPLY

    reply = build_reply(msg, ext, decision, kb)
    assert "aktif bir indirim kodu" in reply

    politikalar_indirimsiz = {
        "kargo": {"firma": "Yurtiçi Kargo", "sure": "1-3 iş günü"},
        "hayvan_testi": {"metin_tr": "test edilmez", "metin_en": "not tested"},
    }
    kb_indirimsiz = KnowledgeBase(siparisler=[], urunler=[], politikalar=politikalar_indirimsiz)
    decision_eksik = decide(msg, ext, kb_indirimsiz)
    assert decision_eksik.aksiyon == Action.HUMAN_ESCALATION
    assert "politika:indirim:aktif_kodlar" in decision_eksik.eksik_bilgiler


def test_policy_missing_hayvan_testi_escalates():
    politikalar = {"kargo": {"firma": "Yurtiçi Kargo", "sure": "1-3 iş günü"}}
    kb = KnowledgeBase(siparisler=[], urunler=[], politikalar=politikalar)
    msg = _msg(musteri_id=11, mesaj="Ürünleriniz hayvanlar üzerinde test ediliyor mu?")
    ext = _ext([Intent.POLITIKA])

    decision = decide(msg, ext, kb)
    assert decision.aksiyon == Action.HUMAN_ESCALATION
    assert "politika:hayvan_testi" in decision.eksik_bilgiler


def test_multi_intent_price_and_order_msg8():
    kb = _kb()
    msg = _msg(musteri_id=4, mesaj="Güneş kreminin fiyatı ne kadar? Bir de 4 numaralı siparişim ne zaman gelir?")
    ext = _ext([Intent.FIYAT, Intent.SIPARIS_DURUMU], siparis_no=[4], urun=["gunes_kremi_spf50"])

    decision = decide(msg, ext, kb)
    assert decision.aksiyon == Action.AUTO_REPLY
    assert decision.oncelik == Priority.P2

    reply = build_reply(msg, ext, decision, kb)
    assert "450" in reply
    assert "hazırlanıyor" in reply


def test_hangi_urun_alani_soruluyor():
    from triage.decide import asked_product_fields
    from triage.text import fold

    # "alkol var mı" içerik sorusudur, stok sorusu sanılmamalı
    assert asked_product_fields(fold("Tonik 200 ml mi? İçeriğinde alkol var mı?")) == {"hacim_ml", "alkol_icerir"}
    assert asked_product_fields(fold("Retinol serumunuz var mı?")) == {"stokta"}
    # "nemlendirici" kelimesindeki "ml" hacim sorusu değildir
    assert "hacim_ml" not in asked_product_fields(fold("Nemlendirici kuru ciltte kullanılır mı?"))


def test_bilinmeyen_alan_adiyla_soylenir_ve_tarih_turkce():
    kb = KnowledgeBase.load()
    msg = Message(id=13, kanal="whatsapp", musteri_id=9, mesaj="Tonik 200 ml mi? İçeriğinde alkol var mı?")
    ext = Extraction(dil="tr", intents=[Intent.URUN_BILGISI], entities=Entities(urun=["tonik"]))
    reply = build_reply(msg, ext, decide(msg, ext, kb), kb)
    assert "alkol içeriği" in reply
    assert "stoklarımızda" not in reply

    msg2 = Message(id=2, kanal="instagram", musteri_id=5, mesaj="5 numaralı siparişimin durumu nedir acaba?")
    ext2 = Extraction(dil="tr", intents=[Intent.SIPARIS_DURUMU], entities=Entities(siparis_no=[5]))
    reply2 = build_reply(msg2, ext2, decide(msg2, ext2, kb), kb)
    assert "24.09.2026" in reply2 and "2026-09-24" not in reply2
