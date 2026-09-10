"""Faz 4: TensorRT olcumu. BULUTTA calisir (Kaggle T4), yerelde degil.

Neden yerelde degil
-------------------
Bu makinedeki GTX 1080 agir yuk altinda dort kez dustu ve TensorRT motor
derlemesi tam da o yuk. Olcum kiralik bir GPU'da yapiliyor; sonucun ne
oldugu ve NE OLMADIGI bu yuzden acikca yaziliyor: bir T4 sayisi, uc cihaz
sayisi degil.

Neden ham TensorRT API'si degil
-------------------------------
ONNX Runtime'in TensorrtExecutionProvider'i altta TensorRT calistiriyor ama
motor derlemesini kendisi yapiyor. Elde zaten dogrulanmis ONNX dosyalari
varken ham API'yle ugrasmak yeni bir soru cevaplamiyor.

Olculen dort sey
----------------
  CPUExecutionProvider        taban
  CUDAExecutionProvider       GPU, TensorRT yok
  TensorrtExecutionProvider   FP32
  TensorrtExecutionProvider   FP16

DOGRULUK, hizdan onemli
-----------------------
FP16'ya inmek logitleri degistirir ve iki yerden vurabilir:

  1. Kisitli isin aramasi ikinci en iyi ADAYI kaybedebilir -> okuma degisir
  2. Guven marja dayaniyor ve bolum 23'te okumadan cok daha KIRILGAN oldugu
     olculdu: ayni plakayi okuyan 139 kirpmanin 85'inde guven farki 0.05'i
     asmisti. Yani "FP16 dogrulugu bozmadi" yeterli bir cumle degil;
     kalibrasyonu bozup bozmadigi ayrica olculmeli.

Bu yuzden her saglayici icin cozumlenen plaka referansla karsilastiriliyor
ve logit farkinin marja etkisi ayrica basiliyor.

Kullanim (Kaggle defterinde):
    !pip install -q onnxruntime-gpu
    !python trt_bench.py --paket /kaggle/input/<veri-seti-adi>
"""

from __future__ import annotations

import argparse
import os
import statistics
import time
from pathlib import Path

import numpy as np


def coz_greedy(logits: np.ndarray, alfabe: str) -> str:
    """train_recognizer.coz_greedy ile ayni; buraya kopyalandi cunku bu
    betik bulutta TEK BASINA calisiyor, depo yaninda degil."""
    yol = logits.argmax(axis=-1)
    cikti, onceki = [], -1
    for k in yol:
        if k != onceki and k != 0:
            cikti.append(alfabe[k - 1])
        onceki = k
    return "".join(cikti)


ALFABE = "ABCDEFGHIJKLMNOPRSTUVYZ0123456789"


def sure(f, tekrar=50, isinma=10):
    for _ in range(isinma):
        f()
    o = []
    for _ in range(tekrar):
        t = time.perf_counter()
        f()
        o.append((time.perf_counter() - t) * 1000)
    return statistics.median(o)


def saglayicilar(onbellek: str):
    """(ad, provider listesi) - kurulu olanlar."""
    import onnxruntime as ort
    var = ort.get_available_providers()
    out = [("CPU", ["CPUExecutionProvider"])]
    if "CUDAExecutionProvider" in var:
        out.append(("CUDA", ["CUDAExecutionProvider", "CPUExecutionProvider"]))
    if "TensorrtExecutionProvider" in var:
        ortak = {"trt_engine_cache_enable": True,
                 "trt_engine_cache_path": onbellek}
        out.append(("TensorRT FP32",
                    [("TensorrtExecutionProvider", {**ortak, "trt_fp16_enable": False}),
                     "CUDAExecutionProvider", "CPUExecutionProvider"]))
        out.append(("TensorRT FP16",
                    [("TensorrtExecutionProvider", {**ortak, "trt_fp16_enable": True}),
                     "CUDAExecutionProvider", "CPUExecutionProvider"]))
    return out


def main(argv: list[str] | None = None) -> int:
    import onnxruntime as ort

    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--paket", type=Path, required=True)
    ap.add_argument("--onbellek", default="/kaggle/working/trt_cache")
    args = ap.parse_args(argv)

    os.makedirs(args.onbellek, exist_ok=True)
    p = args.paket
    kose_girdi = np.load(p / "girdi_kose.npy")
    tan_girdi = np.load(p / "girdi_taniyici.npy")
    r_kose = np.load(p / "referans_kose.npy")
    r_logit = np.load(p / "referans_logit.npy")
    r_plaka = (p / "referans_plaka.txt").read_text(encoding="utf-8").split()

    print(f"onnxruntime {ort.__version__}")
    print(f"saglayicilar: {ort.get_available_providers()}")
    print(f"girdi: kose {kose_girdi.shape}, taniyici {tan_girdi.shape}\n")

    liste = saglayicilar(args.onbellek)
    if len(liste) == 1:
        print("UYARI: yalnizca CPU var. GPU'lu bir ortamda ve")
        print("`pip install onnxruntime-gpu` ile calistirin.\n")

    sonuc = []
    for ad, saglayici in liste:
        print(f"--- {ad} ---", flush=True)
        try:
            ks = ort.InferenceSession(str(p / "kose.onnx"), providers=saglayici)
            ts = ort.InferenceSession(str(p / "taniyici.onnx"), providers=saglayici)
        except Exception as e:
            print(f"  kurulamadi: {e}\n")
            continue

        # Motor derlemesi ilk cagrida oluyor; olcumden once bir kez.
        t0 = time.perf_counter()
        o_kose, o_varlik = ks.run(None, {"kirpma": kose_girdi})
        o_logit = ts.run(None, {"plaka": tan_girdi})[0]
        ilk = time.perf_counter() - t0

        # Tek ornek gecikmesi - boru hattinda arac arac isleniyor.
        k1 = {"kirpma": kose_girdi[:1]}
        t1 = {"plaka": tan_girdi[:1]}
        ms_kose = sure(lambda: ks.run(None, k1))
        ms_tan = sure(lambda: ts.run(None, t1))

        d_kose = float(np.abs(o_kose - r_kose).max())
        d_logit = float(np.abs(o_logit - r_logit).max())
        plakalar = [coz_greedy(o_logit[:, j, :], ALFABE)
                    for j in range(o_logit.shape[1])]
        ayni = sum(a == b for a, b in zip(plakalar, r_plaka))

        # Marj: guvenin dayanagi. Logit farki marji ne kadar oynatiyor?
        def marjlar(L):
            m = []
            for j in range(L.shape[1]):
                s = np.sort(L[:, j, :], axis=-1)
                m.append(float((s[:, -1] - s[:, -2]).mean()))
            return np.array(m)
        dm = float(np.abs(marjlar(o_logit) - marjlar(r_logit)).max())

        sonuc.append((ad, ms_kose, ms_tan, d_kose, d_logit, ayni,
                      len(r_plaka), dm, ilk))
        print(f"  ilk cagri (motor derlemesi dahil) {ilk:6.2f} sn")
        print(f"  kose {ms_kose:6.2f} ms   taniyici {ms_tan:6.2f} ms")
        print(f"  cozumlenen plaka referansla ayni: {ayni}/{len(r_plaka)}\n",
              flush=True)

    if not sonuc:
        return 1
    taban = sonuc[0][1] + sonuc[0][2]
    print("=" * 78)
    print(f"{'saglayici':<16}{'kose':>8}{'taniyici':>10}{'toplam':>9}"
          f"{'hizlanma':>10}{'plaka ayni':>12}{'marj farki':>12}")
    print("-" * 78)
    for ad, a, b, dk, dl, ay, n, dm, _ in sonuc:
        print(f"{ad:<16}{a:>8.2f}{b:>10.2f}{a+b:>9.2f}"
              f"{taban/(a+b):>9.2f}x{f'{ay}/{n}':>12}{dm:>12.4f}")
    print("\nSayilar bu GPU icin. Uc cihaz olcumu DEGIL - o donanim yok.")
    print("'marj farki' guvenin dayanagindaki kayma: kalibrasyon esikleri")
    print("(bolum 15, 21) bu saglayici icin yeniden uydurulmali mi sorusu.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
