"""Kural tabanlı sınıflandırıcı: mesajı ANLAR, olgu bilmez.

Akış: detect_language / extract_* / match_products / safety_intents birer küçük
kural katmanıdır; classify() bunları birleştirip Extraction üretir. Her intent
kararının bir gerekçesi vardır (audit satırı) — decide() bunu olduğu gibi taşır.
"""
from __future__ import annotations

import re

from .knowledge import KnowledgeBase
from .models import Entities, Extraction, Intent, Message
from .text import fold

# --- dil ---

_EN_STOPWORDS = {"where", "my", "order", "is", "the", "hi", "has", "been", "week", "it"}
_TR_CHARS = set("çğıöşüİı")


def detect_language(text: str) -> str:
    """Türkçe'ye özgü harf varsa doğrudan "tr"; yoksa İngilizce stopword sayımına bak.

    Türkçe metinde çğıöşüİı harfleri sık geçer, İngilizcede hiç geçmez — bu yüzden
    onları görmek stopword sayımından daha güvenilir bir ilk kontrol.
    """
    if any(ch in _TR_CHARS for ch in text):
        return "tr"
    words = re.findall(r"[a-zA-Z']+", text.lower())
    hits = sum(1 for w in words if w in _EN_STOPWORDS)
    return "en" if hits >= 2 else "tr"


# --- sipariş numarası ---

# Her desenin bir de kısa TR etiketi var: classify() bunu gerekçe satırında kullanır.
_ORDER_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(\d+)\s*numarali"), "'numaralı' kalıbı"),
    (re.compile(r"(\d+)\s*nolu"), "'nolu' kalıbı"),
    (re.compile(r"siparis\s*(?:no\b|numarasi\b)?\s*:?\s*#?\s*(\d+)"), "'sipariş no' kalıbı"),
    (re.compile(r"order\s*#?\s*(\d+)"), "'order' kalıbı"),
    (re.compile(r"#\s*(\d+)"), "'#' kalıbı"),
]

# Sayı bu birimlerden biriyle bitişikse sipariş no DEĞİLDİR ("200 ml", "%100").
_UNIT_SUFFIX = re.compile(r"^\s*(ml|gr|mg|g|tl|lira|%)\b")


def _find_order_candidates(folded: str) -> list[tuple[int, int, str]]:
    """(pozisyon, sayı, desen-etiketi) — birim/yüzde önek-sonekli sahte eşleşmeler elenir."""
    candidates: list[tuple[int, int, str]] = []
    for pattern, label in _ORDER_PATTERNS:
        for m in pattern.finditer(folded):
            start, end = m.span(1)
            if start > 0 and folded[start - 1] == "%":
                continue  # "%100" gibi yüzde öneki sipariş no değildir
            if _UNIT_SUFFIX.match(folded[end:]):
                continue  # "200 ml" gibi birim soneki sipariş no değildir
            candidates.append((start, int(m.group(1)), label))
    candidates.sort(key=lambda c: c[0])
    return candidates


def extract_order_numbers(text: str) -> list[int]:
    folded = fold(text)
    ordered: list[int] = []
    for _, number, _ in _find_order_candidates(folded):
        if number not in ordered:
            ordered.append(number)
    return ordered


# --- link ---

_URL_PATTERN = re.compile(
    r"https?://\S+|www\.\S+|\b[a-z0-9-]+\.(?:ly|com|net|org|co|io|me|tr)/\S+",
    re.IGNORECASE,
)


def extract_urls(text: str) -> list[str]:
    urls: list[str] = []
    for m in _URL_PATTERN.finditer(text):
        url = m.group(0).rstrip(".,;:!?)")
        if url not in urls:
            urls.append(url)
    return urls


# --- ürün eşleştirme ---


def match_products(text: str, kb: KnowledgeBase) -> list[str]:
    """Takma ad, katlanmış metinde sol kelime sınırıyla geçiyorsa ürün eşleşti sayılır.

    Sağ tarafta sınır ARANMAZ: "güneş kremi" -> "gunes kremi", Türkçe çekim eki
    ("kreminin") eklenmiş olsa da eşleşsin diye.
    """
    folded_text = fold(text)
    hits: list[tuple[int, str]] = []
    for slug, aliases in kb.product_aliases().items():
        for alias in aliases:
            pattern = re.compile(r"(?<![a-z0-9])" + re.escape(fold(alias)))
            m = pattern.search(folded_text)
            if m:
                hits.append((m.start(), slug))
                break
    hits.sort(key=lambda h: h[0])
    ordered: list[str] = []
    for _, slug in hits:
        if slug not in ordered:
            ordered.append(slug)
    return ordered


# --- güvenlik (sağlık şikâyeti) katmanı — LLM modunda da bağımsız çalışır ---

_SAFETY_STEMS = [
    "yand", "kizar", "kasin", "kasint", "sisl", "sisti", "alerji", "reaksiyon",
    "dokuntu", "tahris", "kabar", "yan etki",
    "burn", "rash", "itch", "allerg", "swell", "irritat", "reaction",
]


def safety_intents(text: str) -> set[Intent]:
    folded = fold(text)
    if any(stem in folded for stem in _SAFETY_STEMS):
        return {Intent.SAGLIK_SIKAYETI}
    return set()


# --- niyet anahtar kelimeleri (sınıflandırma) ---

_PROMO_WORDS = ["takipci", "takip", "organik", "kazan", "tikla", "bedava", "followers"]
_STRONG_SPAM_PHRASES = ["takipci kas"]
_IADE_WORDS = ["iade", "ezik", "hasar", "kirik", "bozuk", "degisim", "return", "damaged", "broken"]
_SIPARIS_STATUS_WORDS = ["nerede", "durum", "ne zaman", "gelir", "ulasmadi", "kargoya"]
_KARGO_PHRASES = ["hangi kargo", "kargo firma", "kargo ucret", "kac gunde", "shipping company"]
_INDIRIM_WORDS = ["indirim", "kod", "kupon", "promosyon", "discount", "coupon"]
_URUN_BILGISI_WORDS = [
    "var mi", "icerik", "icerig", "alkol", "cilt", "kuru", "yagli", "karma",
    "hassas", "uygun", "kullanilir mi",
]
_ML_PATTERN = re.compile(r"\d+\s*ml")
_POLITIKA_WORDS = ["hayvan", "test edil", "cruelty", "vegan"]


def classify(msg: Message, kb: KnowledgeBase) -> Extraction:
    folded = fold(msg.mesaj)
    dil = detect_language(msg.mesaj)
    siparis_no = extract_order_numbers(msg.mesaj)
    urun = match_products(msg.mesaj, kb)
    url = extract_urls(msg.mesaj)
    entities = Entities(siparis_no=siparis_no, urun=urun, url=url)

    intents: list[Intent] = []
    gerekceler: list[str] = []

    def add(intent: Intent, reason: str) -> None:
        # Aynı intent için ilk gerekçe kalır; tekrarları çoğaltmaz.
        if intent not in intents:
            intents.append(intent)
            gerekceler.append(reason)

    # SPAM: link + tanıtım kelimesi, ya da tek başına güçlü kalıp ("takipçi kas...")
    promo_hit = next((w for w in _PROMO_WORDS if w in folded), None)
    strong_hit = next((p for p in _STRONG_SPAM_PHRASES if p in folded), None)
    if url and promo_hit:
        add(Intent.SPAM, "kural: link + tanıtım kelimesi → spam")
    elif strong_hit:
        add(Intent.SPAM, f"kural: güçlü spam kalıbı '{strong_hit}'")

    # SAGLIK_SIKAYETI: bağımsız güvenlik katmanından gelir
    if safety_intents(msg.mesaj):
        stem = next(s for s in _SAFETY_STEMS if s in folded)
        add(Intent.SAGLIK_SIKAYETI, f"kural: sağlık anahtar kelimesi '{stem}'")

    # IADE_HASAR
    iade_hit = next((w for w in _IADE_WORDS if w in folded), None)
    if iade_hit:
        add(Intent.IADE_HASAR, f"kural: iade/hasar anahtar kelimesi '{iade_hit}'")

    # SIPARIS_DURUMU: sipariş no varsa, ya da "sipariş" + durum kelimesi, ya da EN "order"
    has_status_word = any(w in folded for w in _SIPARIS_STATUS_WORDS)
    is_en_order = dil == "en" and "order" in folded
    if siparis_no:
        add(Intent.SIPARIS_DURUMU, f"kural: sipariş no {siparis_no[0]} ({_find_order_candidates(folded)[0][2]})")
    elif ("siparis" in folded and has_status_word) or is_en_order:
        add(Intent.SIPARIS_DURUMU, "kural: sipariş durumu ifadesi")

    # KARGO_BILGISI: sipariş no YOKKEN genel kargo sorusu
    kargo_hit = next((p for p in _KARGO_PHRASES if p in folded), None)
    if not siparis_no and kargo_hit:
        add(Intent.KARGO_BILGISI, f"kural: kargo bilgisi kalıbı '{kargo_hit}'")

    # FIYAT
    has_ucret = "ucret" in folded and "kargo ucret" not in folded
    if "fiyat" in folded or "ne kadar" in folded or "kac tl" in folded or "price" in folded or has_ucret:
        add(Intent.FIYAT, "kural: fiyat anahtar kelimesi")

    # INDIRIM
    indirim_hit = next((w for w in _INDIRIM_WORDS if w in folded), None)
    if indirim_hit:
        add(Intent.INDIRIM, f"kural: indirim anahtar kelimesi '{indirim_hit}'")

    # URUN_BILGISI: ürün eşleşmesi ZORUNLU + destekleyici kelime/"<n> ml"
    urun_kw_hit = next((w for w in _URUN_BILGISI_WORDS if w in folded), None)
    if urun and (urun_kw_hit or _ML_PATTERN.search(folded)):
        add(Intent.URUN_BILGISI, f"kural: ürün eşleşti + '{urun_kw_hit or 'ml miktarı'}'")

    # POLITIKA
    politika_hit = next((w for w in _POLITIKA_WORDS if w in folded), None)
    if politika_hit:
        add(Intent.POLITIKA, f"kural: politika anahtar kelimesi '{politika_hit}'")

    # BILINMIYOR: hiçbir kural tutmadıysa
    if not intents:
        add(Intent.BILINMIYOR, "kural: hiçbir niyet kalıbı eşleşmedi")

    return Extraction(dil=dil, intents=intents, entities=entities, gerekceler=gerekceler)
