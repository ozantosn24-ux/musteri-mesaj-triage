# Müşteri Mesajı Onay Kuyruğu

_Üretim: 2026-09-25 15:19 · Veriler VARSAYIM etiketlidir (case-brief.md e-postaya eklenmemişti, sipariş/ürün/politika verisi örnek veridir)._

## Özet

- Toplam mesaj: **15**
- İnsana aktarıldı: **3**
- Doğrulama gerekli: **2**
- Otomatik yanıt: **9**
- Karantina: **1**
- ACİL (sağlık şikâyeti) sayısı: **1**

## Bilgi tabanı boşlukları (varsayımsal tahmin)

- `urun:tonik:alkol_icerir` bilinmiyor → engellenen mesajlar: #13

Otomatik yanıt oranı: **%60 → %67** (varsayımsal tahmin; ilgili alanlar doldurulsaydı).

## İnsana aktarıldı

### #4 · ACİL · instagram · müşteri 14 · ekip: kalite

> Dün aldığım serumu kullandım, yüzüm yandı ve kızardı. Ne yapmalıyım?

**Taslak yanıt**

> Merhaba,
> 
> Geçmiş olsun. Ürünü kullanmayı hemen bırakmanızı rica ederiz. Şikâyetiniz sürer ya da artarsa lütfen bir sağlık profesyoneline başvurun. Kalite ekibimiz en kısa sürede sizinle iletişime geçecek. Bize şu bilgileri paylaşabilir misiniz: ürün adı, lot/seri numarası (kutunun altında), etkilenen bölgenin fotoğrafı?
> 
> İyi günler dileriz.

**Gerekçeler**
- kural: sağlık anahtar kelimesi 'yandi'

Kaynaklar: politikalar.json#saglik

### #5 · YÜKSEK · whatsapp · müşteri 18 · ekip: iade

> Kutu ezik geldi, ürünü iade etmek istiyorum.

**Taslak yanıt**

> Merhaba,
> 
> Yaşadığınız sorun için üzgünüz. Hasarlı gelen ürünlerde fotoğraf ve sipariş numarasıyla ücretsiz değişim ya da iade yapılır. Ürünün fotoğrafını ve sipariş numaranızı paylaşabilir misiniz?
> 
> İyi günler dileriz.

**Gerekçeler**
- kural: iade/hasar anahtar kelimesi 'iade'

Kaynaklar: politikalar.json#iade

### #13 · DÜŞÜK · whatsapp · müşteri 9 · ekip: urun

> Tonik 200 ml mi? İçeriğinde alkol var mı?

**Taslak yanıt**

> Merhaba,
> 
> Tonik 200 ml'dir. Tonik ürününün alkol içeriği bilgisini ürün ekibimizden teyit edip size döneceğiz.
> 
> İyi günler dileriz.

**Veride eksik (bu yüzden insana gitti):** `urun:tonik:alkol_icerir`

**Gerekçeler**
- kural: ürün eşleşti + 'var mi'

Kaynaklar: urunler.json#tonik

## Doğrulama gerekli

### #1 · YÜKSEK · whatsapp · müşteri 7 · ekip: destek

> Merhaba, 12 numaralı siparişim nerede? Ne zaman kargoya verilir?

**Taslak yanıt**

> Merhaba,
> 
> Bu numarayla size ait bir sipariş göremedik. Sipariş numaranızı ve siparişte kullandığınız telefon numarasını ya da e-posta adresini paylaşır mısınız?
> 
> İyi günler dileriz.

**Gerekçeler**
- kural: sipariş no 12 ('numaralı' kalıbı)
- sipariş 12 bu müşteriye ait değil; bilgi paylaşılmadı

### #3 · YÜKSEK · whatsapp · müşteri 22 · ekip: destek

> 9999 numaralı siparişim hâlâ elime ulaşmadı, kontrol eder misiniz?

**Taslak yanıt**

> Merhaba,
> 
> Bu numarayla size ait bir sipariş göremedik. Sipariş numaranızı ve siparişte kullandığınız telefon numarasını ya da e-posta adresini paylaşır mısınız?
> 
> İyi günler dileriz.

**Gerekçeler**
- kural: sipariş no 9999 ('numaralı' kalıbı)
- sipariş 9999 bulunamadı

## Otomatik yanıt

### #2 · NORMAL · instagram · müşteri 5 · ekip: —

> 5 numaralı siparişimin durumu nedir acaba?

**Taslak yanıt**

> Merhaba,
> 
> 5 numaralı siparişiniz kargoda. Kargo firması: Yurtiçi Kargo. Takip numarası: YK3000000005. Kargoya veriliş tarihi: 24.09.2026. Tahmini varış tarihi: 26.09.2026.
> 
> İyi günler dileriz.

**Gerekçeler**
- kural: sipariş no 5 ('numaralı' kalıbı)

Kaynaklar: siparisler.json#5

### #6 · NORMAL · instagram · müşteri 3 · ekip: —

> Hi, where is my order #3? It has been a week.

**Taslak yanıt**

> Hello,
> 
> Order #3 is on the way. Carrier: Yurtiçi Kargo. Tracking number: YK3000000003. Shipped on: 2026-09-24. Estimated delivery: 2026-09-26.
> 
> Best regards.

**Gerekçeler**
- kural: sipariş no 3 ('order' kalıbı)

Kaynaklar: siparisler.json#3

### #8 · NORMAL · whatsapp · müşteri 4 · ekip: —

> Güneş kreminin fiyatı ne kadar? Bir de 4 numaralı siparişim ne zaman gelir?

**Taslak yanıt**

> Merhaba,
> 
> 4 numaralı siparişiniz hazırlanıyor. Tahmini kargoya veriliş tarihi: 26.09.2026. Güneş Kremi SPF50: 450 TL.
> 
> İyi günler dileriz.

**Gerekçeler**
- kural: sipariş no 4 ('numaralı' kalıbı)
- kural: fiyat anahtar kelimesi

Kaynaklar: siparisler.json#4, urunler.json#gunes_kremi_spf50

### #9 · DÜŞÜK · whatsapp · müşteri 1 · ekip: —

> Retinol serumunuz var mı? Kuru ciltte kullanılır mı?

**Taslak yanıt**

> Merhaba,
> 
> Retinol Serum stoklarımızda var. Retinol Serum normal, kuru ve karma ciltler için uygundur.
> 
> İyi günler dileriz.

**Gerekçeler**
- kural: ürün eşleşti + 'var mi'

Kaynaklar: urunler.json#retinol_serum

### #10 · DÜŞÜK · instagram · müşteri 2 · ekip: —

> Nemlendirici krem ne kadar?

**Taslak yanıt**

> Merhaba,
> 
> Nemlendirici Krem: 380 TL.
> 
> İyi günler dileriz.

**Gerekçeler**
- kural: fiyat anahtar kelimesi

Kaynaklar: urunler.json#nemlendirici_krem

### #11 · DÜŞÜK · whatsapp · müşteri 8 · ekip: —

> C vitamini serumu hangi cilt tipine uygundur?

**Taslak yanıt**

> Merhaba,
> 
> C Vitamini Serumu normal, karma ve yağlı ciltler için uygundur.
> 
> İyi günler dileriz.

**Gerekçeler**
- kural: ürün eşleşti + 'cilt'

Kaynaklar: urunler.json#c_vitamini_serum

### #12 · DÜŞÜK · instagram · müşteri 6 · ekip: —

> Siparişler hangi kargo firmasıyla gönderiliyor?

**Taslak yanıt**

> Merhaba,
> 
> Siparişleriniz Yurtiçi Kargo ile gönderiliyor. Teslimat süresi genellikle 1-3 iş günü.
> 
> İyi günler dileriz.

**Gerekçeler**
- kural: kargo bilgisi kalıbı 'hangi kargo'

Kaynaklar: politikalar.json#kargo

### #14 · DÜŞÜK · instagram · müşteri 10 · ekip: —

> İndirim kodunuz var mı, fiyat listesi paylaşır mısınız?

**Taslak yanıt**

> Merhaba,
> 
> Güncel fiyat listemiz: Güneş Kremi SPF50: 450 TL; Retinol Serum: 650 TL; Nemlendirici Krem: 380 TL; C Vitamini Serumu: 590 TL; Tonik: 320 TL. Şu an aktif bir indirim kodumuz bulunmuyor.
> 
> İyi günler dileriz.

**Gerekçeler**
- kural: fiyat anahtar kelimesi
- kural: indirim anahtar kelimesi 'indirim'
- fiyat listesi paylaşılabilir
- aktif kod yok, kod uydurulmadı

Kaynaklar: politikalar.json#fiyat_listesi, urunler.json#gunes_kremi_spf50, urunler.json#retinol_serum, urunler.json#nemlendirici_krem, urunler.json#c_vitamini_serum, urunler.json#tonik, politikalar.json#indirim

### #15 · DÜŞÜK · whatsapp · müşteri 11 · ekip: —

> Merhaba, ürünleriniz hayvanlar üzerinde test ediliyor mu?

**Taslak yanıt**

> Merhaba,
> 
> Ürünlerimiz ve hammaddelerimiz hayvanlar üzerinde test edilmemektedir.
> 
> İyi günler dileriz.

**Gerekçeler**
- kural: politika anahtar kelimesi 'hayvan'

Kaynaklar: politikalar.json#hayvan_testi

## Karantina

### #7 · DÜŞÜK · instagram · müşteri 27 · ekip: —

> Takipçi kasmak ister misiniz? 🔥 %100 organik takipçi: bit.ly/takip-artir

**Taslak yanıt**

> _yanıt verilmez_

**Gerekçeler**
- kural: link + tanıtım kelimesi → spam

