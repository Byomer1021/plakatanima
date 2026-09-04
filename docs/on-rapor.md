# Ön Rapor
## Türk Plakası Tanıma — Sentetik Veri, CTC ve Gerçek Zamanlı Boru Hattı

**Proje türü:** Kişisel portfolyo projesi — üçüncü görüntü işleme projesi
**Öncüller:** [otonomarac](https://github.com/Byomer1021/otonomarac),
[trafikisaret](https://github.com/Byomer1021/trafikisaret)

---

## 1. Bu belge neyi yapıyor

Elimde ayrıntılı bir proje planı vardı: 10 hafta, Jetson Orin Nano, global
shutter kamera, IR aydınlatma, uç cihazda 30 FPS. Plan iyi ama **donanımı olan
biri için** yazılmış.

Bu belge o planı **gerçek kısıtlara oturtuyor** ve neyin değiştiğini, neden
değiştiğini kayda geçiriyor. Kapsamı sessizce daraltmak yerine açıkça daraltmak
ilk iki projenin de kuralıydı.

---

## 2. Bağlayıcı kısıtlar — ölçüldü, tahmin edilmedi

| Kısıt | Durum | Etkisi |
|---|---|---|
| Uç cihaz (Jetson) | **Yok** | Faz 6 tamamen düşüyor |
| Kamera (global shutter, IR) | **Yok** | Faz 0.3 mevcut kayıtlardan |
| Yerel GPU | GTX 1080, **ağır yükte üç kez düştü** | Eğitim buluta taşınıyor |
| Disk | C'de 17 GB, **D'de 589 GB** | Proje D'ye taşındı, kısıt kalktı |
| Bulut GPU | Erişilebilir | Faz 1-5 buradan |

GPU'nun güvenilmezliği ölçülmüş bir gerçek: trafikisaret projesinde YOLO
eğitimi ilk epoch'u bitirmeden `CUDA error: unknown error` ile düştü, ve bu
üçüncü düşüştü. O proje 40 epoch'u CPU'da 4,4 saatte tamamladı — 556 kareyle.
Bu projede istenen 200.000 sentetik görüntü, aynı hızda **haftalar** demek.
Yani bulut bir konfor değil, zorunluluk.

Disk ilk taslakta kısıttı (C'de 17 GB) ve veri stratejisi ona göre
daraltılmıştı. D sürücüsünde 589 GB boş olduğu anlaşılınca proje oraya taşındı
ve kısıt kalktı: kareler kaynak çözünürlükte diske yazılabiliyor. Bu önemli,
çünkü kırpma parametrelerini sonradan değiştirmek isteyeceğiz ve videoyu her
seferinde yeniden çözmek pahalı.

---

## 3. Veri: kamera almadan gerçek Türk plakası

Plan 500-2000 gerçek plaka istiyordu ve bunun için kamera kurulumu
öngörüyordu. Ama elimde zaten iki saatlik dashcam kaydı var (Maltepe 75 dk,
İstanbul yağmur 19 dk, İstanbul gece 26 dk) ve içi araç dolu.

Ölçüldü — 60 rastgele karede COCO araç tespiti:

```
172 araç            ->  kare başına 2.9
plakası okunabilecek kadar yakın (araç genişliği >= 200 px):
                        kare başına 1.08
2 saatlik kayıt, 2 sn'de bir kare (~3600 kare)
                    ->  kabaca 3900 plaka adayı
```

Üstelik bu sayı **1920'ye küçültülmüş** karelerden; kaynak videolar 2560
(maltepe) ve 3840 (yağmur, gece) genişlikte. Plaka için piksel sayısı belirleyici
olduğundan çıkarma **kaynak çözünürlükte** yapılacak.

### Bu verinin dürüst sınırları

Dashcam kaydı, sabit yol kenarı kamerası değil. Farkları saklamak yerine
yazıyorum:

- **Arka plakalar baskın.** Önündeki aracın arkasını görüyorsun. Ön plaka
  yalnızca karşı yönden gelen araçlarda ve orada da hızlı geçiyor.
- **Hareket bulanıklığı var** ve düzeltilemez. Plan bunu "kamera ayarıyla önle"
  diyor; bende önlenmiş değil, o yüzden **ölçülecek** (bkz. bölüm 5).
- **IR yok**, gece kareleri görünür ışıkta. Retroreflektif plakanın IR'daki
  avantajı elde yok.
- **Global shutter yok**, rolling shutter eğilmesi mümkün.

Bu sınırlar projeyi bitirmiyor, senaryoyu değiştiriyor: yaptığım şey sabit
gişe ANPR'si değil, **hareketli araçtan plaka okuma**. Bu da gerçek bir
kullanım (devriye aracı, mobil denetim) ve dürüstçe böyle adlandırılacak.

---

## 4. Tez cümlesi — donanımsız sürüm

Orijinal plan şunu iddia ediyordu:

> "Uç cihazda C++ ve TensorRT ile 30 FPS gerçek zamanlı çalıştırdım."

Kanıtlayamayacağım bir cümle. Yerine:

> "Türk plakası için sentetik veri üretim hattı kurup tespit ve tanıma modeli
> eğittim. Format gramerini çözümleyiciye gömerek ve zamansal oylamayla tek
> kare doğruluğunu araç bazında tam eşleşmeye taşıdım. C++ ve TensorRT ile
> gerçek zamanlı boru hattını kurdum ve bulut GPU'da ölçtüm; uç cihaz ölçümü
> yapılmadı."

Son cümle eksikliği gizlemiyor. Ölçülmeyen şeyi ölçülmüş gibi yazmak, bu üç
projenin de karşı durduğu şey.

---

## 5. Donanım eksikliğini ölçüme çevirmek

Planın kamera bölümü haklı: hareket bulanıklığı yazılımla düzeltilemez, ve
pozlama ayarı algoritmadan önce gelir. Ama bu bir **iddia** olarak kalırsa
değeri az; benim kayıtlarımda bulanıklık zaten var, o yüzden **maliyeti
ölçülebilir**.

Yapılacak: tanıma doğruluğunu iki kesitte ayrı raporla.

| kesit | beklenti |
|---|---|
| Park halindeki / yavaş araç (keskin plaka) | yüksek |
| Hareket halindeki araç (bulanık plaka) | belirgin düşük |

Çıkan fark, "kamera spesifikasyonu neden önce gelir" sorusunun **sayısal**
cevabı olur. trafikisaret'te aynı şey yapıldı: gündüz 0.608, yağmur+gece 0.361
— ve o ayrım, toplam sayının neyi gizlediğini gösterdi.

---

## 6. Faz planı — neyin kaldığı

| faz | konu | durum |
|---|---|---|
| 0 | Sentetik üreteç + gerçek veri toplama | ✅ tam |
| 1 | Tespit modeli (köşe regresyonlu) | ✅ bulut GPU |
| 2 | Tanıma modeli, CTC | ✅ bulut GPU |
| 3 | Kısıtlı çözümleme, değerlendirme, güven kalibrasyonu | ✅ CPU yeterli |
| 4 | TensorRT FP16/INT8 | ⚠️ bulut GPU'da, Jetson'da değil |
| 5 | C++ boru hattı, takip, zamansal oylama | ⚠️ kiralık Linux GPU |
| 6 | Termal, güç, çoklu akış | ❌ **kapsam dışı — donanım yok** |

Faz 6'nın düşmesi kabul edilebilir çünkü projenin en özgün parçaları donanıma
bağlı olmayanlar: sentetik üreteç, CTC, kısıtlı çözümleme, zamansal oylama,
güven kalibrasyonu. Donanım gelirse Faz 5-6 sonradan eklenir; plan zaten
ayrılabilir yapıda.

---

## 7. Kapsam dışı — bilinçli

- Uç cihaz ölçümleri (termal, güç, çoklu akış) — donanım yok
- Bariyer/kapı otomasyonu, veritabanı, arayüz, ödeme entegrasyonu
- Araç marka-model tanıma
- Çoklu ülke plaka desteği — önce TR
- Ön plaka senaryosu — veri arka plaka ağırlıklı, bu yazılacak

---

## 8. Başarı kriterleri

Metrikler **yalnızca gerçek veride** ölçülür. Sentetik veride ölçülen doğruluk
kendi ürettiğin dağılımda kendi modelini test etmektir ve hiçbir şey söylemez.

- [ ] Sentetik üreteç tek komutla çalışıyor, dağılımı belgelenmiş
- [ ] Gerçek TR test kümesi ayrılmış ve **hiçbir aşamada eğitime girmemiş**
- [ ] Tespit: köşe hatası ve boyuta göre ayrıştırılmış recall raporlanmış
- [ ] Tanıma: tek kare tam dizi doğruluğu, karakter doğruluğu, düzenleme mesafesi
- [ ] Kısıtsız vs kısıtlı çözümleme farkı ölçülmüş
- [ ] Reddetme oranı ve reddedilmeyenlerde hata oranı eğrisi çıkarılmış
- [ ] Güven skoru kalibre edilmiş, güvenilirlik diyagramı çizilmiş
- [ ] Zamansal oylama kazancı kare sayısına göre grafiklenmiş
- [ ] Keskin vs bulanık kesit ayrı raporlanmış
- [ ] TensorRT precision × gecikme × doğruluk tablosu (bulut GPU)

**Kritik metrik:** reddedilmeyen okumalarda hata oranı. Yanlış plaka okumak,
"okuyamadım" demekten pahalıdır — ücret toplamada yanlış kişiye fatura demektir.

---

## 9. Mahremiyet

Plaka, bir kişiye bağlandığı anda kişisel veri. Kurallar:

- Ham sahne görüntüleri depoya **girmez** (diskte durur, git'e girmez)
- Yayınlanacaksa yalnızca **bağlamsız plaka kırpması**
- Demo görsellerinde araç ve yüzler bulanıklaştırılır — trafikisaret'teki
  `make_demo.py` yaklaşımı buraya taşınır (bulanıklaştırma elle değil kodla,
  denetlenebilir olsun diye)

---

## 10. Riskler

| risk | önlem |
|---|---|
| Sentetik-gerçek uçurumu | Değerlendirme yalnızca gerçek veride; kalibrasyon seti de gerçek |
| Depolama | Proje D sürücüsünde (589 GB boş); kareler kaynak çözünürlükte saklanıyor |
| Bulut oturumu kopması | Kısa eğitimler, sık checkpoint, veri seti küçük tutulur |
| Hareket bulanıklığı tavanı düşürür | Ölçülür ve raporlanır; gizlenmez |
| Etiketleme emeği | trafikisaret'in etiketleme aracı devralınır, sıfırdan yazılmaz |
