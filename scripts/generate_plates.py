"""Sentetik Turk plakasi ureteci (Faz 0.2).

Bozulma araliklari TAHMIN EDILMEDI, gercek veriden olculdu. Projenin sirasi
bunun icin boyle kuruldu: once 690 gercek plaka etiketlendi, sonra uretec
onlara bakilarak ayarlandi. Olculenler docs/veri-olcumleri.md icinde,
ozeti asagida.

KADRAJI DOLDUR: tanima modeli plakayi sahnede gormuyor
------------------------------------------------------
Ilk surum plakayi kadrajin ICINE kucuk ve egik ciziyor, etrafinda arka plan
birakiyordu - cunku olculen perspektif araliklari (yaw ~7, pitch ~20 derece)
oyle soyluyordu. O olcum DOGRUYDU ama YANLIS ASAMAYA aitti.

Tanima modeli plakayi sahnede hic gormuyor. Boru hatti soyle:

    dedektor -> dort kose -> DIKLESTIRME -> tanima

`export_plates.py` dort koseyi kadrajin tamamina oturtuyor, yani gercek egitim
verisinde plaka kareyi KENARDAN KENARA dolduruyor: egim yok, arka plan yok.
Sentetik ise plakayi kucuk ve egik uretiyordu. Model "koyu zeminde kucuk egik
plaka" ogrenip "kadraji dolduran plaka" ile test edildi.

Sonucu olculdu ve tartisilmaz: 20 epoch, egitim kaybi 6.44'ten 0.047'ye
(sentetigi ezberledi), gercek veride tam dizi dogrulugu 20 epoch boyunca
0.000. Kademeli bir alan farki olsaydi yavas bir tirmanis gorulurdu; duz
cizgi "model bu goruntuleri hic tanimiyor" demekti.

Olculen sahne perspektifi Faz 1'in kose regresyonu icin gecerli, Faz 2 icin
degil. Burada modellenmesi gereken sey ARTIK HATA: insanin (ya da dedektorun)
koseyi birkac piksel kaydirmis olmasi. Plaka her zaman kadraji dolduruyor,
yalnizca kenarlari biraz kayiyor.

Olcek: kucult, sonra buyut
--------------------------
Gercek plakalar kaynak karede 70-269 px genisliginde ve tanima icin 256'ya
buyutuluyor. Yani gercek veri bir KUCULTME-BUYUTME kaybi tasiyor. Uretec ayni
yoldan geciyor: yuksek cozunurlukte cizip, gercek dagilimdan ornekelenen bir
genislige indirip, sonra depolama boyutuna geri buyutuyor. Bu adim atlanirsa
sentetik plakalar gercekte hic olmayan bir netlikte olur.

Font: tek font degil, bir kac font
----------------------------------
Resmi plaka fontu elde yok. Tek bir benzer font kullanmak, modelin O FONTUN
kendine has ozelliklerini ogrenmesi riskini tasiyor - sahada karsilasacagi font
farkli olacak. Birkac dar sans-serif donusumlu kullanilarak model fontun
ayrintisina degil karakterin seklinine dayanmaya zorlaniyor.

Il kodu dagitimi
----------------
Gercek verinin 240 plakasindan 201'i "34" (Istanbul cekimi). Uretec bu
carpikligi TASIMIYOR, 01-81 arasini duzgun dagitiyor. Aksi halde model "34"
ezberler ve baska ilde coker.

Kullanim:
    python scripts/generate_plates.py --adet 200 --sheet
    python scripts/generate_plates.py --adet 50000 --out data/synth
"""

from __future__ import annotations

import argparse
import math
import random
import string
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent

#: Turk plakasinda Q, W, X yok; Turkce'ye ozgu harfler de yok.
#: CTC sinif sayisi: 23 harf + 10 rakam + 1 blank = 34.
HARFLER = "ABCDEFGHIJKLMNOPRSTUVYZ"
RAKAMLAR = string.digits

#: Gecerli duzenler: (harf sayisi, rakam sayisi). Il kodu hepsinde iki hane.
#:
#: DIKKAT - bu liste bir kez EKSIKTI ve pahaliya mal oldu. (3, 3) yoktu, oysa
#: 272 gercek plakanin 146'si (%54) tam olarak o duzende. Uretec bugune kadar
#: tek bir 3harf-3rakam plaka uretmedi. Bolum 11'deki "sentetik %75 yedi
#: karakterli, gercek %87 sekiz karakterli" bulgusunun sebebi buydu: belirti
#: gorulmustu, sebebi bulunmamisti.
#:
#: Agirliklar da olculdu. Duzenler esit olasilikla secilirse sentetigin
#: duzen dagilimi gercege benzemiyor; bootstrap ile gercek dagilim tasiniyor.
DUZEN_YEDEK = [((3, 3), 146), ((2, 4), 79), ((3, 2), 22),
               ((2, 3), 21), ((1, 4), 2)]
DUZENLER = [d for d, _ in DUZEN_YEDEK]

#: Gercek plaka 520x110 mm = 4.7:1. Cizim bu oranda yapiliyor.
CIZIM_YUKSEKLIK = 220
CIZIM_GENISLIK = int(CIZIM_YUKSEKLIK * 520 / 110)

#: Depolama boyutu - export_plates.py ile ayni olmali ki sentetik ve gercek
#: veri ayni boru hattindan gecsin.
HEDEF_GENISLIK, HEDEF_YUKSEKLIK = 256, 64

#: Kose isaretleme ARTIK HATASI: her kosenin kadraj boyutuna oranla ne kadar
#: kayabilecegi. Gercek veride en/boy orani 4.6 olculdu, gercek plaka 4.7 -
#: yani kose isaretlemesi kabaca %2 hata tasiyor. Uretec bunun biraz uzerine
#: cikiyor ki dedektorun kose regresyonu daha kaba oldugunda da dayansin.
KOSE_HATASI = 0.05

#: Gercek plaka genisligi dagilimi: %10=70, ortanca=105, %90=269 px.
#: Bu ARALIK olarak degil DAGILIM olarak kullanilmali. Ilk surumde
#: uniform(55, 280) orneklemesi yapiliyordu ve ortancasi 167 cikiyordu -
#: gercegin bir buçuk kati. Sonuc: sentetik plakalar sistematik olarak fazla
#: buyuk cizildi, dolayisiyla fazla keskin kaldi ve zorluk mufredati bu
#: etkinin altinda kayboldu (zorluk 0'dan 1'e giderken keskinlik ortancasi
#: yalnizca 177'den 116'ya indi, gercek 69 iken).
#:
#: Cozum: gercek olculen genislikleri bootstrap ile ornekle. Dagilimin sekli
#: (saga carpik) boylece tahmin edilmiyor, aynen tasiniyor.
OLCEK_YEDEK = (55, 280)   # plates.jsonl yoksa geri donus

#: Metnin kadraji ne kadar doldurdugu: (dikey, yatay). Bu, uretecin
#: kalibrasyonundaki UCUNCU asama hatasiydi ve en pahalisi oldu.
#:
#: Uretec fiziksel olarak dogru plakayi ciziyor: kenarlik, mavi TR bandi,
#: kenar payi. Ama model plakayi gormuyor - dort koseden DIKLESTIRILMIS
#: kirpmayi goruyor, ve o kirpma metne yapisik cikiyor. Olculdu (811 gercek
#: kirpma): dikey doluluk ortancasi 1.00, %61'i 0.95 uzerinde; sentetikte
#: ayni sayi 0.78. Karakter adimi gercekte 14.1 px, sentetikte 12.3 px.
#:
#: Sonucu: model "karakter su boyuttadir" diye ogrendi, gercekte %15 daha
#: buyugunu gordu ve sembol DUSURDU. Gercek dogrulamada plaka basina 7.82
#: karakter yerine 4.76 karakter basiyordu; sentetikte ayni model uzunlugu
#: tam tutturuyordu (fark -0.10). Yani ariza taniyicida degil, buradaydi.
#:
#: 1.00'de yigilma sansur belirtisi: kadraj disina tasan metin de 1.00
#: olculur. Bu yuzden az miktarda TASMA da uretiliyor - olcum bunu
#: gosteremez, ama yigilmanin sebebi budur.
DOLULUK_YEDEK = [(0.97, 1.00)]   # data/plates yoksa geri donus

FONT_ADAYLARI = ["arialnb.ttf", "arialn.ttf", "bahnschrift.ttf"]

#: Mufredat rampasinin egimi. 1.0 dogrusal; buyudukce zorluk erken
#: doyuyor ve kumede zor orneklerin payi artiyor. Deger olculerek
#: secildi (bkz. docs/veri-olcumleri.md, sentetik kalibrasyon).
RAMPA = 1.6

#: Zemin/yazi renkleri. Beyaz standart, sari ticari. Digerleri az sayida.
RENKLER = [
    ((250, 250, 250), (20, 20, 20), 0.82),   # beyaz zemin, siyah yazi
    ((250, 210, 40), (20, 20, 20), 0.14),    # sari (ticari)
    ((200, 40, 40), (250, 250, 250), 0.02),  # kirmizi (resmi)
    ((40, 70, 190), (250, 250, 250), 0.02),  # mavi (diplomatik)
]


def gercek_keskinlik_tabani(dilim: float = 0.05) -> float:
    """Gercek plakalarin en bulanik %5'lik esigi - sentetigin alt siniri."""
    klasor = ROOT / "data" / "plates"
    if not klasor.is_dir():
        return 0.0
    v = []
    for p in sorted(klasor.glob("*.jpg")):
        im = cv2.imread(str(p), cv2.IMREAD_GRAYSCALE)
        if im is not None:
            v.append(float(cv2.Laplacian(im, cv2.CV_64F).var()))
    if not v:
        return 0.0
    v.sort()
    return v[max(0, int(dilim * len(v)) - 1)]


def _doluluk_olc(gri: np.ndarray) -> tuple[float, float] | None:
    """Bir kirpmada metnin kadraji ne kadar doldurdugunu olcer."""
    e = cv2.threshold(gri, 0, 255,
                      cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1] > 0
    h, w = e.shape
    ic = e[:, int(w * 0.12):]          # sol %12: TR bandi ve kenarlik
    if ic.size == 0:
        return None
    satir, sutun = ic.mean(axis=1), ic.mean(axis=0)
    var_s = satir > max(0.08, satir.max() * 0.35)
    var_c = sutun > max(0.08, sutun.max() * 0.30)
    if not var_s.any() or not var_c.any():
        return None
    yuk = h - int(np.argmax(var_s[::-1])) - int(np.argmax(var_s))
    gen = ic.shape[1] - int(np.argmax(var_c[::-1])) - int(np.argmax(var_c))
    return yuk / h, gen / ic.shape[1]


def gercek_doluluk() -> list[tuple[float, float]]:
    """Gercek kirpmalarin doluluk dagilimi (bootstrap kaynagi)."""
    klasor = ROOT / "data" / "plates"
    if not klasor.is_dir():
        print("UYARI: data/plates yok, doluluk dagilimi OLCULMEDI, yedek "
              "deger kullaniliyor. Once: python scripts/export_plates.py")
        return []
    cikti = []
    for yol in sorted(klasor.glob("*.jpg")):
        im = cv2.imread(str(yol), cv2.IMREAD_GRAYSCALE)
        if im is None:
            continue
        d = _doluluk_olc(im)
        if d:
            cikti.append(d)
    return cikti


def gercek_genislikler() -> list[float]:
    """Olculen gercek plaka genisliklerini dondurur (bootstrap kaynagi).

    Dosya yoksa uyarip yedek araliga duser - ama o durumda uretecin olcek
    dagilimi gercege dayanmiyor demektir ve bu sessizce gecmemeli.
    """
    yol = ROOT / "data" / "plates.jsonl"
    if not yol.is_file():
        print("UYARI: plates.jsonl yok, olcek dagilimi OLCULMEDI, yedek "
              "aralik kullaniliyor. Once: python scripts/export_plates.py")
        return []
    import json
    return [json.loads(l)["genislik_px"]
            for l in yol.read_text(encoding="utf-8").splitlines() if l.strip()]


def fontlari_bul() -> list[Path]:
    kok = Path("C:/Windows/Fonts")
    bulunan = [kok / ad for ad in FONT_ADAYLARI if (kok / ad).is_file()]
    if not bulunan:
        raise SystemExit(
            "Dar sans-serif font bulunamadi. FONT_ADAYLARI listesini "
            "sistemdeki bir fontla guncelleyin."
        )
    return bulunan


def gercek_duzenler() -> list[tuple[int, int]]:
    """Gercek plaka metinlerinden olculen duzen dagilimi (bootstrap kaynagi).

    Agirlikli havuz olarak donuyor: her duzen gercekte gorulen sayida
    tekrarlaniyor, rng.choice dogrudan dogru olasilikla cekiyor.
    """
    import re
    yol = ROOT / "data" / "plates.jsonl"
    if not yol.is_file():
        print("UYARI: plates.jsonl yok, duzen dagilimi OLCULMEDI, olculmus "
              "yedek dagilim kullaniliyor.")
        return [d for d, n in DUZEN_YEDEK for _ in range(n)
                if d in DUZENLER]
    import json
    havuz = []
    for satir in yol.read_text(encoding="utf-8").splitlines():
        if not satir.strip():
            continue
        m = re.fullmatch(r"(\d{2})([A-Z]+)(\d+)",
                         json.loads(satir).get("metin", ""))
        if m and (len(m.group(2)), len(m.group(3))) in DUZENLER:
            havuz.append((len(m.group(2)), len(m.group(3))))
    if not havuz:
        return [d for d, n in DUZEN_YEDEK for _ in range(n)
                if d in DUZENLER]
    return havuz


def plaka_metni(rng: random.Random, duzen_havuzu=None) -> str:
    """Gecerli bir plaka dizisi uretir; il kodu 01-81 arasinda DUZGUN dagilir."""
    il = rng.randint(1, 81)
    harf_n, rakam_n = rng.choice(duzen_havuzu or DUZENLER)
    harf = "".join(rng.choice(HARFLER) for _ in range(harf_n))
    rakam = "".join(rng.choice(RAKAMLAR) for _ in range(rakam_n))
    return f"{il:02d}{harf}{rakam}"


def temiz_plaka(metin: str, font_yolu: Path, rng: random.Random):
    """Katman 1: dogru oranli, TR bantli, temiz plaka.

    (goruntu, metin_kutusu) dondurur; kutuyu metne_kirp kullaniyor.
    """
    zemin, yazi, _ = _agirlikli_secim(RENKLER, rng)
    im = Image.new("RGB", (CIZIM_GENISLIK, CIZIM_YUKSEKLIK), zemin)
    ciz = ImageDraw.Draw(im)

    # Sol taraftaki mavi AB/TR bandi.
    bant_g = int(CIZIM_GENISLIK * 0.075)
    ciz.rectangle([0, 0, bant_g, CIZIM_YUKSEKLIK], fill=(20, 50, 150))
    try:
        kucuk = ImageFont.truetype(str(font_yolu), int(CIZIM_YUKSEKLIK * 0.22))
        ciz.text((bant_g // 2, int(CIZIM_YUKSEKLIK * 0.72)), "TR",
                 font=kucuk, fill=(250, 250, 250), anchor="mm")
    except OSError:
        pass

    # Kenarlik.
    ciz.rectangle([0, 0, CIZIM_GENISLIK - 1, CIZIM_YUKSEKLIK - 1],
                  outline=yazi, width=max(2, CIZIM_YUKSEKLIK // 40))

    # Metin: bandin sagina, dikeyde ortalanmis.
    # Carpan sartnameden: gercek plakada karakter 80 mm, plaka 110 mm = 0.73.
    # Kenarliga pay birakip 0.70. Onceki 0.62 uydurmaydi ve gercek plakalarla
    # yan yana konunca karakterler belirgin kucuk kaliyordu.
    boyut = int(CIZIM_YUKSEKLIK * 0.70)
    font = ImageFont.truetype(str(font_yolu), boyut)
    alan_sol, alan_sag = bant_g + int(CIZIM_GENISLIK * 0.02), CIZIM_GENISLIK - 12
    # Karakter araligi gercek plakadaki gibi acilir; tek tek ciziliyor.
    aralik = rng.uniform(0.06, 0.13) * boyut
    genislikler = [ciz.textlength(c, font=font) for c in metin]
    toplam = sum(genislikler) + aralik * (len(metin) - 1)
    olcek = min(1.0, (alan_sag - alan_sol) / toplam)
    if olcek < 1.0:
        boyut = int(boyut * olcek)
        font = ImageFont.truetype(str(font_yolu), boyut)
        aralik *= olcek
        genislikler = [ciz.textlength(c, font=font) for c in metin]
        toplam = sum(genislikler) + aralik * (len(metin) - 1)

    x = alan_sol + (alan_sag - alan_sol - toplam) / 2
    y = CIZIM_YUKSEKLIK / 2
    kutu = None
    for c, g in zip(metin, genislikler):
        b = ciz.textbbox((x, y), c, font=font, anchor="lm")
        kutu = b if kutu is None else (min(kutu[0], b[0]), min(kutu[1], b[1]),
                                       max(kutu[2], b[2]), max(kutu[3], b[3]))
        ciz.text((x, y), c, font=font, fill=yazi, anchor="lm")
        x += g + aralik

    return cv2.cvtColor(np.array(im), cv2.COLOR_RGB2BGR), kutu


def metne_kirp(im: np.ndarray, kutu, rng: random.Random,
               doluluk_havuzu: list[tuple[float, float]] | None) -> np.ndarray:
    """Katman 1b: kadraji gercek kirpmalarin doluluguna gore daraltir.

    Gercek veri diklestirilmis kirpma; kenarlik ve TR bandi cogunlukla
    kadrajin disinda kaliyor. Buradaki kirpma o kadraji taklit ediyor.
    Doluluk sabit bir sayi degil OLCULEN DAGILIMDAN cekiliyor - genislik
    ve keskinlikte oldugu gibi, dagilimin sekli tahmin edilmiyor tasiniyor.
    """
    if kutu is None:
        return im
    h, w = im.shape[:2]
    x0, y0, x1, y1 = kutu
    mh, mw = max(1.0, y1 - y0), max(1.0, x1 - x0)

    if doluluk_havuzu:
        d_dikey, d_yatay = doluluk_havuzu[rng.randrange(len(doluluk_havuzu))]
    else:
        d_dikey, d_yatay = DOLULUK_YEDEK[0]

    # Olcum 1.00'de sansurlu: kadraji tasan metin de 1.00 okunur. Yigilmanin
    # payi kadar tasma geri veriliyor, yoksa uretecin ust ucu gercekten
    # sistematik olarak genis kalir.
    if d_dikey >= 0.995:
        d_dikey = rng.uniform(0.98, 1.06)
    if d_yatay >= 0.995:
        d_yatay = rng.uniform(0.99, 1.04)

    hedef_h, hedef_w = mh / max(0.3, d_dikey), mw / max(0.3, d_yatay)
    cy, cx = (y0 + y1) / 2, (x0 + x1) / 2
    ky0, ky1 = cy - hedef_h / 2, cy + hedef_h / 2
    kx0, kx1 = cx - hedef_w / 2, cx + hedef_w / 2

    # Tuval disina tasan kisim plaka disi (arac govdesi) olurdu; onu
    # modellemek ayri bir is. Kirpma tuvale sikistiriliyor.
    ky0, ky1 = max(0, int(round(ky0))), min(h, int(round(ky1)))
    kx0, kx1 = max(0, int(round(kx0))), min(w, int(round(kx1)))
    if ky1 - ky0 < 8 or kx1 - kx0 < 24:
        return im
    return im[ky0:ky1, kx0:kx1]


def _agirlikli_secim(secenekler, rng: random.Random):
    r = rng.random()
    birikim = 0.0
    for s in secenekler:
        birikim += s[-1]
        if r <= birikim:
            return s
    return secenekler[0]


def fiziksel_yipranma(im: np.ndarray, rng: random.Random) -> np.ndarray:
    """Katman 2: kir, cizik, vida delikleri, solma."""
    h, w = im.shape[:2]
    out = im.astype(np.float32)

    # Kir/camur: dusuk frekansli gurultu maskesi.
    if rng.random() < 0.7:
        kucuk = np.random.RandomState(rng.randint(0, 10**6)).rand(
            max(2, h // 24), max(2, w // 24)).astype(np.float32)
        maske = cv2.resize(kucuk, (w, h), interpolation=cv2.INTER_CUBIC)
        maske = np.clip((maske - 0.5) * rng.uniform(0.3, 1.0) + 0.5, 0, 1)
        yogunluk = rng.uniform(0.05, 0.35)
        out *= (1 - yogunluk * (1 - maske))[..., None]

    # Cizikler.
    for _ in range(rng.randint(0, 3)):
        x1, y1 = rng.randint(0, w), rng.randint(0, h)
        x2, y2 = x1 + rng.randint(-w // 3, w // 3), y1 + rng.randint(-h // 4, h // 4)
        cv2.line(out, (x1, y1), (x2, y2),
                 (rng.randint(90, 200),) * 3, rng.randint(1, 3))

    # Montaj vidalari.
    if rng.random() < 0.5:
        for kx in (int(w * 0.12), int(w * 0.88)):
            cv2.circle(out, (kx, int(h * rng.uniform(0.12, 0.2))),
                       max(2, h // 28), (rng.randint(60, 140),) * 3, -1)

    # Solma: kontrasti dusur.
    if rng.random() < 0.4:
        k = rng.uniform(0.65, 0.95)
        out = out * k + 255 * (1 - k) * rng.uniform(0.3, 0.7)

    return np.clip(out, 0, 255).astype(np.uint8)


def kose_hatasi(im: np.ndarray, rng: random.Random) -> np.ndarray:
    """Katman 3: kose isaretleme artik hatasi - plaka kadraji DOLDURMAYA devam eder.

    Gercek veride plaka dikleştirilmis geliyor ve kadraji kenardan kenara
    dolduruyor. Modellenecek tek bozulma, koselerin birkac piksel kaymis
    olmasi: insan elle isaretlerken ya da dedektor kose tahmin ederken tam
    isabet etmiyor. Kayma bazen plakanin biraz disini, bazen biraz icini
    aliyor.

    Onceki surum burada buyuk bir sahne perspektifi uyguluyor ve plakayi
    kadrajin icinde kucultuyordu. O, tanima modelinin hic gormeyecegi bir
    goruntu uretiyordu (bkz. modul aciklamasi).
    """
    h, w = im.shape[:2]
    d = KOSE_HATASI
    def sap():
        return rng.uniform(-d, d)
    # Kaynak koseler kadrajin hafif icinde/disinda; hedef tam kadraj.
    kaynak = np.float32([
        [w * sap(),         h * sap()],
        [w * (1 + sap()),   h * sap()],
        [w * (1 + sap()),   h * (1 + sap())],
        [w * sap(),         h * (1 + sap())],
    ])
    hedef = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
    M = cv2.getPerspectiveTransform(kaynak, hedef)
    return cv2.warpPerspective(im, M, (w, h), borderMode=cv2.BORDER_REPLICATE,
                               flags=cv2.INTER_CUBIC)


def goruntuleme(im: np.ndarray, rng: random.Random, zorluk: float,
                genislik_havuzu: list[float] | None = None) -> np.ndarray:
    """Katman 4: olcek kaybi, bulaniklik, gurultu, parlama, JPEG.

    `zorluk` 0-1: mufredat icin. Egitimin basinda hafif, sonra artan.
    """
    h, w = im.shape[:2]

    # Gercek olcege indir - asil bilgi kaybi burada. Genislik olculen
    # dagilimdan bootstrap ile cekiliyor; sabit bir aralik yerine gercegin
    # sekli tasiniyor.
    if genislik_havuzu:
        hedef_g = int(rng.choice(genislik_havuzu))
    else:
        hedef_g = int(rng.uniform(*OLCEK_YEDEK))
    hedef_g = max(38, hedef_g)
    kucuk = cv2.resize(im, (hedef_g, max(10, int(hedef_g * h / w))),
                       interpolation=cv2.INTER_AREA)

    # Hareket bulanikligi: yonlu cekirdek. Mufredatin asil tasiyicisi bu -
    # olcek artik zorluga degil gercek dagilima bagli oldugu icin.
    if rng.random() < 0.25 + 0.55 * zorluk:
        uzunluk = max(3, int(rng.uniform(3, 5 + 10 * zorluk)))
        aci = rng.uniform(-25, 25)
        cekirdek = np.zeros((uzunluk, uzunluk), np.float32)
        cekirdek[uzunluk // 2, :] = 1.0
        R = cv2.getRotationMatrix2D((uzunluk / 2 - 0.5, uzunluk / 2 - 0.5), aci, 1.0)
        cekirdek = cv2.warpAffine(cekirdek, R, (uzunluk, uzunluk))
        s = cekirdek.sum()
        if s > 0:
            kucuk = cv2.filter2D(kucuk, -1, cekirdek / s)

    # Odak bulanikligi.
    if rng.random() < 0.25 + 0.35 * zorluk:
        k = rng.choice([3, 3, 5] if zorluk < 0.6 else [3, 5, 5])
        kucuk = cv2.GaussianBlur(kucuk, (k, k), 0)

    # Parlaklik / kontrast.
    kucuk = np.clip(kucuk.astype(np.float32) * rng.uniform(0.55, 1.35)
                    + rng.uniform(-45, 45), 0, 255)

    # Far parlamasi: radyal parlak leke.
    if rng.random() < 0.25:
        yy, xx = np.mgrid[0:kucuk.shape[0], 0:kucuk.shape[1]]
        cx, cy = rng.uniform(0, kucuk.shape[1]), rng.uniform(0, kucuk.shape[0])
        yaricap = rng.uniform(0.2, 0.6) * kucuk.shape[1]
        g = np.exp(-((xx - cx) ** 2 + (yy - cy) ** 2) / (2 * yaricap ** 2))
        kucuk = np.clip(kucuk + (g * rng.uniform(40, 130))[..., None], 0, 255)

    # Gurultu.
    kucuk = np.clip(kucuk + np.random.RandomState(rng.randint(0, 10**6)).normal(
        0, rng.uniform(2, 6 + 10 * zorluk), kucuk.shape), 0, 255).astype(np.uint8)

    # JPEG artefakti.
    kalite = int(rng.uniform(30, 95))
    ok, tampon = cv2.imencode(".jpg", kucuk, [cv2.IMWRITE_JPEG_QUALITY, kalite])
    if ok:
        kucuk = cv2.imdecode(tampon, cv2.IMREAD_COLOR)

    # Depolama boyutuna geri buyut - gercek veri de bu yoldan geciyor.
    return cv2.resize(kucuk, (HEDEF_GENISLIK, HEDEF_YUKSEKLIK),
                      interpolation=cv2.INTER_CUBIC)


def uret(rng: random.Random, fontlar: list[Path], zorluk: float,
         genislik_havuzu: list[float] | None = None,
         keskinlik_tabani: float = 0.0,
         doluluk_havuzu: list[tuple[float, float]] | None = None,
         duzen_havuzu: list[tuple[int, int]] | None = None
         ) -> tuple[np.ndarray, str]:
    """Bir sentetik plaka uretir; taban altinda kalirsa yeniden dener.

    Taban neden var: bozulma katmanlari birlesince bazen GERCEK VERIDE HIC
    BULUNMAYAN bir bulaniklik cikiyor. Olculdu - sentetigin %10'luk dilimi 7,
    gercegin %10'luk dilimi 19. O bolgede plaka insan gozuyle de okunmuyor,
    yani etiket kurtarilamaz durumda ve model oradan gurultu ogrenir.

    Taban gercek dagilimin %5'lik dilimi: sentetik hicbir ornek gercekte
    gorulenden daha bozuk olmasin. Ust uc serbest birakildi - gercekten daha
    KESKIN ornek zararsiz, yalnizca kolay.
    """
    for _ in range(6):
        metin = plaka_metni(rng, duzen_havuzu)
        im, kutu = temiz_plaka(metin, rng.choice(fontlar), rng)
        im = metne_kirp(im, kutu, rng, doluluk_havuzu)
        im = fiziksel_yipranma(im, rng)
        im = kose_hatasi(im, rng)
        im = goruntuleme(im, rng, zorluk, genislik_havuzu)
        if keskinlik_tabani <= 0:
            return im, metin
        gri = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY)
        if float(cv2.Laplacian(gri, cv2.CV_64F).var()) >= keskinlik_tabani:
            return im, metin
    # Alti denemede tutmadiysa sonuncusu doner: dongunun sonsuza gitmesi,
    # bir kac fazla bulanik ornekten daha kotu.
    return im, metin


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--adet", type=int, default=200)
    parser.add_argument("--out", type=Path, default=ROOT / "data" / "synth")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--zorluk", type=float, default=None,
                        help="0-1 sabit zorluk; verilmezse mufredat (0->1)")
    parser.add_argument("--sheet", action="store_true",
                        help="Ornek tabakasi uret, dosya yazma")
    args = parser.parse_args(argv)

    rng = random.Random(args.seed)
    fontlar = fontlari_bul()
    havuz = gercek_genislikler()
    doluluk = gercek_doluluk()
    duzenler = gercek_duzenler()
    print(f"{len(fontlar)} font: " + ", ".join(f.name for f in fontlar))
    taban = gercek_keskinlik_tabani()
    if havuz:
        print(f"olcek dagilimi {len(havuz)} gercek plakadan bootstrap ediliyor")
    if taban:
        print(f"keskinlik tabani {taban:.0f} (gercek verinin %5'lik dilimi)")
    if doluluk:
        import statistics as ist
        print(f"doluluk dagilimi {len(doluluk)} gercek kirpmadan bootstrap "
              f"ediliyor (dikey ortanca "
              f"{ist.median(d for d, _ in doluluk):.2f})")

    if args.sheet:
        hucreler = []
        for i in range(24):
            im, metin = uret(rng, fontlar, i / 23, havuz, taban, doluluk, duzenler)
            c = np.full((HEDEF_YUKSEKLIK + 26, HEDEF_GENISLIK, 3), 22, np.uint8)
            c[:HEDEF_YUKSEKLIK] = im
            cv2.putText(c, metin, (4, HEDEF_YUKSEKLIK + 18),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 205), 1, cv2.LINE_AA)
            hucreler.append(c)
        satirlar = [np.hstack(hucreler[i:i + 4]) for i in range(0, 24, 4)]
        yol = ROOT / "data" / "synth_ornek.jpg"
        cv2.imwrite(str(yol), np.vstack(satirlar))
        print(f"24 ornek (soldan saga zorluk artiyor) -> {yol}")
        return 0

    args.out.mkdir(parents=True, exist_ok=True)
    for p in args.out.glob("*.jpg"):
        p.unlink()
    manifest = []
    for i in range(args.adet):
        # Mufredat: bastan en zor ornekleri vermek modelin ogrenmesini
        # engelliyor. Zorluk sirali uretiliyor, egitimde sirali okunacak.
        #
        # Rampa DOGRUSAL DEGIL, sikistirilmis. Dogrusal rampada orneklerin
        # yarisi kolay bolgede kaliyor ve kumenin toplam dagilimi gercekten
        # belirgin temiz cikiyordu (ortanca 105'e karsi 69). Zorluk kumenin
        # ilk %62'sinde 1.0'a ulasip orada kaliyor: mufredat korunuyor ama
        # orneklerin ucte birinden fazlasi en zor bantta uretiliyor.
        z = (args.zorluk if args.zorluk is not None
             else min(1.0, i / max(1, args.adet - 1) * RAMPA))
        im, metin = uret(rng, fontlar, z, havuz, taban, doluluk, duzenler)
        ad = f"{i:07d}_{metin}.jpg"
        cv2.imwrite(str(args.out / ad), im, [cv2.IMWRITE_JPEG_QUALITY, 95])
        manifest.append(f"{ad}\t{metin}\t{z:.3f}")
        if (i + 1) % 5000 == 0:
            print(f"  {i + 1}/{args.adet}", flush=True)

    (args.out.parent / "synth.tsv").write_text("\n".join(manifest) + "\n",
                                               encoding="utf-8")
    print(f"\n{args.adet} sentetik plaka -> {args.out}")
    print("Zorluk sirali uretildi (mufredat icin); egitimde sirayi koru.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
