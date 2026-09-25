"""Türkçe metin normalizasyonu."""
from __future__ import annotations

import unicodedata

_ASCII = str.maketrans({"ı": "i", "ş": "s", "ğ": "g", "ü": "u", "ö": "o", "ç": "c", "â": "a", "î": "i", "û": "u"})


def fold(text: str) -> str:
    """Türkçe kurallarla küçült, sonra ASCII'ye indir.

    "İndirim" -> "indirim", "IŞIK" -> "isik", "güneş" -> "gunes".
    Müşteri Türkçe karakter kullansa da kullanmasa da aynı anahtar kelimeyle eşleşir.
    """
    # Bazı kaynaklar "İ" harfini ayrıştırılmış biçimde yollar (I + üstüne nokta,
    # U+0307): NFC bunu tek karaktere ("İ") geri birleştirir, aksi halde alttaki
    # replace() hiçbir şeyi yakalayamaz.
    text = unicodedata.normalize("NFC", text)
    lowered = text.replace("İ", "i").replace("I", "ı").lower()
    # NFC her kombinasyonu birleştiremez (ör. küçük "i" + U+0307 için tekil karakter
    # yok) — küçültmeden sonra kalan noktayı ayıkla.
    lowered = lowered.replace("̇", "")
    return lowered.translate(_ASCII)
