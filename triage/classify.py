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

_EN_STOPWORDS = {
    "where", "my", "order", "is", "the", "hi", "has", "been", "week", "it",
    "how", "what", "when", "does", "do", "you", "your", "are", "a", "to", "for", "and", "of", "can", "on",
}
_TR_CHARS = set("çğıöşüİı")


def detect_language(text: str) -> str:
    """Türkçe'ye özgü harf varsa doğrudan "tr"; yoksa İngilizce stopword sayımına bak.

    Türkçe metinde çğıöşüİı harfleri sık geçer, İngilizcede hiç geçmez — bu yüzden
    onları görmek stopword sayımından daha güvenilir bir ilk kontrol.
    ⚠️ İSTİSNA: metinde bir özel ad yüzünden tek bir Türkçe harf geçse de
    (ör. "Hi, I'm Gökhan, where is my order #3?") 3+ İngilizce stopword yeterince
    güçlü bir sinyaldir — Türkçe harf kontrolünden ÖNCE bakılır.
    """
    words = re.findall(r"[a-zA-Z']+", text.lower())
    hits = sum(1 for w in words if w in _EN_STOPWORDS)
    if hits >= 3:
        return "en"
    if any(ch in _TR_CHARS for ch in text):
        return "tr"
    return "en" if hits >= 2 else "tr"


# --- sipariş numarası ---

# Her desenin bir de kısa TR etiketi var: classify() bunu gerekçe satırında kullanır.
_ORDER_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(\d+)\s*numarali"), "'numaralı' kalıbı"),
    (re.compile(r"(\d+)\s*no['’]?lu"), "'nolu' kalıbı"),
    (re.compile(r"siparis\s*(?:no\b|numarasi\b)?\s*:?\s*#?\s*(\d+)"), "'sipariş no' kalıbı"),
    (re.compile(r"siparis\w*\s*numara\w*\s*:?\s*#?\s*(\d+)"), "'sipariş numaram' kalıbı"),
    (re.compile(r"order\s*(?:number|no\.?)?\s*#?\s*(\d+)"), "'order' kalıbı"),
    (re.compile(r"#\s*(\d+)"), "'#' kalıbı"),
]

# "3 ve 12 numaralı siparişlerim" / "3, 12 numaralı" gibi tek kalıba bağlı birden
# çok sayı — grup(1) tüm sayı listesini taşır, tek tek ayıklanır.
_ORDER_LIST_PATTERN = re.compile(r"(\d+(?:\s*(?:ve|,)\s*\d+)+)\s*numarali")

# Sayı bu birimlerden biriyle bitişikse sipariş no DEĞİLDİR ("200 ml", "%100").
_UNIT_SUFFIX = re.compile(r"^\s*(ml|gr|mg|g|tl|lira|%)\b")
# "3 gün önce", "2 hafta", "5 days" gibi süre/adet ifadeleri sipariş no değildir.
_TIME_QTY_SUFFIX = re.compile(r"^\s*(gun\w*|hafta\w*|ay\w*|saat\w*|adet\w*|tane\w*|days?\b|weeks?\b|bottles?\b)")
# "67 numaralı telefon/hat/oda/kapı" — sipariş değil, başka bir referans numarası.
_REF_SUFFIX = re.compile(r"^\s*(telefon|hat|oda|kapi)\b")
# "3.5" / "3,500" gibi ondalık/basamak ayraçlı sayının tam hâli sipariş no değildir.
_DECIMAL_SUFFIX = re.compile(r"^[.,]\d")


def _find_order_candidates(folded: str) -> list[tuple[int, int, str]]:
    """(pozisyon, sayı, desen-etiketi) — birim/yüzde/süre/referans önek-sonekli sahte eşleşmeler elenir."""
    candidates: list[tuple[int, int, str]] = []
    for m in _ORDER_LIST_PATTERN.finditer(folded):
        base = m.start(1)
        for nm in re.finditer(r"\d+", m.group(1)):
            candidates.append((base + nm.start(), int(nm.group()), "sayı listesi + 'numaralı' kalıbı"))
    for pattern, label in _ORDER_PATTERNS:
        for m in pattern.finditer(folded):
            start, end = m.span(1)
            if start > 0 and folded[start - 1] == "%":
                continue  # "%100" gibi yüzde öneki sipariş no değildir
            if folded[end:end + 1] == "%":
                continue  # "100%" gibi yüzde soneki de sipariş no değildir
            if _UNIT_SUFFIX.match(folded[end:]):
                continue  # "200 ml" gibi birim soneki sipariş no değildir
            if _TIME_QTY_SUFFIX.match(folded[end:]):
                continue  # "3 gün önce" gibi süre/adet soneki sipariş no değildir
            if _DECIMAL_SUFFIX.match(folded[end:]):
                continue  # "3.5" gibi ondalık sayının tam sayı kısmı sipariş no değildir
            if _REF_SUFFIX.match(folded[m.end():]):
                continue  # "numaralı telefon/hat/oda/kapı" sipariş no değildir
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
    r"https?://\S+|www\.\S+|\b[a-z0-9-]+\.(?:ly|com|net|org|co|io|me|tr|tk|xyz|info|biz)\b(?:/\S*)?",
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
            # Sağda da sınır: "spf" alias'ı "spf30" gibi başka bir sayı-varyantına
            # yapışmasın diye hemen ardından gelen rakamı reddeder ("spf50" -> alias
            # "spf" zaten kendi ürününe ait olduğu için buna takılmaz, ayrım rakamla).
            pattern = re.compile(r"(?<![a-z0-9])" + re.escape(fold(alias)) + r"(?![0-9])")
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

# Düz alt-dizge yerine kelime sınırlı regex: "Şişli"/"yandan"/"yandex"/"burnu"/
# "kabarık saç"/"switch"/"kitchen"/"crash"/"trash" gibi masum kelimelerin içine
# sızmasın. Her kalıp katlanmış (fold edilmiş) metne uygulanır.
_SAFETY_PATTERNS: list[re.Pattern[str]] = [re.compile(p) for p in [
    r"\byan(di|dim|iyor|ik|ma|mis)",
    r"\bkizar(di|ik|ma|mis|iyor)",
    r"\bkasin",
    r"\bkasint",
    r"\bsis(lik|ti|me|mis|kin)",
    r"\bkabar(cik|di|ma|ti)",
    r"alerji",
    r"reaksiyon",
    r"dokuntu",
    r"tahris",
    r"yan etki",
    r"\bsoyul",
    r"pul pul",
    r"sivilce",
    r"egzama",
    r"iltihap",
    r"leke olus",
    r"lekelen",
    r"\bburn(ing|ed|s|t)?\b",
    r"\brash(es)?\b",
    r"\bitch(y|ing|es)?\b",
    r"\ballerg",
    r"\bswell",
    r"\birritat",
    r"\breaction",
    r"\bhives\b",
    r"\bblister",
    # "peeling" KASITLI YOK: "Tonik peeling var mı?" bir ürün türüdür, semptom değil
    # (2. hakem bulgusu) — TR karşılığı "soyul" zaten yukarıda ayrı kalıp.
]]


def safety_intents(text: str) -> set[Intent]:
    folded = fold(text)
    if any(p.search(folded) for p in _SAFETY_PATTERNS):
        return {Intent.SAGLIK_SIKAYETI}
    return set()


# --- niyet anahtar kelimeleri (sınıflandırma) ---

# "hediye" bilerek YOK: "Hediye paketi yapıyor musunuz?" gerçek bir müşteri sorusu, karantinaya düşmemeli.
_PROMO_WORDS = ["takipci", "organik", "kazan", "tikla", "bedava", "followers", "bonus"]
# Link olmadan da spam sayılan kalıplar (dolandırıcılık / çekiliş dili)
_STRONG_SPAM_PHRASES = [
    "takipci kas", "kazandiniz", "katina cikar", "kripto", "bitcoin",
    "you won", "you have won", "free gift", "claim it", "click here",
]
_IADE_WORDS = ["iade", "ezik", "hasar", "kirik", "bozuk", "degisim", "return", "damaged", "broken"]
_SIPARIS_STATUS_WORDS = ["nerede", "nerde", "durum", "ne zaman", "gelir", "gelmedi", "ulasmadi", "kargoya"]
# "sipariş" kelimesi geçmese de siparişe gönderme yapan ifadeler ("kargom gelmedi")
_SIPARIS_REF_WORDS = ["siparis", "kargom", "paketim"]
# Belirsiz/tek başına kalıplar ("hangi kargo firması" gibi) — bağlam gerektirmez.
_KARGO_PHRASES = [
    "hangi kargo", "kargo firma", "kargo ucret", "shipping company",
    "shipping take", "delivery take", "how long does shipping",
]
# "kaç gün(de)" yalnız kargo/teslimat bağlamında sayılır — aksi halde "Retinolü kaç
# gün kullanmalıyım?" ya da "İade süresi kaç gün?" yanlışlıkla kargo_bilgisi olur.
_KARGO_GUN_PATTERN = re.compile(r"\bkac gun(de)?\b")
_KARGO_CONTEXT_WORDS = ["kargo", "teslim", "gelir", "ulasir", "shipping", "delivery"]
# "Kargo ne kadar sürer?" bir süre sorusudur, FIYAT değil — aynı kalıp fiyatta hariç tutulur.
_SURE_SORUSU = re.compile(r"ne kadar\s*sur")
# "How many days does shipping usually take?" -> shipping + take/days birlikte kargo demektir.
_EN_SURE_KELIME = re.compile(r"\b(take|takes|days)\b")
_INDIRIM_WORDS = ["indirim", "kupon", "promosyon", "discount", "coupon"]
_URUN_BILGISI_WORDS = [
    "var mi", "icerik", "icerig", "alkol", "cilt", "kuru", "yagli", "karma",
    "hassas", "uygun", "kullanilir mi", "kac ml", "stok",
]
_ML_PATTERN = re.compile(r"\d+\s*ml")
# "kodunuz var mı" gibi başka bir şeye bağlı "var mı" ürün sorusu değildir
_BAGLI_VAR_MI = re.compile(r"(kod|kupon|indirim|kampanya)\w*\s+var mi")
# Katalogda olmayan ama ürün sorusu olduğu belli ifadeler ("saç serumunuz var mı")
_URUN_KATEGORI_WORDS = ["serum", "krem", "sampuan", "maske", "losyon", "sabun", "parfum"]
_POLITIKA_WORDS = ["hayvan", "test edil", "cruelty", "vegan", "test on animals"]


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
        hit = next(m.group(0) for p in _SAFETY_PATTERNS if (m := p.search(folded)))
        add(Intent.SAGLIK_SIKAYETI, f"kural: sağlık anahtar kelimesi '{hit}'")

    # IADE_HASAR
    iade_hit = next((w for w in _IADE_WORDS if w in folded), None)
    if iade_hit:
        add(Intent.IADE_HASAR, f"kural: iade/hasar anahtar kelimesi '{iade_hit}'")

    # SIPARIS_DURUMU: sipariş no varsa, ya da "sipariş" + durum kelimesi, ya da EN "order"
    has_status_word = any(w in folded for w in _SIPARIS_STATUS_WORDS)
    has_order_ref = any(w in folded for w in _SIPARIS_REF_WORDS)
    is_en_order = dil == "en" and "order" in folded
    if siparis_no:
        add(Intent.SIPARIS_DURUMU, f"kural: sipariş no {siparis_no[0]} ({_find_order_candidates(folded)[0][2]})")
    elif (has_order_ref and has_status_word) or is_en_order:
        add(Intent.SIPARIS_DURUMU, "kural: sipariş durumu ifadesi")

    # KARGO_BILGISI: sipariş no YOKKEN genel kargo sorusu
    kargo_context = any(w in folded for w in _KARGO_CONTEXT_WORDS)
    kargo_phrase_hit = next((p for p in _KARGO_PHRASES if p in folded), None)
    kargo_gun_hit = "'kaç gün' + kargo bağlamı" if (_KARGO_GUN_PATTERN.search(folded) and kargo_context) else None
    kargo_sure_hit = "'ne kadar sürer' + kargo bağlamı" if (_SURE_SORUSU.search(folded) and kargo_context) else None
    kargo_en_hit = "shipping + take/days" if ("shipping" in folded and _EN_SURE_KELIME.search(folded)) else None
    kargo_hit = kargo_phrase_hit or kargo_gun_hit or kargo_sure_hit or kargo_en_hit
    if not siparis_no and kargo_hit:
        add(Intent.KARGO_BILGISI, f"kural: kargo bilgisi kalıbı '{kargo_hit}'")

    # FIYAT: "ne kadar sürer/sürede" bir süre sorusudur, fiyat değil (KARGO_BILGISI'ne bırakılır)
    has_ucret = "ucret" in folded and "kargo ucret" not in folded
    has_ne_kadar = "ne kadar" in folded and not _SURE_SORUSU.search(folded)
    fiyat_kaliplari = ("fiyat", "kac tl", "kac para", "price", "how much")
    if any(k in folded for k in fiyat_kaliplari) or has_ne_kadar or has_ucret:
        add(Intent.FIYAT, "kural: fiyat anahtar kelimesi")

    # INDIRIM
    indirim_hit = next((w for w in _INDIRIM_WORDS if w in folded), None)
    if indirim_hit:
        add(Intent.INDIRIM, f"kural: indirim anahtar kelimesi '{indirim_hit}'")

    # URUN_BILGISI: ürün eşleşmesi ZORUNLU + destekleyici kelime/"<n> ml"
    urun_metni = _BAGLI_VAR_MI.sub("", folded)
    urun_kw_hit = next((w for w in _URUN_BILGISI_WORDS if w in urun_metni), None)
    if urun and (urun_kw_hit or _ML_PATTERN.search(folded)):
        add(Intent.URUN_BILGISI, f"kural: ürün eşleşti + '{urun_kw_hit or 'ml miktarı'}'")
    elif not urun and urun_kw_hit and any(k in folded for k in _URUN_KATEGORI_WORDS) and not safety_intents(msg.mesaj):
        # Katalogda olmayan ürün soruluyor: karar katmanı "hangi ürün?" diye doğrulama ister
        add(Intent.URUN_BILGISI, f"kural: katalog dışı ürün sorusu + '{urun_kw_hit}'")

    # POLITIKA
    politika_hit = next((w for w in _POLITIKA_WORDS if w in folded), None)
    if politika_hit:
        add(Intent.POLITIKA, f"kural: politika anahtar kelimesi '{politika_hit}'")

    # BILINMIYOR: hiçbir kural tutmadıysa
    if not intents:
        add(Intent.BILINMIYOR, "kural: hiçbir niyet kalıbı eşleşmedi")

    return Extraction(dil=dil, intents=intents, entities=entities, gerekceler=gerekceler)
