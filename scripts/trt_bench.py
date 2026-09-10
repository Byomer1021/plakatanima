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

SURUM UYUMU
-----------
onnxruntime-gpu'nun PyPI surumu belli bir CUDA surumune bagli ve yanlis
esleme SESSIZ dususe yol aciyor. 1.29 CUDA 13 istiyor; Kaggle'da CUDA 12
var ve hem CUDA hem TensorRT saglayicisi yuklenemeden CPU'ya dusuyor.
CUDA 12 icin surum sabitlenmeli. PyPI'da her surum numarasi YOK - 1.20.1
diye bir surum yok, 1.20.2 var; yanlis numara verince pip once mevcut
kurulumu kaldirip sonra basarisiz oluyor ve ortam bos kaliyor.

Kurulumun TUTTUGUNU calistirmadan once dogrula:
    import onnxruntime as ort
    s = ort.InferenceSession("kose.onnx",
        providers=["CUDAExecutionProvider", "CPUExecutionProvider"])
    print(s.get_providers())      # CUDA burada gorunmeli

TensorRT SURUMU AYRICA ESLESMELI
-------------------------------
`pip install tensorrt` TensorRT 11 kuruyor (libnvinfer.so.11); ORT 1.20.2
libnvinfer.so.10 ariyor. `tensorrt==10.5.0` gerekiyor. Ve LD_LIBRARY_PATH
SUREC BASLAMADAN ayarlanmali - hucre icinde os.environ ile degistirmek
ise yaramiyor, dinamik yukleyici onu baslangicta okuyor:

    !pip install -q "onnxruntime-gpu==1.20.2" "tensorrt==10.5.0"
    !LD_LIBRARY_PATH=<site-packages>/tensorrt_libs:$LD_LIBRARY_PATH       python trt_bench.py --paket <veri-seti>

Kullanim (Kaggle defterinde):
    !pip install -q "onnxruntime-gpu==1.20.2"
    !python trt_bench.py --paket /kaggle/input/<veri-seti-adi>

Betik istenen saglayicinin gercekten yuklendigini dogruluyor; yuklenmezse
o satir tabloya girmiyor.
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
    print(f"listelenen saglayicilar: {ort.get_available_providers()}")
    print("  (listelenmis olmasi CALISACAGI anlamina gelmiyor - .so diskte")
    print("   varsa listeleniyor, yuklenip yuklenmedigi ayri mesele)")
    try:
        import subprocess
        r = subprocess.run(["nvidia-smi",
                            "--query-gpu=name,driver_version",
                            "--format=csv,noheader"],
                           capture_output=True, text=True, timeout=20)
        if r.returncode == 0:
            print(f"GPU: {r.stdout.strip()}")
        r = subprocess.run(["nvcc", "--version"], capture_output=True,
                           text=True, timeout=20)
        if r.returncode == 0:
            son = [l for l in r.stdout.splitlines() if "release" in l]
            if son:
                print(f"CUDA: {son[0].strip()}")
    except Exception:
        pass
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

        # ISTENEN saglayici GERCEKTEN yuklendi mi.
        #
        # Bu kontrol bir kere eksikti ve olcumu tamamen bozdu. ORT istenen
        # saglayiciyi kuramazsa SESSIZCE zincirdeki bir sonrakine dusuyor;
        # get_available_providers() ise .so dosyasi diskte oldugu icin onu
        # yine de "var" diye listeliyor. Sonuc: dort satirin dordu de CPU
        # olcen, ama TensorRT FP16 yazan bir tablo. Sayilar makul gorunuyordu
        # (1.02x, 1.03x) ve "plaka ayni 157/157" bedavaydi - ayni yoldu.
        #
        # Artik gercekten calisan saglayici okunuyor ve istenen degilse
        # satir tabloya GIRMIYOR.
        istenen = (saglayici[0][0] if isinstance(saglayici[0], tuple)
                   else saglayici[0])
        calisan = ks.get_providers()
        if istenen not in calisan:
            print(f"  ISTENEN SAGLAYICI YUKLENMEDI: {istenen}")
            print(f"  gercekte calisan: {calisan}")
            print(f"  -> bu satir olculmedi, tabloya girmiyor\n")
            continue
        if calisan[0] != istenen:
            print(f"  not: {istenen} yuklu ama zincirin basinda degil "
                  f"({calisan})")

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
        print("\nHicbir saglayici olculemedi.")
        return 1
    if len(sonuc) == 1:
        print("\nUYARI: yalnizca bir saglayici calisti "
              f"({sonuc[0][0]}). Karsilastirma yok.")
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
