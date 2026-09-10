"""Modelleri ONNX'e cikarir ve PyTorch ile AYNI seyi yaptigini dogrular.

Neden bu adim
-------------
Faz 4 (TensorRT) ve Faz 5'in C++ boru hatti ayni onkosula bagli: modellerin
cerceveden bagimsiz bir bicimde olmasi. TensorRT ONNX tuketiyor; C++ tarafinda
model calistirmanin makul yolu da ONNX Runtime.

Dogrulama neden isin YARISI
---------------------------
Bir modeli baska bir cerceveye tasimak sessizce bozulabilen bir istir:
operator farklari, varsayilan degerler, sayisal hassasiyet. Bozulma bir
istisna olarak degil, biraz farkli sayilar olarak gorunur ve boru hattinin
ucunda "model kotulesti" diye yorumlanir.

Bu yuzden cikarim yeterli sayilmiyor. Uc kademede karsilastiriliyor:

  1. HAM CIKTI      : ayni girdide iki cercevenin tensorleri ne kadar farkli
  2. COZUMLENMIS    : taniyicinin greedy cikardigi PLAKA METNI ayni mi
  3. HIZ            : ONNX Runtime PyTorch'tan hizli mi (CPU'da)

Ikinci kademe birincisinden onemli: 1e-5'lik bir tensor farki plakayi
degistirmiyorsa onemsizdir, degistiriyorsa kritiktir. Toleransa degil
SONUCA bakiliyor.

Kullanim:
    python scripts/export_onnx.py
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from train_corners import (GENISLIK as K_GEN, YUKSEKLIK as K_YUK,  # noqa: E402
                           girdiye, ikiye_bol, kayitlari_oku,
                           model_kur as kose_model_kur, plakaya_gore_bol)
from train_recognizer import (coz_greedy, diziden,  # noqa: E402
                              model_kur as tan_model_kur)


def sure(f, tekrar=30, isinma=3):
    for _ in range(isinma):
        f()
    o = []
    for _ in range(tekrar):
        t = time.perf_counter()
        f()
        o.append((time.perf_counter() - t) * 1000)
    return statistics.median(o)


def cikar(model, ornek, yol: Path, girdi_ad, cikti_ad):
    import torch
    model.eval()
    with torch.no_grad():
        torch.onnx.export(
            model, ornek, str(yol),
            input_names=[girdi_ad], output_names=cikti_ad,
            # Yigin boyutu degisken: boru hattinda arac sayisi kareden
            # kareye degisiyor, sabit yigin gereksiz dolgu demek olurdu.
            dynamic_axes={girdi_ad: {0: "yigin"},
                          **{a: {0: "yigin"} for a in cikti_ad}},
            opset_version=17)
    return yol.stat().st_size / 1e6


def main(argv: list[str] | None = None) -> int:
    import torch

    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--kose", type=Path,
                    default=ROOT / "runs" / "varlik" / "best.pt")
    ap.add_argument("--taniyici", type=Path,
                    default=ROOT / "runs" / "ince" / "best.pt")
    ap.add_argument("--out", type=Path, default=ROOT / "onnx")
    ap.add_argument("--ornek", type=int, default=157,
                    help="dogrulamada kullanilacak gercek kirpma sayisi")
    args = ap.parse_args(argv)

    try:
        import onnxruntime as ort
    except ImportError:
        raise SystemExit("onnxruntime yok:  pip install onnx onnxruntime")

    args.out.mkdir(parents=True, exist_ok=True)
    cihaz = torch.device("cpu")

    # --- gercek girdiler: rastgele tensor yerine RAPOR kumesinin kendisi ---
    # Rastgele girdide iki cerceve kolayca uyusur; onemli olan modelin
    # gercekte gordugu dagilimda uyusmasi.
    import cv2
    kayitlar = kayitlari_oku(ROOT / "data" / "crops",
                             ROOT / "data" / "labels.jsonl")
    _, dogrulama = plakaya_gore_bol(kayitlar)
    _, rapor = ikiye_bol(dogrulama)
    rapor = rapor[:args.ornek]
    kose_girdi = np.stack([
        girdiye(cv2.resize(cv2.imread(str(y)), (K_GEN, K_YUK),
                           interpolation=cv2.INTER_AREA))
        for y, _, _ in rapor])
    print(f"dogrulama girdisi: {len(kose_girdi)} gercek arac kirpmasi "
          f"(rapor kumesi)\n")

    # ---------------------------------------------------------------- kose
    km = kose_model_kur().to(cihaz).eval()
    km.load_state_dict(torch.load(args.kose, map_location=cihaz,
                                  weights_only=False)["model"])
    kose_yol = args.out / "kose.onnx"
    mb = cikar(km, torch.from_numpy(kose_girdi[:1]), kose_yol,
               "kirpma", ["kose", "varlik"])
    print(f"kose.onnx     {mb:>6.1f} MB")

    with torch.no_grad():
        t_kose, t_varlik = km(torch.from_numpy(kose_girdi))
    o_sess = ort.InferenceSession(str(kose_yol),
                                  providers=["CPUExecutionProvider"])
    o_kose, o_varlik = o_sess.run(None, {"kirpma": kose_girdi})

    d_kose = float(np.abs(t_kose.numpy() - o_kose).max())
    d_varlik = float(np.abs(t_varlik.numpy() - o_varlik).max())
    # Kose farkinin PIKSEL karsiligi: 0-1 arasi koordinat, kadraj 288 px.
    print(f"  ham cikti farki (maks):  kose {d_kose:.2e}"
          f"  ({d_kose * K_GEN:.4f} px)   varlik {d_varlik:.2e}")

    # --------------------------------------------------------------- tanima
    tm = tan_model_kur().to(cihaz).eval()
    tm.load_state_dict(torch.load(args.taniyici, map_location=cihaz,
                                  weights_only=False)["model"])
    gri = np.stack([diziden(cv2.resize(
        cv2.cvtColor(cv2.imread(str(y)), cv2.COLOR_BGR2GRAY), (128, 32),
        interpolation=cv2.INTER_AREA)) for y, _, _ in rapor])

    tan_yol = args.out / "taniyici.onnx"
    mb = cikar(tm, torch.from_numpy(gri[:1]), tan_yol, "plaka", ["logit"])
    print(f"taniyici.onnx {mb:>6.1f} MB")

    with torch.no_grad():
        t_log = tm(torch.from_numpy(gri))          # (T, B, C)
    t_sess = ort.InferenceSession(str(tan_yol),
                                  providers=["CPUExecutionProvider"])
    o_log = t_sess.run(None, {"plaka": gri})[0]
    d_log = float(np.abs(t_log.numpy() - o_log).max())
    print(f"  ham cikti farki (maks):  {d_log:.2e}")

    # --- ASIL SINAV: cozumlenen plaka metni degisiyor mu ------------------
    t_metin = [coz_greedy(t_log[:, j, :].numpy()) for j in range(t_log.shape[1])]
    o_metin = [coz_greedy(o_log[:, j, :]) for j in range(o_log.shape[1])]
    ayni = sum(a == b for a, b in zip(t_metin, o_metin))
    print(f"\nCOZUMLENEN PLAKA: {ayni}/{len(t_metin)} kirpmada AYNI")
    if ayni != len(t_metin):
        for a, b in zip(t_metin, o_metin):
            if a != b:
                print(f"    pytorch '{a}'  onnx '{b}'")

    # --- hiz --------------------------------------------------------------
    print("\nHIZ (tek kirpma, medyan ms)")
    x1 = torch.from_numpy(kose_girdi[:1])
    g1 = torch.from_numpy(gri[:1])
    with torch.no_grad():
        pt_kose = sure(lambda: km(x1))
        pt_tan = sure(lambda: tm(g1))
    n_kose = {"kirpma": kose_girdi[:1]}
    n_tan = {"plaka": gri[:1]}
    or_kose = sure(lambda: o_sess.run(None, n_kose))
    or_tan = sure(lambda: t_sess.run(None, n_tan))
    print(f"  {'model':<14}{'PyTorch':>10}{'ONNX Runtime':>15}{'oran':>8}")
    for ad, a, b in (("kose", pt_kose, or_kose), ("taniyici", pt_tan, or_tan)):
        print(f"  {ad:<14}{a:>10.2f}{b:>15.2f}{a/b:>8.2f}x")

    (args.out / "dogrulama.json").write_text(json.dumps({
        "ornek": len(kose_girdi),
        "ham_fark": {"kose": d_kose, "kose_piksel": d_kose * K_GEN,
                     "varlik": d_varlik, "taniyici": d_log},
        "cozumlenen_ayni": f"{ayni}/{len(t_metin)}",
        "hiz_ms": {"pytorch_kose": pt_kose, "onnx_kose": or_kose,
                   "pytorch_taniyici": pt_tan, "onnx_taniyici": or_tan},
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n-> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
