"""Sentetikle egitilmis taniyiciyi GERCEK plakalarla ince ayarlar.

Neden bu adim
-------------
Uc egitim kosusunun ucunde de gercek plakalarin TAMAMI dogrulamadaydi ve
hicbiri egitimde kullanilmadi. Model gercek bir plakayi hic gormeden gercek
plakalarda sinandi. Bolme zaten PLAKAYA gore yapildigi icin egitim yarisini
(566 kirpma / 204 plaka) egitime katmak sizinti degil - kullanilmamis veri.

Ucuncu kosunun sonucu: kirpma tam dizi 0.155, plaka bazinda cogunluk oyu
0.118. 68 plakanin 58'inde hicbir kirpma dogru okunmuyor.

Olcum durustlugu: SECIM ve RAPOR ayri
-------------------------------------
60 epoch boyunca 68 plakalik bir kumeye bakip en iyisini secmek, o kumeye
secim yoluyla asiri uydurmaktir - bildirilen sayi artik saf degildir.
Bu yuzden dogrulama plakalari ikiye boluniyor:

  secim  : hangi epoch'un alinacagina bu karar verir
  rapor  : hicbir karara girmez, yalnizca sonunda bir kez okunur

Rapor kumesi kucuk (~34 plaka) ve sayisi kaba; cozunurlugu gizlemeyelim
diye kirpma/plaka sayilari da basiliyor.

Cihaz
-----
Varsayilan `cpu` ve bu bilincli: bu makinedeki GTX 1080 agir yuk altinda
dort kez dustu. Zaten olculdu - 566+566 ornekli epoch CPU'da ~10 saniye,
60 epoch 10 dakika. Bu is icin GPU gerekmiyor.

Kullanim:
    python scripts/finetune.py
    python scripts/finetune.py --epoch 80 --dondur-govde
"""

from __future__ import annotations

import argparse
import json
import random
import time
from collections import Counter
from pathlib import Path

import cv2
import numpy as np

from train_recognizer import (ALFABE, coz_greedy, diziden, duzenleme_mesafesi,
                              gercek_bol, kodla, model_kur, paketi_ac,
                              GENISLIK, YUKSEKLIK)

ROOT = Path(__file__).resolve().parent.parent

#: Gercek kirpmalara uygulanan artirmanin siddeti. 566 kirpmayi 60 kez
#: gostermek ezberleme demek; artirma bunun tek savunmasi. Ama gercek
#: kirpma ZATEN bozuk - uzerine agir bozulma eklemek gercekte bulunmayan
#: bir dagilim uretir. Bu yuzden hafif tutuluyor ve geometrik kismi
#: uretecteki KOSE_HATASI ile ayni seyi modelliyor: kose isaretlemenin
#: birkac piksel kaymasi.
KOSE_JITTER = 0.03


def artir(im: np.ndarray, rng: random.Random) -> np.ndarray:
    """Tek bir gercek kirpmayi hafifce degistirir (uint8 32x128 girer/cikar)."""
    h, w = im.shape[:2]

    # Kose kaymasi: yeniden isaretlense birkac piksel farkli cikardi.
    d = KOSE_JITTER
    def sap():
        return rng.uniform(-d, d)
    kaynak = np.float32([[w * sap(), h * sap()],
                         [w * (1 + sap()), h * sap()],
                         [w * (1 + sap()), h * (1 + sap())],
                         [w * sap(), h * (1 + sap())]])
    M = cv2.getPerspectiveTransform(
        kaynak, np.float32([[0, 0], [w, 0], [w, h], [0, h]]))
    im = cv2.warpPerspective(im, M, (w, h), borderMode=cv2.BORDER_REPLICATE,
                             flags=cv2.INTER_LINEAR)

    # Parlaklik / kontrast.
    im = np.clip(im.astype(np.float32) * rng.uniform(0.85, 1.15)
                 + rng.uniform(-20, 20), 0, 255)

    # Hafif bulaniklik ve gurultu.
    if rng.random() < 0.3:
        im = cv2.GaussianBlur(im, (3, 3), 0)
    if rng.random() < 0.5:
        im = im + np.random.RandomState(rng.randint(0, 10**6)).normal(
            0, rng.uniform(1, 4), im.shape)
    return np.clip(im, 0, 255).astype(np.uint8)


def plakaya_gore_bol(kayitlar, oran=0.5, seed=7):
    """Dogrulamayi secim/rapor diye ikiye boler - yine PLAKAYA gore."""
    plakalar = sorted({k[2] for k in kayitlar})
    random.Random(seed).shuffle(plakalar)
    kesim = int(len(plakalar) * oran)
    a = set(plakalar[:kesim])
    return ([k for k in kayitlar if k[2] in a],
            [k for k in kayitlar if k[2] not in a])


def degerlendir(model, kayitlar, cihaz, yigin=64) -> dict:
    """Kirpma ve PLAKA bazinda olcer.

    Plaka bazindaki cogunluk oyu asil sayi: ayni plakanin 82 kirpmasi
    bagimsiz olcum degil, ve urun plakayi okumak zorunda, kirpmayi degil.
    """
    import torch
    model.eval()
    tahminler = []
    with torch.no_grad():
        for i in range(0, len(kayitlar), yigin):
            parca = kayitlar[i:i + yigin]
            x = torch.from_numpy(
                np.stack([diziden(k[0]) for k in parca])).to(cihaz)
            for L, k in zip(model(x).permute(1, 0, 2).cpu().numpy(), parca):
                tahminler.append((coz_greedy(L), k[1], k[2]))

    d = [duzenleme_mesafesi(t, h) for t, h, _ in tahminler]
    kt = sum(len(h) for _, h, _ in tahminler)
    kd = sum(max(0, len(h) - m) for m, (_, h, _) in zip(d, tahminler))

    plaka = {}
    for t, h, p in tahminler:
        plaka.setdefault(p, []).append((t, h))
    cogunluk = sum(Counter(t for t, _ in v).most_common(1)[0][0] == v[0][1]
                   for v in plaka.values())
    en_az_bir = sum(any(t == h for t, h in v) for v in plaka.values())

    return {
        "tam_dizi": sum(t == h for t, h, _ in tahminler) / max(1, len(tahminler)),
        "karakter": kd / max(1, kt),
        "duzenleme": float(np.mean(d)) if d else 0.0,
        "plaka_cogunluk": cogunluk / max(1, len(plaka)),
        "plaka_en_az_bir": en_az_bir / max(1, len(plaka)),
        "n_kirpma": len(tahminler), "n_plaka": len(plaka),
    }


def main(argv: list[str] | None = None) -> int:
    import torch
    import torch.nn as nn

    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--paket", type=Path, default=ROOT / "paket")
    parser.add_argument("--baslangic", type=Path,
                        default=ROOT / "runs" / "taniyici" / "son.pt")
    parser.add_argument("--epoch", type=int, default=60)
    parser.add_argument("--yigin", type=int, default=64)
    parser.add_argument("--lr", type=float, default=3e-5,
                        help="egitimin 1/10'u; agirlik sifirdan degil "
                             "sentetikte ogrenilmis halden basliyor")
    parser.add_argument("--sentetik-orani", type=float, default=1.0,
                        help="her epoch gercek basina kac sentetik ornek")
    parser.add_argument("--dondur-govde", action="store_true",
                        help="yalnizca basligi egit - 566 kirpmada ezberlemeye "
                             "karsi en sert onlem")
    parser.add_argument("--cihaz", default="cpu")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--out", type=Path, default=ROOT / "runs" / "ince")
    args = parser.parse_args(argv)

    rng = random.Random(args.seed)
    torch.manual_seed(args.seed)
    cihaz = torch.device(args.cihaz)
    args.out.mkdir(parents=True, exist_ok=True)

    (sx, sy), (gx, gy) = paketi_ac(args.paket)
    kayitlar = [(gx[i], gy[i], gy[i]) for i in range(len(gx))]
    g_egitim, g_dogrulama = gercek_bol(kayitlar, val_oran=0.25, seed=0)
    secim, rapor = plakaya_gore_bol(g_dogrulama)

    print(f"gercek egitim   {len(g_egitim):>4} kirpma / "
          f"{len({k[2] for k in g_egitim}):>3} plaka   (ilk kez egitimde)")
    print(f"secim kumesi    {len(secim):>4} kirpma / "
          f"{len({k[2] for k in secim}):>3} plaka   (epoch secimi buna bakar)")
    print(f"rapor kumesi    {len(rapor):>4} kirpma / "
          f"{len({k[2] for k in rapor}):>3} plaka   (hicbir karara girmez)")
    print(f"sentetik havuzu {len(sx):>6}\n")

    model = model_kur().to(cihaz)
    if not args.baslangic.is_file():
        raise SystemExit(f"baslangic agirligi yok: {args.baslangic}")
    durum = torch.load(args.baslangic, map_location=cihaz, weights_only=False)
    model.load_state_dict(durum["model"])
    print(f"baslangic: {args.baslangic.name} (epoch {durum.get('epoch', '?')})")
    # Rapor kumesindeki sonucun anlamli olmasi icin AYNI kumede baslangic
    # degeri lazim. Iki sayiyi basmak o kumeyi bir karara sokmaz.
    import copy
    baslangic_durumu = copy.deepcopy(model.state_dict())

    if args.dondur_govde:
        for p in model.govde.parameters():
            p.requires_grad = False
        print("govde donduruldu; yalnizca baslik egitiliyor")

    # Baslangic seviyesi: ince ayarin bir sey KATTIGINI gostermek icin
    # once dokunulmamis halin sayisi lazim.
    ilk = degerlendir(model, secim, cihaz)
    print(f"\nbaslangic (secim kumesi)  tam dizi {ilk['tam_dizi']:.3f}   "
          f"plaka cogunluk {ilk['plaka_cogunluk']:.3f}   "
          f"duzenleme {ilk['duzenleme']:.2f}\n")

    par = [p for p in model.parameters() if p.requires_grad]
    opt = torch.optim.AdamW(par, lr=args.lr, weight_decay=1e-4)
    ctc = nn.CTCLoss(blank=0, zero_infinity=True)

    n_sentetik = int(len(g_egitim) * args.sentetik_orani)
    en_iyi = (-1.0, 1e9)
    gecmis = []
    basladi = time.perf_counter()

    for epoch in range(1, args.epoch + 1):
        model.train()
        # Her epoch: gercek egitim kirpmalarinin TAMAMI (artirilmis) +
        # sentetikten taze bir orneklem. Sentetigi tutmanin sebebi
        # felaket unutma: yalnizca 566 gercekle egitmek modelin sentetikte
        # ogrendigi genel karakter bilgisini silebilir.
        parti = [(artir(k[0], rng), k[1]) for k in g_egitim]
        for i in rng.sample(range(len(sx)), min(n_sentetik, len(sx))):
            parti.append((sx[i], sy[i]))
        rng.shuffle(parti)

        toplam = adim = 0
        for i in range(0, len(parti) - 1, args.yigin):
            obek = parti[i:i + args.yigin]
            X, hedef, uzunluk = [], [], []
            for im, metin in obek:
                kod = kodla(metin)
                if not kod:
                    continue
                X.append(diziden(im))
                hedef.extend(kod)
                uzunluk.append(len(kod))
            if len(X) < 2:
                continue
            x = torch.from_numpy(np.stack(X)).to(cihaz)
            logits = model(x)
            logp = logits.log_softmax(2)
            kayip = ctc(logp,
                        torch.tensor(hedef, dtype=torch.long, device=cihaz),
                        torch.full((len(X),), logits.shape[0],
                                   dtype=torch.long, device=cihaz),
                        torch.tensor(uzunluk, dtype=torch.long, device=cihaz))
            opt.zero_grad(set_to_none=True)
            kayip.backward()
            nn.utils.clip_grad_norm_(par, 5.0)
            opt.step()
            toplam += kayip.detach().item()
            adim += 1

        o = degerlendir(model, secim, cihaz)
        gecmis.append({"epoch": epoch, "kayip": toplam / max(1, adim), **o})
        print(f"epoch {epoch:>3}  kayip {toplam/max(1,adim):>6.3f}  "
              f"tam dizi {o['tam_dizi']:>6.3f}  "
              f"plaka cogunluk {o['plaka_cogunluk']:>6.3f}  "
              f"duzenleme {o['duzenleme']:>5.2f}  "
              f"{(time.perf_counter()-basladi)/60:>5.1f} dk", flush=True)

        kayit = {"model": model.state_dict(), "alfabe": ALFABE,
                 "girdi": [YUKSEKLIK, GENISLIK], "epoch": epoch, **o}
        torch.save(kayit, args.out / "son.pt")
        # Secim: once tam dizi, esitlikte duzenleme mesafesi. Ucuncu kosuda
        # tek olcute bakmak yanlis epoch'u secmisti; ikisi birlikte.
        aday = (o["tam_dizi"], -o["duzenleme"])
        if aday > (en_iyi[0], -en_iyi[1]):
            en_iyi = (o["tam_dizi"], o["duzenleme"])
            torch.save(kayit, args.out / "best.pt")

    (args.out / "gecmis.json").write_text(
        json.dumps(gecmis, indent=2, ensure_ascii=False), encoding="utf-8")

    # --- Rapor: secilen agirlik, hic bakilmamis kumede ---------------------
    model.load_state_dict(torch.load(args.out / "best.pt",
                                     map_location=cihaz,
                                     weights_only=False)["model"])
    r = degerlendir(model, rapor, cihaz)
    model.load_state_dict(baslangic_durumu)
    r_ilk = degerlendir(model, rapor, cihaz)

    print("\n" + "=" * 68)
    print(f"RAPOR KUMESI - hicbir karara girmedi "
          f"({r['n_kirpma']} kirpma / {r['n_plaka']} plaka)")
    print("=" * 68)
    print(f"  {'olcut':<24}{'ince ayar oncesi':>18}{'sonrasi':>12}")
    print("  " + "-" * 54)
    for ad, k, ters in (("kirpma tam dizi", "tam_dizi", False),
                        ("karakter", "karakter", False),
                        ("duzenleme (dusuk iyi)", "duzenleme", True),
                        ("PLAKA cogunluk oyu", "plaka_cogunluk", False),
                        ("PLAKA en az bir dogru", "plaka_en_az_bir", False)):
        bicim = "{:>18.2f}{:>12.2f}" if ters else "{:>18.3f}{:>12.3f}"
        iyi = (r[k] < r_ilk[k]) if ters else (r[k] > r_ilk[k])
        print(f"  {ad:<24}" + bicim.format(r_ilk[k], r[k])
              + ("  +" if iyi else ""))
    print(f"\n  PLAKA cogunluk: "
          f"{round(r_ilk['plaka_cogunluk']*r['n_plaka'])}"
          f"/{r['n_plaka']} -> {round(r['plaka_cogunluk']*r['n_plaka'])}"
          f"/{r['n_plaka']} plaka")
    print(f"\n  {r['n_plaka']} plakada bir plaka = {1/r['n_plaka']:.3f}; "
          f"bu sayinin cozunurlugu bu.")
    print(f"\nagirlik -> {args.out / 'best.pt'} (ve son.pt)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
