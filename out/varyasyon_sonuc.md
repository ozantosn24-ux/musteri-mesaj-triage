# Varyasyon seti (20 mesaj): kural tabanlı sınıflandırma

Not: ilk ölçüm (kurallar bu mesajları görmeden) docs/varyasyon_ilk_olcum.md içinde; bu sonuç düzeltmelerden sonradır, genelleme kanıtı değildir.

Tamamen doğru: **19/20**

| Alan | Doğru |
|---|---|
| dil | 20/20 |
| intents | 19/20 |
| oncelik | 20/20 |
| aksiyon | 19/20 |
| ekip | 19/20 |

## Yanlışlar

- #117 "How many days does shipping usually take?"
  - intents: beklenen ['kargo_bilgisi'], çıkan ['bilinmiyor']
  - aksiyon: beklenen auto_reply, çıkan human_escalation
  - ekip: beklenen None, çıkan destek
