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

## 2. Etiketleme: isabet kaynağa göre ve kuyruk sırasına göre değişiyor

**Nihai durum: 2119 kırpma etiketlendi, 811 okunabilir, 272 farklı plaka.**

```
ok         811  (%38)
plakasiz   706  (%33)
okunmaz    602  (%28)
```

İlk turda kaynağa göre ayrıştırılmıştı ve isabet 39/31/37 çıkmıştı. Yağmur ilk
139 kırpmada **%12** veriyordu; kuyruk keskinliğe göre sıralanınca %31'e çıktı.
Sıralama, aynı emekle iki buçuk kat plaka demek.

### Etiketler bir kez kaybedildi

İlk turun 1875 etiketi `git filter-branch` sırasında silindi: komut iş bitince
çalışma ağacını yeniden yazılmış HEAD'e döndürüyor ve geçmişten çıkarılan
dosyaları diskten de siliyor, ardından `gc --prune=now` kurtarılabilir
nesneleri yok etti. Kaynak kırpmalar (3011) durduğu için yeniden etiketlendi.

Sonuç öncekinden iyi: **272 plaka**, kaybedilen 240'ın üzerinde. En/boy oranı
ortancası da 4.2'den **4.6**'ya çıktı (gerçek plaka 4.7:1) — ikinci turda köşe
işaretlemesi daha isabetli yapıldı.

Alınan önlem: etiketleyici artık her kayıtta depo **dışına** ikinci bir kopya
yazıyor. Saatlerce emek tek kopya halinde, üstelik depo işlemlerinin
menzilinde durmamalı.

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

Yeni bir plakanın maliyeti iki katına çıktı. İkinci turda kuyruk baştan
keskinliğe göre sıralı olduğu için verim daha yüksek başladı, ama doygunluk
aynı yere vardı: **811 okunabilir kırpma, 272 farklı plaka** (2.98
kırpma/plaka).

Kuyruğun son 891 kırpması (keskinlik 35 altı) toplam 8 okunabilir plaka
veriyordu; oraya hiç girilmedi. Bu, ölçülen bant tablosunun doğrudan
kullanıldığı bir karar.

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
| 1 | 194 (%71) |
| 3+ | **48** |

Yani zamansal oylama kazancı yalnızca **48 plaka** üzerinde ölçülebilir. Bu,
projenin manşet iddiasının dayanacağı taban ve şimdiden yazılıyor — sonradan
"neden bu kadar az" diye sorulmasın.

---

## 6. Kapsama ve çarpıklık

- **Harf:** 23 harfin 23'ü geçiyor.
- **İl kodu:** 25 farklı, ama **272 plakanın 222'si "34"** (%82).

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


---

## 9. Nihai gerçek veri seti ve sentetikle farkı

811 dikleştirilmiş plaka, 272 farklı. Ölçülenler:

| ölçü | %10 | ortanca | %90 |
|---|---|---|---|
| kaynak genişlik | 69 px | 105 px | 258 px |
| kaynak yükseklik | 16 px | 24 px | 54 px |
| en/boy oranı | 3.9 | **4.6** | 5.2 |
| perspektif eğriliği | 0.0 | 0.0 | 0.05 |

Keskinlik dağılımının sentetikle karşılaştırması:

| | %5 | %10 | %25 | ortanca | %75 | %90 |
|---|---|---|---|---|---|---|
| gerçek (811) | 13 | 17 | 29 | **59** | 132 | 330 |
| sentetik (100k) | 17 | 20 | 32 | **88** | 300 | 785 |

Alt çeyrek oturuyor; üst yarı sentetikte hâlâ daha temiz. Sentetiğin **%0.0**'ı
gerçeğin %5 eşiğinin altında — keskinlik tabanı görevini yapıyor.

**Sentetik küme yeniden üretilmedi.** Gerekçe bölüm 8'dekiyle aynı: aşağı
akışta bir metrik olmadan dağılım kovalamak tahmin yürütmektir. Model eğitilip
gerçek veride ölçülünce alan farkının zarar verip vermediği görülecek; verirse
yeniden üretmek 29 dakika. Üreteç ölçek dağılımını ve keskinlik tabanını
çalışma anında `data/plates` içinden okuduğu için yeniden üretim otomatik
olarak yeni dağılıma göre kalibre olur.


---

## 10. İlk eğitim koşusu: sıfır, ve sebebi ölçüm değil kusur

100k sentetikle 20 epoch, Kaggle T4. Sonuç:

```
epoch  1  kayıp 6.444  tam dizi 0.000  karakter 0.144  düzenleme 6.87
epoch 10  kayıp 0.185  tam dizi 0.000  karakter 0.207  düzenleme 6.20
epoch 20  kayıp 0.047  tam dizi 0.000  karakter 0.218  düzenleme 6.11
```

Eğitim kaybı 6.44'ten **0.047**'ye indi — model sentetiği ezberledi. Gerçek
veride ise 20 epoch boyunca **tek plaka bile okumadı** ve karakter doğruluğu
hiç kıpırdamadı.

Bu deseni alan farkı üretmez. Kademeli bir fark olsaydı yavaş bir tırmanış
görülürdü; **düz çizgi**, modelin bu görüntüleri hiç tanımadığını söyler.

### Kusur: sentetik ile gerçek farklı kadrajdaydı

İki görüntüyü yan yana koyunca tartışmasız görüldü:

- **Gerçek:** `export_plates.py` dört köşeyi kadrajın tamamına oturtuyor.
  Plaka kareyi **kenardan kenara dolduruyor** — eğim yok, arka plan yok.
- **Sentetik:** plaka kadrajın **içinde küçük ve eğik**, etrafında koyu arka
  plan.

Model "koyu zeminde küçük eğik plaka" öğrenip "kadrajı dolduran plaka" ile
sınandı. Karakterler tamamen farklı ölçek ve konumda.

### Kök sebep: doğru ölçüm, yanlış aşama

Bölüm 8'deki perspektif ölçümü (yaw ~7°, pitch ~20°) **doğruydu** — ama plakanın
*sahnedeki* eğimini ölçüyordu. Tanıma modeli plakayı sahnede hiç görmüyor:

```
dedektör → dört köşe → DİKLEŞTİRME → tanıma
```

O ölçüm **Faz 1'in köşe regresyonu** için geçerli, Faz 2 için alakasız. Aynı
sayıyı yanlış aşamaya taşımak, ölçümün kendisinden daha sinsi bir hata: sayı
doğru olduğu için sorgulanmıyor.

### Düzeltme

Üreteç artık plakayı kadrajı dolduracak şekilde çiziyor ve tek bozulma olarak
**köşe işaretleme artık hatasını** modelliyor (`KOSE_HATASI = 0.05`): insanın
ya da dedektörün köşeyi birkaç piksel kaydırmış olması. Plaka her zaman kadrajı
dolduruyor, yalnızca kenarları biraz kayıyor.

Ayrıca karakter yüksekliği çarpanı 0.62'den **0.70**'e çıkarıldı. 0.62
uydurmaydı; gerçek plakada karakter 80 mm, plaka 110 mm — yani 0.73, kenarlığa
pay bırakılarak 0.70.
