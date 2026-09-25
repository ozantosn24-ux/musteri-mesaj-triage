# Müşteri Mesajı Onay Kuyruğu

_Üretim: 2026-09-25 14:44 · Veriler VARSAYIM etiketlidir (case-brief.md e-postaya eklenmemişti, sipariş/ürün/politika verisi örnek veridir)._

## Özet

- Toplam mesaj: **15**
- İnsana aktarıldı: **3**
- Doğrulama gerekli: **2**
- Otomatik yanıt: **9**
- Karantina: **1**
- P0 (acil) sayısı: **1**

## Bilgi tabanı boşlukları (varsayımsal tahmin)

- `urun:tonik:alkol_icerir` bilinmiyor → engellenen mesajlar: #13

Otomatik yanıt oranı: **%60 → %67** (varsayımsal tahmin; ilgili alanlar doldurulsaydı).

## İnsana aktarıldı

### #4 · instagram · müşteri 14 · P0 · kalite

> Dün aldığım serumu kullandım, yüzüm yandı ve kızardı. Ne yapmalıyım?

**Taslak yanıt**

> Merhaba,
> 
> Ürünü kullanmayı hemen bırakmanızı rica ederiz. Şikâyetiniz sürer ya da artarsa lütfen bir sağlık profesyoneline başvurun. Kalite ekibimiz en kısa sürede sizinle iletişime geçecek. Bize şu bilgileri paylaşabilir misiniz: ürün adı, lot/seri numarası (kutunun altında), cildin fotoğrafı?
> 
> İyi günler dileriz.

**Gerekçeler**
- kural: sağlık anahtar kelimesi 'yand'

Kaynaklar: politikalar.json#saglik

### #5 · whatsapp · müşteri 18 · P1 · iade

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

### #13 · whatsapp · müşteri 9 · P3 · urun

> Tonik 200 ml mi? İçeriğinde alkol var mı?

**Taslak yanıt**

> Merhaba,
> 
> Tonik 200 ml'dir. Tonik ürününün alkol içeriği bilgisini ürün ekibimizden teyit edip size döneceğiz.
> 
> İyi günler dileriz.

**Gerekçeler**
- kural: ürün eşleşti + 'var mi'

## Doğrulama gerekli

### #1 · whatsapp · müşteri 7 · P1 · destek

> Merhaba, 12 numaralı siparişim nerede? Ne zaman kargoya verilir?

**Taslak yanıt**

> Merhaba,
> 
> Güvenlik nedeniyle sipariş bilgilerini yalnızca sipariş sahibiyle paylaşabiliyoruz. Sipariş numarasını ve o siparişte kullanılan telefon/e-posta bilgisini teyit edebilir misiniz?
> 
> İyi günler dileriz.

**Gerekçeler**
- kural: sipariş no 12 ('numaralı' kalıbı)
- sipariş 12 bu müşteriye ait değil; bilgi paylaşılmadı

### #3 · whatsapp · müşteri 22 · P1 · destek

> 9999 numaralı siparişim hâlâ elime ulaşmadı, kontrol eder misiniz?

**Taslak yanıt**

> Merhaba,
> 
> Güvenlik nedeniyle sipariş bilgilerini yalnızca sipariş sahibiyle paylaşabiliyoruz. Sipariş numarasını ve o siparişte kullanılan telefon/e-posta bilgisini teyit edebilir misiniz?
> 
> İyi günler dileriz.

**Gerekçeler**
- kural: sipariş no 9999 ('numaralı' kalıbı)
- sipariş 9999 bulunamadı

## Otomatik yanıt

### #2 · instagram · müşteri 5 · P2 · —

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

### #6 · instagram · müşteri 3 · P2 · —

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

### #8 · whatsapp · müşteri 4 · P2 · —

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

### #9 · whatsapp · müşteri 1 · P3 · —

> Retinol serumunuz var mı? Kuru ciltte kullanılır mı?

**Taslak yanıt**

> Merhaba,
> 
> Retinol Serum stoklarımızda var. Retinol Serum, normal, kuru, karma cilt tipleri için uygundur.
> 
> İyi günler dileriz.

**Gerekçeler**
- kural: ürün eşleşti + 'var mi'

Kaynaklar: urunler.json#retinol_serum

### #10 · instagram · müşteri 2 · P3 · —

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

### #11 · whatsapp · müşteri 8 · P3 · —

> C vitamini serumu hangi cilt tipine uygundur?

**Taslak yanıt**

> Merhaba,
> 
> C Vitamini Serumu, normal, karma, yağlı cilt tipleri için uygundur.
> 
> İyi günler dileriz.

**Gerekçeler**
- kural: ürün eşleşti + 'cilt'

Kaynaklar: urunler.json#c_vitamini_serum

### #12 · instagram · müşteri 6 · P3 · —

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

### #14 · instagram · müşteri 10 · P3 · —

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

### #15 · whatsapp · müşteri 11 · P3 · —

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

### #7 · instagram · müşteri 27 · P3 · —

> Takipçi kasmak ister misiniz? 🔥 %100 organik takipçi: bit.ly/takip-artir

**Taslak yanıt**

> _yanıt verilmez_

**Gerekçeler**
- kural: link + tanıtım kelimesi → spam

