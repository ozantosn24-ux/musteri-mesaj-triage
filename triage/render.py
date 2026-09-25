"""Rapor + panel üretimi: pipeline'ın SON adımı.

Girdi: `Result` listesi + `KnowledgeBase`. Çıktı: `rapor.md` (insan onay kuyruğu,
Markdown) ve `panel.html` (tek dosya, JS/CDN yok, satır içi CSS). İkisi de aynı
karşı-olgusal bilgi-boşluğu hesabını (`knowledge_gap_report`) kullanır.

Güvenlik: panel.html'e giren HER dinamik string `html.escape(..., quote=True)`
üzerinden geçer (mesaj metni müşteriden geliyor, güvenilmez veri).
"""
from __future__ import annotations

import html
from datetime import datetime
from pathlib import Path
from typing import Any

from triage.knowledge import KnowledgeBase
from triage.models import (
    Action,
    Entities,
    Extraction,
    Intent,
    Message,
    PRIORITY_RANK,
    Result,
)

# Rapor/panelde aksiyon grupları bu SIRAYLA gösterilir (en acil ekip müdahalesi önce).
GROUP_ORDER = [
    Action.HUMAN_ESCALATION.value,
    Action.NEEDS_VERIFICATION.value,
    Action.AUTO_REPLY.value,
    Action.QUARANTINE.value,
]

ACTION_LABELS_TR = {
    Action.AUTO_REPLY.value: "Otomatik yanıt",
    Action.NEEDS_VERIFICATION.value: "Doğrulama gerekli",
    Action.HUMAN_ESCALATION.value: "İnsana aktarıldı",
    Action.QUARANTINE.value: "Karantina",
}


def _val(x: Any) -> str:
    """Enum ya da düz string; ikisinde de karşılık gelen değeri döner (contract Result.* : str)."""
    return x.value if hasattr(x, "value") else str(x)


def _e(x: Any) -> str:
    """Tüm dinamik metinler için tek kaçış noktası."""
    return html.escape(str(x), quote=True)


def _fmt_pct(x: float) -> str:
    return f"%{x * 100:.0f}"


def _sort_key(r: Result) -> tuple[int, int]:
    return (PRIORITY_RANK.get(r.oncelik, 99), r.id)


def _grouped(results: list[Result]) -> list[tuple[str, list[Result]]]:
    """Aksiyon -> öncelik+id sıralı mesajlar (boş grup atlanır)."""
    groups: list[tuple[str, list[Result]]] = []
    for aksiyon in GROUP_ORDER:
        items = sorted((r for r in results if _val(r.aksiyon) == aksiyon), key=_sort_key)
        if items:
            groups.append((aksiyon, items))
    return groups


# --------------------------------------------------------------------------
# Karşı-olgusal bilgi boşluğu hesabı
# --------------------------------------------------------------------------


def knowledge_gap_report(results: list[Result], kb: KnowledgeBase) -> dict:
    """Eksik KB alanları doldurulsaydı otomatik yanıt oranı ne olurdu (TAHMİN).

    Yalnız "eksik_bilgiler" yüzünden devredilen mesajlara bakar; sahiplik/sağlık
    gibi başka engellerle devredilenler (eksik_bilgiler boş) hiç hesaba girmez ve
    KB doldurulsa bile decide() başka engelden ötürü hâlâ auto_reply DEMEYEBİLİR
    — o durumda "dönüşecek" sayılmaz (kör optimistik sayım yapılmaz).
    """
    total = len(results)
    current_auto = sum(1 for r in results if _val(r.aksiyon) == Action.AUTO_REPLY.value)

    eksik_alanlar: dict[str, list[int]] = {}
    for r in results:
        for alan in r.eksik_bilgiler:
            eksik_alanlar.setdefault(alan, []).append(r.id)

    try:
        from triage.decide import decide  # gecikmeli import: bu modül henüz yazılmamış olabilir
    except ImportError:
        mevcut_oran = current_auto / total if total else 0.0
        return {
            "toplam": total,
            "mevcut_otomatik": current_auto,
            "tahmini_otomatik": current_auto,
            "mevcut_oran": mevcut_oran,
            "tahmini_oran": mevcut_oran,
            "eksik_alanlar": eksik_alanlar,
            "donusecek_mesajlar": [],
            "etiket": "hesaplanamadı",
        }

    donusecek: list[int] = []
    for r in results:
        if not r.eksik_bilgiler or _val(r.aksiyon) == Action.AUTO_REPLY.value:
            continue
        msg = Message(id=r.id, kanal=r.kanal, musteri_id=r.musteri_id, mesaj=r.mesaj)
        ext = Extraction(
            dil=r.dil,
            intents=[Intent(v) for v in r.intents],
            entities=Entities(**r.entities),
            gerekceler=[],
        )
        varsayimsal_kb = kb.filled(r.eksik_bilgiler)
        yeni_karar = decide(msg, ext, varsayimsal_kb)
        if _val(yeni_karar.aksiyon) == Action.AUTO_REPLY.value:
            donusecek.append(r.id)

    tahmini_otomatik = current_auto + len(donusecek)
    mevcut_oran = current_auto / total if total else 0.0
    tahmini_oran = tahmini_otomatik / total if total else 0.0
    return {
        "toplam": total,
        "mevcut_otomatik": current_auto,
        "tahmini_otomatik": tahmini_otomatik,
        "mevcut_oran": mevcut_oran,
        "tahmini_oran": tahmini_oran,
        "eksik_alanlar": eksik_alanlar,
        "donusecek_mesajlar": donusecek,
        "etiket": "varsayımsal tahmin",
    }


# --------------------------------------------------------------------------
# rapor.md
# --------------------------------------------------------------------------


def _blockquote(text: str) -> str:
    lines = text.splitlines() or [""]
    return "\n".join(f"> {line}" for line in lines)


def _build_rapor_md(results: list[Result], gap: dict) -> str:
    total = len(results)
    by_aksiyon: dict[str, int] = {}
    for r in results:
        key = _val(r.aksiyon)
        by_aksiyon[key] = by_aksiyon.get(key, 0) + 1
    p0_count = sum(1 for r in results if r.oncelik == "P0")

    lines: list[str] = []
    lines.append("# Müşteri Mesajı Onay Kuyruğu")
    lines.append("")
    lines.append(
        f"_Üretim: {datetime.now().strftime('%Y-%m-%d %H:%M')} · "
        "Veriler VARSAYIM etiketlidir (case-brief.md e-postaya eklenmemişti, "
        "sipariş/ürün/politika verisi örnek veridir)._"
    )
    lines.append("")
    lines.append("## Özet")
    lines.append("")
    lines.append(f"- Toplam mesaj: **{total}**")
    for aksiyon in GROUP_ORDER:
        if aksiyon in by_aksiyon:
            lines.append(f"- {ACTION_LABELS_TR[aksiyon]}: **{by_aksiyon[aksiyon]}**")
    lines.append(f"- P0 (acil) sayısı: **{p0_count}**")
    lines.append("")
    lines.append("## Bilgi tabanı boşlukları (varsayımsal tahmin)")
    lines.append("")
    if gap["eksik_alanlar"]:
        for alan, ids in gap["eksik_alanlar"].items():
            id_list = ", ".join(f"#{i}" for i in ids)
            lines.append(f"- `{alan}` bilinmiyor → engellenen mesajlar: {id_list}")
    else:
        lines.append("- Bilinen bilgi boşluğu yok.")
    lines.append("")
    lines.append(
        f"Otomatik yanıt oranı: **{_fmt_pct(gap['mevcut_oran'])} → {_fmt_pct(gap['tahmini_oran'])}** "
        f"({gap['etiket']}; ilgili alanlar doldurulsaydı)."
    )
    lines.append("")

    for aksiyon, items in _grouped(results):
        lines.append(f"## {ACTION_LABELS_TR[aksiyon]}")
        lines.append("")
        for r in items:
            ekip = r.ekip or "—"
            lines.append(f"### #{r.id} · {r.kanal} · müşteri {r.musteri_id} · {r.oncelik} · {ekip}")
            lines.append("")
            lines.append(_blockquote(r.mesaj))
            lines.append("")
            lines.append("**Taslak yanıt**")
            lines.append("")
            if r.yanit_taslagi:
                lines.append(_blockquote(r.yanit_taslagi))
            else:
                lines.append("> _yanıt verilmez_")
            lines.append("")
            if r.gerekceler:
                lines.append("**Gerekçeler**")
                for g in r.gerekceler:
                    lines.append(f"- {g}")
                lines.append("")
            if r.kaynaklar:
                lines.append(f"Kaynaklar: {', '.join(r.kaynaklar)}")
                lines.append("")
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------
# panel.html
# --------------------------------------------------------------------------

_CSS = """
:root {
  --bg: #f5f6f8; --fg: #1f2430; --muted: #5f6368; --card-bg: #ffffff;
  --border: #e2e5ea; --accent: #2563eb; --radius: 10px;
  --p0-bg: #fdecea; --p0-fg: #b3261e;
  --p1-bg: #fff4e0; --p1-fg: #8a5200;
  --p2-bg: #e8f0fe; --p2-fg: #1d4ed8;
  --p3-bg: #f1f3f4; --p3-fg: #5f6368;
  --danger-bg: #fdecea; --danger-fg: #b3261e; --danger-border: #f6c4c0;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #14161a; --fg: #e7e9ee; --muted: #a0a4ad; --card-bg: #1d2026; --border: #2b2f37; --accent: #7ea6ff;
    --p0-bg: #3a1f1d; --p0-fg: #ff8a80;
    --p1-bg: #3a2c12; --p1-fg: #ffcc80;
    --p2-bg: #182842; --p2-fg: #8ab4ff;
    --p3-bg: #23262c; --p3-fg: #b7bac1;
    --danger-bg: #3a1f1d; --danger-fg: #ff8a80; --danger-border: #5c2b28;
  }
}
* { box-sizing: border-box; }
body {
  margin: 0; padding: 0 12px 32px; background: var(--bg); color: var(--fg);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  line-height: 1.5;
}
.wrap { max-width: 880px; margin: 0 auto; }
header.top { padding: 24px 0 8px; }
h1 { font-size: 1.4rem; margin: 0 0 4px; }
.subtitle { color: var(--muted); font-size: 0.9rem; margin: 0; }
.kpis { display: grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap: 10px; margin: 16px 0; }
.kpi { background: var(--card-bg); border: 1px solid var(--border); border-radius: var(--radius); padding: 12px; text-align: center; }
.kpi .n { font-size: 1.25rem; font-weight: 700; display: block; }
.kpi .l { font-size: 0.72rem; color: var(--muted); }
.banner { background: var(--danger-bg); border: 1px solid var(--danger-border); color: var(--danger-fg);
  border-radius: var(--radius); padding: 12px 14px; margin: 16px 0; font-size: 0.9rem; }
.banner strong { display: block; margin-bottom: 4px; }
.banner ul { margin: 4px 0 0 18px; padding: 0; }
.gap { background: var(--card-bg); border: 1px solid var(--border); border-radius: var(--radius); padding: 14px; margin: 16px 0; font-size: 0.9rem; }
.gap ul { margin: 6px 0 0 18px; padding: 0; }
.section-title { font-size: 1rem; margin: 24px 0 8px; }
.card { background: var(--card-bg); border: 1px solid var(--border); border-radius: var(--radius);
  padding: 14px; margin-bottom: 12px; overflow-wrap: anywhere; word-break: break-word; }
.card-head { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; margin-bottom: 8px; }
.badge { font-size: 0.72rem; font-weight: 700; padding: 2px 8px; border-radius: 999px; }
.badge-P0 { background: var(--p0-bg); color: var(--p0-fg); }
.badge-P1 { background: var(--p1-bg); color: var(--p1-fg); }
.badge-P2 { background: var(--p2-bg); color: var(--p2-fg); }
.badge-P3 { background: var(--p3-bg); color: var(--p3-fg); }
.chip { font-size: 0.72rem; background: var(--bg); border: 1px solid var(--border); border-radius: 999px;
  padding: 2px 8px; color: var(--muted); }
.meta { font-size: 0.78rem; color: var(--muted); margin-left: auto; }
.label { font-size: 0.72rem; text-transform: uppercase; letter-spacing: .03em; color: var(--muted); margin: 8px 0 2px; }
.msg, .draft { background: var(--bg); border-left: 3px solid var(--border); padding: 8px 10px; border-radius: 6px;
  margin: 4px 0 6px; font-size: 0.9rem; white-space: pre-wrap; }
.draft { border-left-color: var(--accent); }
details { margin-top: 8px; font-size: 0.85rem; }
details summary { cursor: pointer; color: var(--accent); }
details ul { margin: 6px 0 0 18px; padding: 0; }
.actions { display: flex; gap: 8px; margin-top: 10px; }
button { border: 1px solid var(--border); background: var(--card-bg); color: var(--muted); border-radius: 6px;
  padding: 6px 12px; font-size: 0.85rem; cursor: not-allowed; }
button[disabled] { opacity: 0.6; }
@media (max-width: 480px) {
  .meta { margin-left: 0; width: 100%; }
}
""".strip()


def _kpis_html(results: list[Result], gap: dict) -> str:
    total = gap["toplam"]
    verify_human = sum(
        1 for r in results if _val(r.aksiyon) in (Action.NEEDS_VERIFICATION.value, Action.HUMAN_ESCALATION.value)
    )
    p0 = sum(1 for r in results if r.oncelik == "P0")
    quarantine = sum(1 for r in results if _val(r.aksiyon) == Action.QUARANTINE.value)
    cards = [
        (str(total), "Toplam mesaj"),
        (_fmt_pct(gap["mevcut_oran"]), "Otomatik yanıt oranı"),
        (str(verify_human), "Doğrulama / insan gerekli"),
        (str(p0), "P0 (acil)"),
        (str(quarantine), "Karantina"),
    ]
    return "".join(f'<div class="kpi"><span class="n">{_e(n)}</span><span class="l">{_e(l)}</span></div>' for n, l in cards)


def _p0_banner_html(results: list[Result]) -> str:
    p0 = sorted((r for r in results if r.oncelik == "P0"), key=lambda r: r.id)
    if not p0:
        return ""
    items = []
    for r in p0:
        kisa = r.mesaj if len(r.mesaj) <= 80 else r.mesaj[:80] + "…"
        items.append(f"<li>#{_e(r.id)} — {_e(kisa)}</li>")
    return (
        '<div class="banner"><strong>P0 — acil, sağlık ile ilgili '
        f'{len(p0)} mesaj</strong><ul>{"".join(items)}</ul></div>'
    )


def _gap_section_html(gap: dict) -> str:
    if gap["eksik_alanlar"]:
        items = "".join(
            f"<li><code>{_e(alan)}</code> → mesajlar: "
            + ", ".join(f"#{_e(i)}" for i in ids)
            + "</li>"
            for alan, ids in gap["eksik_alanlar"].items()
        )
    else:
        items = "<li>Bilinen bilgi boşluğu yok.</li>"
    return (
        '<div class="gap"><div class="section-title" style="margin-top:0">Bilgi tabanı boşlukları</div>'
        f"<p>Otomatik yanıt oranı: <strong>{_e(_fmt_pct(gap['mevcut_oran']))} → "
        f"{_e(_fmt_pct(gap['tahmini_oran']))}</strong> ({_e(gap['etiket'])})</p>"
        f"<ul>{items}</ul></div>"
    )


def _card_html(r: Result) -> str:
    oncelik = _e(r.oncelik)
    aksiyon_key = _val(r.aksiyon)
    aksiyon_label = _e(ACTION_LABELS_TR.get(aksiyon_key, aksiyon_key))
    ekip = _e(r.ekip) if r.ekip else "—"
    intents_html = "".join(f"<span class=\"chip\">{_e(i)}</span>" for i in r.intents)
    mesaj_html = _e(r.mesaj).replace("\n", "<br>")
    if r.yanit_taslagi:
        draft_html = _e(r.yanit_taslagi).replace("\n", "<br>")
    else:
        draft_html = "<em>yanıt verilmez</em>"
    gerekce_items = "".join(f"<li>{_e(g)}</li>" for g in r.gerekceler)
    kaynak_items = "".join(f"<li>{_e(k)}</li>" for k in r.kaynaklar)
    details = ""
    if gerekce_items or kaynak_items:
        details = f"<details><summary>Gerekçe ve kaynaklar</summary><ul>{gerekce_items}{kaynak_items}</ul></details>"
    return f"""<article class="card">
  <div class="card-head">
    <span class="badge badge-{oncelik}">{oncelik}</span>
    <span class="chip">{_e(r.kanal)}</span>
    <span class="chip">{aksiyon_label}</span>
    <span class="chip">{ekip}</span>
    {intents_html}
    <span class="meta">#{_e(r.id)} · müşteri {_e(r.musteri_id)}</span>
  </div>
  <div class="label">Mesaj</div>
  <div class="msg">{mesaj_html}</div>
  <div class="label">Taslak yanıt</div>
  <div class="draft">{draft_html}</div>
  {details}
  <div class="actions">
    <button type="button" disabled title="Demo: gerçek sistemde onay akışına bağlanır">Onayla</button>
    <button type="button" disabled title="Demo: gerçek sistemde onay akışına bağlanır">Düzenle</button>
  </div>
</article>"""


def _build_panel_html(results: list[Result], gap: dict) -> str:
    generated = datetime.now().strftime("%Y-%m-%d %H:%M")
    cards = "\n".join(_card_html(r) for r in sorted(results, key=_sort_key))
    return f"""<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Müşteri Mesajı Onay Kuyruğu</title>
<style>
{_CSS}
</style>
</head>
<body>
<div class="wrap">
  <header class="top">
    <h1>Müşteri Mesajı Onay Kuyruğu</h1>
    <p class="subtitle">Üretim: {_e(generated)} · Veriler VARSAYIM etiketli örnek veridir</p>
  </header>
  <div class="kpis">{_kpis_html(results, gap)}</div>
  {_p0_banner_html(results)}
  {_gap_section_html(gap)}
  <div class="section-title">Kuyruk</div>
  {cards}
</div>
</body>
</html>
"""


# --------------------------------------------------------------------------
# Genel giriş noktası (run.py bunu çağırır)
# --------------------------------------------------------------------------


def write_reports(results: list[Result], kb: KnowledgeBase, out_dir: Path | str) -> dict[str, Path]:
    """`rapor.md` ve `panel.html` yazar; ikisinin de yolunu döner."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    gap = knowledge_gap_report(results, kb)

    rapor_path = out_dir / "rapor.md"
    panel_path = out_dir / "panel.html"
    rapor_path.write_text(_build_rapor_md(results, gap), encoding="utf-8")
    panel_path.write_text(_build_panel_html(results, gap), encoding="utf-8")

    return {"rapor": rapor_path, "panel": panel_path}
