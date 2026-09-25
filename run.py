"""CLI: mesajları işler, out/results.json yazar, kısa bir özet tablo basar.

Kullanım: python run.py [--llm] [--data-dir data] [--out out]
"""
from __future__ import annotations

import argparse
import io
import json
import sys
from pathlib import Path

from triage.knowledge import KnowledgeBase
from triage.models import Message, Result
from triage.pipeline import Extractor, process_all
from triage.render import write_reports


def _reconfigure_stdout_utf8() -> None:
    """Windows konsolu varsayılan cp1252'dir; Türkçe karakterler için UTF-8'e geçirir."""
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")


def _load_messages(data_dir: Path) -> list[Message]:
    ham = json.loads((data_dir / "mesajlar.json").read_text(encoding="utf-8"))
    return [Message.from_dict(d) for d in ham]


def _make_extractor(use_llm: bool) -> Extractor | None:
    if not use_llm:
        return None  # pipeline.process varsayılan olarak triage.classify.classify kullanır

    from triage.llm import make_extractor

    extractor = make_extractor()
    if extractor is None:
        print("Uyarı: LLM extractor kurulamadı (örn. API anahtarı yok), kural tabanlı sınıflandırıcıya dönülüyor.")
        return None
    return extractor


def _print_summary(results: list[Result]) -> None:
    genislik = (4, 10, 8, 19, 0)
    basliklar = ("id", "kanal", "oncelik", "aksiyon", "niyetler")
    print(" | ".join(f"{b:<{g}}" for b, g in zip(basliklar, genislik)))
    for r in results:
        satir = (str(r.id), r.kanal, r.oncelik, r.aksiyon, ",".join(r.intents))
        print(" | ".join(f"{s:<{g}}" for s, g in zip(satir, genislik)))


def main() -> None:
    _reconfigure_stdout_utf8()

    parser = argparse.ArgumentParser(description="Müşteri mesajı triage çalıştırıcı")
    parser.add_argument("--llm", action="store_true", help="Opsiyonel LLM extractor'ı dene")
    kok = Path(__file__).resolve().parent
    parser.add_argument("--data-dir", default=str(kok / "data"))
    parser.add_argument("--out", default=str(kok / "out"))
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    kb = KnowledgeBase.load(data_dir)
    messages = _load_messages(data_dir)
    extractor = _make_extractor(args.llm)

    results = process_all(messages, kb, extractor)

    out_path = out_dir / "results.json"
    out_path.write_text(
        json.dumps([r.to_dict() for r in results], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    write_reports(results, kb, out_dir)
    _print_summary(results)


if __name__ == "__main__":
    main()
