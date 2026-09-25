"""Görülmemiş mesajlarla ölçüm.

tests/varyasyonlar.json'daki 20 mesaj, kuralları GÖRMEMİŞ ayrı bir yapay zekâ ajanı tarafından yazıldı ve
beklenen davranışla etiketlendi. Kurallar bu mesajlara göre ayarlanmadı; bu betik kural tabanlı
sınıflandırmanın yeni ifadelere ne kadar dayandığını dürüstçe gösterir.

    python eval_varyasyon.py            # özet + hatalar
    python eval_varyasyon.py --md out/varyasyon_sonuc.md
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from triage.knowledge import KnowledgeBase
from triage.models import Message
from triage.pipeline import process_all

ROOT = Path(__file__).resolve().parent
FIELDS = ["dil", "intents", "oncelik", "aksiyon", "ekip"]


def compare(result: dict, expected: dict) -> list[str]:
    wrong = []
    for f in FIELDS:
        got, want = result[f], expected[f]
        if f == "intents":
            got, want = sorted(got), sorted(want)
        if got != want:
            wrong.append(f"{f}: beklenen {want}, çıkan {got}")
    return wrong


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--md", help="sonucu markdown olarak da yaz")
    args = ap.parse_args()

    rows = json.loads((ROOT / "tests" / "varyasyonlar.json").read_text(encoding="utf-8"))
    results = process_all([Message.from_dict(r) for r in rows], KnowledgeBase.load())

    per_field = {f: 0 for f in FIELDS}
    fully_right = 0
    lines = []
    for row, res in zip(rows, results):
        d = res.to_dict()
        wrong = compare(d, row["beklenen"])
        for f in FIELDS:
            if not any(w.startswith(f + ":") for w in wrong):
                per_field[f] += 1
        if not wrong:
            fully_right += 1
        else:
            lines.append(f"- #{row['id']} \"{row['mesaj']}\"\n  - " + "\n  - ".join(wrong))

    n = len(rows)
    out = [f"# Görülmemiş {n} mesaj: kural tabanlı sınıflandırma", "",
           f"Tamamen doğru: **{fully_right}/{n}**", "",
           "| Alan | Doğru |", "|---|---|"]
    out += [f"| {f} | {per_field[f]}/{n} |" for f in FIELDS]
    out += ["", "## Yanlışlar", ""] + (lines or ["_yok_"])
    text = "\n".join(out) + "\n"
    print(text)
    if args.md:
        Path(args.md).parent.mkdir(parents=True, exist_ok=True)
        Path(args.md).write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
