# Veri Ölçümleri — Faz 0

Hasat ve etiketleme sırasında ölçülenler. Amaç sonucu güzel göstermek değil,
**hangi kararın neye dayandığını** kayda geçirmek.

---

## 1. Hasat: filtreler üçte ikiyi eliyor

Üç dashcam kaydından, 2 saniyede bir kare, kaynak çözünürlükte:

| kaynak | kare | kırpma | elenen (yan görünüm / kadraj kenarı) |
|---|---|---|---|
| maltepe (1440p) | 2264 | 900 | 1587 / 456 |
| yağmur (4K) | 558 | 1152 | 416 / 315 |
| gece (4K) | 793 | 959 | 303 / 292 |
| **toplam** | 3615 | **3011** | 2306 / 1063 |

İlk denemede 40 kırpmanın ancak dörtte birinde plaka vardı; kalanı araçların
**yan görünümüydü** ve yandan bakınca aracın alt şeridinde plaka değil tekerlek
var. "Aracın alt %45'i" varsayımı arkadan doğru, yandan yanlış.

Ayırt edici en/boy oranı: arkadan görünen otomobil kabaca kare, yandan görünen
2-3 kat geniş. Eşik 1.8, artı kadraj kenarına değen kutular (yarım araç, plaka
kesik olabilir).

Yağmur ve gece kare başına maltepe'den 3-5 kat fazla kırpma verdi — kaynak 4K
olduğu için daha çok araç 240 px eşiğini geçiyor.

---

## 2. Etiketleme: isabet kaynağa göre değişiyor

1875 kırpma etiketlendi.

| kaynak | etiketli | okunabilir | isabet |
|---|---|---|---|
| maltepe | 900 | 350 | 39% |
| yağmur | 395 | 123 | 31% |
| gece | 580 | 217 | 37% |

Yağmur ilk 139 kırpmada **%12** veriyordu; kuyruk keskinliğe göre sıralanınca
%31'e çıktı. Sıralama, aynı emekle iki buçuk kat plaka demek.

---

## 3. Keskinlik: yanlış bir sonuç ve düzeltilmesi

Laplacian varyansı etiketleme sırasında otomatik ölçülüyor (insana sorulmuyor:
nesnel olsun ve etiketleyene maliyeti olmasın diye).

**İlk sonuç yanlıştı.** 180 gece kırpmasıyla şu tablo çıkmıştı:

```
50-80    64%
80-120   64%
120+     45%
```

Buradan "gecede keskinlik okunabilirliği öngörmüyor" sonucu çıkarıldı. Yanlıştı.
Kuyruk sıralı olduğu için o 180 kırpma **aralığın yalnızca üst ucundan**
geliyordu ve eğri orada zaten düz. 580 kırpmayla tam aralık görününce:

| keskinlik | n | okunabilir |
|---|---|---|
| 0-35 | 67 | **1%** |
| 35-45 | 100 | 13% |
| 45-55 | 82 | 34% |
| 55-70 | 143 | 41% |
| 70-90 | 111 | 61% |
| 90+ | 77 | 62% |

Keskinlik **çok güçlü** öngörüyor: %1'den %62'ye. İlk sonuç ölçümün yanlış
olmasından değil, **kesilmiş bir aralıktan genelleme yapılmasından** çıktı.

Bu yüzden kuyruk eşik değil sıralama kullanıyor: sert bir eşik, altında kalan
okunabilir plakaları veri setine hiç sokmazdı ve kimse fark etmezdi.

---

## 4. Doygunluk: bu görüntü elindekini verdi

**En önemli ölçüm bu.**

```
ilk 586 okunabilir kırpma  ->  223 farklı plaka   (2.6 kırpma/plaka)
sonraki 104 kırpma         ->   17 farklı plaka   (6.1 kırpma/plaka)
```

Yeni bir plakanın maliyeti iki katına çıktı. Toplam **690 okunabilir kırpma,
240 farklı plaka**.

Ölçümün gerçek paydası kırpma sayısı değil plaka sayısı: aynı aracı 30 saniye
takip edince aynı plaka onlarca kırpmada geçiyor (en çok tekrarlanan 82 kez).
Bölme kırpmaya göre yapılırsa aynı plaka hem eğitimde hem testte olur ve skor
şişer.

Daha fazla etiketleme bu sayıyı anlamlı ölçüde büyütmez. Büyütecek olan şey
**yeni çekim**, ve o şimdilik kapsam dışı.

---

## 5. Zamansal oylamanın ölçülebilirlik sınırı

Planın tez cümlesi tek kare doğruluğunu zamansal oylamayla araç bazında tam
eşleşmeye taşımayı vaat ediyor. O kazancı ölçmek için **aynı plakanın birden
fazla görünümü** gerekiyor.

| plaka başına kırpma | plaka sayısı |
|---|---|
| 1 | 171 (%71) |
| 2 | 31 |
| 3+ | **38** |

Yani zamansal oylama kazancı yalnızca **38 plaka** üzerinde ölçülebilir. Bu,
projenin manşet iddiasının dayanacağı taban ve şimdiden yazılıyor — sonradan
"neden bu kadar az" diye sorulmasın.

---

## 6. Kapsama ve çarpıklık

- **Harf:** 23 harfin 23'ü geçiyor. Yalnızca `I` iki kez.
- **İl kodu:** 23 farklı, ama **240 plakanın 201'i "34"** (%84).

İkincisinin doğrudan bir sonucu var: **sentetik üreteç il kodunu 01-81 arasında
düzgün dağıtmak zorunda.** Gerçek veri İstanbul ağırlıklı olduğu için model
"34" ezberlemeye meyilli olacak ve başka ilde çöker. Üretecin görevi bu
çarpıklığı taşımak değil, dengelemek.

---

## 7. İki satırlı plakalar

Örneklerde motosiklet plakası çıktı: `34 HNU` üstte, `227` altta. Plan yalnızca
tek satırlı 520×110 formatını modelliyor ve bütün tanıma tasarımı buna dayanıyor
(CTC yatay şeritte, 32×128 girdi, 4.7:1 oran).

Silinmedi, `iki_satirli` durumuyla işaretlendi: veri elde kalıyor, kapsam dışı
olduğu kayıtlı, ileride ayrı bir kafa eğitilmek istenirse örnekler hazır.
**Kapsamı daraltmak ile veriyi atmak aynı şey değil.**


---

## 8. Sentetik üreteç kalibrasyonu

Üretecin bozulma ayarları tahmin edilmedi; 690 gerçek plakaya bakılarak
ayarlandı. Projenin sırası bunun için böyle kurulmuştu.

### Perspektif: planın önerisi bu veriye uymuyor

Etiketli dört köşeden ölçülen:

| eksen | ortanca | %90 | en büyük | planın önerisi |
|---|---|---|---|---|
| yatay (yaw) | 0.023 | 0.057 (~7°) | 0.125 (~14°) | **±35°** |
| düşey (pitch) | 0.074 | 0.181 (~20°) | 0.586 (~49°) | ±25° |
| düzlem içi dönme | 1.3° | 4.5° | 14.7° | ±10° |

Yatay eğim planın önerdiğinin **beşte biri**. Sebebi senaryoda: dashcam öndeki
aracın arkasında ve yukarısında; sağa-sola açı küçük, yukarıdan aşağı açı
büyük. Üreteç ölçülen aralıklara ayarlandı (yaw ±15, pitch ±30, dönme ±10).

**Bu sayılar senaryoya özgü.** Yol kenarı sabit kamerası büyük yatay açı görür;
oradaki bir sistem için yeniden ölçülmeli.

### Ölçek: aralık değil dağılım

İlk sürüm plaka genişliğini `uniform(55, 280)` ile örnekliyordu, ortancası 167.
Gerçeğin ortancası **105**. Sonuç: sentetik plakalar sistematik olarak fazla
büyük çizildi, fazla keskin kaldı, ve müfredat bu etkinin altında kayboldu —
zorluk 0'dan 1'e giderken keskinlik ortancası yalnızca 177'den 116'ya indi.

Çözüm: gerçek genişlikleri **bootstrap** ile örnekle. Dağılımın şekli (sağa
çarpık) tahmin edilmiyor, aynen taşınıyor.

### Keskinlik dağılımı: üç adımda hizalandı

| aşama | %5 | %10 | %25 | ortanca | %75 | %90 |
|---|---|---|---|---|---|---|
| **gerçek (690)** | 14 | 19 | 34 | **69** | 147 | 362 |
| sentetik, ilk sürüm | – | 13 | 46 | 162 | 444 | 1034 |
| + ölçek bootstrap | – | 7 | – | 55 | – | 703 |
| + keskinlik tabanı | 17 | 21 | 35 | 105 | 352 | 863 |
| + sıkıştırılmış rampa | 18 | 20 | 36 | **91** | 304 | 732 |

Alt yarı birebir oturuyor (%5, %10, %25 neredeyse aynı). Üst yarı hâlâ
gerçekten temiz; kalan fark ölçeğin büyük ve bulanıklığın uygulanmadığı
örneklerden geliyor.

**Burada durduk.** Dağılımı daha fazla kovalamak, aşağı akışta bir metrik
olmadan tahmin yürütmek olurdu. Sentetik küme gerçeğin zor ucunu kapsıyor;
kalan fark gerçek veriyle ince ayarda kapanacak ve transferin gerçekten olup
olmadığı model eğitilince **ölçülebilir**.

### Keskinlik tabanı ve kalan risk

Taban, **okunabilir** gerçek plakaların %5'lik dilimi (14). Yani sentetik
hiçbir örnek, okunabildiği bilinen en bulanık gerçek plakadan daha bozuk değil.

Kalan risk: keskinlik zayıf bir vekil (bölüm 3'te ölçüldü). Parlama ya da düşük
kontrast yüzünden eşiğin üstünde olup yine de okunamayan örnekler olabilir ve
onların etiketi kurtarılamaz. Sayısı ölçülmedi.
