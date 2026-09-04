"""Dashcam kayitlarindan plaka adayi kirpmalari cikarir (Faz 0.3).

Plan yeni bir kamera kurulumu ongoruyordu; kamera yok ama iki saatlik dashcam
kaydi var ve icinde bol arac. Olculdu: kare basina ~1.08 arac plakasi
okunabilecek kadar yakin, yani 2 saatten kabaca 3900 aday cikiyor. Plan 500-2000
gercek plaka istiyordu.

Neden aracin tamamini degil de ALT KISMINI kesiyoruz
----------------------------------------------------
Plaka aracin alt seridinde. Butun araci kesmek etiketleyene gereksiz piksel
gosterir ve kirpmalar buyudukce diskte ve ekranda yer kaplar. Alt %45'i almak
plakayi guvenle iceriyor ve tampon/far baglamini da birakiyor - o baglam
etiketleyene "bu bir arac arkasi" demek icin yeterli.

Cozunurluk burada kritik
------------------------
Kareler KAYNAK cozunurlukte cikariliyor (maltepe 2560, yagmur/gece 3840),
1920'ye kucultulmeden. Trafik isareti projesinde 1920 yetiyordu cunku levha
39x33 pikseldi ve sinif ayrimi kaba bir sekil isiydi. Plaka ise KARAKTER
okumak demek: ayni levha genisliginde 8 karakter var. Her piksel sayiyor.

Mahremiyet
----------
Kirpmalar depoya girmiyor (.gitignore). Yayin yapilacaksa yalnizca baglamsiz
plaka kirpmasi yayinlanir, tam sahne degil: plaka bir kisiye baglandigi anda
kisisel veri oluyor ve tam sahne o baglantiyi kurmayi kolaylastiriyor.

Kullanim:
    python scripts/harvest_plates.py "D:/videos/maltepe.mkv" --every 2
    python scripts/harvest_plates.py <video> --every 1.5 --min-width 260
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parent.parent

#: COCO sinif kimlikleri: car, motorcycle, bus, truck.
ARAC_SINIFLARI = {2, 3, 5, 7}

#: Bu genislikten dar araclarda plaka okunacak piksele sahip degil.
#: 200 px'lik bir arac kabaca 50 px plaka demek ve bu tanima icin alt sinir;
#: varsayilan biraz uzerinde tutuluyor, sinirdaki ornekler zaman kaybettiriyor.
MIN_ARAC_GENISLIGI = 240

#: Aracin alt yuzdesi - plaka burada.
ALT_ORAN = 0.45

#: En/boy orani bu degerin ustundeki kutular ELENIR.
#:
#: Ilk denemede 40 kirpmanin ancak dortte birinde plaka vardi; kalani araclarin
#: YAN gorunumuydu ve yandan bakinca alt seritte plaka yok, tekerlek var.
#: "Aracin alt %45'i" varsayimi arkadan/onden gorunum icin dogru, yandan degil.
#:
#: Ayirt edici olan en/boy: arkadan gorunen bir otomobil kabaca kare (1.0-1.5),
#: yandan gorunen ayni araba 2-3 kat genis. Esik olculerek secildi, bkz.
#: docs/hasat-olcumu.md.
MAX_EN_BOY = 1.8

#: Kadraj kenarina degen kutular yarim arac demek; plaka kesilmis olabilir.
#: Kenardan bu kadar piksel iceride olmayan kutular elenir.
KENAR_PAYI = 8

#: Kirpma bu kadar buyutulur. Tanima modeli 32x128 gibi kucuk girdilerle
#: calisacak ama etiketleyen insanin karakterleri okumasi gerekiyor.
MIN_KIRPMA_GENISLIGI = 320


def harvest(video: Path, out: Path, every: float, min_width: int,
            conf: float, limit: int | None, max_en_boy: float = MAX_EN_BOY) -> dict:
    from ultralytics import YOLO

    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        raise SystemExit(f"Video acilamadi: {video}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    toplam_kare = cap.get(cv2.CAP_PROP_FRAME_COUNT)
    sure = toplam_kare / fps
    genislik = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    yukseklik = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    coco = YOLO("yolov8n.pt")
    out.mkdir(parents=True, exist_ok=True)
    stem = video.stem.replace(" ", "_")

    print(f"{video.name}: {sure/60:.1f} dk, {fps:.0f} fps, {genislik}x{yukseklik}")
    print(f"{every} saniyede bir kare -> ~{int(sure/every)} kare taranacak\n")

    basladi = time.perf_counter()
    saniye = 0.0
    kare_sayisi = kirpma_sayisi = 0
    genislikler = []
    elenen = {"yan": 0, "kenar": 0}

    while saniye < sure:
        cap.set(cv2.CAP_PROP_POS_MSEC, saniye * 1000)
        ok, frame = cap.read()
        if not ok:
            break
        kare_sayisi += 1

        # Tespit kucultulmus kopyada yapiliyor - hiz icin. Kirpma ise
        # HAM kareden aliniyor, yani cozunurluk kaybi yok.
        sonuc = coco.predict(frame, conf=conf, imgsz=960, verbose=False)[0]

        for i, kutu in enumerate(sonuc.boxes):
            if int(kutu.cls[0]) not in ARAC_SINIFLARI:
                continue
            x1, y1, x2, y2 = (int(v) for v in kutu.xyxy[0].tolist())
            w, h = x2 - x1, y2 - y1
            if w < min_width or h < 1:
                continue
            if w / h > max_en_boy:
                elenen["yan"] += 1
                continue
            if (x1 < KENAR_PAYI or y1 < KENAR_PAYI
                    or x2 > genislik - KENAR_PAYI or y2 > yukseklik - KENAR_PAYI):
                elenen["kenar"] += 1
                continue

            # Aracin alt seridi: plaka orada.
            ust = y2 - int(h * ALT_ORAN)
            kesit = frame[max(0, ust):min(yukseklik, y2),
                          max(0, x1):min(genislik, x2)]
            if kesit.size == 0 or kesit.shape[1] < 40:
                continue

            if kesit.shape[1] < MIN_KIRPMA_GENISLIGI:
                olcek = MIN_KIRPMA_GENISLIGI / kesit.shape[1]
                kesit = cv2.resize(
                    kesit,
                    (MIN_KIRPMA_GENISLIGI, max(1, int(kesit.shape[0] * olcek))),
                    interpolation=cv2.INTER_CUBIC,
                )

            ad = f"{stem}_{int(saniye):05d}_{i}.jpg"
            cv2.imwrite(str(out / ad), kesit, [cv2.IMWRITE_JPEG_QUALITY, 95])
            kirpma_sayisi += 1
            genislikler.append(w)

            if limit and kirpma_sayisi >= limit:
                cap.release()
                return _rapor(kare_sayisi, kirpma_sayisi, genislikler,
                              time.perf_counter() - basladi, out, elenen)

        if kare_sayisi % 100 == 0:
            print(f"  {kare_sayisi} kare, {kirpma_sayisi} kirpma", flush=True)
        saniye += every

    cap.release()
    return _rapor(kare_sayisi, kirpma_sayisi, genislikler,
                  time.perf_counter() - basladi, out, elenen)


def _rapor(kare: int, kirpma: int, genislikler: list[int],
           gecen: float, out: Path, elenen: dict) -> dict:
    genislikler.sort()
    ortanca = genislikler[len(genislikler) // 2] if genislikler else 0
    print(f"\n{kare} kare tarandi, {kirpma} kirpma yazildi")
    print(f"elenen: {elenen['yan']} yan gorunum, {elenen['kenar']} kadraj kenari")
    if genislikler:
        print(f"arac genisligi: ortanca {ortanca} px, "
              f"en dar {genislikler[0]} px, en genis {genislikler[-1]} px")
    print(f"{gecen/60:.1f} dakika -> {out}")
    return {"kare": kare, "kirpma": kirpma, "dakika": gecen / 60}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("video", type=Path)
    parser.add_argument("--out", type=Path, default=ROOT / "data" / "crops")
    parser.add_argument("--every", type=float, default=2.0,
                        help="Kac saniyede bir kare taransin")
    parser.add_argument("--min-width", type=int, default=MIN_ARAC_GENISLIGI,
                        help="Bundan dar araclar atlanir (plaka okunmaz)")
    parser.add_argument("--conf", type=float, default=0.35)
    parser.add_argument("--max-en-boy", type=float, default=MAX_EN_BOY,
                        help="Bundan genis kutular yan gorunum sayilir ve elenir")
    parser.add_argument("--limit", type=int, default=None,
                        help="Bu kadar kirpmadan sonra dur (deneme icin)")
    args = parser.parse_args(argv)

    if not args.video.is_file():
        raise SystemExit(f"Video yok: {args.video}")
    harvest(args.video, args.out, args.every, args.min_width,
            args.conf, args.limit, args.max_en_boy)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
