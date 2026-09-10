"""TensorRT olcumu icin bulut paketi hazirlar.

Neden bir paket
---------------
Faz 4 GPU istiyor ve bu makinedeki GTX 1080 agir yuk altinda dort kez dustu;
TensorRT motor derlemesi tam da o yuk. Olcum bulutta yapilacak (Kaggle T4).

Icerik

  kose.onnx, taniyici.onnx   modeller
  girdi_kose.npy             (N, 3, 96, 288)  on islenmis tensorler
  girdi_taniyici.npy         (N, 1, 32, 128)
  referans_kose.npy          CPU'da uretilmis dogru cikti
  referans_varlik.npy
  referans_logit.npy
  referans_plaka.txt         cozumlenen plakalar (satir basina bir)

  yolov8n.onnx               dedektor
  girdi_yolo.npy             (N, 3, 960, 960)  mektuplu kutu uygulanmis kareler
  referans_yolo.npy          (N, 84, 18900)

JPEG yerine on islenmis tensor: olcumu temizliyor (JPEG cozme ve yeniden
boyutlandirma GPU'da olcmek istedigimiz sey degil) ve referans ciktilar
yaninda gittigi icin "FP16 ayni plakayi okuyor mu" sorusu bulutta
cevaplanabiliyor.

MAHREMIYET. Bu bir "goruntusuz" paket DEGIL. Kirpma tensorleri gercek
plakalardan turemis; YOLO girdileri ise TAM SAHNE - sokak, baska araclar,
yayalar. Tensor olmalari bir sey degistirmiyor, geri goruntuye cevrilirler.
Kaggle veri seti PRIVATE kalmali; gercek.npz icin verilen kararin aynisi ve
tam kareler onun da otesinde.

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


def mektuplu_kutu(im, boyut: int = 960):
    """Ultralytics'in letterbox'i: en/boy korunarak sigdir, 114 gri ile
    doldur, ORTALA. Referans ciktilar da bu fonksiyonla uretiliyor, yani
    bulut tarafiyla tutarli - amac ultralytics'i birebir taklit etmek degil,
    iki tarafin AYNI girdiyi gormesi.
    """
    import cv2
    h, w = im.shape[:2]
    o = min(boyut / h, boyut / w)
    yh, yw = int(round(h * o)), int(round(w * o))
    kucuk = cv2.resize(im, (yw, yh), interpolation=cv2.INTER_LINEAR)
    tuval = np.full((boyut, boyut, 3), 114, np.uint8)
    ust, sol = (boyut - yh) // 2, (boyut - yw) // 2
    tuval[ust:ust + yh, sol:sol + yw] = kucuk
    # BGR -> RGB, CHW, 0-1  (ultralytics'in on islemesi)
    return (tuval[:, :, ::-1].transpose(2, 0, 1) / 255.0).astype(np.float32)


def main(argv: list[str] | None = None) -> int:
    import cv2
    import onnxruntime as ort

    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--onnx", type=Path, default=ROOT / "onnx")
    ap.add_argument("--out", type=Path, default=ROOT / "trt_paket")
    ap.add_argument("--yolo", type=Path, default=ROOT / "onnx" / "yolov8n.onnx")
    ap.add_argument("--video", type=Path,
                    default=Path.home() / "Videos" / "maltepe.mkv")
    ap.add_argument("--kare", type=int, default=6,
                    help="YOLO dogrulamasi icin kac kare (0 = YOLO'yu atla)")
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
    # --- YOLO ---------------------------------------------------------
    # Kare maliyetinin %85'i YOLO'da (bolum 22) ve butun hizlandirma
    # calismasinin disinda kaldi. Zamanlama girdiden bagimsiz ama
    # "FP16 tespitleri degistiriyor mu" sorusu gercek kare istiyor.
    #
    # Kareler TAM SAHNE: sokak, baska araclar, plakalar. Kirpma
    # tensorlerinden daha fazlasini gosteriyor; Kaggle veri seti private
    # kalmali.
    if args.kare > 0 and args.yolo.is_file() and args.video.is_file():
        import onnxruntime as ort2
        shutil.copy(args.yolo, args.out / "yolov8n.onnx")
        cap = cv2.VideoCapture(str(args.video))
        n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        kareler = []
        for konum in np.linspace(0, n - 1, args.kare).astype(int):
            cap.set(cv2.CAP_PROP_POS_FRAMES, int(konum))
            ok, kare = cap.read()
            if ok:
                kareler.append(kare)
        cap.release()
        girdi = np.stack([mektuplu_kutu(k, 960) for k in kareler])
        ys = ort2.InferenceSession(str(args.yolo),
                                   providers=["CPUExecutionProvider"])
        # Girdi yigini 1'de sabit; kare kare calistiriliyor.
        ref = np.concatenate([ys.run(None, {"images": girdi[i:i + 1]})[0]
                              for i in range(len(girdi))])
        np.save(args.out / "girdi_yolo.npy", girdi.astype(np.float32))
        np.save(args.out / "referans_yolo.npy", ref.astype(np.float32))
        print(f"YOLO: {len(girdi)} kare, girdi {girdi.shape}, "
              f"referans {ref.shape}")
    else:
        print("YOLO atlandi (model, video ya da --kare 0)")

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
