"""LLM tabanlı (opsiyonel) extractor: kural motoruna alternatif ANLAMA katmanı.

Sınır (katı): LLM yalnız dil + niyet + ürün slug çıkarır. Olgu (sipariş/fiyat/politika
metni) ÜRETMEZ ve GÖRMEZ, yanıt taslağı yazmaz. Çıktı JSON şema ile doğrulanır;
geçersiz/eksik/refuse/hata durumunda kural tabanlı classify()'a düşer (`llm_fallback`
gerekçesiyle) — pipeline.py'nin güvenlik katmanı bu düşüşten SONRA da aynen uygulanır.

`anthropic` opsiyonel bir bağımlılıktır: modül seviyesinde import edilmez, yalnız
`make_extractor()` içinde tembel (lazy) import edilir; paket yoksa sistem kural tabanlı çalışır.
"""
from __future__ import annotations

import json
import os
from typing import Any, Optional

from . import classify
from .knowledge import KnowledgeBase
from .models import Entities, Extraction, Intent, Message

SYSTEM_PROMPT = """Sen bir kozmetik markasının müşteri mesajı ANLAMA asistanısın.
Olgu üretmezsin; sipariş durumu, fiyat, politika metni BİLMEZSİN — yalnız mesajın
dilini, niyet(ler)ini ve geçen ürünlerin slug'ını çıkarırsın.

Niyetler (birden fazla geçerli olabilir, mesajda geçenlerin hepsini işaretle):
- siparis_durumu: sipariş nerede / ne zaman gelir, kargo takibi sorusu
- iade_hasar: hasarlı/bozuk/ezik ürün, iade veya değişim isteği
- saglik_sikayeti: kullanım sonrası yanma, kızarma, tahriş, alerji gibi cilt tepkisi
- urun_bilgisi: ürün içeriği, cilt tipine uygunluk, kullanım şekli sorusu
- fiyat: bir ürünün fiyatı, ne kadar tuttuğu
- indirim: indirim kodu, kupon, kampanya sorusu
- kargo_bilgisi: genel kargo firması/süresi/ücreti (belirli bir sipariş numarası OLMADAN)
- politika: hayvan testi, vegan içerik, iade süresi gibi şirket politikası sorusu
- spam: tanıtım, takipçi artırma, bağlantı yayma amaçlı istenmeyen mesaj
- bilinmiyor: yukarıdakilerden hiçbiri uymuyorsa

Ürün slug'ları SADECE sana verilen listeden seçilir; listede olmayan bir ürün adı
UYDURMA, eşleşen slug yoksa boş bırak.

Yalnız verilen JSON şemasına uyan bir nesne döndür, şema dışında hiçbir açıklama ekleme."""

# Şema, Intent enum'ından türetilir — iki liste ayrı elle tutulup sürüklenmesin.
OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "dil": {"type": "string", "enum": ["tr", "en"]},
        "intents": {
            "type": "array",
            "items": {"type": "string", "enum": [i.value for i in Intent]},
        },
        "urun": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["dil", "intents", "urun"],
    "additionalProperties": False,
}


class _FallbackNeeded(Exception):
    """LLM yanıtı geçersiz/eksik/refuse: kural tabanlı sınıflandırmaya düşülmeli."""


class LLMExtractor:
    """Anthropic modeliyle anlama katmanı; olgu bilmez, yalnız dil/niyet/ürün çıkarır."""

    def __init__(self, client: Any, model: str) -> None:
        self.client = client
        self.model = model

    def __call__(self, msg: Message, kb: KnowledgeBase) -> Extraction:
        try:
            return self._extract(msg, kb)
        except _FallbackNeeded as exc:
            return self._fallback(msg, kb, str(exc))
        except Exception as exc:  # SDK/ağ hatası, beklenmeyen şekil vb. — kör uygulama yok
            # Hata metni rapora yazılmaz (sağlayıcı ayrıntısı sızabilir); yalnız hata türü.
            return self._fallback(msg, kb, f"beklenmeyen hata ({type(exc).__name__})")

    def _extract(self, msg: Message, kb: KnowledgeBase) -> Extraction:
        slugs = list(kb.product_aliases().keys())
        response = self.client.messages.create(
            model=self.model,
            max_tokens=2000,
            system=SYSTEM_PROMPT,
            output_config={"effort": "low", "format": {"type": "json_schema", "schema": OUTPUT_SCHEMA}},
            messages=[{"role": "user", "content": f"Ürün listesi (slug): {slugs}\n\nMüşteri mesajı:\n{msg.mesaj}"}],
        )

        if getattr(response, "stop_reason", None) == "refusal":
            raise _FallbackNeeded("model reddetti (refusal)")

        text = next((b.text for b in response.content if getattr(b, "type", None) == "text"), None)
        if text is None:
            raise _FallbackNeeded("yanıtta metin bloğu yok")

        try:
            data = json.loads(text)
        except (json.JSONDecodeError, TypeError, ValueError):
            raise _FallbackNeeded("JSON ayrıştırılamadı")

        # Şemayı yerelde de tam doğrula: anahtarlar, tipler, enum değerleri. İhlal = kurallara düş.
        if not isinstance(data, dict) or set(data) != {"dil", "intents", "urun"}:
            raise _FallbackNeeded("şema ihlali (anahtarlar)")
        dil, raw_intents, raw_urun = data["dil"], data["intents"], data["urun"]
        if dil not in ("tr", "en"):
            raise _FallbackNeeded("şema ihlali (dil)")
        if not isinstance(raw_intents, list) or not isinstance(raw_urun, list):
            raise _FallbackNeeded("şema ihlali (tip)")
        gecerli = {i.value for i in Intent}
        if not raw_intents or any(r not in gecerli for r in raw_intents):
            raise _FallbackNeeded("şema ihlali (niyet)")
        intents: list[Intent] = list(dict.fromkeys(Intent(r) for r in raw_intents))

        notlar: list[str] = []
        known_slugs = kb.product_aliases()
        urun: list[str] = []
        for raw in raw_urun:
            if raw in known_slugs:
                if raw not in urun:
                    urun.append(raw)
            else:
                notlar.append(f"bilinmeyen ürün slug'ı '{raw}' atıldı")

        entities = Entities(
            siparis_no=classify.extract_order_numbers(msg.mesaj),
            urun=urun,
            url=classify.extract_urls(msg.mesaj),
        )
        gerekceler = [f"llm: {self.model} niyet/dil çıkardı", *notlar]
        return Extraction(dil=dil, intents=intents, entities=entities, gerekceler=gerekceler)

    def _fallback(self, msg: Message, kb: KnowledgeBase, sebep: str) -> Extraction:
        ext = classify.classify(msg, kb)
        ext.gerekceler.insert(0, f"llm_fallback: {sebep} → kural tabanlı sınıflandırma")
        return ext


def make_extractor() -> Optional[LLMExtractor]:
    """Ortamda API anahtarı VE `anthropic` paketi varsa LLMExtractor kurar, yoksa None.

    None dönerse run.py hiç bu extractor'ı kullanmadan kural tabanlı classify()'a düşer.
    """
    if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
        return None
    try:
        import anthropic  # type: ignore  # opsiyonel bağımlılık, yalnız burada import edilir
    except ImportError:
        return None
    model = os.environ.get("LLM_MODEL", "claude-opus-5")
    return LLMExtractor(anthropic.Anthropic(), model)
