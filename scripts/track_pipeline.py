"""Faz 5'in kalan yarisi: ByteTrack ile takip, ve takibin kendi hatalari.

Neden gerekli
-------------
Bolum 17'nin her sayisi kirpmalari GERCEK plaka metnine gore grupladi, yani
kusursuz bir takipci varsaydi. Gercek boru hattinda gruplari takipci kuruyor
ve iki tur hata yapiyor:

  parcalanma : bir arac birden cok ize bolunur -> her izde daha az kare,
               oylama zayiflar
  birlesme   : iki arac tek ize girer -> farkli plakalarin okumalari birlikte
               oylanir, sonuc yanlis

Olcum neden dogrudan yapilamiyor
--------------------------------
Etiketli 811 kirpma IKISER SANIYE arayla ornekleendi (harvest_plates.py
--every saniye cinsinden). ByteTrack o boslukta bir araci baglayamaz, yani
mevcut etiketler ize baglanamiyor. Iz duzeyinde etiket de yok.

Ne olculuyor, ve neden dairesel degil
-------------------------------------
Tanıyıcı izlerden HABERSIZ. Dolayisiyla:

  * Iki ayri izin ayni plakayi yuksek guvenle okumasi -> parcalanmanin
    BAGIMSIZ kaniti. Okuma kimligi izden gelmiyor.
  * Tek bir izin icinde yuksek guvenli okumalarin FARKLI gecerli plakalarda
    ayrilmasi -> birlesmenin isareti.

Bu, iz etiketlerinin yerini tutmaz ve tutuyormus gibi de sunulmuyor. Neyin
olculmedigi asagida ayrica yaziliyor.

Kullanim:
    python scripts/track_pipeline.py --saniye 90
"""

from __future__ import annotations

import argparse
import json
import re
import struct
import subprocess
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from export_plates import dikleştir                                # noqa: E402
from harvest_plates import (ALT_ORAN, ARAC_SINIFLARI, KENAR_PAYI,  # noqa: E402
                            MAX_EN_BOY, MIN_ARAC_GENISLIGI)
from train_corners import (GENISLIK as K_GEN, YUKSEKLIK as K_YUK,  # noqa: E402
                           girdiye, model_kur as kose_model_kur)
from train_recognizer import diziden, model_kur as tan_model_kur   # noqa: E402
from generate_plates import DUZENLER                               # noqa: E402

HEDEF_GENISLIK, HEDEF_YUKSEKLIK = 256, 64


def kirpmalari_topla(video: Path, saniye: float, atla: int, yolo_yolu: Path):
    """ByteTrack ile izleyip her izin arac kirpmalarini toplar.

    Hasat betigindeki filtrelerin AYNISI uygulaniyor: genislik, en/boy,
    kenar payi. Boru hattinin geri kalani o filtreden gecmis kirpmalarla
    egitildi; burada baska bir dagilim vermek olcumu bozardi.
    """
    from ultralytics import YOLO

    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        raise SystemExit(f"Video acilamadi: {video}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    G = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    Y = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    n_kare = int(saniye * fps)
    model = YOLO(str(yolo_yolu))

    print(f"{video.name}: {G}x{Y} @ {fps:.0f} fps")
    print(f"{saniye:.0f} saniye, her {atla}. kare islenecek "
          f"-> {n_kare // atla} kare  (etkin {fps/atla:.0f} fps)\n")

    kayitlar = []
    elenen = Counter()
    basladi = time.perf_counter()
    for i in range(n_kare):
        ok, kare = cap.read()
        if not ok:
            break
        if i % atla:
            continue
        r = model.track(kare, persist=True, verbose=False, imgsz=960,
                        classes=sorted(ARAC_SINIFLARI), tracker="bytetrack.yaml")[0]
        if r.boxes is None or r.boxes.id is None:
            continue
        for kutu, iz in zip(r.boxes.xyxy.cpu().numpy(),
                            r.boxes.id.cpu().numpy().astype(int)):
            x1, y1, x2, y2 = (int(v) for v in kutu)
            w, h = x2 - x1, y2 - y1
            if w < MIN_ARAC_GENISLIGI or h < 1:
                elenen["dar"] += 1
                continue
            if w / h > MAX_EN_BOY:
                elenen["yan"] += 1
                continue
            if (x1 < KENAR_PAYI or y1 < KENAR_PAYI
                    or x2 > G - KENAR_PAYI or y2 > Y - KENAR_PAYI):
                elenen["kenar"] += 1
                continue
            ust = y2 - int(h * ALT_ORAN)
            kesit = kare[max(0, ust):min(Y, y2), max(0, x1):min(G, x2)]
            if kesit.size == 0 or kesit.shape[1] < 40:
                continue
            kayitlar.append((int(iz), i, kesit))
        if (i // atla) % 100 == 0 and i:
            print(f"  {i}/{n_kare} kare, {len(kayitlar)} kirpma, "
                  f"{(time.perf_counter()-basladi)/60:.1f} dk", flush=True)
    cap.release()
    print(f"\n{len(kayitlar)} kirpma / {len({k[0] for k in kayitlar})} iz")
    print(f"elenen: {dict(elenen)}\n")
    return kayitlar, fps


def oku(kayitlar, kose_yolu: Path, tan_yolu: Path, exe: Path, egri: Path,
        gecici: Path):
    """Her kirpma icin plaka ve guven."""
    import torch

    cihaz = torch.device("cpu")
    km = kose_model_kur().to(cihaz).eval()
    km.load_state_dict(torch.load(kose_yolu, map_location=cihaz,
                                  weights_only=False)["model"])
    tm = tan_model_kur().to(cihaz).eval()
    tm.load_state_dict(torch.load(tan_yolu, map_location=cihaz,
                                  weights_only=False)["model"])

    matrisler, varlik = [], []
    with torch.no_grad():
        for i in range(0, len(kayitlar), 32):
            parca = kayitlar[i:i + 32]
            X = [girdiye(cv2.resize(k[2], (K_GEN, K_YUK),
                                    interpolation=cv2.INTER_AREA))
                 for k in parca]
            p, varlik_logit = km(torch.from_numpy(np.stack(X)))
            p = p.numpy()
            varlik.extend(
                (1 / (1 + np.exp(-varlik_logit.numpy()))).tolist())
            kirpmalar = []
            for tahmin, (_, _, im) in zip(p, parca):
                h, w = im.shape[:2]
                kirpmalar.append(dikleştir(im, (tahmin * [w, h]).tolist(),
                                           HEDEF_GENISLIK, HEDEF_YUKSEKLIK))
            G = [diziden(cv2.resize(cv2.cvtColor(c, cv2.COLOR_BGR2GRAY),
                                    (128, 32), interpolation=cv2.INTER_AREA))
                 for c in kirpmalar]
            logp = tm(torch.from_numpy(np.stack(G))).log_softmax(2)
            for j in range(logp.shape[1]):
                matrisler.append(logp[:, j, :].numpy().astype(np.float32))

    gecici.mkdir(parents=True, exist_ok=True)
    T, C = matrisler[0].shape
    with (gecici / "logits.bin").open("wb") as f:
        f.write(b"PLKA")
        f.write(struct.pack("<iii", len(matrisler), T, C))
        for m in matrisler:
            f.write(np.ascontiguousarray(m).tobytes())
    subprocess.run([str(exe), str(gecici / "logits.bin"),
                    str(gecici / "cozum.tsv")], check=True, capture_output=True)

    w = json.loads(egri.read_text(encoding="utf-8"))["agirliklar"]
    out = []
    for s in (gecici / "cozum.tsv").read_text(encoding="utf-8").splitlines():
        if not s.strip():
            continue
        p = s.split("\t")
        lp, ikinci = float(p[3]), float(p[5])
        marj = 30.0 if not np.isfinite(ikinci) else min(lp - ikinci, 30.0)
        z = w["sabit"] + w["marj"] * marj + w["lp"] * max(lp, -30.0)
        out.append((p[2], float(1 / (1 + np.exp(-np.clip(z, -30, 30))))))
    # Varlik puani MARJDAN BAGIMSIZ ikinci bir sinyal. Bolum 20'de guvenin
    # tek basina uydurmayi ayiramadigi olculdu; bu onu kapatmak icin var.
    return [(a_, b_, c_) for (a_, b_), c_ in zip(out, varlik)]


#: Cozumleyici gecerli bir tam plaka uretemediginde en olasi ON EKI donuyor
#: ("01", "0", "34KF" gibi). Bunlar plaka DEGIL ve plaka sayilirsa her sayi
#: bozulur. Ilk kosuda tam bu oldu: izlerin cogu "01" ya da "0" okuyor
#: gorundu.
BICIM = re.compile(r"(\d{2})([A-Z]+)(\d+)")


def gecerli_plaka(p: str) -> bool:
    m = BICIM.fullmatch(p)
    if not m:
        return False
    return (1 <= int(m.group(1)) <= 81
            and (len(m.group(2)), len(m.group(3))) in DUZENLER)


def oyla(v):
    puan = defaultdict(float)
    for t, g in v:
        puan[t] += g
    return max(puan.items(), key=lambda x: x[1])[0]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--video", type=Path,
                    default=Path.home() / "Videos" / "maltepe.mkv")
    ap.add_argument("--saniye", type=float, default=90.0)
    ap.add_argument("--atla", type=int, default=4,
                    help="her kaci bir islensin (60 fps'te 4 -> 15 fps)")
    ap.add_argument("--varlik-esik", type=float, default=0.5,
                    help="kose modelinin 'okunur plaka var' puani esigi")
    ap.add_argument("--esik", type=float, default=0.7,
                    help="guvenli okuma esigi; bolum 15'te %98.2 dogruluk")
    ap.add_argument("--kose", type=Path, default=ROOT / "runs" / "varlik" / "best.pt")
    ap.add_argument("--taniyici", type=Path,
                    default=ROOT / "runs" / "ince" / "best.pt")
    ap.add_argument("--exe", type=Path, default=ROOT / "cpp" / "decode.exe")
    ap.add_argument("--egri", type=Path, default=ROOT / "runs" / "kalibrasyon.json")
    ap.add_argument("--yolo", type=Path, default=ROOT / "yolov8n.pt")
    ap.add_argument("--gecici", type=Path, default=ROOT / "runs" / "_izleme")
    args = ap.parse_args(argv)

    kayitlar, fps = kirpmalari_topla(args.video, args.saniye, args.atla,
                                     args.yolo)
    if not kayitlar:
        raise SystemExit("hic kirpma cikmadi")
    okumalar = oku(kayitlar, args.kose, args.taniyici, args.exe, args.egri,
                   args.gecici)

    iz = defaultdict(list)
    iz_kare = defaultdict(list)
    for (iz_id, kare, _), (plaka, guven, varlik) in zip(kayitlar, okumalar):
        iz[iz_id].append((plaka, guven, varlik))
        iz_kare[iz_id].append(kare)

    # Ham sonuclar saklaniyor: bu kosu dakikalar suruyor ve her analiz icin
    # yeniden calistirmak gereksiz. Ayrica tekrarlanabilir olsun.
    args.gecici.mkdir(parents=True, exist_ok=True)
    (args.gecici / "izler.json").write_text(json.dumps(
        [{"iz": int(a_), "kare": int(b_), "plaka": c_, "guven": round(d_, 4),
          "varlik": round(e_, 4)}
         for (a_, b_, _), (c_, d_, e_) in zip(kayitlar, okumalar)],
        ensure_ascii=False), encoding="utf-8")
    print(f"ham sonuclar -> {args.gecici / 'izler.json'}\n")

    uzunluk = sorted(len(v) for v in iz.values())
    print("=" * 66)
    print(f"IZ ISTATISTIKLERI  ({len(iz)} iz, {len(kayitlar)} kirpma)")
    print("=" * 66)
    print(f"  iz basina kirpma: ortanca {np.median(uzunluk):.0f}, "
          f"en cok {max(uzunluk)}, tek kirpmali {sum(u == 1 for u in uzunluk)}")
    # Hasat edilen arac kirpmalarinin yalnizca %38'inde okunur plaka var
    # (811 'ok' / 2119 etiket). Kalanlarda okunacak bir sey yok ve
    # cozumleyici onek donuyor. Bunlari elemek kusur degil, isin tanimi.
    tam = [(p, g) for p, g, _ in okumalar if gecerli_plaka(p)]
    print(f"  gecerli TAM plaka ureten kirpma: {len(tam)}/{len(okumalar)}"
          f"  (%{100*len(tam)/max(1,len(okumalar)):.0f})")
    print(f"  karsilastirma: etiketlemede kirpmalarin %38'inde okunur")
    print(f"  plaka vardi; bu oran ona yakin olmali\n")

    guvenli_iz = {i: [(x[0], x[1]) for x in v
                      if x[1] >= args.esik and gecerli_plaka(x[0])
                      and x[2] >= args.varlik_esik]
                  for i, v in iz.items()}
    guvenli_iz = {i: v for i, v in guvenli_iz.items() if v}
    print(f"  gecerli VE guvenli (>={args.esik}) okuma ureten iz: "
          f"{len(guvenli_iz)}/{len(iz)}")

    # --- PARCALANMA: iki ayri iz ayni plakayi okuyorsa ---------------------
    oy = {i: oyla(v) for i, v in guvenli_iz.items()}
    plakaya = defaultdict(list)
    for i, p in oy.items():
        plakaya[p].append(i)
    parcali = {p: v for p, v in plakaya.items() if len(v) > 1}
    print(f"\nPARCALANMA")
    print(f"  guvenli iz sayisi        {len(oy)}")
    print(f"  benzersiz plaka          {len(plakaya)}")
    print(f"  birden cok ize bolunen   {len(parcali)} plaka")
    for p, v in list(parcali.items())[:6]:
        araliklar = [f"{min(iz_kare[i])/fps:.0f}-{max(iz_kare[i])/fps:.0f}s"
                     for i in v]
        print(f"    {p:<10} iz {v}  saniye {araliklar}")
    if parcali:
        fazla = sum(len(v) - 1 for v in parcali.values())
        print(f"  parcalanma yuzunden fazladan {fazla} iz "
              f"(%{100*fazla/max(1,len(oy)):.0f})")

    # --- BIRLESME: tek izde farkli plakalar --------------------------------
    print(f"\nBIRLESME")
    karisik = []
    for i, v in guvenli_iz.items():
        farkli = {t for t, _ in v}
        if len(farkli) > 1:
            # Guven agirlikli en iyi ikisi arasindaki pay - gurultuyle
            # gercek karisim arasinda kaba bir ayrim.
            puan = defaultdict(float)
            for t, g in v:
                puan[t] += g
            sirali = sorted(puan.values(), reverse=True)
            if len(sirali) > 1 and sirali[1] / sirali[0] > 0.5:
                karisik.append((i, dict(Counter(t for t, _ in v))))
    print(f"  icinde ciddi olcude farkli plaka okunan iz: "
          f"{len(karisik)}/{len(guvenli_iz)}")
    for i, sayim in karisik[:6]:
        print(f"    iz {i}: {sayim}")

    print(f"\n{'='*66}")
    print("OLCULMEYEN")
    print(f"{'='*66}")
    print("  Iz duzeyinde etiket YOK. Yukaridaki iki sayi takipcinin")
    print("  hatalarinin ALT SINIRI: yalnizca tanıyıcının guvenle okudugu")
    print("  izlerde gorulebilen hatalari sayiyor. Plakasi hic okunamayan")
    print("  bir aracin izi bolunmusse bu sayilara girmiyor.")
    print("\n  Ayrica parcalanma sayisi kendi icinde bir varsayim tasiyor:")
    print("  ayni plakayi okuyan iki iz GERCEKTEN ayni arac olmali. Ayni")
    print("  plakanin iki farkli araca ait olmasi mumkun degil, ama iki")
    print("  izin ayni plakayi YANLIS okumasi mumkun.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
