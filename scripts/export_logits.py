"""Tanima modelinin CTC olasilik matrislerini C++ cozumleyici icin dokum eder.

Neden ayri bir dosya
--------------------
Faz 3'un kisitli cozumleyicisi C++ yaziliyor. Iki tarafi bir surecte
birlestirmek (pybind, ctypes) su asamada gereksiz karmasiklik: olculecek
sey cozumleyicinin KAZANCI, baglama maliyeti degil. Matris dosyaya
dokuluyor, C++ ikilisi okuyor, sonuc TSV olarak geri geliyor.

Bicim
-----
logits.bin  : "PLKA" + int32 n + int32 T + int32 C + n*T*C adet float32
              (log-softmax uygulanmis; C++ tarafinda tekrar normalize
              edilmesine gerek yok)
logits.tsv  : satir basina  indeks \\t kume \\t plaka_metni

Etiket bilerek AYRI dosyada: cozumleyici dogru cevabi gormemeli.
"""

from __future__ import annotations

import argparse
import struct
from pathlib import Path

import numpy as np

from train_recognizer import (ALFABE, diziden, gercek_bol, model_kur,
                              paketi_ac)
from finetune import plakaya_gore_bol

ROOT = Path(__file__).resolve().parent.parent


def main(argv: list[str] | None = None) -> int:
    import torch

    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--paket", type=Path, default=ROOT / "paket")
    ap.add_argument("--agirlik", type=Path,
                    default=ROOT / "runs" / "ince" / "best.pt")
    ap.add_argument("--out", type=Path, default=ROOT / "paket")
    ap.add_argument("--cihaz", default="cpu")
    args = ap.parse_args(argv)

    cihaz = torch.device(args.cihaz)
    (_, _), (gx, gy) = paketi_ac(args.paket)
    kayitlar = [(gx[i], gy[i], gy[i]) for i in range(len(gx))]
    egitim, dogrulama = gercek_bol(kayitlar, val_oran=0.25, seed=0)
    secim, rapor = plakaya_gore_bol(dogrulama)

    kume = {}
    for ad, kume_kayitlari in (("egitim", egitim), ("secim", secim),
                               ("rapor", rapor)):
        for k in kume_kayitlari:
            kume[id(k)] = ad

    hepsi = egitim + secim + rapor
    model = model_kur().to(cihaz)
    durum = torch.load(args.agirlik, map_location=cihaz, weights_only=False)
    model.load_state_dict(durum["model"])
    model.eval()
    print(f"agirlik: {args.agirlik} (epoch {durum.get('epoch', '?')})")

    matrisler = []
    with torch.no_grad():
        for i in range(0, len(hepsi), 64):
            parca = hepsi[i:i + 64]
            x = torch.from_numpy(
                np.stack([diziden(k[0]) for k in parca])).to(cihaz)
            logp = model(x).log_softmax(2)          # (T, B, C)
            for j in range(len(parca)):
                matrisler.append(logp[:, j, :].cpu().numpy().astype(np.float32))

    T, C = matrisler[0].shape
    assert C == len(ALFABE) + 1, f"{C} != alfabe+blank"
    yol = args.out / "logits.bin"
    with yol.open("wb") as f:
        f.write(b"PLKA")
        f.write(struct.pack("<iii", len(matrisler), T, C))
        for m in matrisler:
            f.write(np.ascontiguousarray(m).tobytes())

    with (args.out / "logits.tsv").open("w", encoding="utf-8") as f:
        for i, k in enumerate(hepsi):
            f.write(f"{i}\t{kume[id(k)]}\t{k[1]}\n")

    print(f"{len(matrisler)} matris  T={T} C={C}  "
          f"-> {yol} ({yol.stat().st_size/1e6:.1f} MB)")
    print(f"kume dagilimi: egitim {len(egitim)}, secim {len(secim)}, "
          f"rapor {len(rapor)}")
    print(f"alfabe (blank=0, sonrasi 1..{C-1}): {ALFABE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
