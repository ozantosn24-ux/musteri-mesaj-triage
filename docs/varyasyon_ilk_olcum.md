> Bu dosya, kurallar varyasyon setini hiç görmeden yapılan ilk ölçümdür (commit f2faf60 anındaki kod). Sonraki düzeltmeler için eval_varyasyon.py çıktısına bakın.

# Görülmemiş 20 mesaj: kural tabanlı sınıflandırma

Tamamen doğru: **10/20**

| Alan | Doğru |
|---|---|
| dil | 17/20 |
| intents | 11/20 |
| oncelik | 18/20 |
| aksiyon | 14/20 |
| ekip | 15/20 |

## Yanlışlar

- #104 "kargom hala gelmedi, ne zaman kargoya verildi bilgi alabilir miyim?"
  - intents: beklenen ['siparis_durumu'], çıkan ['bilinmiyor']
  - oncelik: beklenen P2, çıkan P3
  - aksiyon: beklenen needs_verification, çıkan human_escalation
- #106 "urunu 2 gundur kullaniyorum cildim soyulmaya basladi, normal mi bu?"
  - intents: beklenen ['saglik_sikayeti'], çıkan ['bilinmiyor']
  - oncelik: beklenen P0, çıkan P3
  - ekip: beklenen kalite, çıkan destek
- #109 "Kripto yatırımıyla paranızı 1 haftada 2 katına çıkarın 💰 Detay: kazan2x-bonus.net"
  - intents: beklenen ['spam'], çıkan ['bilinmiyor']
  - aksiyon: beklenen quarantine, çıkan human_escalation
  - ekip: beklenen None, çıkan destek
- #110 "Congratulations!! You won a free gift box, reply YES now to claim it 🎁"
  - dil: beklenen en, çıkan tr
  - intents: beklenen ['spam'], çıkan ['bilinmiyor']
  - aksiyon: beklenen quarantine, çıkan human_escalation
  - ekip: beklenen None, çıkan destek
- #111 "Retinol serum kaç para?"
  - intents: beklenen ['fiyat'], çıkan ['bilinmiyor']
  - aksiyon: beklenen auto_reply, çıkan human_escalation
  - ekip: beklenen None, çıkan destek
- #112 "Güneş kreminin fiyatı nedir, indirim kodunuz var mı?"
  - intents: beklenen ['fiyat', 'indirim'], çıkan ['fiyat', 'indirim', 'urun_bilgisi']
- #115 "Saç serumunuz var mı, saçlar için de ürün çıkardınız mı?"
  - intents: beklenen ['urun_bilgisi'], çıkan ['bilinmiyor']
  - aksiyon: beklenen needs_verification, çıkan human_escalation
- #117 "How many days does shipping usually take?"
  - dil: beklenen en, çıkan tr
  - intents: beklenen ['kargo_bilgisi'], çıkan ['bilinmiyor']
  - aksiyon: beklenen auto_reply, çıkan human_escalation
  - ekip: beklenen None, çıkan destek
- #118 "Hi, are your products vegan and cruelty-free? Do you test on animals?"
  - dil: beklenen en, çıkan tr
- #119 "Ürününüzü kullandım yüzümde şiddetli kaşıntı ve döküntü oldu!! Hediye kazanmak için tıklayın: kazandiniz-hediye.tk"
  - intents: beklenen ['saglik_sikayeti', 'spam'], çıkan ['saglik_sikayeti']
