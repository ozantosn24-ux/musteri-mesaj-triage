from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Optional

import pytest

from triage import classify
from triage.knowledge import KnowledgeBase
from triage.llm import OUTPUT_SCHEMA, LLMExtractor, make_extractor
from triage.models import Intent, Message

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


class _FakeMessages:
    """Anthropic SDK'sının `.messages` nesnesini taklit eder; çağrı kwargs'ını saklar."""

    def __init__(self, payload: Optional[dict] = None, raw_text: Optional[str] = None,
                 stop_reason: str = "end_turn") -> None:
        self._payload = payload
        self._raw_text = raw_text
        self.stop_reason = stop_reason
        self.last_kwargs: Optional[dict[str, Any]] = None

    def create(self, **kwargs: Any) -> SimpleNamespace:
        self.last_kwargs = kwargs
        text = self._raw_text if self._raw_text is not None else json.dumps(self._payload)
        return SimpleNamespace(
            stop_reason=self.stop_reason,
            content=[SimpleNamespace(type="text", text=text)],
        )


class FakeClient:
    """Gerçek `anthropic.Anthropic()` yerine geçer; ağ/anahtar gerekmez."""

    def __init__(self, payload: Optional[dict] = None, raw_text: Optional[str] = None,
                 stop_reason: str = "end_turn") -> None:
        self.messages = _FakeMessages(payload=payload, raw_text=raw_text, stop_reason=stop_reason)


@pytest.fixture(scope="module")
def kb() -> KnowledgeBase:
    return KnowledgeBase.load()


@pytest.fixture(scope="module")
def messages() -> dict[int, dict]:
    raw = json.loads((DATA_DIR / "mesajlar.json").read_text(encoding="utf-8"))
    return {m["id"]: m for m in raw}


def _msg(messages: dict[int, dict], msg_id: int) -> Message:
    return Message.from_dict(messages[msg_id])


# --- geçerli yanıt: niyet eşleşir, sipariş no LLM'den DEĞİL regex'ten gelir ---


def test_valid_response_maps_intent_and_order_no_from_regex(messages, kb):
    msg = _msg(messages, 6)  # "Hi, where is my order #3? It has been a week."
    client = FakeClient(payload={"dil": "en", "intents": ["siparis_durumu"], "urun": []})
    extractor = LLMExtractor(client, "fake-model")

    ext = extractor(msg, kb)

    assert ext.dil == "en"
    assert ext.intents == [Intent.SIPARIS_DURUMU]
    assert ext.entities.siparis_no == [3]


# --- istek şekli: json_schema formatı var, temperature/top_p YOK ---


def test_request_uses_json_schema_and_omits_temperature(messages, kb):
    msg = _msg(messages, 6)
    client = FakeClient(payload={"dil": "en", "intents": ["siparis_durumu"], "urun": []})
    extractor = LLMExtractor(client, "fake-model")

    extractor(msg, kb)

    kwargs = client.messages.last_kwargs
    assert kwargs is not None
    assert kwargs["output_config"]["format"]["type"] == "json_schema"
    assert kwargs["output_config"]["format"]["schema"] == OUTPUT_SCHEMA
    assert "temperature" not in kwargs
    assert "top_p" not in kwargs


# --- bozuk JSON metni -> kural tabanlı fallback ---


def test_malformed_text_falls_back_to_rules(messages, kb):
    msg = _msg(messages, 6)
    client = FakeClient(raw_text="not json")
    extractor = LLMExtractor(client, "fake-model")

    ext = extractor(msg, kb)
    expected = classify.classify(msg, kb)

    assert ext.gerekceler[0].startswith("llm_fallback")
    assert ext.dil == expected.dil
    assert {i.value for i in ext.intents} == {i.value for i in expected.intents}


# --- stop_reason "refusal" -> fallback ---


def test_refusal_falls_back_to_rules(messages, kb):
    msg = _msg(messages, 6)
    client = FakeClient(
        payload={"dil": "en", "intents": ["siparis_durumu"], "urun": []},
        stop_reason="refusal",
    )
    extractor = LLMExtractor(client, "fake-model")

    ext = extractor(msg, kb)

    assert ext.gerekceler[0].startswith("llm_fallback")


# --- şema ihlali (bilinmeyen niyet, eksik/fazla anahtar, yanlış tip) -> fallback ---


@pytest.mark.parametrize("payload", [
    {"dil": "tr", "intents": ["hack", "fiyat"], "urun": []},        # enum dışı niyet
    {"dil": "tr", "intents": ["fiyat"]},                            # eksik anahtar
    {"dil": "tr", "intents": ["fiyat"], "urun": [], "yanit": "x"},  # fazla anahtar
    {"dil": "tr", "intents": "fiyat", "urun": []},                  # yanlış tip
    {"dil": "tr", "intents": [], "urun": []},                       # boş niyet
])
def test_schema_violation_falls_back_to_rules(messages, kb, payload):
    msg = _msg(messages, 8)
    ext = LLMExtractor(FakeClient(payload=payload), "fake-model")(msg, kb)

    assert ext.gerekceler[0].startswith("llm_fallback")
    assert "şema ihlali" in ext.gerekceler[0]


# --- istemci hata fırlatırsa -> fallback; hata METNİ rapora sızmaz ---


class _RaisingMessages:
    def create(self, **kwargs: Any) -> Any:
        raise RuntimeError("sağlayıcı ayrıntısı: gizli-istek-kimliği-123")


def test_client_exception_falls_back_without_leaking_message(messages, kb):
    msg = _msg(messages, 6)
    client = SimpleNamespace(messages=_RaisingMessages())

    ext = LLMExtractor(client, "fake-model")(msg, kb)

    assert ext.gerekceler[0].startswith("llm_fallback")
    assert "RuntimeError" in ext.gerekceler[0]
    assert not any("gizli-istek-kimliği" in g for g in ext.gerekceler)


# --- bilinmeyen ürün slug'ı atılır ---


def test_unknown_product_slug_dropped(messages, kb):
    msg = _msg(messages, 9)  # "Retinol serumunuz var mı? Kuru ciltte kullanılır mı?"
    client = FakeClient(payload={"dil": "tr", "intents": ["urun_bilgisi"], "urun": ["sac_serumu"]})
    extractor = LLMExtractor(client, "fake-model")

    ext = extractor(msg, kb)

    assert ext.entities.urun == []
    assert any("sac_serumu" in g for g in ext.gerekceler)


# --- güvenlik: pipeline'ın overlay'i LLM'in "spam" dediğini bile ezer ---


def test_safety_overlay_via_pipeline_forces_escalation(messages, kb):
    from triage import pipeline

    msg = _msg(messages, 4)  # "... yüzüm yandı ve kızardı ..."
    client = FakeClient(payload={"dil": "tr", "intents": ["spam"], "urun": []})
    extractor = LLMExtractor(client, "fake-model")

    result = pipeline.process(msg, kb, extractor=extractor)

    # Action/Priority str-Enum oldukları için ==, dönen değer plain str ya da enum olsa da çalışır.
    assert result.aksiyon == "human_escalation"
    assert result.oncelik == "P0"


# --- make_extractor: ortam yoksa None ---


def test_make_extractor_returns_none_without_env(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)

    assert make_extractor() is None


def test_make_extractor_returns_none_without_anthropic_package(monkeypatch):
    # Paket kurulu olsa da olmasa da: import başarısız olursa anahtar olsa bile None döner.
    import sys

    monkeypatch.setitem(sys.modules, "anthropic", None)  # "import anthropic" -> ImportError
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-fake")

    assert make_extractor() is None
