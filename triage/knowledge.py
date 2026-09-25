"""Bilgi tabanı: sipariş, ürün ve politika verisine TEK erişim noktası.

Kural: olgu yalnız buradan gelir. Alan yoksa ya da None ise "bilinmiyor" demektir;
çağıran taraf bunu olumsuz cevaba çevirmez, devreder.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Optional

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

# Karşı-olgusal hesap (bilgi boşluğu raporu) için bilinmeyen alanlara konan yer tutucu.
FILLED_PLACEHOLDER = "<doldurulmuş varsayımsal değer>"


class KnowledgeBase:
    def __init__(self, siparisler: list[dict], urunler: list[dict], politikalar: dict):
        self._siparisler = {int(s["siparis_no"]): s for s in siparisler}
        self._urunler = {u["slug"]: u for u in urunler}
        self._politikalar = politikalar

    @classmethod
    def load(cls, data_dir: Path = DATA_DIR) -> "KnowledgeBase":
        def read(name: str) -> Any:
            return json.loads((Path(data_dir) / name).read_text(encoding="utf-8"))

        return cls(
            siparisler=read("siparisler.json")["siparisler"],
            urunler=read("urunler.json")["urunler"],
            politikalar={k: v for k, v in read("politikalar.json").items() if not k.startswith("_")},
        )

    # --- siparişler ---
    def find_order(self, siparis_no: int) -> Optional[dict]:
        return self._siparisler.get(int(siparis_no))

    # --- ürünler ---
    def find_product(self, slug: str) -> Optional[dict]:
        return self._urunler.get(slug)

    def products(self) -> list[dict]:
        return list(self._urunler.values())

    def product_aliases(self) -> dict[str, list[str]]:
        """slug -> takma adlar (ham; eşleştirirken text.fold ile katlayın)."""
        return {slug: [u["ad"], *u.get("aliases", [])] for slug, u in self._urunler.items()}

    # --- politikalar ---
    def get_policy(self, key: str) -> Optional[Any]:
        return self._politikalar.get(key)

    # --- karşı-olgusal kopya ---
    def filled(self, eksik_bilgiler: list[str]) -> "KnowledgeBase":
        """Verilen eksik alanları yer tutucu BİLİNEN değerle doldurulmuş bir kopya döndürür.

        Anahtar biçimleri (Decision.eksik_bilgiler ile aynı):
          "urun:<slug>:<alan>"          -> ürünün alanı
          "politika:<anahtar>"          -> politikanın tamamı
          "politika:<anahtar>:<alan>"   -> politikanın bir alanı
        """
        kb = copy.deepcopy(self)
        for key in eksik_bilgiler:
            parts = key.split(":")
            if parts[0] == "urun" and len(parts) == 3 and parts[1] in kb._urunler:
                kb._urunler[parts[1]][parts[2]] = FILLED_PLACEHOLDER
            elif parts[0] == "politika" and len(parts) == 2:
                kb._politikalar[parts[1]] = {"metin_tr": FILLED_PLACEHOLDER, "metin_en": FILLED_PLACEHOLDER}
            elif parts[0] == "politika" and len(parts) == 3:
                kb._politikalar.setdefault(parts[1], {})[parts[2]] = FILLED_PLACEHOLDER
        return kb
