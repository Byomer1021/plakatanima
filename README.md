# plakatanima

**Türk plakası tanıma — sentetik veri üretimi, CTC ile dizi tanıma, kısıtlı
çözümleme ve uçtan uca ölçülmüş bir boru hattı.**

*Turkish licence plate recognition: a synthetic data pipeline, a CTC sequence
recogniser, a constrained decoder in C++, and a pipeline measured end to end.
English summary below.*

---

## Sonuç

Hiçbir karara girmemiş **34 plakalık** test kümesinde (157 kırpma), plaka
bazında güven ağırlıklı oylamayla:

| kurulum | doğru okunan plaka |
|---|---|
| elle işaretlenmiş köşelerle | **22/34** (%64.7) |
| **köşeleri model bulunca (tam otomatik)** | **18/34** (%52.9) |

**İkinci satır sistemin gerçek sayısı.** Birincisi tanıyıcının kendi
başarısını gösteriyor ama insanın işaretlediği dört köşeyi varsayıyor;
dağıtımda o köşeleri bir model buluyor ve hatası her şeyin üstüne biniyor.

Aradaki dört plakalık fark bile kesin değil: ayrık on plakanın yedisi kayıp
üçü kazanç, McNemar ile p ≈ 0.34. Yani bu örneklem farkı çözemiyor
([bölüm 18](docs/veri-olcumleri.md)).

Oraya nasıl gelindiği:

| aşama | plaka |
|---|---|
| yalnızca sentetikle eğitim | 4/34 |
| + gerçek veriyle ince ayar | 18/34 |
| + C++ kısıtlı çözümleyici | 22/34 |
| + köşeleri modelin bulması | 18/34 |

**Yol düz gelmedi.** İlk eğitim sıfır verdi, ikincisi 0.42'de takıldı, üreteç
gerçek plakaların %54'ünü hiç üretmiyordu, ve boru hattı bir ara okunacak
hiçbir şey olmayan kırpmalarda tam güvenle plaka uyduruyordu. Hepsi ölçülüp
düzeltildi — 25 bölümlük [ölçüm günlüğü](docs/veri-olcumleri.md).

### Hız

| | |
|---|---|
| yerel CPU, kare başına | 115.4 ms → **8.7 FPS** |
| T4'te GPU'ya düşen iş, kare başına | **8.93 ms** |
| TensorRT FP16 hızlanması | YOLO **24.7x**, tanıma **5.4x** |

FP16 doğruluğu bozmuyor: 157/157 plaka aynı, YOLO kutuları ortalama 0.022
piksel oynuyor. Kayıt 60 fps; sistem o hızda gerçek zamanlı **değil**, ama
bir araç kadrajda saniyelerce kalıyor ve oylama birkaç kare istiyor
([bölüm 19, 24, 25](docs/veri-olcumleri.md)).

### Fazlar

| faz | konu | durum |
|---|---|---|
| 0 | Sentetik üreteç + gerçek veri toplama | ✅ |
| 1 | Köşe regresyonu + kabul etme kapısı | ✅ |
| 2 | Tanıma modeli (CTC) + gerçek veriyle ince ayar | ✅ |
| 3 | Kısıtlı çözümleme (C++) + güven kalibrasyonu | ✅ |
| 4 | ONNX + TensorRT FP16 (T4'te ölçüldü) | ✅ |
| 5 | Zamansal oylama, ByteTrack takibi, C++ boru hattı | ✅ |
| 6 | Uç cihaz ölçümleri | ❌ kapsam dışı — donanım yok |

---

## Neden bu proje böyle kuruldu

Elimizdeki plan Jetson Orin Nano, global shutter kamera ve IR aydınlatma
varsayıyordu. Hiçbiri yok. [docs/on-rapor.md](docs/on-rapor.md) planı gerçek
kısıtlara oturtuyor ve neyin **neden** düştüğünü yazıyor — tez cümlesi dahil:
"uç cihazda 30 FPS" yerine "bulut GPU'da ölçüldü, uç cihaz ölçümü yapılmadı".

Kamera yerine elde olan dashcam kaydı kullanıldı.

---

## Ölçüm disiplini

Bu projede asıl iş model eğitmek değil, **sayıların yalan söylememesini
sağlamak**. Ayrıntısı [docs/veri-olcumleri.md](docs/veri-olcumleri.md) içinde.
Birkaç örnek:

**Test kümesi hiçbir karara girmiyor.** Doğrulama plakaya göre ikiye bölündü:
biri epoch ve eşik seçiminde kullanılıyor, diğeri yalnızca sonda bir kez
okunuyor. İki model ayırt edilemediğinde rapor kümesindeki skoruna bakıp
seçim yapmak reddedildi ([bölüm 13, 16](docs/veri-olcumleri.md)).

**Üreteç tahminle değil ölçümle ayarlandı.** Önce 272 gerçek plaka
etiketlendi, sonra üreteç onlara bakılarak kalibre edildi. Plan yatay
perspektif için ±35° öneriyordu; ölçülen ~7°. Ölçek `uniform(55, 280)` ile
örnekleniyordu, ortancası 167; gerçeğin ortancası 105. Artık gerçek
genişlikler bootstrap ediliyor.

**Aynı hata üç kez tekrarlandı ve deseni yazıldı.** Ölçek doğru ölçülüp yanlış
örneklendi; perspektif doğru ölçülüp yanlış aşamaya taşındı; plaka geometrisi
doğru çizilip yanlış kadrajda sunuldu. Üçünde de ölçüm kusursuzdu — yanlış
olan, ölçümün **nereye ait olduğuydu** ([bölüm 11](docs/veri-olcumleri.md)).

**Beklentiye uyan yanlış sayı, yanlış görünen yanlış sayıdan tehlikeli.** Bir
GPU ölçümü dört satırın dördü de CPU olan bir tablo üretti ve hızlanma 1.02x
çıktığı için "modeller küçük" diye makul göründü. Betiğin kendi stderr'i
"CPU'ya düşülüyor" yazarken tablosu "TensorRT FP16" diyordu
([bölüm 24](docs/veri-olcumleri.md)).

**Bir sonuç yanlış çıktı ve düzeltildi, silinmedi.** 180 kırpmayla "gecede
keskinlik okunabilirliği öngörmüyor" sonucuna varılmıştı. Öngörüyor: %1'den
%62'ye. İlk ölçüm sıralı kuyruğun yalnızca üst ucundan geliyordu.

**Negatif sonuçlar da kayıtta.** Ortak gövdeli çok görevli öğrenme iki işi
birden bozdu; C++ boru hattı Python'dan yavaş çıktı; TensorRT FP32 küçük
modellerde hiçbir şey kazandırmadı. Üçü de ölçülmeseydi tersi aynı derecede
inandırıcı görünürdü.

---

## Veri, ve neden depoda yok

Gerçek plaka görüntüleri ve metinleri **depoda değil**. Plaka Türkiye'de
kişisel veri; kırpmanın kendisi "bağlamsız" sayılabilirdi ama dosya adı kaynak
videoyu ve saniyeyi kodluyor, etiket dosyası da metni ona bağlıyor — birleşim
plaka + yer + zaman ediyor. Eğitilmiş ağırlıklar (`*.pt`, `onnx/`) de aynı
sebeple dışarıda.

Etiketlemenin ölçüsü: 2119 araç kırpması gözden geçirildi, **yalnızca %38'inde
okunur plaka vardı** (811 kırpma / 272 plaka). Kalanı 706 plakasız + 602
okunmaz. Bu oran boru hattı düzeyindeki verimi belirliyor ve bölüm 10-18'deki
her doğruluk sayısının yazılmamış koşuluydu
([bölüm 20](docs/veri-olcumleri.md)).

Depoda yayınlanan şey **kod ve sentetik boru hattı**. Sentetik üreteç tek
komutla çalışıyor ve kimsenin verisine ihtiyaç duymuyor:

```bash
python scripts/generate_plates.py --adet 200 --sheet    # örnek tabakası
python scripts/generate_plates.py --adet 100000         # ~29 dk
```

---

## Akış

**Veri**

```bash
python scripts/harvest_plates.py <video>        # araç kırpmaları çıkar
python scripts/build_queue.py --kaynak <kayit>  # keskinliğe göre sırala
python scripts/label_plates.py --only <kuyruk>  # 4 köşe + metin
python scripts/export_plates.py                 # dikleştir ve ölç
python scripts/generate_plates.py --adet 100000 # sentetik küme
```

**Modeller**

```bash
python scripts/train_recognizer.py --cihaz cuda --epoch 20   # bulutta
python scripts/finetune.py                      # gerçek veriyle ince ayar
python scripts/train_corners.py                 # köşe regresyonu
python scripts/train_presence.py                # "okunur plaka var mı" kapısı
```

**Çözümleme ve ölçüm**

```bash
g++ -O2 -std=c++17 -o cpp/decode.exe cpp/decode.cpp
python scripts/export_logits.py && ./cpp/decode.exe
python scripts/score_decoder.py                 # kısıtın kazancı
python scripts/calibrate.py                     # güven eğrisi
python scripts/end_to_end.py                    # köşe hatasının bedeli
python scripts/vote.py                          # zamansal oylama
python scripts/track_pipeline.py                # ByteTrack + uçtan uca
python scripts/benchmark.py                     # gecikme
```

**Dağıtım**

```bash
python scripts/export_onnx.py                   # ONNX + sayısal doğrulama
g++ -O2 -std=c++17 -o cpp/pipeline.exe cpp/pipeline.cpp -Icpp/dis
python scripts/compare_cpp.py                   # C++ ile Python aynı mı
python scripts/trt_paket.py                     # TensorRT için bulut paketi
```

**Testler**

```bash
python tests/test_dilbilgisi.py                 # plaka dilbilgisi, C++/Python
python tests/test_etiketleme.py                 # etiketleyici kip davranışı
```

Eğitim **bulutta** yapılır. Yerel GTX 1080 ağır yük altında dört kez düştü;
sonuncusu `cuda if available` diyen bir betikti ve makineyi resetletti. Cihaz
varsayılanı `cpu`, GPU açıkça istenmeli.

---

## English

A Turkish licence plate recogniser built around a synthetic data pipeline,
because the plan it started from assumed hardware that does not exist here — no
Jetson, no global shutter camera, no IR illuminator.

**The result.** On a 34-plate test set that entered no decision, the full
automatic pipeline reads **18 plates** correctly; with corners marked by hand
rather than predicted it reads 22. The second number is the recogniser's own
performance and the first is the system's, and this page leads with both
because only one of them is what a camera would deliver. Even that four-plate
gap is not resolvable here: of ten discordant plates seven are losses and three
are gains, McNemar p ≈ 0.34.

**How it got there.** Synthetic-only training read 4 of 34. Fine-tuning on real
plates took it to 18, a constrained beam search in C++ over the Turkish plate
grammar to 22, and putting a model in place of the hand-marked corners brought
it back to 18. Every step is measured; the log runs to 25 sections.

**The work is mostly in making the numbers honest.** Validation is split by
plate into a half that chooses epochs and thresholds and a half that is read
once at the end. When two models could not be told apart on the selection half,
picking the one that scored higher on the report half was refused, because that
would have turned the reported number into a decision.

**Three failures share one shape.** The scale distribution was measured
correctly and sampled wrongly; the perspective was measured correctly and
carried to the wrong stage; the plate geometry was drawn correctly and framed
wrongly. Each measurement was sound. What was wrong each time was where it
belonged.

**A wrong number that matches your expectation is worse than one that looks
wrong.** A GPU benchmark once produced a four-row table in which every row was
the CPU, and 1.02x looked plausible for small launch-bound models. The script's
own stderr said it was falling back to the CPU while its summary said TensorRT
FP16.

**Negative results are kept.** Multi-task training on a shared body damaged
both tasks; the C++ pipeline came out slower than Python because hand-written
image operations lose to OpenCV's kernels; TensorRT at FP32 bought nothing for
models this small. Unmeasured, the opposite would have been just as believable.

**Speed.** 115.4 ms per frame on this machine's CPU, 8.7 FPS. On a T4 the two
GPU stages come to 8.93 ms per frame, with TensorRT FP16 giving 24.7x on the
detector and 5.4x on the recogniser while all 157 plates still decode
identically and detection boxes move by 0.022 px on average. Not real-time at
the 60 fps the footage was recorded at; comfortably enough for a task where a
vehicle stays in shot for seconds.

**Real plate images, texts and trained weights are not in this repository.** A
plate is personal data; a crop alone might be context-free, but the filename
encodes the source recording and timestamp and the label file ties the text to
it. What is published is the code and the synthetic pipeline, which needs
nobody's data to run.
