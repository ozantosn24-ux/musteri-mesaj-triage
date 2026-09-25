"""decide()/build_reply() birim testleri.

classify'a BAĞIMLI DEĞİL: Extraction nesneleri elle kurulur, bu yüzden
triage/classify.py henüz yazılmamışken de çalışır.
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
    # 200 ml biliniyor: bilinen alanın kaynağı da defterde görünsün (kısmi yanıt kanıtı).
    assert "urunler.json#tonik" in decision.kaynaklar

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


# --- §A: sahip olunan sipariş, yalnız DURUM sorulunca otomatik yanıtlanır ----

def test_owned_order_cancel_request_is_human_no_status_leak():
    kb = _kb()
    msg = _msg(musteri_id=5, mesaj="5 numaralı siparişimi iptal etmek istiyorum")
    ext = _ext([Intent.SIPARIS_DURUMU], siparis_no=[5])

    decision = decide(msg, ext, kb)
    assert decision.aksiyon == Action.HUMAN_ESCALATION
    assert decision.oncelik == Priority.P1
    assert decision.ekip == "destek"

    reply = build_reply(msg, ext, decision, kb)
    for kelime in ("kargoda", "YK3000000005", "Takip numarası"):
        assert kelime not in reply


def test_owned_order_status_question_still_auto_reply():
    kb = _kb()
    msg = _msg(musteri_id=5, mesaj="5 numaralı siparişim ne zaman gelir?")
    ext = _ext([Intent.SIPARIS_DURUMU], siparis_no=[5])

    decision = decide(msg, ext, kb)
    assert decision.aksiyon == Action.AUTO_REPLY
    assert decision.oncelik == Priority.P2

    reply = build_reply(msg, ext, decision, kb)
    assert "kargoda" in reply


# --- §B: ürün eşleşti ama tanınan alan sorulmuyorsa uydurulmaz --------------

def test_paraben_question_unknown_field_escalates_to_urun():
    kb = _kb()
    msg = _msg(musteri_id=9, mesaj="Tonikte paraben var mı?")
    ext = _ext([Intent.URUN_BILGISI], urun=["tonik"])

    decision = decide(msg, ext, kb)
    assert decision.aksiyon == Action.HUMAN_ESCALATION
    assert decision.ekip == "urun"
    assert "sorulan ürün bilgisi veride yok/tanınmadı → ürün ekibi" in decision.gerekceler


# --- §C: politika alt-konusu hayvan testiyle karışmaz -----------------------

def test_vegan_only_question_is_human():
    kb = _kb()
    msg = _msg(musteri_id=1, mesaj="Vegan mısınız?")
    ext = _ext([Intent.POLITIKA])

    decision = decide(msg, ext, kb)
    assert decision.aksiyon == Action.HUMAN_ESCALATION
    assert decision.ekip == "destek"
    assert "politika:vegan" in decision.eksik_bilgiler


def test_hayvan_testi_question_is_auto_when_policy_known():
    kb = _kb()
    msg = _msg(musteri_id=11, mesaj="Ürünleriniz hayvanlar üzerinde test ediliyor mu?")
    ext = _ext([Intent.POLITIKA])

    decision = decide(msg, ext, kb)
    assert decision.aksiyon == Action.AUTO_REPLY


def test_vegan_and_animals_en_message_is_human_but_keeps_animal_sentence():
    kb = _kb()
    msg = _msg(musteri_id=28, mesaj="Hi, are your products vegan and cruelty-free? Do you test on animals?")
    ext = Extraction(dil="en", intents=[Intent.POLITIKA], entities=Entities())

    decision = decide(msg, ext, kb)
    assert decision.aksiyon == Action.HUMAN_ESCALATION
    assert decision.ekip == "destek"
    assert "politika:vegan" in decision.eksik_bilgiler

    reply = build_reply(msg, ext, decision, kb)
    assert "not tested on animals" in reply


# --- §D: spam + gerçek talep birlikteyse karantinaya atılmaz -----------------

def test_spam_with_real_intent_is_human_not_quarantine():
    kb = _kb()
    msg = _msg(musteri_id=4, mesaj="Takipçi kasmak ister misiniz? Güneş kreminin fiyatı ne kadar?")
    ext = _ext([Intent.SPAM, Intent.FIYAT], urun=["gunes_kremi_spf50"])

    decision = decide(msg, ext, kb)
    assert decision.aksiyon == Action.HUMAN_ESCALATION
    assert "spam işareti var ama gerçek bir talep de var → insan" in decision.gerekceler


# --- §E: EN sağlık yanıtı Türkçe harf içermez, cilt tipi cümlesi tekrarsız --

def test_saglik_en_reply_has_no_turkish_letters():
    kb = _kb()
    msg = _msg(musteri_id=14, mesaj="I used the serum yesterday, my face burned and turned red.")
    ext = Extraction(dil="en", intents=[Intent.SAGLIK_SIKAYETI], entities=Entities())

    reply = build_reply(msg, ext, decide(msg, ext, kb), kb)
    turkce_harfler = set("çğıöşüİ")
    assert not (turkce_harfler & set(reply))


def test_cilt_tipi_cumlesi_kelime_tekrari_yok():
    kb = _kb()
    msg = _msg(musteri_id=1, mesaj="Güneş kremi hangi cilt tipine uygun?")
    ext = _ext([Intent.URUN_BILGISI], urun=["gunes_kremi_spf50"])
    reply = build_reply(msg, ext, decide(msg, ext, kb), kb)
    assert "cilt tipleri cilt tipleri" not in reply
    assert "tüm cilt tipleri için uygundur" in reply

    msg2 = _msg(musteri_id=1, mesaj="Retinol serum hangi cilt tipine uygun?")
    ext2 = _ext([Intent.URUN_BILGISI], urun=["retinol_serum"])
    reply2 = build_reply(msg2, ext2, decide(msg2, ext2, kb), kb)
    assert "normal, kuru ve karma ciltler için uygundur" in reply2


# --- İkinci hakem bulguları -------------------------------------------------

def test_hamilelik_sorusu_tibbi_soru_kalite_ekibine_gider():
    """§1 BLOKER: hamilelik/tıbbi uygunluk cilt tipi sorusu SANILMAZ."""
    kb = _kb()
    msg = _msg(musteri_id=20, mesaj="Retinol hamilelikte uygun mu?")
    ext = _ext([Intent.URUN_BILGISI], urun=["retinol_serum"])

    decision = decide(msg, ext, kb)
    assert decision.aksiyon == Action.HUMAN_ESCALATION
    assert decision.oncelik == Priority.P2
    assert decision.ekip == "kalite"

    reply = build_reply(msg, ext, decision, kb)
    assert "uygundur" not in reply


def test_kargo_ucret_sorusu_missing_fee_escalates():
    """§2: taşıyıcı/süre paylaşılır ama ücret veride yok → devir."""
    kb = _kb()
    msg = _msg(musteri_id=6, mesaj="Kargo ücreti ne kadar?")
    ext = _ext([Intent.KARGO_BILGISI])

    decision = decide(msg, ext, kb)
    assert decision.aksiyon == Action.HUMAN_ESCALATION
    assert decision.ekip == "destek"
    assert "politika:kargo:ucret" in decision.eksik_bilgiler

    reply = build_reply(msg, ext, decision, kb)
    assert "Yurtiçi Kargo" in reply
    assert "teyit" in reply


def test_iade_hasarsiz_normal_return_uses_sure_gun_not_damaged_text():
    """§3: hasar kelimesi yoksa (ör. "hasarsız") sıradan iade metni kullanılır."""
    kb = _kb()
    msg = _msg(musteri_id=30, mesaj="Ürünü beğenmedim, iade etmek istiyorum, kutu hasarsız duruyor.")
    ext = _ext([Intent.IADE_HASAR])

    decision = decide(msg, ext, kb)
    assert decision.aksiyon == Action.HUMAN_ESCALATION
    assert decision.oncelik == Priority.P1
    assert decision.ekip == "iade"

    reply = build_reply(msg, ext, decision, kb)
    assert "14" in reply
    assert "ücretsiz değişim" not in reply


def test_pipeline_forces_siparis_durumu_when_extractor_omits_it():
    """§5: extractor sipariş no bulup SIPARIS_DURUMU niyetini atlarsa, güvenlik
    katmanı niyeti zorla ekler — sahiplik doğrulaması ATLANAMAZ."""
    from triage.pipeline import process

    kb = _kb()

    def eksik_extractor(msg, kb):
        return Extraction(dil="tr", intents=[], entities=Entities(siparis_no=[], urun=[]))

    msg = Message(id=99, kanal="whatsapp", musteri_id=7, mesaj="12 numaralı siparişim nerede?")
    result = process(msg, kb, extractor=eksik_extractor)

    assert "siparis_durumu" in result.intents
    assert result.aksiyon == "needs_verification"  # 12, m7'ye ait değil


def test_owned_order_missing_durum_needs_verification_no_none_leak():
    """§6: "durum" alanı None ise auto_reply verilmez, "None" asla basılmaz."""
    siparisler = [{"siparis_no": 50, "musteri_id": 40, "durum": None}]
    kb = KnowledgeBase(siparisler=siparisler, urunler=[], politikalar={})
    msg = _msg(musteri_id=40, mesaj="50 numaralı siparişim nerede?")
    ext = _ext([Intent.SIPARIS_DURUMU], siparis_no=[50])

    decision = decide(msg, ext, kb)
    assert decision.aksiyon == Action.NEEDS_VERIFICATION
    assert "siparis:50:durum" in decision.eksik_bilgiler

    reply = build_reply(msg, ext, decision, kb)
    assert "None" not in reply


def test_asked_product_fields_stok_without_var_mi():
    from triage.decide import asked_product_fields
    from triage.text import fold

    assert asked_product_fields(fold("Tonik stokta mı?")) == {"stokta"}


# --- ikinci inceleme turundan kalan karşı örnekler (uçtan uca, pipeline üzerinden) ---

def _uc(musteri_id: int, mesaj: str):
    from triage.pipeline import process

    return process(Message(id=0, kanal="whatsapp", musteri_id=musteri_id, mesaj=mesaj), KnowledgeBase.load())


def test_urune_bagli_olmayan_var_mi_stok_sorusu_degil():
    r = _uc(1, "Tonik peeling var mı?")
    assert r.aksiyon != "auto_reply"
    assert "stoklarımızda" not in (r.yanit_taslagi or "")
    assert _uc(1, "Retinol serumunuz var mı?").aksiyon == "auto_reply"


def test_hediye_paketi_sorusu_karantinaya_dusmez():
    r = _uc(1, "Hediye paketi yapıyor musunuz? nurederm.com")
    assert r.aksiyon != "quarantine"


def test_yalniz_bilinmeyen_politika_sorusunda_diger_nokta_denmez():
    r = _uc(1, "Ürünleriniz dermatolojik olarak test edildi mi?")
    assert r.aksiyon == "human_escalation"
    assert "diğer" not in r.yanit_taslagi


# --- son (Fable) inceleme turu karşı örnekleri ---

def test_sahibin_geldi_mi_sorusu_otomatik_cevaplanir():
    r = _uc(5, "5 numaralı siparişim geldi mi?")
    assert r.aksiyon == "auto_reply"
    assert "YK3000000005" in r.yanit_taslagi


def test_takip_calismiyor_sikayeti_otomatige_dusmez():
    r = _uc(5, "Takip numaram çalışmıyor, 5 numaralı siparişim görünmüyor")
    assert r.aksiyon != "auto_reply"


def test_sahibi_olmayan_sipariste_celiskili_taslak_yok():
    r = _uc(3, "Hello, can you check order #12")
    assert r.aksiyon == "needs_verification"
    assert "YK3000000012" not in r.yanit_taslagi
    assert "request" not in r.yanit_taslagi.lower() or "couldn't find" in r.yanit_taslagi


def test_turkce_karaktersiz_turkce_mesaj_ingilizce_sanilmaz():
    r = _uc(5, "Merhaba, 5 numarali siparisim 3 is gunu icinde gelir dediniz, on gun oldu")
    assert r.dil == "tr"


def test_ingilizce_saglik_sikayeti_acil():
    for mesaj in ("hi my skin is peeling after using the toner",
                  "the toner made my face red and it stings"):
        assert _uc(1, mesaj).oncelik == "P0", mesaj


def test_telefon_numarasi_siparis_sanilmaz_ama_hatali_urun_siparisi_kaybolmaz():
    from triage.classify import extract_order_numbers

    assert extract_order_numbers("05321234567 numaralı telefonumdan arayın") == []
    assert extract_order_numbers("5 numaralı hatalı ürün geldi") == [5]
