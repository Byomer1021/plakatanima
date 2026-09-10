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

---

## 11. İkinci koşu: model öğrendi, ama karakter *düşürüyordu*

Bölüm 10'un düzeltmesiyle yeniden üretilen 100k, aynı ayarla yeniden koşuldu.

```
epoch  1  kayıp 5.886  tam dizi 0.000  karakter 0.107  düzenleme 7.24
epoch  3  kayıp 0.375  tam dizi 0.000  karakter 0.418  düzenleme 4.55
epoch  6  kayıp 0.098  tam dizi 0.012  karakter 0.356  düzenleme 5.03
epoch 12  kayıp 0.043  tam dizi 0.008  karakter 0.406  düzenleme 4.65
epoch 20  kayıp 0.004  tam dizi 0.008  karakter 0.400  düzenleme 4.69
```

Bölüm 10'daki düz çizgi gitti: karakter doğruluğu 0.107'den 0.418'e çıktı.
Kadraj kusuru gerçekten kusurdu ve düzeltilmesi işe yaradı.

**Eğrinin şekli önemli ve ilk bakışta yanlış okundu.** Epoch 3-6 arası düşüş
(0.418 → 0.356) aşırı-öğrenme sanıldı. Yirmi epoch'un tamamı görülünce desen
başka: değerler epoch 3'ten sonra **0.356-0.418 bandında salınıyor**, eğitim
kaybı 0.375'ten 0.004'e (yüz kat) inerken. Bu düşüş değil **doygunluk** —
model sentetiğin gerçek hakkında öğretebileceğini üç epoch'ta alıyor, kalan
on yedi epoch hiçbir şey eklemiyor. Kısa pencereden bakıp trend çıkarmak,
bölüm 3'teki kesilmiş aralık hatasının aynısı.

### `tam dizi` bu ölçekte model seçmek için kullanılamaz

Doğrulama 245 kırpma. `tam dizi 0.012` demek **3 kırpma** demek; iki epoch
arasındaki 0.008 → 0.012 farkı tek bir kırpma. `best.pt` bu sayının artışına
bakarak seçiliyordu, yani gürültüye göre seçiyordu. Ölçüt **düzenleme
mesafesi** yapıldı: her kırpmadan sinyal alıyor. Ayrıca her epoch `son.pt`
yazılıyor.

### Arıza: uzunluk çökmesi

Ağırlık yerelde açılıp doğrulama kümesi tek tek çözümlendi:

```
ortalama hedef  7.82 karakter
ortalama tahmin 4.76 karakter
245 kırpmanın 244'ünde tahmin hedeften KISA
uzunluğu tutturduğu 18 kırpmada karakter doğruluğu 0.735  (genel 0.372)
```

Model karakterleri okuyabiliyor; çıkaramıyor. Uzunluğu tutturduğu yerde
doğruluk iki katına çıkıyor. Üç aday elendi:

| aday | ölçüm | sonuç |
|---|---|---|
| Çözümleyici/mimari kısa basıyor | sentetiğin *zor* ucunda uzunluk farkı **−0.10**, tam dizi 0.827 | elendi |
| Gerçek kırpmalar daha bulanık | gerçekte uzunluk hatası keskinlikle **değişmiyor**: en bulanık üçte bir −3.41, en keskin üçte bir −3.01 | elendi |
| Ölçek farkı | aşağıda | **sebep** |

İkinci satır özellikle önemli: en keskin üçte birin keskinliği (1406) sentetiğin
ortancasından (875) yüksek, yani sentetikten *daha temiz* gerçek kırpmalar bile
üç karakter düşürüyor. Bulanıklık hipotezi bu tek ölçümle düştü.

### Kök sebep: metin kadrajı doldurmuyordu

811 gerçek kırpma ile sentetik yan yana ölçüldü (ikisi de modelin gördüğü
32×128 halde):

| | dikey doluluk | yatay doluluk | karakter adımı |
|---|---|---|---|
| sentetik (8 karakterli) | 0.781 | 0.867 | 12.25 px |
| **gerçek** (8 karakterli) | **0.969** | **1.000** | **14.12 px** |

Üreteç fiziksel olarak doğru plakayı çiziyordu: kenarlık, mavi TR bandı, kenar
payı. Ama model plakayı görmüyor — dört köşeden **dikleştirilmiş kırpmayı**
görüyor ve o kırpmada metin kadraja yapışık. Model "karakter şu boyuttadır"
diye öğrenip %15 daha büyüğüyle karşılaştı ve sembol düşürdü.

**Bu, aynı hatanın üçüncüsü.** Bölüm 8'de ölçek dağılımı doğru ölçülüp yanlış
örneklenmişti; bölüm 10'da perspektif doğru ölçülüp yanlış aşamaya taşınmıştı;
burada plaka geometrisi doğru çizilip yanlış kadrajda sunuldu. Üçünün de ortak
yanı, ölçümün kendisinin kusursuz olması. Yanlış olan, ölçümün **nereye ait
olduğu**.

### Düzeltme ve doğrulaması

Üretece `metne_kirp()` katmanı eklendi: kadraj metnin sınırlarına daraltılıyor,
daralma oranı 811 gerçek kırpmadan **bootstrap** ediliyor (genişlik ve
keskinlikte olduğu gibi; dağılımın şekli tahmin edilmiyor taşınıyor).

Ölçümün 1.00'de yığılması sansür belirtisi: kadraj dışına taşan metin de 1.00
okunur. Bu yüzden az miktarda taşma da üretiliyor — ölçüm bunu gösteremez,
ama yığılmanın sebebi budur ve gerçek kırpmalarda kesilmiş karakterler gözle
görülüyor.

600 örneklik denemede:

| | dikey | yatay | karakter adımı |
|---|---|---|---|
| eski sentetik | 0.781 | 0.823 | 12.71 px |
| **yeni sentetik** | 1.000 | 0.965 | 15.24 px |
| gerçek | 1.000 | 1.000 | 14.08 px |

Karakter adımı artık %10 eksik yerine %8 fazla. Kalan fark kovalanmadı: aşağı
akışta bir metrik olmadan dağılım kovalamak tahmin yürütmektir ve metrik artık
mevcut — bir sonraki koşu.

---

## 12. Üçüncü koşu: ölçek düzeltmesinin bedeli ölçüldü

Bölüm 11'in `metne_kirp()` katmanıyla yeniden üretilen 100k, aynı ayarla:

```
epoch  1  kayıp 5.375  tam dizi 0.000  karakter 0.367  düzenleme 4.95
epoch  4  kayıp 0.064  tam dizi 0.106  karakter 0.681  düzenleme 2.49
epoch 12  kayıp 0.012  tam dizi 0.069  karakter 0.589  düzenleme 3.22
epoch 20  kayıp 0.000  tam dizi 0.155  karakter 0.678  düzenleme 2.51
```

| | 2. koşu | 3. koşu |
|---|---|---|
| `karakter` | 0.400 | **0.678** |
| `tam dizi` | 0.008 (2 kırpma) | **0.155** (38 kırpma) |
| `düzenleme` | 4.69 | **2.51** |

Bölüm 11'de kurulan çıkarım — "ölçek farkı sebep, düzeltilirse doğruluk
artar" — o zaman ölçülmemişti, çıkarımdı. Ölçüldü ve tuttu. Epoch 1'de
`karakter` 0.367; önceki koşunun **yirmi epoch sonunda** vardığı yerin
neredeyse iki katı.

### Seçim ölçütü hâlâ tam oturmadı

Bölüm 11'de `tam dizi` gürültülü olduğu için ölçüt düzenleme mesafesi
yapılmıştı. Bu koşuda ikisi **ayrıştı**:

| epoch | düzenleme | tam dizi |
|---|---|---|
| 4 | **2.49** ← seçilen | 0.106 (26 kırpma) |
| 20 | 2.51 | **0.155** (38 kırpma) |

Düzenleme mesafesi arasında %0.8 fark var; tam dizide %46. `best.pt` epoch
4'ü aldı, yani ürün açısından önemli olan ölçütte **daha kötü** olanı.

Ders: 245 kırpmada iki ölçütün ikisi de tek başına yeterli değil. Düzenleme
mesafesi kararlı ama plakanın tamamının okunmasını izlemiyor; tam dizi onu
izliyor ama kırpma sayısı çözünürlüğü vermiyor. Şimdilik `son.pt` her epoch
yazıldığı için hiçbir ağırlık kaybolmuyor — seçim ölçütünü tek bir sayıya
indirmek yerine iki aday yerelde karşılaştırılacak.

### Nerede duruyoruz

Plan tek kare tam dizi doğruluğunu %90-95 bandına koyuyordu; ölçülen
**%15.5**. Aradaki fark hâlâ büyük ve iki bilinen kaldıraç var:

1. **Gerçek veri eğitimde hiç kullanılmadı.** 272 plakanın tamamı doğrulamada.
   Eğitim yarısı (204 plaka / ~566 kırpma) ince ayar için duruyor.
2. **Faz 3'ün kısıtlı çözümleyicisi yazılmadı.** Ortalama düzenleme mesafesi
   2.51; geçerli plaka biçimi (il 01-81, düzen kalıpları) kısıtı bu hataların
   bir kısmını kapatır. Ne kadarını kapattığı ölçülecek, tahmin edilmeyecek.

---

## 13. Gerçek veriyle ince ayar, ve ilk kez dürüst bir test kümesi

Üç eğitim koşusunun üçünde de gerçek plakaların **tamamı** doğrulamadaydı;
hiçbiri eğitimde kullanılmadı. Bölme zaten plakaya göre yapıldığı için eğitim
yarısını (566 kırpma / 204 plaka) eğitime katmak sızıntı değil — kullanılmamış
veri. `scripts/finetune.py` bunu yapıyor: `son.pt`'den devam, her epoch tüm
gerçek eğitim kırpmaları (hafif artırılmış) + sentetikten taze eşit sayıda
örnek, öğrenme oranı 1/10.

Sentetik karışımda kalıyor çünkü yalnızca 566 gerçekle eğitmek modelin
sentetikte öğrendiği genel karakter bilgisini silebilir.

**60 epoch, yerelde CPU'da 11.6 dakika.** Bu iş için GPU gerekmiyor ve bu
makinede GPU zaten güvenilir değil.

### Seçim ve rapor ayrıldı

60 epoch boyunca 68 plakaya bakıp en iyisini seçmek, o kümeye **seçim yoluyla**
aşırı uydurmaktır; bildirilen sayı artık saf değildir. Doğrulama plakaları
ikiye bölündü:

| küme | boyut | rolü |
|---|---|---|
| seçim | 88 kırpma / 34 plaka | epoch seçimi buna bakar |
| rapor | 157 kırpma / 34 plaka | **hiçbir karara girmez** |

Üç küme (eğitim / seçim / rapor) plaka metni bazında **tamamen ayrık** —
doğrulandı. Tek istisna bir yakın çift: eğitimdeki `34FY3424` ile rapordaki
`34FT3424` bir karakter farklı.

### Sonuç — rapor kümesi, ince ayar öncesi ve sonrası

| ölçüt | öncesi | sonrası |
|---|---|---|
| **PLAKA çoğunluk oyu** | 0.118 (4/34) | **0.529 (18/34)** |
| PLAKA en az bir doğru | 0.176 | 0.559 |
| karakter | 0.676 | 0.953 |
| düzenleme | 2.55 | **0.37** |
| kırpma tam dizi | 0.102 | 0.758 |

**Son satırı manşet yapmıyoruz.** Rapor kümesinde plaka başına kırpma sayısı
ortanca 1 ama en çok 70: tek bir plaka (`34KF2718`) 157 kırpmanın 70'i, yani
%45'i. Kırpma bazında ölçmek o plakayı 70 kez saymak demek. Bölüm 9'da kurulan
kural burada bir kez daha karşılığını buldu — **gerçek payda plaka**.

### Sınırlar, sayıyı olduğundan büyük okumamak için

- **34 plaka.** Çözünürlük 1/34 = %2.9; tek plaka oynaması sonucu %3 oynatıyor.
- **Tek kayıt.** Eğitim de test de aynı dashcam'in aynı sürüşlerinden. Başka
  kamera, başka şehir, başka gece koşulu için ölçüm **yok**.
- Ölçülen şey dikleştirilmiş kırpmadan okuma; dedektörün köşeleri ne kadar iyi
  bulduğu buraya dahil değil (Faz 1 henüz yok).

### Sırada ne var, ve neden şimdi

Ortalama düzenleme mesafesi **0.37**. Bu, hataların çoğunun artık tek karakter
olduğu anlamına geliyor — ve geçerli plaka biçimi kısıtı (il 01-81, düzen
kalıpları, Q/W/X yok) tam olarak bu hataları kapatan şey. Faz 3 ilk kez
üzerinde çalışacağı düzgün bir tabana sahip; düzenleme mesafesi 2.51 iken
kısıt koymak anlamlı olmazdı.

---

## 14. Faz 3: kısıtlı çözümleyici (C++), ve yazarken bulunan gramer hatası

### Önce: gramer gerçek plakaların yarısını reddediyordu

Kısıtı yazmadan önce zorunlu bir kontrol yapıldı — dilbilgisi gerçek
etiketleri kabul ediyor mu? Sonuç:

| düzen (harf, rakam) | gerçek plaka | üreteçte var mı |
|---|---|---|
| 3 harf 3 rakam (8 kr) | **146** | **HAYIR** |
| 2 harf 4 rakam (8 kr) | 79 | evet |
| 3 harf 2 rakam (7 kr) | 22 | evet |
| 2 harf 3 rakam (7 kr) | 21 | evet |
| 1 harf 4 rakam (7 kr) | 2 | evet |

`DUZENLER` listesinde **(3, 3) yoktu** ve o, gerçek verinin en yaygın düzeni:
272 plakanın 146'sı, %54'ü. Üreteç bugüne kadar tek bir 3harf-3rakam plaka
üretmedi.

Bu, bölüm 11'de **belirti olarak görülmüştü**: "sentetik %75 yedi karakterli,
gerçek %87 sekiz karakterli". Belirti kayda geçmiş, sebebi aranmamıştı. Sebebi
buymuş.

Bu dilbilgisiyle kısıt yazılsaydı doğruluk artmaz, **çökerdi** — çözümleyici
gerçek plakaların %54'ünü geçersiz sayardı.

Düzeltildi: `(3, 3)` eklendi ve düzenler artık eşit olasılıkla değil,
**ölçülen gerçek dağılımdan** bootstrap ediliyor. Üretilen uzunluk dağılımı
%88 sekiz karakterli — gerçekte %87.

`tests/test_dilbilgisi.py` bu hatayı tutuyor. Üç test birden düşüyor:
ölçülen düzenin listede olması, üretilen metinlerin geçerliliği, ve uzunluk
dağılımı. Testin hatayı gerçekten yakaladığı `(3, 3)` geri çıkarılarak
doğrulandı — geçen bir test, tuttuğunu iddia ettiği hatada düşmüyorsa
işe yaramaz.

### Çözümleyici

`cpp/decode.cpp` — kısıtlı CTC ön ek ışını araması. Python `log_softmax`
matrislerini `paket/logits.bin` olarak döküyor, C++ ikilisi okuyup çözüyor,
Python puanlıyor. İki tarafı tek süreçte birleştirmek (pybind, ctypes) bu
aşamada gereksiz: ölçülecek şey çözümleyicinin **kazancı**, bağlama maliyeti
değil.

Dilbilgisi: il 01-81, 1-3 harf (Q/W/X yok), 2-4 rakam, geçerli (harf, rakam)
çiftleri (1,4) (2,3) (2,4) (3,2) (3,3). 272 gerçek plakanın **270'ini** kabul
ediyor. Etmediği ikisi `013426` ve `E83KZV` — hiçbir Türk plakası biçimine
uymuyorlar, muhtemelen etiketleme hatası. **Kısıtın bedeli bu:** biçime
uymayan plaka artık asla doğru okunamaz. %0.7 ve bilerek ödendi.

### Doğrulama: aynı matris, aynı greedy

Kazancı ölçmeden önce C++ tarafındaki **kısıtsız** greedy'nin Python'unkiyle
birebir aynı çıkması gerekiyordu. 811/811 aynı. Bu geçmeseydi "kısıtın
kazancı" diye ölçülen şey matris aktarım hatası olurdu.

### Sonuç — rapor kümesi (hiçbir karara girmedi, 34 plaka)

| ölçüt | greedy | kısıtlı | fark |
|---|---|---|---|
| **PLAKA çoğunluk oyu** | 0.529 (18/34) | **0.647 (22/34)** | **+4 plaka** |
| kırpma tam dizi | 0.758 | 0.815 | +0.057 |
| karakter | 0.953 | 0.964 | +0.011 |
| düzenleme | 0.369 | **0.280** | −0.089 |

Rapor kümesinde kısıt 21 kırpmada çıktıyı değiştirdi: **9 düzeldi, 0 bozuldu.**
Düzelttikleri tam da beklenen sınıf — biçim bilgisiyle ayırt edilebilen tekil
karakter hataları:

```
349Y8229   -> 34RY8229     9/R
34JF5O99   -> 34JF5099     O/0
350FU335   -> 35CFU335     0/C
34KJGB14   -> 34KJG814     B/8
34KF271I8  -> 34KF2718     fazladan I
```

**Eğitim kümesinde kısıt hiçbir şey kazandırmıyor, çok az kaybettiriyor**
(düzenleme 0.004 → 0.005). Beklenen: model o örnekleri zaten %99.6 doğru
okuyor ve zaten doğru olan bir çıktıda kısıt ancak zarar verebilir. Kazanç
modelin *emin olmadığı* yerden geliyor.

### Toplam yol

| aşama | rapor kümesinde doğru okunan plaka |
|---|---|
| yalnızca sentetik (3. koşu) | 4/34 |
| + gerçek veriyle ince ayar | 18/34 |
| + kısıtlı çözümleyici | **22/34** |

---

## 15. Güven kalibrasyonu

Çözümleyici her kırpma için bir plaka veriyor ama "ne kadar eminim" demiyordu.
Faz 5'in zamansal oylaması buna dayanacak: bir aracın 20 karesinden gelen 20
okumayı eşit saymak, emin olunan okumayla tahmin yürütüleni aynı kefeye
koymak olur.

### İki sayı, biri neden yetmiyor

Çözümleyici artık en iyi **iki** geçerli plakayı ve log olasılıklarını
döndürüyor.

- **marj** = en iyinin log olasılığı − ikincininki. Uzunluktan bağımsız.
- **lp** = en iyinin kendi log olasılığı. Tek başına yanıltıcı: uzun plaka her
  zaman daha düşük alır çünkü daha çok çarpan var. Marjla birlikte bilgi
  taşıyor.

Ham marj tek başına bile ayırıyor:

| | rapor kümesi |
|---|---|
| doğru okumalarda ortanca marj | 6.27 |
| yanlış okumalarda ortanca marj | 0.79 |
| AUC | 0.947 |

### Eğri ve ölçümü

İki özellikten olasılığa lojistik regresyon, IRLS ile numpy'da — scipy ya da
sklearn bağımlılığı eklemeye değmeyecek kadar küçük bir iş.

Eğri **seçim** yarısına uyduruldu, kalitesi **rapor** yarısında ölçüldü.
Eğitim kırpmaları kullanılamazdı: model onları %99.6 doğru okuyor, yani
neredeyse hiç olumsuz örnek yok ve oradan uydurulan eğri sistematik olarak
fazla emin çıkardı.

| kova | n | tahmin | gözlenen | fark |
|---|---|---|---|---|
| 0.00-0.53 | 32 | 0.326 | 0.344 | +0.018 |
| 0.53-0.87 | 31 | 0.719 | 0.774 | +0.055 |
| 0.87-0.95 | 31 | 0.914 | 0.968 | +0.054 |
| 0.95-0.98 | 31 | 0.963 | 1.000 | +0.037 |
| 0.98-1.00 | 32 | 0.987 | 1.000 | +0.013 |

ECE **0.035**. Farkların hepsi **artı**: eğri sistematik olarak *az* emin.
Güvenli yön bu — abartan bir güven, Faz 5'te yanlış okumayı doğruların
üstüne çıkarırdı.

### Kullanımı

| eşik | kapsam | kapsananların doğruluğu |
|---|---|---|
| — | 1.000 | 0.815 |
| 0.70 | 0.701 | **0.982** |
| 0.80 | 0.662 | 0.990 |
| 0.95 | 0.389 | 1.000 |

Eşik koymanın anlamı düşük güvenli okumayı **atmak**, Faz 5'te onu başka
karelerin oyuyla değiştirmek üzere.

### Sayıyı olduğundan kesin okumamak için

Uydurma kümesindeki AUC **0.862**, rapor kümesindeki **0.950**. Normalde
tersi beklenir — uydurulan küme iyimser çıkar. Sebep kümelerin farkı: rapor
tarafında 70 kırpmalı tek bir kolay plaka var ve ayrım orada daha rahat.
Doğru okuma "AUC 0.95" değil, "0.86-0.95 aralığında".

Uydurma kümesi 88 kırpma. İki parametreli bir eğri için yeterli ama ince.

---

## 16. `(3,3)` düzeltmesi ölçüldü: kazanç yok

Bölüm 14 üreteçteki eksik düzeni buldu ve düzeltti. Açık kalan soru şuydu:
düzeltilmiş sentetikle yeniden eğitmek modeli iyileştirir mi? Ön eğitim
Kaggle turu gerektiriyor, o yüzden önce **ucuz yarısı** ölçüldü.

### Önce: kusur hâlâ görünüyor mu

Doğrulama kırpmaları düzene göre ayrıldı. Ön eğitimde hiç üretilmemiş `(3,3)`
diğerlerinden kötüyse fark orada görünmeli:

| düzen | plaka | çoğunluk oyu | ön eğitimde |
|---|---|---|---|
| 2h4r | 19 | 0.684 | vardı |
| 3h3r | 39 | 0.615 | **yoktu** |
| 2h3r | 7 | 0.571 | vardı |
| 3h2r | 2 | 1.000 | vardı |

`(3,3)` ile `(2,4)` arasındaki fark 0.069; bu örneklem boyutlarında belirsizlik
±0.13. Üstelik ön eğitimde **bulunan** `2h3r` daha da düşük. Ceza görünmüyor.

Muhtemel açıklama: ince ayar gerçek veriyle yapıldı ve gerçeğin %54'ü zaten
`(3,3)`. Ön eğitimdeki boşluğu ince ayar kapatmış.

### Sonra: kontrollü deney

100k düzeltilmiş üreteçle yeniden üretildi (uzunluk dağılımı artık %13/%87 —
gerçekle birebir) ve ince ayar **aynı başlangıç ağırlığından, aynı
hiperparametrelerle, aynı bölme tohumuyla** tekrarlandı. Tek değişken sentetik
kümenin düzen dağılımı.

Seçim kümesinde, kısıtlı çözümleyiciyle:

| | plaka çoğunluk oyu |
|---|---|
| `ince` (eski sentetik) | 21/34 |
| `ince2` (düzeltilmiş) | 21/34 |

**Ayırt edilemiyorlar.**

### Seçim rapor kümesine bakılarak yapılmadı

Rapor kümesinde `ince2` bir plaka önde (23/34'e karşı 22/34). O sayıya bakıp
`ince2`'yi seçmek, rapor kümesini bir karara sokmak olurdu — bölüm 13'te tam
bunu önlemek için ayrılmıştı ve seçilen sayı şişerdi. Seçim ölçütü ayırt
edemediği için mevcut model (`ince`) korundu.

Bir plaka farkı zaten 34 plakalık kümede %2.9, yani çözünürlüğün kendisi
kadar.

### Sonuç

Ön eğitim için Kaggle turu **yapılmadı ve gerekçesi ölçüm**: iki bağımsız
sinyal aynı yönü gösteriyor — düzen kırılımında ceza yok, kontrollü deneyde
fark yok.

Ölçülmeyen şey açıkça yazılsın: bu deney düzeltilmiş sentetiğin **ince ayar
karışımındaki** etkisini ölçtü. Ön eğitimin kendisini düzeltilmiş kümeyle
tekrarlamak ayrı bir sorudur ve ölçülmedi. Eldeki kanıt o turun değmeyeceğini
söylüyor, kanıtlamıyor.

Düzeltme yine de yerinde duruyor ve doğrudur: sentetikten sıfır eğiten biri
gerçek plakaların %54'ünü hiç görmezdi.

---

## 17. Faz 5: zamansal oylama, ve neden kazancı gösterilemedi

Aynı plaka onlarca karede geçiyor ve her karede ayrı okunuyor. Beklenti:
kareleri birleştirmek tek kareyi geçmeli, çünkü farklı karelerde farklı
karakterler bozuluyor.

Altı strateji, seçim kümesinde seçilip rapor kümesinde bildirildi:

| strateji | seçim | rapor | rapor, çok kareli (7 plaka) |
|---|---|---|---|
| ilk kare (oylama yok) | 0.588 | 0.588 | 0.429 (3/7) |
| düz çoğunluk | 0.618 | 0.647 | 0.714 (5/7) |
| **güven ağırlıklı** | **0.647** | **0.676** | **0.857 (6/7)** |
| eşikli (0.7) ağırlıklı | 0.647 | 0.676 | 0.857 |
| karakter oylama | 0.647 | 0.676 | 0.857 |
| en güvenli tek kare | 0.647 | 0.676 | 0.857 |

**Dizgi oylamasının tavanı** (bir plakanın karelerinden en az biri doğruysa):
seçimde 0.647, raporda 0.676.

### Güven ağırlıklı oylama tavana değiyor

Doğru bir okuma varsa buluyor, kaçırmıyor. Düz çoğunluk değmiyor (0.647): eşit
oy vermek, emin olunan okumayı emin olunmayanın altında bırakabiliyor.
Ağırlığın işe yaradığı yer burası.

### Ama oylamanın seçime üstünlüğü gösterilemiyor

**En güvenli tek kareyi almak — ki oylama değil, seçim — aynı sonucu
veriyor.** Kalibrasyon yeterince iyi (AUC 0.95) olduğu için, doğru bir okuma
varsa zaten en yüksek güvenli olan o oluyor. Bu veride toplamaya gerek
kalmıyor.

Karakter oylaması da tavanı **aşamadı**. Aşabilirdi: doğru karakterleri farklı
karelerden toplayıp hiçbir karesi tam doğru olmayan bir plakayı kurtarmak
dizgi oylamasının yapamayacağı şey. Yapmadı. Rapor kümesinde çok kareli
yalnızca 7 plaka var; böyle bir kurtarma için fırsat da yok denecek kadar az.

### Ölçünün gerçek boyutu

Rapor kümesinin 34 plakasından **yalnızca 7'sinde birden fazla kare var**.
Oylama yalnızca o 7'yi etkileyebilir. "0.676'ya karşı 0.647" farkı **tek bir
plaka**. Tablodaki sayılar bu çözünürlükle okunmalı.

Kare sayısıyla doğruluk ilişkisi (seçim + rapor, 68 plaka):

| kare sayısı | doğru |
|---|---|
| 1 kare | 31/50 = 0.620 |
| 2-4 kare | 6/10 = 0.600 |
| 5+ kare | 8/8 = 1.000 |

Bunu "daha çok oy daha iyi" diye okumak yanlış olur. Bir plakanın çok karesi
olması, aracın uzun süre yakın ve görünür kalması demektir — yani kolay plaka
demektir. Karıştırıcı değişken var ve bu ölçüm onu ayıramıyor.

### Ölçülmeyen: takip

Kırpmalar **gerçek plaka metnine göre** gruplandı, yani kusursuz bir takipçi
varsayıldı. Gerçek boru hattında grupları ByteTrack kurar ve takip hatası —
iki aracı birleştirmek, bir aracı ikiye bölmek — buraya ek gürültü katardı.
O gürültü bu sayılara **dahil değil**. Ölçülen şey oylamanın kendi kazancı,
boru hattının ucu değil.

Faz 5'in diğer iki parçası (C++ boru hattı, takip) yapılmadı.

### Bir kontrol

Karakter oylaması pozisyonları bağımsız oyluyor, dolayısıyla dilbilgisine
aykırı bir dizgi üretebilirdi. Üretmedi: altı stratejinin de her iki kümedeki
tüm çıktıları geçerli plaka. Bu bir sınır değil, olsaydı hata olurdu.

---

## 18. Faz 1: köşe modeli, ve otomatikleştirmenin ölçülemeyen bedeli

Bölüm 10-17'deki her sayı "dikleştirilmiş kırpma verilmiş" varsayımıyla
ölçüldü; o kırpmaları insan eliyle işaretlenmiş köşeler üretti. Bu bölüm o
varsayımı kaldırıyor.

`train_corners.py`: araç kırpmasından dört köşe. Gövde her köşe için bir ısı
haritası üretiyor, uzamsal softmax'ın beklenen değeri koordinatı veriyor.
Doğrudan 8 sayı regresyonu (global havuz → tam bağlı) konum bilgisini havuzda
kaybediyor ve 566 örnekle zayıf genelliyor; beklenen değer ızgara
çözünürlüğünün altında hassasiyet verebiliyor. 0.46M parametre, CPU'da 300
epoch 44 dakika.

Bölme tanıyıcıyla **aynı tohumdan**: rapor kümesindeki 34 plaka birebir aynı,
yoksa uçtan uca karşılaştırma anlamsız olurdu.

### Köşe hatası

Rapor kümesinde, plaka genişliğinin oranı olarak: ortanca **0.030**, ortalama
0.038, **%8.3'ü 0.05'i aşıyor**.

### Asıl ölçüm: aşağı akış

| ölçüt | elle köşe | model köşe |
|---|---|---|
| kırpma tam dizi | 0.815 | **0.720** |
| karakter | 0.964 | 0.902 |
| düzenleme | 0.280 | 0.771 |
| PLAKA güven ağırlıklı oy | 0.647 (22/34) | 0.529 (18/34) |

Ve kırılım, üreteç tasarımını aşağı akıştan doğruluyor:

| köşe hatası | n | tam dizi |
|---|---|---|
| 0.00-0.03 | 78 | 0.782 |
| 0.03-0.05 | 66 | 0.758 |
| 0.05-0.10 | 7 | 0.286 |
| >0.10 | 6 | 0.000 |

Okuma **tam 0.05'te** çöküyor — üretecin `KOSE_HATASI = 0.05` ile modellediği
eşik. Tanıyıcı eğitildiği bozulma aralığında dayanıklı, dışında değil. Bu,
iyileştirme hedefini de belirliyor: ortalama köşe hatasını düşürmek değil,
**eşiği aşan kırpma oranını** düşürmek.

### Fark 4 plaka, ama şanstan ayrılamıyor

22'ye karşı 18 net −4. Ayrık plakalara bakınca: **7 kayıp, 3 kazanç.**
McNemar ile on ayrık plakanın yedisi bir yönde; iki yönlü p ≈ **0.34**. Bu
örneklem farkı çözemiyor.

Kırpma bazında ise fark gerçek ve ölçülü: 157 kırpmada tam dizi 0.815'ten
0.720'ye. Yani bozulma var, plaka bazındaki oylama onun çoğunu yutuyor.

### Kaybedilen yedi plakanın hepsi tek kareli

| plaka | kare | köşe hatası | model okudu |
|---|---|---|---|
| 34KRK58 | 1 | 0.149 | 34Y3420 |
| 52LC081 | 1 | 0.145 | 52V6677 |
| 34GPN760 | 1 | 0.086 | 06DN760 |
| 34RY8229 | 1 | 0.062 | 34PY8229 |
| 34AEL236 | 1 | 0.030 | 34AEL230 |
| 34EGN767 | 1 | 0.025 | 34EGN757 |
| 34LTR416 | 1 | 0.021 | 34LTP416 |

İkisi önemli:

**Oylama köşe hatasını yutuyor, ama yalnızca yutacak kare varsa.** Yedi kaybın
yedisi de tek kareli. Çok kareli plakalarda köşe hatası oylamada eriyor.

**Son üçünde köşe hatası zaten düşük** (%2-3) ve okuma tek karakter kayıyor.
Bu bir köşe arızası değil: tanıyıcı o kırpmalarda zaten sınırda ve küçük bir
dikleştirme farkı deviriyor. Köşe modelini iyileştirmek bunları kurtarmaz.

### Elle işaretleme altın standart değil

Model **üç plakada elle işaretlemeyi geçti**. Elle işaretlenmiş köşeler
doğru cevap değil, bir insanın işaretlemesi; dikleştirme kalitesi açısından
model bazen daha iyi kadraj kuruyor. "Otomatikleştirmenin bedeli" çerçevesi
bu yüzden olduğundan keskin görünüyor.

### Üçüncü kez aynı seçim hatası

`best.pt` önce **ortalama** köşe hatasına göre seçiliyordu. Ortalama birkaç
felaket vakadan şişip epoch'lar arasında zıplıyor; ortanca 150 epoch boyunca
düzenli düşüyordu (0.067 → 0.022). Ortalamaya göre epoch 50 seçilmişti, oysa
epoch 150 ortancada 0.022'ye karşı 0.030 ve eşik üstü oranda 0.136'ya karşı
0.205 ile belirgin daha iyiydi — uçtan uca bir plaka.

Ölçüt artık **eşiği aşan kırpma oranı**, eşitlikte ortanca. Gerekçesi yukarıdaki
kırılım: okuma orada çöküyor.

Bu, projede üçüncü seçim ölçütü hatası. Öncekiler: `tam dizi`'nin 245 kırpmada
üç kırpmalık çözünürlüğü (bölüm 11), düzenleme mesafesinin tam diziyle
ayrışması (bölüm 12). Ortak yan: **seçim ölçütü önemsenen şeyle aynı
olmadığında sessizce yanlış ağırlığı veriyor.**

### İki betik aynı şeyi farklı ölçüyordu

`train_corners.py` hatayı küçültülmüş (288×96) uzayda, `end_to_end.py`
orijinal uzayda ölçüyordu. Yeniden boyutlandırma anizotropik (386×144 →
288×96) olduğu için aynı küme için farklı sayı çıkıyordu: 0.070'e karşı 0.083.
Dikleştirme orijinal uzayda yapıldığına göre anlamlı olan o; düzeltildi ve
ikisi artık birebir aynı (0.030 / 0.038 / 0.083).

Kayda geçsin: eldeki ağırlık **eski tanıma göre** seçildi. Sıralamanın
değişmesi beklenmiyor ama doğrulanmadı.

---

## 19. Hız: planın manşet iddiası, ilk kez ölçüldü

> **Düzeltme (bölüm 22):** Aşağıdaki YOLO süresi `imgsz=640` ile
> ölçülmüş, oysa boru hattı 960 kullanıyor. Doğrusu 57.65 değil
> **97.84 ms**, kare başına 75.6 değil **115.4 ms**, yani 13.2 değil
> **8.7 FPS**. Sonuç cümlesi değişmiyor, sayılar değişiyor.

Başlangıçtaki plan "Jetson Orin Nano'da 30 FPS" diyordu. Donanım olmadığı için
o iddia düşürüldü ve yerine "bulut GPU'da ölçüldü, uç cihaz ölçülmedi" yazıldı.
Ama proje bugüne kadar hızı **hiçbir yerde** ölçmedi; "ne kadar hızlı"
sorusuna verecek sayısı yoktu.

`scripts/benchmark.py`, bu makinede (6 iş parçacığı, CPU), `maltepe.mkv`
üzerinde:

| adım | medyan | birim |
|---|---|---|
| YOLO araç tespiti | 57.65 ms | kare |
| köşe modeli | 5.29 ms | araç |
| dikleştirme (OpenCV) | 0.59 ms | araç |
| tanıyıcı (CTC) | 5.20 ms | araç |
| C++ kısıtlı çözüm | 1.76 ms | araç |

Kare başına 1.40 araç genişlik filtresini geçiyor → **75.6 ms/kare, 13.2 FPS.**

### İki ölçüm hatası, ikisi de sayıyı şişiriyordu

**Videonun ilk 40 karesi alınmıştı.** 60 fps'te bu 0.7 saniye ve o anda yakın
araç yok; genişlik filtresini geçen araç sayısı 0.00 çıktı, yani aşağı akış
maliyeti sıfır göründü. Kareler artık video boyunca dağıtılıyor.

**Araç sayısı YOLO'nun tüm tespitlerinden sayılmıştı** (3.84/kare). Oysa köşe
ve tanıyıcı adımlarını yalnızca genişlik filtresini geçenler tetikliyor
(1.40/kare). Filtresiz sayı kare maliyetini %60 fazla gösteriyordu.

### Sayının anlamı, ham FPS'te değil işin gereğinde

Kayıt 60 fps; her kareyi işlemek 16.7 ms ister, ölçülen 75.6 — **4.5 kat
yavaş**. Ama plaka okuma her kareyi istemiyor. Bir araç kadrajda saniyelerce
kalıyor ve 13.2 FPS'te bu **saniyede 13 işlenmiş kare** demek. Bölüm 17'de
beş ve üzeri karesi olan plakaların hepsi doğru okunmuştu; bu hız onu
fazlasıyla sağlıyor.

Yani dürüst ifade şu: **kayıt hızında gerçek zamanlı değil, işin gerektirdiği
hızda fazlasıyla yeterli.**

### Darboğaz projenin kendi kodunda değil

YOLO kare maliyetinin **%76'sı**. Projenin yazdığı üç model — köşe, tanıyıcı,
kısıtlı çözümleyici — araç başına 12.8 ms, kare başına 17.9 ms. Faz 4'ün
(TensorRT) hızlandıracağı yer hazır bir modelde.

C++ çözümleyici ayrı bir süreç olarak çağrılıyor ve tek çağrıda 14.3 ms
görünüyor; bunun neredeyse tamamı süreç başlatma. 200 örnekten hesaplanan saf
çözüm süresi **1.76 ms**. Gerçek bir boru hattında kütüphane olarak
bağlanacağı için geçerli olan ikincisi.

### Sınırlar

- Toplu işleme yok: her araç tek tek geçirildi. Yığınlamak araç başına
  maliyeti düşürürdü; ölçülen en kötü hal.
- Tek makine, tek kayıt, CPU. Başka donanım için sayı yok.
- YOLO ölçümü `yolov8n` ile; daha büyük bir model daha yavaş, daha küçüğü
  yok.

---

## 20. Takip, ve güvenin ters yönü gösterdiği arıza

Bölüm 17'nin her sayısı kırpmaları gerçek plaka metnine göre grupladı, yani
kusursuz bir takipçi varsaydı. `track_pipeline.py` o varsayımı kaldırıyor:
ByteTrack izliyor, gruplar iz numarasından geliyor.

**Ölçüm neden dolaylı olmak zorunda:** etiketli 811 kırpma **ikişer saniye**
arayla örneklendi (`harvest_plates.py --every` saniye cinsinden). ByteTrack o
boşlukta bir aracı bağlayamaz, dolayısıyla mevcut etiketler ize
bağlanamıyor ve iz düzeyinde etiket yok. Tanıyıcı ise izlerden habersiz —
bu yüzden iki ayrı izin aynı plakayı okuması, kimliğin **bağımsız** kanıtı.

`maltepe.mkv`, 180 saniye, her 4. kare (etkin 15 fps): **211 iz, 2472 kırpma.**

### Verim: projenin şimdiye kadar yazmadığı sayı

| | adet | pay |
|---|---|---|
| kırpma | 2472 | |
| dilbilgisine uygun plaka üretti | 1303 | %53 |
| ayrıca güvenli (≥0.7) | 561 | %23 |

Bu düşüklük kusur değil, işin tanımı. Etiketlemede de hasat edilen
kırpmaların yalnızca **%38'inde okunur plaka vardı** (811 `ok` / 2119 etiket;
kalanı 706 `plakasiz` + 602 `okunmaz`).

**Ve bu, bölüm 10-18'deki her sayının yazılmamış koşuluydu.** "34 plakanın
22'sini okuyor" doğru ama eksik: o 34 plaka, plakası okunabilen kırpmalardan
seçilmişti. Boru hattı düzeyindeki verim ile tanıyıcı düzeyindeki doğruluk
farklı sayılar ve proje şimdiye kadar yalnızca ikincisini yazmıştı.

### Parçalanma

Zamansal olarak tutarlı 84 plakanın **7'si (%8)** birden çok ize bölünmüş,
10 fazladan iz. Bölünmeler eşzamanlı — `34AEM481` için dört iz ve hepsi 3-5.
saniyede. Yani ByteTrack aynı araca aynı anda birden çok kimlik veriyor,
zaman içinde kaybedip yeniden bulmuyor.

105 izin **30'u yalnızca tek güvenli okuma** üretiyor. Bölüm 18'de kaybedilen
yedi plakanın yedisi de tek kareliydi; oylama korumasının olmadığı yer burası
ve takip onu genişletmiyor.

### Asıl bulgu: güven uydurmayı ayıramıyor, tersini gösteriyor

Güvenli okumaların içinde, **aynı plaka metnini dakikalarca arayla ve farklı
izlerde** üreten dört kayıt çıktı:

| plaka | yayılım | iz |
|---|---|---|
| 01CCC01 | 132 s | 6 |
| 10CCC01 | 131 s | 6 |
| 09CCC01 | 129 s | 4 |
| 08CCC01 | 81 s | 3 |

Bir araç dashcam önünde iki dakika kalıp sonra geri gelmez. Bunlar uydurma.
Ve hepsinde aynı imza var — harf bloğu tek harfin tekrarı:

| küme | tekrarlı harf bloğu |
|---|---|
| imkânsız okumalar | 4/4 |
| tutarlı okumalar | 6/119 |
| gerçek 811 plaka | 3/811 (%0.4) |

**Güven bunları süzmüyor. Süzemez:**

| | güven ortancası |
|---|---|
| uydurma okumalar | **1.000** |
| tutarlı okumalar | 0.933 |

| eşik | kirlilik |
|---|---|
| 0.70 | %4.3 |
| 0.80 | %5.0 |
| 0.90 | %6.5 |
| 0.95 | **%9.4** |

Eşiği yükseltmek kirliliği **artırıyor**: uydurmalar her eşikten geçiyor,
elenen gerçek okumalar oluyor.

Sebep, güvenin tanımında ve bölüm 15'te yazılmıştı: güven **marja** dayanıyor,
en iyi ile ikinci en iyi geçerli plaka arasındaki farka. Okunacak bir şey
olmayan kırpmada modelin tek bir varsayılan kalıbı var ve **rakibi yok**;
marj tavan yapıyor. Gerçekten zor ama okunabilir bir plakada rakip adaylar
var ve marj küçülüyor.

Marj "alternatifler arasında ne kadar eminim" sorusunu cevaplıyor. "Burada
okunacak bir şey var mı" başka bir soru ve boru hattında onu soran hiçbir
bileşen yok.

### Kök sebep: modele hiç "yok" demesi öğretilmedi

- Sentetik 100k'nın hepsinde plaka var.
- Gerçek ince ayar `durum == "ok"` olan 811 kırpmayla yapıldı.
- Kalibrasyon eğrisi de aynı kümede uyduruldu.
- **706 `plakasiz` + 602 `okunmaz` kırpma etiketli olarak duruyor ve hiçbir
  aşamada kullanılmadı.**

Kısıtlı çözümleyici bunu ağırlaştırıyor: dilbilgisi kısıtı çöp girdide bile
geçerli bir plaka üretmeye zorluyor. Bölüm 14 kısıtın kazancını ölçmüştü;
bedeli burada görünüyor.

Dağıtımda bu en kötü arıza tipi: sistem "okuyamadım" demek yerine belirli bir
plaka numarası uyduruyor ve bunu tam güvenle yapıyor.

### İlk okumamdaki hata

Bu oranı önce **%11** hesaplamıştım. Gevşek bir dilbilgisiyle
(`\d{2}[A-Z]+\d+`) süzmüştüm; boru hattının kendi süzgeci `DUZENLER`'i de
kontrol ediyor ve `08C0` gibi dizgileri zaten eliyor. Doğru oran **%4.3**.
Oran daha küçük, yön problemi aynı.

### Ölçülmeyen

İz düzeyinde etiket yok. Yukarıdaki parçalanma ve uydurma sayıları
takipçinin ve tanıyıcının hatalarının **alt sınırı**: yalnızca güvenle
okunan izlerde görülebilen hataları sayıyor. Plakası hiç okunamayan bir
aracın izi bölünmüşse bu sayılara girmiyor.

Uydurma tespiti de bir varsayım taşıyor: aynı plakayı dakikalarca arayla
okuyan izlerin aynı araç olamayacağı. Bu güçlü bir varsayım ama kanıt değil;
kesin ayrım ancak iz etiketleriyle yapılır.

---

## 21. Kabul etme: boru hattına "okuyamadım" demeyi öğretmek

Bölüm 20'nin bulgusu: sistem, okunacak hiçbir şey olmayan kırpmalarda
kalıplaşmış bir plaka uyduruyor ve bunu 1.000 güvenle yapıyor. Güven marja
dayanıyor ve boş bir kırpmada rakip aday olmadığı için marj tavan yapıyor.
Eksik olan veri değildi — 706 `plakasiz` + 602 `okunmaz` kırpma başından beri
etiketliydi. Eksik olan **sorunun sorulmasıydı**.

### İlk deneme: ortak gövde, iki başlık — başarısız

Köşe modelinin gövdesine ikinci bir başlık eklendi ve 566 pozitif + 993
negatifle birlikte eğitildi. **İki iş de bozuldu:**

| | önce | ortak gövde |
|---|---|---|
| köşe hatası ortancası (rapor) | 0.030 | 0.062 |
| köşe >%5 oranı (rapor) | **0.083** | **0.631** |
| varlık AUC (rapor) | — | 0.740 |
| varlık AUC (seçim) | — | epoch 55'te 0.960 → epoch 200'de 0.914 |

Köşe eşik-aşma oranı yedi kat arttı. Muhtemel mekanizma BatchNorm: yığının
%64'ü artık negatif ve normalleştirme istatistikleri köşe başlığının gördüğü
dağılımı kaydırıyor. Ayrıca köşe kaybı her adımda yığının yalnızca
%36'sından geliyor.

Çok görevli öğrenme bedava değil ve bedeli burada ölçüldü.

### İkinci deneme: dondurulmuş gövde — çalıştı

Gövde ve köşe başlığı donduruldu, yalnızca varlık başlığı eğitildi. Köşe
doğruluğuna zarar vermesi mümkün değil çünkü o ağırlıklar hiç güncellenmiyor.

**Bir tuzak var ve `requires_grad = False` onu kapatmıyor:** `model.train()`
çağırmak BatchNorm çalışma istatistiklerini günceller ve bu köşe doğruluğunu
sessizce bozardı. Gövde ve köşe başlığı açıkça `eval()` kipinde tutuluyor.

| | ortak gövde | dondurulmuş gövde |
|---|---|---|
| varlık AUC (rapor) | 0.740 | **0.889** |
| köşe doğruluğu | bozuldu | **değişmedi** |

Köşe regresyonu için öğrenilen öznitelikler "burada okunur plaka var mı"
sorusunu cevaplamaya yetiyor. Ek çıkarım maliyeti: tek 1×1 evrişim ve global
havuz.

Uçtan uca sayılar dondurulmuş modelle **birebir aynı** çıktı (kırpma tam dizi
0.720, plaka 18/34) — donmanın gerçekten koruduğunun doğrulaması.

### Eşik seçim kümesinde belirlendi

| tutulan pozitif | eşik | geçen negatif |
|---|---|---|
| %95 | 0.332 | 0.253 |
| **%90** | **0.420** | **0.215** |
| %85 | 0.476 | 0.184 |

İşletme noktası **0.420**. Rapor kümesine ya da takip koşusuna bakarak
seçilmedi; öyle yapılsaydı ölçüm kendi kendini doğrulardı.

### Takip koşusunda sonuç

Aynı 180 saniyelik kesit, aynı takip, tek fark varlık kapısı:

| | kapısız | kapılı |
|---|---|---|
| geçen kırpma | 561 | 432 (−23%) |
| zamansal **tutarlı** plaka | 83 | 62 (−25%) |
| **imkânsız (uydurma) plaka** | 4 | **0** |
| uydurma kırpma | 24 | **0** |
| kirlilik oranı | 0.043 | **0.000** |

Bu hacim kesmek değil, ayrım yapmak. Kapı kırpmaların %23'ünü eliyor ama
uydurma kırpmaların %100'ünü. Elemenin ayrımsız olduğu varsayımı altında 24
kırpmanın hepsinin gitme olasılığı 0.77²⁴ ≈ %0.2.

### Bedeli gerçek, ve bir kalibrasyon açığı gösteriyor

Tutarlı plakaların **dörtte biri** gidiyor. Eşik seçim kümesinde pozitiflerin
%90'ını tutacak şekilde ayarlanmıştı; canlı akışta %75 tutuyor.

Fark, etiketli pozitiflerin ne olduğundan geliyor: `build_queue.py`
kırpmaları keskinliğe göre sıralıyor ve etiketleme oradan ilerledi. Yani
"pozitif" kümesi keskinliğe göre **seçilmiş bir alt küme**, canlı akış ise
tüm dağılım. Aynı eşik iki popülasyonda farklı davranıyor.

Bu, bölüm 3'teki kesilmiş aralık hatasının bir akrabası: ölçüm doğru,
genelleme yapılan popülasyon farklı.

### Eşik ödünleşimi — betimleyici, seçim gerekçesi değil

| varlık eşiği | tutarlı plaka | uydurma | kirlilik |
|---|---|---|---|
| 0.00 | 83 | 4 | 0.043 |
| 0.20 | 66 | 0 | 0.000 |
| 0.30 | 64 | 0 | 0.000 |
| **0.42** | **62** | **0** | **0.000** |
| 0.70 | 56 | 0 | 0.000 |

Uydurmalar 0.20'de zaten bitiyor ve orada 66 plaka kalıyor. Bu tabloya bakıp
0.20'yi seçmek değerlendirme kümesine göre ayar yapmak olurdu ve yapılmadı.
Doğru yol, canlı akışa benzeyen ayrı bir doğrulama kümesinde eşiği belirlemek;
o küme yok ve bu yazılmış bir eksik.

### Bunun çözmediği şeyler

- **Tanıyıcı hâlâ kabul edemiyor.** Kapı onun önünde duruyor; tanıyıcının
  kendisi bir kırpmayı reddedemiyor. Kapıdan geçen bir çöp kırpma yine
  uydurma üretir.
- **Kapı araç kırpmasına bakıyor**, dikleştirilmiş plakaya değil. Plaka
  gerçekten varken köşe modeli yanlış kadraj kurarsa kapı bunu göremez.
- Kapının kendisi %21.5 negatif sızdırıyor (seçim kümesinde). Uydurmaların
  hepsini elemesi bu kesitte oldu; genel bir garanti değil.

---

## 22. ONNX: çerçeveden çıkmak, ve bölüm 19'un düzeltilmesi

Faz 4 (TensorRT) ve Faz 5'in C++ boru hattı aynı önkoşula bağlı: modellerin
çerçeveden bağımsız bir biçimde olması. TensorRT ONNX tüketiyor; C++'ta model
çalıştırmanın makul yolu da ONNX Runtime.

### Doğrulama işin yarısı

Bir modeli başka bir çerçeveye taşımak sessizce bozulabilir: operatör
farkları, varsayılan değerler, sayısal hassasiyet. Bozulma istisna olarak
değil, biraz farklı sayılar olarak görünür ve boru hattının ucunda "model
kötüleşti" diye yorumlanır.

157 gerçek araç kırpması (rapor kümesi) üzerinde:

| | maksimum fark |
|---|---|
| köşe koordinatları | 2.38e-07 → **0.0001 piksel** |
| varlık puanı | 1.91e-06 |
| tanıyıcı logitleri | 1.29e-05 |

**Ve asıl sınav: çözümlenen plaka metni 157/157 kırpmada aynı.** Tolerans
tartışmasına gerek kalmadı — 1e-5'lik bir logit farkı plakayı değiştirmiyorsa
önemsizdir, değiştiriyorsa kritiktir; bakılan şey sonuç.

Girdi olarak rastgele tensör değil rapor kümesinin kendisi kullanıldı.
Rastgele girdide iki çerçeve kolayca uyuşur; önemli olan modelin gerçekte
gördüğü dağılımda uyuşması.

### Hız: ONNX tekdüze hızlı değil

| model | PyTorch | ONNX Runtime | oran |
|---|---|---|---|
| köşe + varlık | 4.82 ms | 2.93 ms | **1.65x** |
| tanıyıcı | 4.33 ms | 1.77 ms | **2.45x** |
| **YOLOv8n** | **95.7 ms** | **134.2 ms** | **0.71x** |

Projenin kendi yazdığı küçük modeller iki kattan fazla hızlanıyor; hazır ve
zaten iyi optimize edilmiş YOLO **yavaşlıyor**. "ONNX hızlıdır" diye tek bir
cümle kurulamıyor, model model bakmak gerekiyor. YOLO PyTorch yolunda
bırakıldı.

Araç başına toplam: **11.38 ms → 6.93 ms**.

### Bölüm 19 yanlıştı: YOLO 640'ta ölçülmüştü

Bu ölçüm sırasında bölüm 19'da bir hata çıktı. Kıyaslama betiği YOLO'yu
`predict()` varsayılanıyla, yani **imgsz=640** ile ölçüyordu. Oysa boru hattı
— `harvest_plates.py` ve `track_pipeline.py` — **imgsz=960** kullanıyor.
Ölçülen şey çalıştırılan şey değildi.

| | bölüm 19 | düzeltilmiş |
|---|---|---|
| YOLO | 57.65 ms | **97.84 ms** |
| kare başına toplam | 75.6 ms | **115.4 ms** |
| | 13.2 FPS | **8.7 FPS** |
| YOLO'nun payı | %76 | **%85** |

Yön aynı kalıyor ve sonuç cümlesi de: kayıt hızında gerçek zamanlı değil,
işin gerektirdiği hızda yeterli. 8.7 FPS, bir aracın kadrajda kaldığı
saniyede 9 işlenmiş kare demek ve bölüm 17'de beş kareli plakaların hepsi
doğru okunmuştu. Ama sayının kendisi %35 yanlıştı ve düzeltildi.

Betik artık `imgsz=960` kullanıyor ve neden kullandığı yazılı.

### Darboğaz daha da netleşti

YOLO artık kare maliyetinin **%85'i**. Projenin kendi üç modeli (köşe,
tanıyıcı, çözümleyici) ONNX ile araç başına 6.93 ms. Hızlandırılacak yer
hazır bir modelde ve orada da ONNX işe yaramıyor — kalan yol TensorRT ya da
daha küçük bir dedektör.

### Modeller depoda değil

`onnx/` de `*.pt` gibi depo dışında. Tanıyıcı 204 gerçek plakayla ince
ayarlandı; bir modelin ezberlediğini geri vermesi kırpmaları yayınlamaktan
çok daha zayıf bir sızıntı, ama bu projenin plaka verisi konusundaki tutumu
belli ve ağırlıkları tek taraflı yayınlamak o tutumla çelişirdi.

Sentetik boru hattı hâlâ kimsenin verisine ihtiyaç duymadan çalışıyor;
ağırlıkları üretmek için gereken her komut depoda.

---

## 23. C++ boru hattı: Python yükü darboğaz değilmiş

`cpp/pipeline.cpp` boru hattının projeye ait her adımını C++'ta çalıştırıyor:
araç kırpması → küçültme → köşe modeli → varlık kapısı → perspektif düzeltme
→ gri + küçültme → tanıyıcı → kısıtlı ışın araması → plaka + güven.

PyTorch yok, OpenCV yok, Python yok. YOLO dışarıda: bölüm 22'de ONNX'te
yavaşladığı ölçüldü ve zaten hazır bir model.

### Ölçüm sorusu

Bölüm 22'de araç başına 6.93 ms ölçülmüştü (Python + ONNX Runtime). Sorusu:
**bunun ne kadarı gerçek hesap, ne kadarı Python yükü?** Aynı işi yapan C++
belirgin şekilde altına inerse Python yükü gerçekti.

### Bağımlılık nasıl kalmadı

ONNX Runtime'ın C API'si tek bir dışa aktarılmış fonksiyon üzerinden çalışıyor
(`OrtGetApiBase`), gerisi işlev işaretçisi tablosu. DLL çalışma anında
açılıyor: import kütüphanesi gerekmiyor, C API olduğu için MinGW/MSVC ABI
sorunu da yok.

OpenCV yerine küçültme (alan ortalaması) ve perspektif düzeltme elle yazıldı.

**Yakalanan tuzak:** `LoadLibrary("onnxruntime.dll")` yanlış sürümü yüklüyor.
Windows'un kendi getirdiği bir `onnxruntime.dll` System32'de duruyor (1.17.1)
ve arama sırası System32'yi PATH'ten önce koyuyor. Belirti yanıltıcı: *"API
version 29 is not available"* — derleme hatası gibi görünüyor, oysa yanlış
dosya. Çözüm açık yol (`PLAKA_ORT_DLL`) ve sürüm geri düşüşü.

Dilbilgisi ve ışın araması `cpp/decoder.hpp`'ye taşındı; `decode.exe` ile
`pipeline.exe` aynı kaynağı kullanıyor. İki ayrı yerde iki gramer tutmak
ikisinin sessizce ayrışması demek olurdu — `tests/test_dilbilgisi.py` zaten
C++ ile Python'un ayrışmasını sınamak için yazılmıştı.

### Aynı şeyi okuyorlar mı

| | |
|---|---|
| aynı plaka | **139/157 (%88.5)** |
| aralarındaki ortalama düzenleme | 0.166 |
| varlık puanı farkı (maks) | 5.25e-03 |
| **gerçek etikete göre doğru** | **C++ 111, Python 113** |

Piksel piksel aynı olamazlar: `cv2` dikleştirmede INTER_CUBIC kullanıyor,
C++ tarafı iki doğrusal. Fark %11.5 kırpmada okumayı değiştiriyor ama
doğruluğu değiştirmiyor — 111'e karşı 113, ve ayrışmalar ikisinin de
genellikle yanıldığı zor kırpmalarda.

### Güven, okumadan çok daha kırılgan

Aynı plakayı okuyan 139 kırpmada güven farkı:

| ortanca | %90 | maks | 0.05'ten büyük |
|---|---|---|---|
| 0.0785 | 0.7717 | 0.9810 | **85/139** |

Sebebi tanımında: güven **marja** dayanıyor, marj ikinci en iyi *adaya*
bağlı, ve minik bir piksel farkı ikinci adayı tamamen değiştirebiliyor.

Pratik sonucu: **kalibrasyon eğrisi ön işlemeye bağlı.** Bölüm 15 ve 21'deki
eşikler `cv2` ön işlemesiyle uyduruldu; C++ yolunda yeniden kalibre edilmeli.
Bu, boru hattının parçalarının sanıldığı kadar bağımsız olmadığını gösteriyor.

### Hız: soru cevaplandı, cevap "hayır"

| | kırpma başına |
|---|---|
| Python + OpenCV + ONNX Runtime | **9.73 ms** |
| C++ (pipeline.exe) | **15.61 ms** |

C++ **daha yavaş**. Adım adım:

| adım | ms |
|---|---|
| JPEG çözme | 3.09 |
| küçültme (elle) | 3.42 |
| köşe modeli (ONNX) | 2.44 |
| dikleştirme (elle) | 2.17 |
| tanıyıcı (ONNX) | 1.69 |
| kısıtlı çözümleme | 2.66 |
| **ONNX toplam** | **4.13** |
| **elle yazılan işlem** | **5.58** |

**ONNX çağrılarında C++ hafifçe hızlı** (4.13'e karşı Python'da ~4.70). Fark
tamamen elle yazılan görüntü işlemlerinde: OpenCV aynı küçültmeyi **0.464
ms**'de yapıyor, elle yazılan 3.42 ms — **7 kat**.

Üç tur optimizasyon yapıldı ve ikisi işe yaramadı:

| | küçültme |
|---|---|
| naif çift döngü | 6.17 ms |
| ayrılabilir (yatay + dikey geçiş) | 4.02 ms |
| dikey geçişte satır tamponu (önbellek) | 3.42 ms |
| ağırlık tablosunu düzleştirme (tahsis) | 3.42 ms — **etkisiz** |

Tahsis yükü hipotezi ölçülüp elendi. Kalan fark SIMD ve OpenCV'nin değeri tam
orada: API'sinde değil, çekirdeklerinde.

### Sonuç

**Python yükü darboğaz değildi.** Bölüm 22'nin 6.93 ms'si büyük ölçüde gerçek
hesaptı; düzenlemeyi C++'a taşımak, OpenCV'nin optimize edilmiş çekirdeklerini
de getirmediğin sürece işi yavaşlatıyor.

Bu, C++'ın işe yaramadığı anlamına gelmiyor — kısıtlı çözümleyici (bölüm 14)
C++'ta yazıldı çünkü gramer üzerinde ışın araması Python'da hem çirkin hem
yavaş olurdu, ve orada kazanç gerçekti. İşe yaramayan şey, iyi optimize
edilmiş bir kütüphanenin yaptığı işi elle yeniden yazmak.

Ölçülmeseydi bunun tersi de aynı derecede inandırıcı görünürdü.
