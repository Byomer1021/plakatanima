# Kaggle'da Eğitim

Eğitim yerelde yapılmıyor ve yapılmamalı: bu makinedeki GTX 1080 ağır yük
altında **dört kez** düştü, sonuncusu `train_recognizer.py`'ın `cuda if
available` diyen ilk sürümüydü ve makineyi resetletti. Betiğin cihaz
varsayılanı bu yüzden `cpu`; GPU açıkça istenmeli.

---

## 1. Paketi hazırla

```bash
python scripts/paketle.py
```

`paket/` klasörü çıkar:

| dosya | içerik |
|---|---|
| `sentetik.npz` | 100.000 örnek, 32×128 gri tonlama, **zorluk sırasında** |
| `gercek.npz` | 811 kırpma / 272 plaka, her satırda plaka metni |
| `train_recognizer.py` | eğitim betiği (defterden çağrılabilsin diye) |

**Neden dosya yığını değil tek dizi:** 100k küçük JPEG bulutta kötü bir format —
yüklemesi yavaş, Kaggle her oturumda arşivi açmak zorunda, ve eğitim her
epoch'ta 100k dosya açıp JPEG çözüyor. İş G/Ç'ye takılıyor, GPU boşta bekliyor.
Eğitim zaten hepsini 32×128 griye indirdiği için dönüşüm bir kez paketlemede
yapılıyor.

**Bedeli:** paket girdi boyutunu sabitliyor. 48×160 denemek istersen paketi
yeniden üret (`--yukseklik 48 --genislik 160`); JPEG'ler yerelde duruyor.

---

## 2. Kaggle'a yükle

1. [kaggle.com](https://www.kaggle.com) → hesap aç, **Phone Verify** yap
   (GPU kotası bunu istiyor).
2. **Datasets → New Dataset** → `paket/` içindeki üç dosyayı sürükle.
3. İsim: `plakatanima-paket`. **Private** bırak — gerçek plaka görüntüleri
   içeriyor ve plaka kişisel veri.
4. Create.

> Depoya gerçek plaka konmuyor, bu pakete konuyor. Fark şu: depo herkese açık,
> Kaggle veri seti private. Yine de gereksiz yere paylaşma.

---

## 3. Defteri kur

**Code → New Notebook** → sağ panel:

- **Add Data** → `plakatanima-paket`
- **Accelerator** → `GPU T4 x2` (ya da P100)
- **Internet** → kapalı kalabilir, paket zaten içeride

Tek hücre:

```python
!cp /kaggle/input/plakatanima-paket/train_recognizer.py .
!python train_recognizer.py \
    --paket /kaggle/input/plakatanima-paket \
    --cihaz cuda \
    --epoch 20 \
    --yigin 256 \
    --out /kaggle/working/taniyici
```

`--yigin 256`: T4'te 32×128 gri görüntüyle rahat sığar ve veri artık diskten
değil bellekten geldiği için yığını büyütmek doğrudan hıza dönüşüyor.

---

## 4. Çıktıda ne aranacak

Her epoch şunu yazdırıyor:

```
epoch  7  kayip  1.842  tam dizi  0.614  karakter  0.923  duzenleme  0.51
```

**Bakılacak sayı `tam dizi`** — plakanın tamamının doğru okunması. Karakter
doğruluğu her zaman daha yüksek çıkar ve yanıltıcıdır: 8 karakterin 7'sini
bilmek plakayı okumak değildir.

**Kritik:** bu sayı yalnızca **gerçek plakalardan** geliyor. Sentetikte ölçülen
doğruluk hiçbir şey ifade etmez — kendi ürettiğin dağılımda kendini test etmiş
olursun. Betik sentetiği sadece eğitimde kullanıyor.

Doğrulama kümesi **plakaya göre** ayrılıyor, kırpmaya göre değil. Bir plaka 82
kırpmada geçebiliyor; kırpmaya göre bölünse aynı plaka iki tarafta da olur,
model ezberler ve skor hiçbir şey iyileşmeden tırmanır.

### Ölçülen (ikinci koşu)

Plan tek kare tam dizi doğruluğunu %90-95 bandına koyuyordu. Ölçülen:

```
epoch  3  kayıp 0.375  tam dizi 0.000  karakter 0.418
epoch 20  kayıp 0.004  tam dizi 0.008  karakter 0.400
```

Karakter doğruluğu epoch 3'te doygunlaşıyor, eğitim kaybı yüz kat inerken
kıpırdamıyor. Bu **ölçülmüş bir alan farkı** ve sebebi bulundu: sentetikte
metin kadrajın %78'ini dolduruyordu, gerçekte %100. Model karakterleri
okuyabiliyor ama sembol düşürüyordu — plaka başına 7.82 yerine 4.76.
Ayrıntısı `docs/veri-olcumleri.md` bölüm 11.

`tam dizi` bu ölçekte **model seçmek için kullanılamaz**: doğrulama 245
kırpma, 0.012 demek 3 kırpma demek. Seçim ölçütü düzenleme mesafesi.

---

## 5. Ağırlığı indir

Koşu bitince **Output** sekmesinden `taniyici/best.pt`. Yerelde
`runs/taniyici/` altına koy; Faz 3'ün kısıtlı çözümleyicisi onu kullanacak.

---

## Sınırlar

- Ücretsiz GPU haftada **30 saat**, oturum en fazla **12 saat**.
- Oturum koparsa checkpoint `/kaggle/working` içinde kalır ama iş durur; 20
  epoch bu veri boyutunda saatler değil dakikalar sürer, risk düşük.
- Kaggle çıktı klasörünü 20 GB'a kadar tutuyor; ağırlık birkaç MB.
