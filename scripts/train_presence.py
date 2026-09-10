"""Varlik basligi: "bu arac kirpmasinda OKUNUR bir plaka var mi".

Neden ayri bir egitim
---------------------
Bolum 20'de olculdu: boru hatti, okunacak hicbir sey olmayan kirpmalarda
kalipsi bir plaka uyduruyor ve bunu 1.000 guvenle yapiyor. Guven marja
dayaniyor - en iyi ile ikinci en iyi gecerli plaka arasindaki farka - ve bos
bir kirpmada modelin tek bir varsayilan kalibi var, rakibi yok, dolayisiyla
marj tavan yapiyor. Marj "alternatifler arasinda ne kadar eminim" sorusunu
cevapliyor; "burada okunacak bir sey var mi" baska bir soru.

Ilk deneme: ORTAK GOVDE, iki baslik. Basarisiz oldu ve olculdu.
------------------------------------------------------------
Kose modelinin govdesine ikinci bir baslik eklenip 566 pozitif + 993 negatifle
birlikte egitildi. Iki is de bozuldu:

  kose >%5 orani (rapor)   0.083 -> 0.631
  varlik AUC (rapor)                0.740
  varlik AUC (secim)       epoch 55'te 0.960, epoch 200'de 0.914

Muhtemel mekanizma BatchNorm: yigin artik %64 negatif ve normallestirme
istatistikleri kose basliginin gordugu dagilimi kaydiriyor. Ayrica kose
kaybi her adimda yiginin yalnizca %36'sindan geliyor.

Bu betik govdeyi DONDURUYOR. Kose agirliklari hic degismiyor, yani kose
dogruluguna zarar vermesi mumkun degil; olculecek tek sey dondurulmus
ozniteliklerin bu soruyu cevaplamaya yetip yetmedigi.

Bolme
-----
Pozitifler plakaya gore (taniyiciyla ayni tohum), negatifler kaynak video +
kare bloguna gore. Kirpmalar iki saniye arayla ornekleendi ama ayni arac
ardisik birkac karede gecebiliyor; rastgele bolmek onu iki tarafa birden
koyar ve olculen ayirma gucunu sisirir.

Kullanim:
    python scripts/train_presence.py
"""

from __future__ import annotations

import argparse
import json
import random
import time
from pathlib import Path

import cv2
import numpy as np

from train_corners import (GENISLIK, YUKSEKLIK, artir, girdiye, ikiye_bol,
                           kayitlari_oku, model_kur, negatif_bol,
                           negatifleri_oku, plakaya_gore_bol)

ROOT = Path(__file__).resolve().parent.parent


def yukle(yol: Path):
    im = cv2.imread(str(yol))
    if im is None:
        return None
    return cv2.resize(im, (GENISLIK, YUKSEKLIK), interpolation=cv2.INTER_AREA)


def puanla(model, goruntuler, cihaz, yigin=64):
    import torch
    model.eval()
    out = []
    with torch.no_grad():
        for i in range(0, len(goruntuler), yigin):
            X = [girdiye(g) for g in goruntuler[i:i + yigin]]
            _, logit = model(torch.from_numpy(np.stack(X)).to(cihaz))
            out.extend(torch.sigmoid(logit).cpu().numpy().tolist())
    return np.array(out)


def olc(puan, etiket, tut=0.95):
    """AUC ve pozitiflerin `tut` kadarini tutan esikte gecen negatif orani."""
    n1 = etiket.sum()
    n0 = len(etiket) - n1
    if n1 == 0 or n0 == 0:
        return {"auc": float("nan")}
    sira = np.argsort(np.argsort(puan)) + 1
    auc = float((sira[etiket == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))
    esik = float(np.quantile(puan[etiket == 1], 1 - tut))
    return {"auc": auc, "esik": esik,
            "sizinti": float((puan[etiket == 0] >= esik).mean()),
            "n_poz": int(n1), "n_neg": int(n0)}


def main(argv: list[str] | None = None) -> int:
    import torch
    import torch.nn as nn

    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--crops", type=Path, default=ROOT / "data" / "crops")
    ap.add_argument("--etiket", type=Path, default=ROOT / "data" / "labels.jsonl")
    ap.add_argument("--kose", type=Path, default=ROOT / "runs" / "kose" / "best.pt",
                    help="govdesi dondurulacak kose modeli")
    ap.add_argument("--epoch", type=int, default=40)
    ap.add_argument("--yigin", type=int, default=64)
    ap.add_argument("--lr", type=float, default=3e-3)
    ap.add_argument("--cihaz", default="cpu")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", type=Path, default=ROOT / "runs" / "varlik")
    args = ap.parse_args(argv)

    rng = random.Random(args.seed)
    torch.manual_seed(args.seed)
    cihaz = torch.device(args.cihaz)
    args.out.mkdir(parents=True, exist_ok=True)

    poz = kayitlari_oku(args.crops, args.etiket)
    p_egitim, p_dog = plakaya_gore_bol(poz)
    p_secim, p_rapor = ikiye_bol(p_dog)
    neg = negatifleri_oku(args.crops, args.etiket)
    n_egitim, n_dog = negatif_bol(neg)
    n_secim, n_rapor = n_dog[::2], n_dog[1::2]

    print(f"pozitif  egitim {len(p_egitim):>4}  secim {len(p_secim):>3}  "
          f"rapor {len(p_rapor):>3}")
    print(f"negatif  egitim {len(n_egitim):>4}  secim {len(n_secim):>3}  "
          f"rapor {len(n_rapor):>3}\n")

    model = model_kur().to(cihaz)
    durum = torch.load(args.kose, map_location=cihaz, weights_only=False)
    eksik = model.load_state_dict(durum["model"], strict=False)
    print(f"kose modeli: epoch {durum.get('epoch','?')}, "
          f"kose hatasi (secim) {durum.get('oran_ortanca', float('nan')):.3f}")
    print(f"  yuklenmeyen (varlik basligi, sifirdan): "
          f"{len(eksik.missing_keys)} tensor")

    # GOVDE VE KOSE BASLIGI DONDURULUYOR. Kose dogruluguna zarar vermesi
    # mumkun degil - o agirliklar hic degismiyor.
    for ad, par in model.named_parameters():
        par.requires_grad = ad.startswith("varlik")
    egitilen = [p for p in model.parameters() if p.requires_grad]
    print(f"  egitilen parametre: {sum(p.numel() for p in egitilen):,} "
          f"/ {sum(p.numel() for p in model.parameters()):,}\n")

    # Onbellek
    p_im = [x for x in (yukle(y) for y, _, _ in p_egitim) if x is not None]
    n_im = [x for x in (yukle(y) for y in n_egitim) if x is not None]
    s_im = [x for x in (yukle(y) for y, _, _ in p_secim) if x is not None] + \
           [x for x in (yukle(y) for y in n_secim) if x is not None]
    s_et = np.array([1.0] * len(p_secim) + [0.0] * len(n_secim))
    print(f"{len(p_im)} pozitif + {len(n_im)} negatif bellege alindi\n")

    opt = torch.optim.AdamW(egitilen, lr=args.lr, weight_decay=1e-4)
    ctc = nn.BCEWithLogitsLoss()

    ilk = olc(puanla(model, s_im, cihaz), s_et)
    print(f"baslangic (egitilmemis baslik): AUC {ilk['auc']:.3f}\n")

    en_iyi = -1.0
    gecmis = []
    basladi = time.perf_counter()
    for epoch in range(1, args.epoch + 1):
        model.train()
        # Govde dondurulmus olsa da BatchNorm calisma istatistikleri train()
        # kipinde guncellenir ve bu KOSE dogrulugunu bozar. Govde eval'de
        # tutuluyor; yalnizca varlik basligi egitiliyor.
        model.govde.eval()
        model.baslik.eval()

        sira = ([("p", j) for j in range(len(p_im))]
                + [("n", j) for j in range(len(n_im))])
        rng.shuffle(sira)
        toplam = adim = 0
        for i in range(0, len(sira) - 1, args.yigin):
            X, Y = [], []
            for tur, j in sira[i:i + args.yigin]:
                im = p_im[j] if tur == "p" else n_im[j]
                im, _ = artir(im, np.zeros((4, 2), np.float32), rng)
                X.append(girdiye(im))
                Y.append(1.0 if tur == "p" else 0.0)
            x = torch.from_numpy(np.stack(X)).to(cihaz)
            y = torch.tensor(Y, dtype=torch.float32, device=cihaz)
            _, logit = model(x)
            kayip = ctc(logit, y)
            opt.zero_grad(set_to_none=True)
            kayip.backward()
            opt.step()
            toplam += kayip.item()
            adim += 1

        o = olc(puanla(model, s_im, cihaz), s_et)
        gecmis.append({"epoch": epoch, "kayip": toplam / max(1, adim), **o})
        print(f"epoch {epoch:>3}  kayip {toplam/max(1,adim):>6.4f}  "
              f"AUC {o['auc']:>6.3f}  sizinti {o['sizinti']:>6.3f}  "
              f"{(time.perf_counter()-basladi)/60:>5.1f} dk", flush=True)
        kayit = {"model": model.state_dict(), "epoch": epoch,
                 "girdi": [YUKSEKLIK, GENISLIK], **o}
        torch.save(kayit, args.out / "son.pt")
        if o["auc"] > en_iyi:
            en_iyi = o["auc"]
            torch.save(kayit, args.out / "best.pt")

    (args.out / "gecmis.json").write_text(
        json.dumps(gecmis, indent=2, ensure_ascii=False), encoding="utf-8")

    model.load_state_dict(torch.load(args.out / "best.pt", map_location=cihaz,
                                     weights_only=False)["model"])
    r_im = [x for x in (yukle(y) for y, _, _ in p_rapor) if x is not None] + \
           [x for x in (yukle(y) for y in n_rapor) if x is not None]
    r_et = np.array([1.0] * len(p_rapor) + [0.0] * len(n_rapor))
    r = olc(puanla(model, r_im, cihaz), r_et)

    print("\n" + "=" * 66)
    print(f"RAPOR KUMESI - hicbir karara girmedi "
          f"({r['n_poz']} pozitif / {r['n_neg']} negatif)")
    print("=" * 66)
    print(f"  AUC                                  {r['auc']:.3f}")
    print(f"  pozitiflerin %95'ini tutan esik      {r['esik']:.3f}")
    print(f"  o esikte gecen negatif               {r['sizinti']:.3f}")
    for tut in (0.90, 0.80):
        rr = olc(puanla(model, r_im, cihaz), r_et, tut=tut)
        print(f"  pozitiflerin %{tut*100:.0f}'ini tutarsak "
              f"gecen negatif  {rr['sizinti']:.3f}")
    print(f"\n  Kose dogrulugu DEGISMEDI: govde donduruldu.")
    print(f"\nagirlik -> {args.out / 'best.pt'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
