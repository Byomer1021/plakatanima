"""Boru hattinin her adimi ne kadar suruyor - bu makinede, olculerek.

Neden bu betik var
------------------
Baslangictaki plan "Jetson Orin Nano'da 30 FPS" diyordu. Donanim olmadigi
icin o iddia dusuruldu ve yerine "bulut GPU'da olculdu, uc cihaz olculmedi"
yazildi. Ama proje bugune kadar hizi HICBIR YERDE olcmedi; "ne kadar hizli"
sorusuna verecek sayisi yoktu. Bu betik o boslugu, abartmadan, elde olan
donanimla dolduruyor.

Olculen sey
-----------
Kare basina degil, ADIM basina. Cunku adimlarin girdi sayisi farkli:

  YOLO        kare basina bir kez
  kose modeli arac basina bir kez
  diklestirme arac basina bir kez
  taniyici    arac basina bir kez
  C++ cozum   arac basina bir kez

Kare basina toplam, bunlarin arac sayisiyla agirlikli toplami. Gercek
veride kare basina 1.08 arac olculmustu (bkz. on-rapor); betik onu
varsaymak yerine kullanilan videodan sayiyor.

Sinirlar acikca
---------------
- Tek is parcacigi degil: PyTorch CPU'da kendi ipliklerini kullaniyor,
  kac iplik oldugu yaziliyor.
- Toplu isleme yok: her arac tek tek gecirildi. Yiginlamak arac basina
  maliyeti dusururdu; olculen sey en kotu hal.
- C++ cozumleyici burada surec baslatma maliyetiyle birlikte olculuyor,
  yani gercek hesabindan buyuk gorunur. Ayrica surecsiz de veriliyor.

Kullanim:
    python scripts/benchmark.py
    python scripts/benchmark.py --kare 200
"""

from __future__ import annotations

import argparse
import statistics
import struct
import subprocess
import sys
import time
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from export_plates import dikleştir                                # noqa: E402
from train_corners import (GENISLIK as K_GEN, YUKSEKLIK as K_YUK,  # noqa: E402
                           girdiye, model_kur as kose_model_kur)
from train_recognizer import diziden, model_kur as tan_model_kur   # noqa: E402

HEDEF_GENISLIK, HEDEF_YUKSEKLIK = 256, 64


def sure(f, tekrar: int, isinma: int = 3):
    """Medyan sure (ms). Ortalama degil: tek bir takilma ortalamayi bozar."""
    for _ in range(isinma):
        f()
    olcum = []
    for _ in range(tekrar):
        t = time.perf_counter()
        f()
        olcum.append((time.perf_counter() - t) * 1000)
    return statistics.median(olcum), olcum


def main(argv: list[str] | None = None) -> int:
    import torch

    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--video", type=Path,
                    default=Path.home() / "Videos" / "maltepe.mkv")
    ap.add_argument("--kare", type=int, default=60,
                    help="YOLO icin kac kare olculecek")
    ap.add_argument("--tekrar", type=int, default=30)
    ap.add_argument("--kose", type=Path, default=ROOT / "runs" / "varlik" / "best.pt")
    ap.add_argument("--taniyici", type=Path,
                    default=ROOT / "runs" / "ince" / "best.pt")
    ap.add_argument("--exe", type=Path, default=ROOT / "cpp" / "decode.exe")
    ap.add_argument("--yolo", type=Path, default=ROOT / "yolov8n.pt")
    args = ap.parse_args(argv)

    cihaz = torch.device("cpu")
    print(f"PyTorch iplik sayisi: {torch.get_num_threads()}")
    print(f"cihaz: cpu (bu makinedeki GTX 1080 agir yuk altinda dort kez "
          f"dustu)\n")

    # --- kaynak kareler ---------------------------------------------------
    kareler = []
    if args.video.is_file():
        cap = cv2.VideoCapture(str(args.video))
        fps = cap.get(cv2.CAP_PROP_FPS) or 30
        toplam_kare = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 0
        # Kareler video BOYUNCA dagitiliyor. Bastan ardisik okumak yaniltici:
        # 60 fps'te 40 kare 0.7 saniye eder ve o anda yakin arac olmayabilir -
        # ilk olcumde tam bu oldu ve kare basina arac sayisi 0.00 cikti.
        if toplam_kare > args.kare:
            noktalar = np.linspace(0, toplam_kare - 1, args.kare).astype(int)
            for n in noktalar:
                cap.set(cv2.CAP_PROP_POS_FRAMES, int(n))
                ok, kare = cap.read()
                if ok:
                    kareler.append(kare)
        else:
            while len(kareler) < args.kare:
                ok, kare = cap.read()
                if not ok:
                    break
                kareler.append(kare)
        cap.release()
        print(f"video: {args.video.name}  {kareler[0].shape[1]}x"
              f"{kareler[0].shape[0]} @ {fps:.0f} fps, {len(kareler)} kare")
    else:
        print(f"video yok ({args.video}); YOLO adimi atlaniyor")
        fps = 30.0

    # --- YOLO -------------------------------------------------------------
    yolo_ms = None
    arac_kare = None
    if kareler and args.yolo.is_file():
        from ultralytics import YOLO
        model = YOLO(str(args.yolo))
        from harvest_plates import MIN_ARAC_GENISLIGI
        hepsi = [0]
        gecen = [0]
        i = [0]

        def bir_kare():
            r = model.predict(kareler[i[0] % len(kareler)], verbose=False,
                              classes=[2, 3, 5, 7], device="cpu")
            kutular = r[0].boxes.xyxy.cpu().numpy() if len(r[0].boxes) else []
            hepsi[0] += len(kutular)
            # Asagi akisin maliyetini yalnizca GENISLIK FILTRESINI gecen
            # araclar dogurur; hepsini saymak kare maliyetini sisiriyor.
            for x1, y1, x2, y2 in kutular:
                if (x2 - x1) >= MIN_ARAC_GENISLIGI:
                    gecen[0] += 1
            i[0] += 1

        yolo_ms, _ = sure(bir_kare, min(args.tekrar, len(kareler)))
        tum_arac = hepsi[0] / max(1, i[0])
        arac_kare = gecen[0] / max(1, i[0])
        print(f"YOLO: kare basina {tum_arac:.2f} arac tespiti, "
              f"bunlarin {arac_kare:.2f} tanesi genislik filtresini "
              f"({MIN_ARAC_GENISLIGI} px) geciyor")
        print(f"      asagi akis maliyetini yalnizca gecenler doguruyor\n")

    # --- kose modeli ------------------------------------------------------
    km = kose_model_kur().to(cihaz).eval()
    km.load_state_dict(torch.load(args.kose, map_location=cihaz,
                                  weights_only=False)["model"])
    ornek_arac = np.random.randint(0, 255, (144, 386, 3), dtype=np.uint8)
    x_kose = torch.from_numpy(np.stack([girdiye(
        cv2.resize(ornek_arac, (K_GEN, K_YUK)))]))

    def kose_adim():
        with torch.no_grad():
            km(x_kose)

    kose_ms, _ = sure(kose_adim, args.tekrar)

    # --- diklestirme ------------------------------------------------------
    kose4 = [[40, 60], [140, 62], [139, 86], [39, 84]]

    def dik_adim():
        dikleştir(ornek_arac, kose4, HEDEF_GENISLIK, HEDEF_YUKSEKLIK)

    dik_ms, _ = sure(dik_adim, args.tekrar * 3)

    # --- taniyici ---------------------------------------------------------
    tm = tan_model_kur().to(cihaz).eval()
    tm.load_state_dict(torch.load(args.taniyici, map_location=cihaz,
                                   weights_only=False)["model"])
    gri = np.random.randint(0, 255, (32, 128), dtype=np.uint8)
    x_tan = torch.from_numpy(np.stack([diziden(gri)]))

    def tan_adim():
        with torch.no_grad():
            tm(x_tan).log_softmax(2)

    tan_ms, _ = sure(tan_adim, args.tekrar)

    # --- C++ cozumleyici --------------------------------------------------
    gecici = ROOT / "runs" / "_kiyas"
    gecici.mkdir(parents=True, exist_ok=True)
    T, C = 32, 34
    with torch.no_grad():
        m = tm(x_tan).log_softmax(2)[:, 0, :].numpy().astype(np.float32)

    def yaz(n):
        with (gecici / "logits.bin").open("wb") as f:
            f.write(b"PLKA")
            f.write(struct.pack("<iii", n, T, C))
            for _ in range(n):
                f.write(np.ascontiguousarray(m).tobytes())

    def coz_adim():
        subprocess.run([str(args.exe), str(gecici / "logits.bin"),
                        str(gecici / "cozum.tsv")], check=True,
                       capture_output=True)

    yaz(1)
    coz1_ms, _ = sure(coz_adim, 10)
    yaz(200)
    coz200_ms, _ = sure(coz_adim, 5)
    coz_ms = (coz200_ms - coz1_ms) / 199        # surec maliyeti dusulmus

    # --- rapor ------------------------------------------------------------
    n_arac = arac_kare if arac_kare is not None else 1.08
    print("=" * 62)
    print("ADIM BASINA (medyan, ms)")
    print("=" * 62)
    satir = [("YOLO arac tespiti", yolo_ms, "kare"),
             ("kose modeli", kose_ms, "arac"),
             ("diklestirme (OpenCV)", dik_ms, "arac"),
             ("taniyici (CTC)", tan_ms, "arac"),
             ("C++ kisitli cozum", coz_ms, "arac")]
    for ad, ms, birim in satir:
        if ms is None:
            print(f"  {ad:<26}{'atlandi':>10}   / {birim}")
        else:
            print(f"  {ad:<26}{ms:>10.2f}   / {birim}")
    print(f"\n  C++ cozumleyici tek cagri (surec baslatma dahil): "
          f"{coz1_ms:.1f} ms")
    print(f"  200 ornekten hesaplanan saf cozum suresi:        {coz_ms:.2f} ms")

    arac_toplam = kose_ms + dik_ms + tan_ms + coz_ms
    print(f"\n  arac basina toplam (YOLO haric): {arac_toplam:>8.2f} ms")
    if yolo_ms:
        kare_toplam = yolo_ms + n_arac * arac_toplam
        print(f"  kare basina toplam ({n_arac:.2f} arac): "
              f"{kare_toplam:>8.2f} ms  ->  {1000/kare_toplam:>5.1f} FPS")
        print(f"\n  Kaydin kendisi {fps:.0f} fps. Gercek zamanli demek icin"
              f" kare basina")
        print(f"  {1000/fps:.1f} ms gerekiyor; olculen {kare_toplam:.1f} ms.")
        oran = kare_toplam / (1000 / fps)
        print(f"  {'YETIYOR' if oran <= 1 else f'{oran:.1f} KAT YAVAS'}"
              f"  (her kare islenirse)")
        # Ham FPS tek basina bir sey soylemiyor; ISIN NE ISTEDIGI lazim.
        pay = 1000 / kare_toplam
        print(f"\n  Ama 60 FPS'in tamami gerekmiyor. Bir arac kadrajda")
        print(f"  saniyelerce kaliyor ve oylama yalnizca birkac kare istiyor:")
        for saniye in (1.0, 2.0):
            print(f"    arac {saniye:.0f} saniye gorunurse -> "
                  f"{pay*saniye:.0f} kare islenir")
        print(f"  Bolum 17'de bes ve uzeri karesi olan plakalarin hepsi dogru")
        print(f"  okunmustu; {pay:.1f} FPS bunu fazlasiyla sagliyor.")
        print(f"\n  Darbogaz YOLO: kare maliyetinin "
              f"%{100*yolo_ms/kare_toplam:.0f}'i.")
        print(f"  Projenin kendi yazdigi uc model (kose, taniyici, cozumleyici)")
        print(f"  toplamda {n_arac*arac_toplam:.1f} ms. Yani hizlandirilacak")
        print(f"  yer hazir bir modelde, projenin kendi kodunda degil.")
    print("\nSinirlar: toplu isleme yok (arac basina tek tek), tek makine,")
    print("CPU. Yigin halinde islemek arac basina maliyeti dusururdu;")
    print("olculen sey en kotu hal.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
