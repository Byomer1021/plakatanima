# plakatanima

**Türk plakası tanıma — sentetik veri üretimi, CTC ile dizi tanıma, ve gerçek
zamanlı boru hattı.**

*Turkish licence plate recognition: a synthetic data pipeline, a CTC sequence
recogniser, and a real-time inference path. English summary below.*

---

## Durum

Faz 0, 2 ve 3 hazır. Sentetikle eğitilen, gerçek plakalarla ince ayarlanan
ve C++ kısıtlı çözümleyiciden geçen tanıyıcı, **hiçbir karara girmemiş**
34 plakalık test kümesinde plakaların **22'sini** doğru okuyor (%64.7);
karakter doğruluğu 0.96, ortalama düzenleme mesafesi 0.28.

| aşama | doğru okunan plaka |
|---|---|
| yalnızca sentetik | 4/34 |
| + gerçek veriyle ince ayar | 18/34 |
| + kısıtlı çözümleyici | **22/34** |

Yol buraya düz gelmedi: ilk koşu sıfır verdi, ikincisi 0.42'de takıldı,
üreteç gerçek plakaların %54'ünü hiç üretmiyordu. Hepsi ölçülüp
düzeltildi ([docs/veri-olcumleri.md](docs/veri-olcumleri.md) bölüm 10-14).

| faz | konu | durum |
|---|---|---|
| 0 | Sentetik üreteç + gerçek veri toplama | ✅ |
| 1 | Köşe regresyonu | ✅ uçtan uca ölçüldü |
| 2 | Tanıma modeli, CTC | ✅ eğitildi + gerçek veriyle ince ayar |
| 3 | Kısıtlı çözümleme (C++) + güven kalibrasyonu | ✅ |
| 4 | TensorRT FP16/INT8 | ⏳ bulut GPU'da |
| 5 | Zamansal oylama ✅ · takip ve C++ boru hattı ⏳ | 🔶 |
| 6 | Uç cihaz ölçümleri | ❌ kapsam dışı — donanım yok |

---

## Neden bu proje böyle kuruldu

Elimizdeki plan Jetson Orin Nano, global shutter kamera ve IR aydınlatma
varsayıyordu. Hiçbiri yok. [docs/on-rapor.md](docs/on-rapor.md) planı gerçek
kısıtlara oturtuyor ve neyin **neden** düştüğünü yazıyor — tez cümlesi dahil:
"uç cihazda 30 FPS" yerine "bulut GPU'da ölçüldü, uç cihaz ölçümü yapılmadı".

Kamera yerine elde olan iki saatlik dashcam kaydı kullanıldı. Ölçüldü: kare
başına ~1.08 araç, plakası okunacak kadar yakın.

---

## Ölçüm disiplini

Bu projede asıl iş model eğitmek değil, **sayıların yalan söylememesini
sağlamak**. Ayrıntısı [docs/veri-olcumleri.md](docs/veri-olcumleri.md) içinde.

**Üreteç tahminle değil ölçümle ayarlandı.** Sıra bilerek böyle kuruldu: önce
690 gerçek plaka etiketlendi, sonra üreteç onlara bakılarak kalibre edildi.

- Plan yatay perspektif için ±35° öneriyordu; ölçülen **~7°**. Dashcam öndeki
  aracın arkasında ve yukarısında duruyor, sağa-sola açı küçük kalıyor.
  ±35° ile eğitmek modele hiç karşılaşmayacağı görüntüler öğretmek olurdu.
- Ölçek `uniform(55, 280)` ile örnekleniyordu, ortancası 167; gerçeğin
  ortancası **105**. Sentetik plakalar sistematik olarak fazla büyük ve fazla
  keskin çıkıyordu. Artık gerçek genişlikler **bootstrap** ediliyor.
- Keskinlik dağılımı üç adımda hizalandı; alt yarı birebir oturuyor. Üst yarı
  hâlâ gerçekten temiz ve **orada bilerek duruldu** — aşağı akışta bir metrik
  olmadan dağılım kovalamak tahmin yürütmektir.

**Bir sonuç yanlış çıktı ve düzeltildi.** 180 kırpmayla "gecede keskinlik
okunabilirliği öngörmüyor" sonucuna varılmıştı. Öngörüyor: %1'den %62'ye. İlk
ölçüm sıralı kuyruğun **yalnızca üst ucundan** geliyordu ve eğri orada düz.
Ölçüm doğruydu; kesilmiş aralıktan genelleme yanlıştı.

---

## Veri, ve neden depoda yok

Gerçek plaka görüntüleri ve metinleri **depoda değil**. Plaka Türkiye'de
kişisel veri; kırpmanın kendisi "bağlamsız" sayılabilirdi ama dosya adı kaynak
videoyu ve saniyeyi kodluyor, etiket dosyası da metni ona bağlıyor — birleşim
plaka + yer + zaman ediyor.

Depoda yayınlanan şey **kod ve sentetik boru hattı**. Sentetik üreteç tek
komutla çalışıyor ve kimsenin verisine ihtiyaç duymuyor:

```bash
python scripts/generate_plates.py --adet 200 --sheet    # örnek tabakası
python scripts/generate_plates.py --adet 100000         # ~29 dk, 0.54 GB
```

---

## Akış

```bash
python scripts/harvest_plates.py <video>        # araç kırpmaları çıkar
python scripts/build_queue.py --kaynak <kayit>  # keskinliğe göre sırala
python scripts/label_plates.py --only <kuyruk>  # 4 köşe + metin
python scripts/export_plates.py                 # dikleştir ve ölç
python scripts/generate_plates.py --adet 100000 # sentetik küme
python scripts/train_recognizer.py --cihaz cuda --epoch 20
python scripts/finetune.py                      # gerçek veriyle ince ayar
g++ -O2 -std=c++17 -o cpp/decode.exe cpp/decode.cpp
python scripts/export_logits.py && ./cpp/decode.exe
python scripts/score_decoder.py                 # kısıtın kazancı
python scripts/calibrate.py                     # güven eğrisi
python scripts/train_corners.py                 # köşe regresyonu
python scripts/end_to_end.py                    # köşe hatasının bedeli
python scripts/vote.py                          # zamansal oylama
python scripts/benchmark.py                     # gecikme
```

Eğitim **bulutta** yapılır. Yerel GTX 1080 ağır yük altında dört kez düştü;
sonuncusu bu betiğin `cuda if available` diyen ilk sürümüydü ve makineyi
resetletti. Cihaz varsayılanı artık `cpu`, GPU açıkça istenmeli.

---

## English

A Turkish licence plate recogniser built around a synthetic data pipeline,
because the plan it started from assumed hardware that does not exist here — no
Jetson, no global shutter camera, no IR illuminator. The scope document records
what was dropped and why, including the headline claim: "30 FPS on an edge
device" became "real-time pipeline measured on a cloud GPU, edge not measured".

**The generator is calibrated against real plates rather than guessed.** The
project was sequenced so 690 real plates were labelled first. That ordering paid
for itself twice. The plan proposes horizontal perspective of ±35 degrees; the
measured value is about 7, because a dashcam sits behind and above the plate
ahead. And plate width was being sampled uniformly with a median of 167 where
the real median is 105, so every synthetic plate was drawn too large and stayed
too sharp — widths are now bootstrapped from the measurements.

**One conclusion in the log was wrong and is corrected rather than dropped.**
With 180 crops, sharpness looked unrelated to readability at night. It is
strongly related: 1% below a threshold, 62% above. Those 180 crops came from a
sharpness-ordered queue, so they covered only the top of the range where the
curve is flat. The measurement was sound; generalising from a truncated range
was not.

**Real plate images and texts are not in this repository.** A plate is personal
data; a crop alone might be context-free, but the filename encodes the source
recording and timestamp and the label file ties the text to it. What is
published is the code and the synthetic pipeline, which needs nobody's data to
run.
