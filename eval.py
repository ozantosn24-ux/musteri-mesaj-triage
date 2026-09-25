"""python eval.py [--results out/results.json] [--golden tests/golden.json]

Not: golden.json bizim yazdığımız BEKLENEN DAVRANIŞ spesifikasyonudur; bağımsız,
dışarıdan gelen bir doğruluk ölçümü DEĞİLDİR. Uyum yalnız "kod spesifikasyona
uyuyor mu" sorusuna cevap verir.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ALANLAR = ("dil", "oncelik", "aksiyon", "ekip")


def _load(path: Path) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))


def evaluate(results: list[dict], golden: list[dict]) -> tuple[int, int, list[str]]:
    """Her alan için (dil, intents-küme, oncelik, aksiyon, ekip) uyumunu sayar."""
    golden_by_id = {g["id"]: g for g in golden}
    toplam = 0
    uyumlu = 0
    uyumsuzlar: list[str] = []

    for r in results:
        g = golden_by_id.get(r["id"])
        if g is None:
            continue

        for alan in _ALANLAR:
            toplam += 1
            if r.get(alan) == g.get(alan):
                uyumlu += 1
            else:
                uyumsuzlar.append(f"id={r['id']} {alan}: beklenen={g.get(alan)!r} gelen={r.get(alan)!r}")

        toplam += 1
        if set(r.get("intents", [])) == set(g.get("intents", [])):
            uyumlu += 1
        else:
            uyumsuzlar.append(f"id={r['id']} intents: beklenen={g.get('intents')!r} gelen={r.get('intents')!r}")

    return uyumlu, toplam, uyumsuzlar


def main() -> int:
    parser = argparse.ArgumentParser(description="results.json'u golden.json ile karşılaştırır")
    parser.add_argument("--results", default="out/results.json")
    parser.add_argument("--golden", default="tests/golden.json")
    args = parser.parse_args()

    results = _load(Path(args.results))
    golden = _load(Path(args.golden))

    uyumlu, toplam, uyumsuzlar = evaluate(results, golden)

    print("Not: golden.json beklenen-davranış spesifikasyonudur, bağımsız bir doğruluk ölçümü değildir.")
    print(f"Uyum: {uyumlu}/{toplam}")
    for u in uyumsuzlar:
        print(f"  UYUMSUZ {u}")

    return 0 if not uyumsuzlar else 1


if __name__ == "__main__":
    sys.exit(main())
