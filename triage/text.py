"""Türkçe metin normalizasyonu."""
from __future__ import annotations

_ASCII = str.maketrans({"ı": "i", "ş": "s", "ğ": "g", "ü": "u", "ö": "o", "ç": "c", "â": "a", "î": "i", "û": "u"})


def fold(text: str) -> str:
    """Türkçe kurallarla küçült, sonra ASCII'ye indir.

    "İndirim" -> "indirim", "IŞIK" -> "isik", "güneş" -> "gunes".
    Müşteri Türkçe karakter kullansa da kullanmasa da aynı anahtar kelimeyle eşleşir.
    """
    lowered = text.replace("İ", "i").replace("I", "ı").lower()
    return lowered.translate(_ASCII)
