"""Uctan uca: kose hatasi plaka okumaya kac plakaya mal oluyor?

Bolum 10-17'deki her sayi insan eliyle isaretlenmis kosseler uzerinden
olculdu. Bu betik o varsayimi kaldiriyor:

    arac kirpmasi -> KOSE MODELI -> diklestirme -> taniyici
                                    -> C++ kisitli cozumleyici -> plaka

ve ayni rapor kumesinde elle isaretlenmis kosselerle karsilastiriyor.
Aradaki fark, kose adimini otomatiklestirmenin BEDELI.

Neden ayri bir betik: kose hatasini piksel cinsinden bilmek bir sey ifade
etmiyor. 0.04'luk bir hata taniyicinin egitildigi bozulma araliginda ve
zararsiz olabilir; 0.08 okumayi bozabilir. Hangisinin oldugunu yalnizca
asagi akistaki sayi soyler.

Kullanim:
    python scripts/end_to_end.py
"""

from __future__ import annotations

import argparse
import json
import struct
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from export_plates import dikleştir                      # noqa: E402
from train_corners import (GENISLIK as K_GEN, YUKSEKLIK as K_YUK,  # noqa: E402
                           girdiye, hazirla, ikiye_bol, kayitlari_oku,
                           model_kur as kose_model_kur, plakaya_gore_bol)
from train_recognizer import (ALFABE, diziden, model_kur as tan_model_kur,  # noqa: E402
                              duzenleme_mesafesi)

#: export_plates.py ile ayni; taniyici bu boyutta egitildi.
HEDEF_GENISLIK, HEDEF_YUKSEKLIK = 256, 64


def kose_tahmin(model, kayitlar, cihaz):
    """Her kirpma icin dort kose - orijinal goruntu olceginde."""
    import torch
    model.eval()
    out = []
    with torch.no_grad():
        for i in range(0, len(kayitlar), 32):
            parca = kayitlar[i:i + 32]
            X, olcekler = [], []
            for yol, kose, metin in parca:
                im = cv2.imread(str(yol))
                if im is None:
                    continue
                h, w = im.shape[:2]
                X.append(girdiye(cv2.resize(im, (K_GEN, K_YUK),
                                            interpolation=cv2.INTER_AREA)))
                olcekler.append((im, w, h, kose, metin))
            if not X:
                continue
            p = model(torch.from_numpy(np.stack(X)).to(cihaz)).cpu().numpy()
            for tahmin, (im, w, h, kose, metin) in zip(p, olcekler):
                t = tahmin * [w, h]
                out.append((im, t.astype(np.float32), kose, metin))
    return out


def kirp(im, kose):
    return dikleştir(im, kose.tolist(), HEDEF_GENISLIK, HEDEF_YUKSEKLIK)


def taniyici_matrisleri(model, kirpmalar, cihaz):
    import torch
    model.eval()
    matrisler = []
    with torch.no_grad():
        for i in range(0, len(kirpmalar), 64):
            X = []
            for im in kirpmalar[i:i + 64]:
                gri = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY)
                gri = cv2.resize(gri, (128, 32), interpolation=cv2.INTER_AREA)
                X.append(diziden(gri))
            logp = model(torch.from_numpy(np.stack(X)).to(cihaz)).log_softmax(2)
            for j in range(logp.shape[1]):
                matrisler.append(logp[:, j, :].cpu().numpy().astype(np.float32))
    return matrisler


def cozumle(matrisler, exe: Path, gecici: Path):
    """C++ kisitli cozumleyiciyi calistirir, (plaka, guven ham sayilari)."""
    gecici.mkdir(parents=True, exist_ok=True)
    binyol, tsvyol = gecici / "logits.bin", gecici / "cozum.tsv"
    T, C = matrisler[0].shape
    with binyol.open("wb") as f:
        f.write(b"PLKA")
        f.write(struct.pack("<iii", len(matrisler), T, C))
        for m in matrisler:
            f.write(np.ascontiguousarray(m).tobytes())
    subprocess.run([str(exe), str(binyol), str(tsvyol)],
                   check=True, capture_output=True)
    out = []
    for s in tsvyol.read_text(encoding="utf-8").splitlines():
        if not s.strip():
            continue
        p = s.split("\t")
        lp, ikinci = float(p[3]), float(p[5])
        marj = 30.0 if not np.isfinite(ikinci) else min(lp - ikinci, 30.0)
        out.append((p[2], marj, max(lp, -30.0)))
    return out


def guvenle(cozumler, egri: Path):
    w = json.loads(egri.read_text(encoding="utf-8"))["agirliklar"]
    out = []
    for plaka, marj, lp in cozumler:
        z = w["sabit"] + w["marj"] * marj + w["lp"] * lp
        out.append((plaka, float(1.0 / (1.0 + np.exp(-np.clip(z, -30, 30))))))
    return out


def olc(tahminler, hedefler):
    """Kirpma ve plaka bazinda; oylama guven agirlikli (bolum 17'nin secimi)."""
    d = [duzenleme_mesafesi(t, h) for (t, _), h in zip(tahminler, hedefler)]
    kt = sum(len(h) for h in hedefler)
    kd = sum(max(0, len(h) - m) for m, h in zip(d, hedefler))
    grup = defaultdict(list)
    for (t, g), h in zip(tahminler, hedefler):
        grup[h].append((t, g))
    oy = 0
    for h, v in grup.items():
        puan = defaultdict(float)
        for t, g in v:
            puan[t] += g
        oy += max(puan.items(), key=lambda x: x[1])[0] == h
    return {"tam": sum(t == h for (t, _), h in zip(tahminler, hedefler)) / len(tahminler),
            "kar": kd / max(1, kt), "duz": float(np.mean(d)),
            "oy": oy / max(1, len(grup)), "oy_n": oy, "n_plaka": len(grup),
            "n": len(tahminler)}


def main(argv: list[str] | None = None) -> int:
    import torch

    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--crops", type=Path, default=ROOT / "data" / "crops")
    ap.add_argument("--etiket", type=Path, default=ROOT / "data" / "labels.jsonl")
    ap.add_argument("--kose", type=Path, default=ROOT / "runs" / "kose" / "best.pt")
    ap.add_argument("--taniyici", type=Path,
                    default=ROOT / "runs" / "ince" / "best.pt")
    ap.add_argument("--egri", type=Path, default=ROOT / "runs" / "kalibrasyon.json")
    ap.add_argument("--exe", type=Path, default=ROOT / "cpp" / "decode.exe")
    ap.add_argument("--gecici", type=Path, default=ROOT / "runs" / "_uctan_uca")
    ap.add_argument("--cihaz", default="cpu")
    args = ap.parse_args(argv)

    for yol, ad in ((args.kose, "kose modeli"), (args.taniyici, "taniyici"),
                    (args.exe, "decode.exe"), (args.egri, "kalibrasyon")):
        if not yol.is_file():
            raise SystemExit(f"{ad} yok: {yol}")

    cihaz = torch.device(args.cihaz)
    kayitlar = kayitlari_oku(args.crops, args.etiket)
    _, dogrulama = plakaya_gore_bol(kayitlar)
    _, rapor = ikiye_bol(dogrulama)
    print(f"rapor kumesi: {len(rapor)} kirpma / "
          f"{len({k[2] for k in rapor})} plaka  (hicbir karara girmedi)\n")

    km = kose_model_kur().to(cihaz)
    kd = torch.load(args.kose, map_location=cihaz, weights_only=False)
    km.load_state_dict(kd["model"])
    print(f"kose modeli : epoch {kd.get('epoch','?')}, "
          f"secim kumesinde hata {kd.get('oran', float('nan')):.3f}")

    tm = tan_model_kur().to(cihaz)
    td = torch.load(args.taniyici, map_location=cihaz, weights_only=False)
    tm.load_state_dict(td["model"])
    print(f"taniyici    : {args.taniyici.parent.name}/{args.taniyici.name}, "
          f"epoch {td.get('epoch','?')}\n")

    veri = kose_tahmin(km, rapor, cihaz)
    hedefler = [metin for _, _, _, metin in veri]

    sonuc = {}
    for ad, secici in (("elle isaretlenmis kose", lambda t, e: e),
                       ("MODELIN buldugu kose", lambda t, e: t)):
        kirpmalar = [kirp(im, secici(tahmin, elle))
                     for im, tahmin, elle, _ in veri]
        m = taniyici_matrisleri(tm, kirpmalar, cihaz)
        sonuc[ad] = olc(guvenle(cozumle(m, args.exe, args.gecici), args.egri),
                        hedefler)

    # Kose hatasinin kendisi
    hata = []
    for _, tahmin, elle, _ in veri:
        gen = np.linalg.norm(elle[1] - elle[0])
        hata.append(np.linalg.norm(tahmin - elle, axis=1).mean() / max(1e-6, gen))
    hata = np.array(hata)

    print("=" * 70)
    print("UCTAN UCA - kose adimini otomatiklestirmenin bedeli")
    print("=" * 70)
    a, b = sonuc["elle isaretlenmis kose"], sonuc["MODELIN buldugu kose"]
    print(f"  {'olcut':<26}{'elle kose':>13}{'model kose':>13}{'fark':>10}")
    for ad, k, ters in (("kirpma tam dizi", "tam", False),
                        ("karakter", "kar", False),
                        ("duzenleme (dusuk iyi)", "duz", True),
                        ("PLAKA guven agirlikli oy", "oy", False)):
        f = b[k] - a[k]
        im = "+" if ((f < 0) if ters else (f > 0)) else (" " if f == 0 else "-")
        print(f"  {ad:<26}{a[k]:>13.3f}{b[k]:>13.3f}{f:>+10.3f} {im}")
    print(f"  {'PLAKA (adet)':<26}{a['oy_n']:>13}{b['oy_n']:>13}"
          f"{b['oy_n']-a['oy_n']:>+10}   /{a['n_plaka']}")

    print(f"\n  kose hatasi (plaka genisliginin orani):"
          f"  ortalama {hata.mean():.3f}   ortanca {np.median(hata):.3f}")
    print(f"  hatasi %5'i asan kirpma: {(hata > 0.05).mean():.3f}")
    print(f"  (uretec taniyiciyi KOSE_HATASI = 0.05 ile egitti)")

    # Hata buyudukce okuma bozuluyor mu - kaldiraç nerede
    print(f"\n  KOSE HATASI -> OKUMA (kirpma bazinda, model kose)")
    print(f"  {'kose hatasi':<20}{'n':>5}{'tam dizi':>11}")
    kenar = [0, 0.03, 0.05, 0.10, 9]
    tah = guvenle(cozumle(taniyici_matrisleri(
        tm, [kirp(im, t) for im, t, _, _ in veri], cihaz), args.exe,
        args.gecici), args.egri)
    for i in range(len(kenar) - 1):
        m = (hata >= kenar[i]) & (hata < kenar[i + 1])
        if m.sum() == 0:
            continue
        dogru = sum(tah[j][0] == hedefler[j] for j in np.where(m)[0])
        ad = (f"{kenar[i]:.2f}-{kenar[i+1]:.2f}" if kenar[i + 1] < 9
              else f">{kenar[i]:.2f}")
        print(f"  {ad:<20}{int(m.sum()):>5}{dogru/m.sum():>11.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
