"""C++ boru hatti Python'la ayni plakayi mi okuyor?

Neden bu karsilastirma sart
---------------------------
C++ tarafi OpenCV kullanmiyor: yeniden boyutlandirma ve perspektif
duzeltme elle yazildi. Ikisi de OpenCV ile PIKSEL PIKSEL ayni olamaz -
diklestirmede cv2 INTER_CUBIC kullaniyor, C++ tarafi iki dogrusal. Soru
bu farkin plakayi degistirip degistirmedigi ve tek cevap saymak.

Ayrica olculecek bir soru daha var: arac basina 6.93 ms'nin (bolum 22,
Python + ONNX Runtime) ne kadari gercek hesap, ne kadari Python yuku.
Ayni isi yapan C++ belirgin sekilde altina inerse Python yuku gercekti.

Kullanim:
    python scripts/compare_cpp.py
"""

from __future__ import annotations

import argparse
import json
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
                           girdiye, ikiye_bol, kayitlari_oku, plakaya_gore_bol)
from train_recognizer import diziden, duzenleme_mesafesi           # noqa: E402


def python_boru(yollar, onnx_kok: Path, egri: Path, exe: Path, gecici: Path):
    """Ayni adimlar, Python + ONNX Runtime + C++ cozumleyici."""
    import onnxruntime as ort

    ks = ort.InferenceSession(str(onnx_kok / "kose.onnx"),
                              providers=["CPUExecutionProvider"])
    ts = ort.InferenceSession(str(onnx_kok / "taniyici.onnx"),
                              providers=["CPUExecutionProvider"])
    w = json.loads(egri.read_text(encoding="utf-8"))["agirliklar"]

    matrisler, varliklar = [], []
    basladi = time.perf_counter()
    for yol in yollar:
        im = cv2.imread(str(yol))
        kucuk = cv2.resize(im, (K_GEN, K_YUK), interpolation=cv2.INTER_AREA)
        kose, varlik = ks.run(None, {"kirpma": girdiye(kucuk)[None]})
        h, wd = im.shape[:2]
        dik = dikleştir(im, (kose[0] * [wd, h]).tolist(), 256, 64)
        gri = cv2.resize(cv2.cvtColor(dik, cv2.COLOR_BGR2GRAY), (128, 32),
                         interpolation=cv2.INTER_AREA)
        logit = ts.run(None, {"plaka": diziden(gri)[None]})[0]
        matrisler.append(logit[:, 0, :].astype(np.float32))
        varliklar.append(float(1 / (1 + np.exp(-varlik[0]))))
    hazir = time.perf_counter() - basladi

    # Cozumleme: ayni C++ ikilisi, toplu halde
    gecici.mkdir(parents=True, exist_ok=True)
    T, C = matrisler[0].shape
    with (gecici / "logits.bin").open("wb") as f:
        f.write(b"PLKA")
        f.write(struct.pack("<iii", len(matrisler), T, C))
        for m in matrisler:
            f.write(np.ascontiguousarray(m).tobytes())
    c0 = time.perf_counter()
    subprocess.run([str(exe), str(gecici / "logits.bin"),
                    str(gecici / "cozum.tsv")], check=True, capture_output=True)
    coz_sn = time.perf_counter() - c0

    out = []
    for s in (gecici / "cozum.tsv").read_text(encoding="utf-8").splitlines():
        if not s.strip():
            continue
        p = s.split("\t")
        lp, ikinci = float(p[3]), float(p[5])
        marj = 30.0 if not np.isfinite(ikinci) else min(lp - ikinci, 30.0)
        z = w["sabit"] + w["marj"] * marj + w["lp"] * max(lp, -30.0)
        out.append((p[2], float(1 / (1 + np.exp(-np.clip(z, -30, 30))))))
    return out, varliklar, hazir + coz_sn


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--onnx", type=Path, default=ROOT / "onnx")
    ap.add_argument("--egri", type=Path, default=ROOT / "runs" / "kalibrasyon.json")
    ap.add_argument("--exe", type=Path, default=ROOT / "cpp" / "decode.exe")
    ap.add_argument("--boru", type=Path, default=ROOT / "cpp" / "pipeline.exe")
    ap.add_argument("--gecici", type=Path, default=ROOT / "runs" / "_cpp")
    args = ap.parse_args(argv)

    kayitlar = kayitlari_oku(ROOT / "data" / "crops",
                             ROOT / "data" / "labels.jsonl")
    _, dogrulama = plakaya_gore_bol(kayitlar)
    _, rapor = ikiye_bol(dogrulama)
    yollar = [y for y, _, _ in rapor]
    hedefler = [m for _, _, m in rapor]
    print(f"rapor kumesi: {len(yollar)} kirpma\n")

    # --- C++ ciktisi -----------------------------------------------------
    tsv = args.gecici / "cikti.tsv"
    if not tsv.is_file():
        raise SystemExit(f"once cpp/pipeline.exe calistirilmali -> {tsv}")
    c_plaka, c_guven, c_varlik = [], [], []
    for s in tsv.read_text(encoding="utf-8").splitlines():
        if not s.strip():
            continue
        p = s.split("\t")
        c_plaka.append(p[2])
        c_guven.append(float(p[3]))
        c_varlik.append(float(p[4]))

    # --- Python ciktisi ---------------------------------------------------
    py, p_varlik, py_sn = python_boru(yollar, args.onnx, args.egri, args.exe,
                                      args.gecici)
    p_plaka = [a for a, _ in py]
    p_guven = [b for _, b in py]

    if len(c_plaka) != len(p_plaka):
        raise SystemExit(f"satir sayisi farkli: C++ {len(c_plaka)}, "
                         f"Python {len(p_plaka)}")

    ayni = sum(a == b for a, b in zip(c_plaka, p_plaka))
    print("=" * 62)
    print("AYNI SEYI OKUYORLAR MI")
    print("=" * 62)
    print(f"  ayni plaka          {ayni}/{len(c_plaka)} "
          f"(%{100*ayni/len(c_plaka):.1f})")
    d = [duzenleme_mesafesi(a, b) for a, b in zip(c_plaka, p_plaka)]
    print(f"  ortalama duzenleme  {np.mean(d):.3f}  (ikisi arasinda)")
    print(f"  varlik puani farki  {np.abs(np.array(c_varlik)-np.array(p_varlik)).max():.2e}")
    # Guven farkinin DAGILIMI - tek bir maksimum yaniltici. Guven marja
    # dayaniyor ve marj ikinci en iyi ADAYA bagli; kucuk bir sayisal fark
    # ikinci adayi tamamen degistirebilir. Yani ayni plakayi okuyan iki
    # boru hatti cok farkli guven verebilir ve bu, guven sinyalinin
    # okumanin kendisinden daha kirilgan oldugunu soyluyor.
    gf = np.array([abs(a - b) for a, b, x, y in
                   zip(c_guven, p_guven, c_plaka, p_plaka) if x == y])
    print(f"  guven farki (ayni plakayi okuyan {len(gf)} kirpmada):")
    print(f"    ortanca {np.median(gf):.4f}   %90 {np.percentile(gf, 90):.4f}"
          f"   maks {gf.max():.4f}")
    print(f"    0.05'ten buyuk olan: {(gf > 0.05).sum()}/{len(gf)}")

    # Asil soru: fark DOGRULUGU degistiriyor mu
    c_dogru = sum(a == h for a, h in zip(c_plaka, hedefler))
    p_dogru = sum(a == h for a, h in zip(p_plaka, hedefler))
    print(f"\n  gercek etikete gore dogru:  C++ {c_dogru}, Python {p_dogru}"
          f"  ({len(hedefler)} kirpma)")

    if ayni != len(c_plaka):
        print(f"\n  FARKLI OKUNAN ilk 8:")
        n = 0
        for a, b, h in zip(c_plaka, p_plaka, hedefler):
            if a != b and n < 8:
                isaret = ("C++ dogru" if a == h else
                          ("Python dogru" if b == h else "ikisi de yanlis"))
                print(f"    hedef {h:<10} C++ '{a}'  Python '{b}'   {isaret}")
                n += 1

    print(f"\n{'='*62}")
    print("HIZ (kirpma basina, ayni 157 kirpma)")
    print("=" * 62)
    print(f"  Python + ONNX Runtime   {py_sn*1000/len(yollar):>7.2f} ms")
    print(f"  C++ (pipeline.exe)      bkz. calistirma ciktisi")
    print(f"\n  Ikisi de ayni ONNX Runtime'i cagiriyor; aradaki fark")
    print(f"  duzenleme yuku (goruntu islemleri, tensor hazirligi, cagri).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
