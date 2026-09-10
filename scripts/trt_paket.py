"""TensorRT olcumu icin bulut paketi hazirlar.

Neden bir paket
---------------
Faz 4 GPU istiyor ve bu makinedeki GTX 1080 agir yuk altinda dort kez dustu;
TensorRT motor derlemesi tam da o yuk. Olcum bulutta yapilacak (Kaggle T4).

Pakete GORUNTU KONMUYOR. Yalnizca:

  kose.onnx, taniyici.onnx   modeller
  girdi_kose.npy             (N, 3, 96, 288)  on islenmis tensorler
  girdi_taniyici.npy         (N, 1, 32, 128)
  referans_kose.npy          CPU'da uretilmis dogru cikti
  referans_varlik.npy
  referans_logit.npy
  referans_plaka.txt         cozumlenen plakalar (satir basina bir)

Goruntu yerine on islenmis tensor gondermenin iki sebebi var. Birincisi
olcumu temizliyor: JPEG cozme ve yeniden boyutlandirma GPU'da olcmek
istedigimiz sey degil. Ikincisi, referans ciktilar yaninda gittigi icin
bulutta "FP16 ayni plakayi okuyor mu" sorusu goruntu olmadan cevaplanabiliyor.

Tensorler yine de gercek plakalardan turemis veri. Kaggle veri seti PRIVATE
kalmali - gercek.npz icin verilen kararin aynisi.

Kullanim:
    python scripts/trt_paket.py
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from export_plates import dikleştir                                # noqa: E402
from train_corners import (GENISLIK as K_GEN, YUKSEKLIK as K_YUK,  # noqa: E402
                           girdiye, ikiye_bol, kayitlari_oku, plakaya_gore_bol)
from train_recognizer import coz_greedy, diziden                   # noqa: E402


def main(argv: list[str] | None = None) -> int:
    import cv2
    import onnxruntime as ort

    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--onnx", type=Path, default=ROOT / "onnx")
    ap.add_argument("--out", type=Path, default=ROOT / "trt_paket")
    args = ap.parse_args(argv)

    args.out.mkdir(parents=True, exist_ok=True)
    for ad in ("kose.onnx", "taniyici.onnx"):
        shutil.copy(args.onnx / ad, args.out / ad)

    kayitlar = kayitlari_oku(ROOT / "data" / "crops",
                             ROOT / "data" / "labels.jsonl")
    _, dogrulama = plakaya_gore_bol(kayitlar)
    _, rapor = ikiye_bol(dogrulama)
    print(f"rapor kumesi: {len(rapor)} kirpma")

    ks = ort.InferenceSession(str(args.onnx / "kose.onnx"),
                              providers=["CPUExecutionProvider"])
    ts = ort.InferenceSession(str(args.onnx / "taniyici.onnx"),
                              providers=["CPUExecutionProvider"])

    kose_girdi, tan_girdi = [], []
    for yol, _, _ in rapor:
        im = cv2.imread(str(yol))
        kucuk = cv2.resize(im, (K_GEN, K_YUK), interpolation=cv2.INTER_AREA)
        x = girdiye(kucuk)[None]
        kose_girdi.append(x[0])
        kose, _ = ks.run(None, {"kirpma": x})
        h, w = im.shape[:2]
        dik = dikleştir(im, (kose[0] * [w, h]).tolist(), 256, 64)
        gri = cv2.resize(cv2.cvtColor(dik, cv2.COLOR_BGR2GRAY), (128, 32),
                         interpolation=cv2.INTER_AREA)
        tan_girdi.append(diziden(gri))

    kose_girdi = np.stack(kose_girdi).astype(np.float32)
    tan_girdi = np.stack(tan_girdi).astype(np.float32)

    r_kose, r_varlik = ks.run(None, {"kirpma": kose_girdi})
    r_logit = ts.run(None, {"plaka": tan_girdi})[0]
    plakalar = [coz_greedy(r_logit[:, j, :]) for j in range(r_logit.shape[1])]

    np.save(args.out / "girdi_kose.npy", kose_girdi)
    np.save(args.out / "girdi_taniyici.npy", tan_girdi)
    np.save(args.out / "referans_kose.npy", r_kose)
    np.save(args.out / "referans_varlik.npy", r_varlik)
    np.save(args.out / "referans_logit.npy", r_logit)
    (args.out / "referans_plaka.txt").write_text("\n".join(plakalar) + "\n",
                                                 encoding="utf-8")
    shutil.copy(ROOT / "scripts" / "trt_bench.py", args.out / "trt_bench.py")

    toplam = sum(p.stat().st_size for p in args.out.iterdir()) / 1e6
    print(f"\n{'dosya':<24}{'MB':>8}")
    for p in sorted(args.out.iterdir()):
        print(f"  {p.name:<22}{p.stat().st_size/1e6:>8.1f}")
    print(f"  {'TOPLAM':<22}{toplam:>8.1f}")
    print(f"\n-> {args.out.resolve()}")
    print("\nKaggle'a PRIVATE veri seti olarak yukle. Icerik gercek")
    print("plakalardan turemis tensorler; gercek.npz icin verilen kararin")
    print("aynisi gecerli.")
    print("\nDefterde:  !python trt_bench.py --paket /kaggle/input/<ad>")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
