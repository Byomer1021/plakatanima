"""Cozumleyici skorunu "bu okuma dogru olma olasiligi"na cevirir.

Neden gerekli
-------------
Cozumleyici her kirpma icin bir plaka veriyor ama "ne kadar eminim" demiyor.
Faz 5'in zamansal oylamasi buna dayanacak: bir aracin 20 karesinden gelen 20
okumayi esit saymak, emin olunan okumayla tahmin yurutuleni ayni kefeye
koymaktir.

Ham skor dogrudan olasilik degil. Iki sey kullaniliyor:

  marj   = en iyi tam plakanin log olasiligi - ikinci en iyininki
           Uzunluktan bagimsiz; "model bu okumada ne kadar kararli".
  lp     = en iyinin kendi log olasiligi
           Uzun plaka her zaman daha dusuk alir (daha cok carpan), o yuzden
           tek basina yaniltici, ama marjla birlikte bilgi tasiyor.

Bunlari dogruluk olasiligina eslemek icin lojistik regresyon; scipy/sklearn
bagimliligi eklemeye degmeyecek kadar kucuk bir is, IRLS ile numpy'da.

Olcum durustlugu
----------------
Egri SECIM yarisina uyduruluyor, kalitesi RAPOR yarisinda olculuyor. Egitim
kirpmalari kullanilamaz: model onlari %99.6 dogru okuyor, yani neredeyse hic
olumsuz ornek yok ve oradan uydurulan egri sistematik olarak fazla emin cikar.

Bedeli acikca yaziliyor: uydurma kumesi 88 kirpma. Bu, iki parametreli bir
egri icin yeterli ama incedir; asagidaki guven araliklari o incelige gore
okunmali.

Kullanim:
    python scripts/calibrate.py
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent


def oku(paket: Path):
    """(kume, hedef, tahmin, marj, lp) satirlari."""
    etiket = {}
    for s in (paket / "logits.tsv").read_text(encoding="utf-8").splitlines():
        if s.strip():
            i, kume, metin = s.split("\t")
            etiket[int(i)] = (kume, metin)

    satirlar = []
    for s in (paket / "cozum.tsv").read_text(encoding="utf-8").splitlines():
        if not s.strip():
            continue
        p = s.split("\t")
        if len(p) < 6:
            raise SystemExit(
                "cozum.tsv guven sutunlarini icermiyor. decode.exe'yi yeniden "
                "derleyip calistirin:\n"
                "  g++ -O2 -std=c++17 -o cpp/decode.exe cpp/decode.cpp\n"
                "  ./cpp/decode.exe paket/logits.bin paket/cozum.tsv")
        i = int(p[0])
        kume, hedef = etiket[i]
        lp, ikinci_lp = float(p[3]), float(p[5])
        # Ikinci aday yoksa marj tanimsiz; pratikte "rakipsiz" demek, yani
        # cok emin. Sonlu ve buyuk bir degerle temsil ediliyor.
        marj = 30.0 if not np.isfinite(ikinci_lp) else lp - ikinci_lp
        satirlar.append((kume, hedef, p[2], min(marj, 30.0), max(lp, -30.0)))
    return satirlar


def lojistik_uydur(X, y, ceza=1.0, adim=60):
    """IRLS ile lojistik regresyon; ceza ayrilabilir veride patlamayi onler."""
    X = np.hstack([np.ones((len(X), 1)), X])
    w = np.zeros(X.shape[1])
    for _ in range(adim):
        z = X @ w
        p = 1.0 / (1.0 + np.exp(-np.clip(z, -30, 30)))
        W = np.clip(p * (1 - p), 1e-6, None)
        H = X.T @ (X * W[:, None]) + ceza * np.eye(X.shape[1])
        g = X.T @ (y - p) - ceza * w
        try:
            w = w + np.linalg.solve(H, g)
        except np.linalg.LinAlgError:
            break
    return w


def uygula(w, X):
    X = np.hstack([np.ones((len(X), 1)), X])
    return 1.0 / (1.0 + np.exp(-np.clip(X @ w, -30, 30)))


def auc(skor, y):
    """Siralama gucu: rastgele bir dogru, rastgele bir yanlistan yuksek mi."""
    if y.sum() == 0 or y.sum() == len(y):
        return float("nan")
    sira = np.argsort(np.argsort(skor)) + 1
    n1 = y.sum()
    n0 = len(y) - n1
    return float((sira[y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


def guvenilirlik(p, y, kova=5):
    """Tahmin edilen olasilik ile gozlenen dogruluk yan yana."""
    kenar = np.quantile(p, np.linspace(0, 1, kova + 1))
    kenar[0], kenar[-1] = -0.001, 1.001
    satir, ece = [], 0.0
    for i in range(kova):
        m = (p > kenar[i]) & (p <= kenar[i + 1])
        if m.sum() == 0:
            continue
        satir.append((kenar[i], kenar[i + 1], int(m.sum()),
                      float(p[m].mean()), float(y[m].mean())))
        ece += m.sum() / len(p) * abs(p[m].mean() - y[m].mean())
    return satir, ece


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--paket", type=Path, default=ROOT / "paket")
    ap.add_argument("--out", type=Path, default=ROOT / "runs" / "kalibrasyon.json")
    args = ap.parse_args(argv)

    satirlar = oku(args.paket)
    kume = {}
    for ad in ("secim", "rapor", "egitim"):
        v = [s for s in satirlar if s[0] == ad]
        kume[ad] = (np.array([[s[3], s[4]] for s in v], dtype=float),
                    np.array([s[1] == s[2] for s in v], dtype=float))

    Xs, ys = kume["secim"]
    Xr, yr = kume["rapor"]
    print(f"uydurma (secim): {len(ys)} kirpma, {int(ys.sum())} dogru")
    print(f"olcum   (rapor): {len(yr)} kirpma, {int(yr.sum())} dogru\n")

    # 1) Ham skor dogruyu yanlistan ayiriyor mu - egri uydurmadan once
    print("HAM MARJ (rapor kumesi)")
    print(f"  dogru okumalarda ortanca marj  {np.median(Xr[yr == 1, 0]):.2f}")
    print(f"  yanlis okumalarda ortanca marj {np.median(Xr[yr == 0, 0]):.2f}")
    print(f"  AUC (siralama gucu)            {auc(Xr[:, 0], yr):.3f}"
          f"   [0.5 = bilgi yok, 1.0 = kusursuz]\n")

    w = lojistik_uydur(Xs, ys)
    pr = uygula(w, Xr)
    ps = uygula(w, Xs)

    print(f"egri: p = sigmoid({w[0]:+.3f} {w[1]:+.3f}*marj {w[2]:+.3f}*lp)")
    print(f"  AUC uydurma kumesinde {auc(ps, ys):.3f}, "
          f"rapor kumesinde {auc(pr, yr):.3f}\n")

    satir, ece = guvenilirlik(pr, yr)
    print("GUVENILIRLIK (rapor kumesi)")
    print(f"  {'kova':<16}{'n':>5}{'tahmin':>10}{'gozlenen':>11}{'fark':>9}")
    for a, b, n, tp, gp in satir:
        print(f"  {a:.2f}-{b:.2f}{'':<6}{n:>5}{tp:>10.3f}{gp:>11.3f}"
              f"{gp - tp:>+9.3f}")
    print(f"\n  ECE (ortalama kalibrasyon hatasi): {ece:.3f}")

    # 2) Pratik kullanim: esik koyunca ne kadarini kapsariz, ne kadari dogru
    print("\nESIK -> KAPSAM ve DOGRULUK (rapor kumesi)")
    print(f"  {'esik':>6}{'kapsam':>10}{'kapsanan dogruluk':>20}{'atilan':>9}")
    for t in (0.5, 0.7, 0.8, 0.9, 0.95, 0.99):
        m = pr >= t
        if m.sum() == 0:
            continue
        print(f"  {t:>6.2f}{m.mean():>10.3f}{yr[m].mean():>20.3f}"
              f"{int((~m).sum()):>9}")
    print(f"\n  Esiksiz dogruluk {yr.mean():.3f}. Esik koymanin anlami:")
    print("  dusuk guvenli okumayi ATMAK, Faz 5'te onu baska karelerin")
    print("  oyuyla degistirmek uzere.")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({
        "agirliklar": {"sabit": w[0], "marj": w[1], "lp": w[2]},
        "uydurma_kumesi": {"n": len(ys), "dogru": int(ys.sum())},
        "rapor_kumesi": {"n": len(yr), "dogru": int(yr.sum()),
                         "auc": auc(pr, yr), "ece": ece},
        "not": "Egri secim yarisina uyduruldu, rapor yarisinda olculdu. "
               "Uydurma kumesi 88 kirpma - ince.",
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\negri -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
