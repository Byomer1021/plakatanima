"""Faz 1: arac kirpmasindan plakanin DORT KOSESINI bulur.

Neden bu eksik
--------------
Bolum 10-17'deki her sayi "diklestirilmis kirpma verilmis" varsayimiyla
olculdu ve o kirpmalari insan eliyle isaretlenmis kosseler uretti. Gercek
boru hattinda kosseleri bir model bulacak ve hatasi her seyin uzerine
binecek. Bu betik o modeli egitiyor; asil sonuc `end_to_end.py` icinde,
kose hatasinin plaka okumaya kac plakaya mal oldugu.

Yaklasim: yumusak-argmax
------------------------
Dogrudan 8 sayi regresyonu (govde -> global havuz -> tam bagli -> 8)
konum bilgisini havuzda kaybediyor ve 566 ornekle zayif genelliyor.
Bunun yerine govde her kose icin bir isi haritasi uretiyor, uzamsal
softmax'in beklenen degeri koordinati veriyor. Turevlenebilir, cok daha
az parametre, ve beklenen deger oldugu icin izgara cozunurlugunun
altinda hassasiyet verebiliyor.

Bolme
-----
Plakaya gore ve TANIYICIYLA AYNI tohumla: rapor kumesindeki plakalar
birebir ayni olsun ki uctan uca sayi karsilastirilabilsin.

Cihaz
-----
Varsayilan cpu. Bu makinedeki GTX 1080 agir yuk altinda dort kez dustu.

Kullanim:
    python scripts/train_corners.py
    python scripts/train_corners.py --epoch 120
"""

from __future__ import annotations

import argparse
import json
import math
import random
import time
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent.parent

#: Modelin girdisi. Arac kirpmalarinin en/boy ortancasi 2.90; 288x96 = 3.0
#: buna yakin. Daha kucuk bir girdi (192x64) kose hassasiyetini kirpmanin
#: kendi cozunurlugunun altina dusuruyordu: 386 px genisligindeki bir
#: kirpmada 192'lik izgaranin 1 pikseli 2 piksel demek ve plaka yalnizca
#: 88 px genisliginde.
GENISLIK, YUKSEKLIK = 288, 96

#: Cikti izgarasi (govde 1/8'e indiriyor). Yumusak-argmax beklenen deger
#: aldigi icin hassasiyet bu izgarayla sinirli degil.
IZGARA_G, IZGARA_Y = GENISLIK // 8, YUKSEKLIK // 8


def kayitlari_oku(kok: Path, etiket: Path):
    """(goruntu yolu, 4x2 kose, plaka metni) - yalnizca 'ok' kayitlari."""
    out = []
    for satir in etiket.read_text(encoding="utf-8").splitlines():
        if not satir.strip():
            continue
        k = json.loads(satir)
        if k.get("durum") != "ok" or "kose" not in k:
            continue
        yol = kok / k["dosya"]
        if yol.is_file():
            out.append((yol, np.array(k["kose"], dtype=np.float32), k["metin"]))
    return out


def negatifleri_oku(kok: Path, etiket: Path):
    """Okunur plaka ICERMEYEN kirpmalar: 'plakasiz' ve 'okunmaz'.

    Bu 1308 kirpma bastan beri etiketliydi ve hicbir asamada kullanilmadi.
    Bedeli bolum 20'de olculdu: modele hic "burada okunacak bir sey yok"
    demesi ogretilmedigi icin, bos bir kirpmada kalipsi bir plaka uyduruyor
    ve kisitli cozumleyici onu gecerli bir plakaya zorluyor. Uydurmalarin
    guveni 1.000 cikiyor, gercek okumalarin 0.933 - yani guven bu arizayi
    ayiramiyor, tersini gosteriyor.

    'okunmaz' da negatif sayiliyor: plaka VAR ama okunmuyor. Boru hatti
    acisindan ikisi ayni sey - okunamayan bir plakadan uretilen dizgi
    uydurmadir.
    """
    out = []
    for satir in etiket.read_text(encoding="utf-8").splitlines():
        if not satir.strip():
            continue
        k = json.loads(satir)
        if k.get("durum") not in ("plakasiz", "okunmaz"):
            continue
        yol = kok / k["dosya"]
        if yol.is_file():
            out.append(yol)
    return out


def negatif_bol(yollar, val_oran=0.25, seed=0):
    """Negatifleri kaynak video + KARE BLOGUNA gore boler.

    Kirpmalar iki saniye arayla ornekleendi ama ayni arac ardisik birkac
    karede gecebiliyor. Rastgele bolmek ayni araci iki tarafa birden koyar
    ve olculen ayirma gucu sisirir - pozitiflerde plakaya gore bolmenin
    sebebi de buydu.
    """
    def anahtar(yol: Path) -> str:
        govde = yol.stem.rsplit("_", 1)[0]          # maltepe_00878
        video, kare = govde.rsplit("_", 1)
        return f"{video}_{int(kare) // 25:04d}"     # ~50 saniyelik blok

    gruplar = sorted({anahtar(y) for y in yollar})
    random.Random(seed).shuffle(gruplar)
    egitim_g = set(gruplar[:int(len(gruplar) * (1 - val_oran))])
    return ([y for y in yollar if anahtar(y) in egitim_g],
            [y for y in yollar if anahtar(y) not in egitim_g])


def plakaya_gore_bol(kayitlar, val_oran=0.25, seed=0):
    """train_recognizer.gercek_bol ile AYNI mantik ve tohum."""
    plakalar = sorted({k[2] for k in kayitlar})
    random.Random(seed).shuffle(plakalar)
    kesim = int(len(plakalar) * (1 - val_oran))
    egitim_p = set(plakalar[:kesim])
    return ([k for k in kayitlar if k[2] in egitim_p],
            [k for k in kayitlar if k[2] not in egitim_p])


def ikiye_bol(kayitlar, oran=0.5, seed=7):
    """finetune.plakaya_gore_bol ile ayni: secim / rapor."""
    plakalar = sorted({k[2] for k in kayitlar})
    random.Random(seed).shuffle(plakalar)
    a = set(plakalar[:int(len(plakalar) * oran)])
    return ([k for k in kayitlar if k[2] in a],
            [k for k in kayitlar if k[2] not in a])


def hazirla(yol: Path, kose: np.ndarray):
    """Goruntuyu sabit boyuta getirir, kosleri ayni olcege tasir.

    Ucuncu deger orijinal (genislik, yukseklik): hata OLCUMU orijinal
    uzayda yapiliyor, cunku diklestirme orada oluyor.
    """
    im = cv2.imread(str(yol))
    if im is None:
        return None, None, None
    h, w = im.shape[:2]
    im = cv2.resize(im, (GENISLIK, YUKSEKLIK), interpolation=cv2.INTER_AREA)
    k = kose.copy()
    k[:, 0] *= GENISLIK / w
    k[:, 1] *= YUKSEKLIK / h
    return im, k, (w, h)


def artir(im: np.ndarray, kose: np.ndarray, rng: random.Random):
    """Gercek boru hattindaki degiskenligi taklit eder.

    En onemlisi kadraj oynamasi: gercekte arac kutusunu YOLO veriyor ve
    kutunun kenarlari kareden kareye kayiyor. Elle kirpilmis bir kutuya
    fazla uyan model o kaymada bozulur.
    """
    h, w = im.shape[:2]
    aci = rng.uniform(-4, 4)
    olcek = rng.uniform(0.88, 1.15)
    tx, ty = rng.uniform(-0.08, 0.08) * w, rng.uniform(-0.08, 0.08) * h
    M = cv2.getRotationMatrix2D((w / 2, h / 2), aci, olcek)
    M[0, 2] += tx
    M[1, 2] += ty
    im = cv2.warpAffine(im, M, (w, h), borderMode=cv2.BORDER_REPLICATE,
                        flags=cv2.INTER_LINEAR)
    kose = (M[:, :2] @ kose.T).T + M[:, 2]

    im = np.clip(im.astype(np.float32) * rng.uniform(0.7, 1.3)
                 + rng.uniform(-30, 30), 0, 255)
    if rng.random() < 0.3:
        im = cv2.GaussianBlur(im, (3, 3), 0)
    if rng.random() < 0.5:
        im = im + np.random.RandomState(rng.randint(0, 10**6)).normal(
            0, rng.uniform(1, 6), im.shape)
    return np.clip(im, 0, 255).astype(np.uint8), kose.astype(np.float32)


def girdiye(im: np.ndarray) -> np.ndarray:
    return (im.astype(np.float32) / 127.5 - 1.0).transpose(2, 0, 1)


def model_kur():
    import torch
    import torch.nn as nn

    def blok(g, c, adim):
        return nn.Sequential(
            nn.Conv2d(g, c, 3, stride=adim, padding=1, bias=False),
            nn.BatchNorm2d(c), nn.ReLU(inplace=True),
            nn.Conv2d(c, c, 3, padding=1, bias=False),
            nn.BatchNorm2d(c), nn.ReLU(inplace=True))

    class Koseci(nn.Module):
        def __init__(self):
            super().__init__()
            self.govde = nn.Sequential(
                blok(3, 32, 2),      # 96x288 -> 48x144
                blok(32, 64, 2),     # -> 24x72
                blok(64, 96, 2),     # -> 12x36
                blok(96, 128, 1))
            self.baslik = nn.Conv2d(128, 4, 1)   # kose basina bir isi haritasi
            # Ikinci baslik: "bu kirpmada OKUNUR bir plaka var mi".
            # Ayni govdeyi paylasiyor, yani cikarimda ek maliyeti yok.
            # Marjdan BAGIMSIZ bir sinyal olmasi onemli: bolum 20'de guvenin
            # bu arizayi ayiramadigi olculdu, cunku marj "alternatifler
            # arasinda ne kadar eminim" sorusunu cevapliyor, "burada bir sey
            # var mi" sorusunu degil.
            self.varlik = nn.Sequential(
                nn.Conv2d(128, 64, 1, bias=False),
                nn.BatchNorm2d(64), nn.ReLU(inplace=True),
                nn.AdaptiveAvgPool2d(1), nn.Flatten(), nn.Linear(64, 1))
            yy, xx = np.mgrid[0:IZGARA_Y, 0:IZGARA_G]
            self.register_buffer("gx", torch.tensor(
                (xx + 0.5) / IZGARA_G, dtype=torch.float32).reshape(1, 1, -1))
            self.register_buffer("gy", torch.tensor(
                (yy + 0.5) / IZGARA_Y, dtype=torch.float32).reshape(1, 1, -1))

        def forward(self, x):
            g = self.govde(x)
            h = self.baslik(g)                        # (B, 4, Y, G)
            B, K = h.shape[0], h.shape[1]
            p = h.reshape(B, K, -1).softmax(dim=-1)   # uzamsal softmax
            x_ = (p * self.gx).sum(-1)
            y_ = (p * self.gy).sum(-1)
            # (kose koordinatlari 0-1, varlik logiti)
            return torch.stack([x_, y_], dim=-1), self.varlik(g).squeeze(-1)

    return Koseci()


def degerlendir(model, kayitlar, cihaz):
    """Kose hatasini PLAKA GENISLIGININ orani olarak olcer.

    Piksel cinsinden hata tek basina anlamsiz: uzaktaki kucuk bir plakada
    3 piksel, yakindaki buyuk bir plakada 3 pikselle ayni sey degil.
    Uretecteki KOSE_HATASI = 0.05 ile ayni birim, boylece taniyicinin
    egitildigi bozulma araligiyla dogrudan karsilastirilabiliyor.
    """
    import torch
    model.eval()
    oranlar, pikseller = [], []
    with torch.no_grad():
        for i in range(0, len(kayitlar), 32):
            parca = kayitlar[i:i + 32]
            X, H = [], []
            for yol, kose, _ in parca:
                im, _, boyut = hazirla(yol, kose)
                if im is None:
                    continue
                X.append(girdiye(im))
                H.append((kose, boyut))     # ORIJINAL uzaydaki hedef
            if not X:
                continue
            t = torch.from_numpy(np.stack(X)).to(cihaz)
            p, _ = model(t)
            p = p.cpu().numpy()
            for tahmin, (hedef, (w, h)) in zip(p, H):
                # Olcum orijinal goruntu uzayinda: yeniden boyutlandirma
                # anizotropik (386x144 -> 288x96) oldugu icin kucultulmus
                # uzayda olculen hata farkli bir sayi verir ve
                # end_to_end.py ile uyusmaz. Diklestirme orijinal uzayda
                # yapildigina gore anlamli olan bu.
                tahmin = tahmin * [w, h]
                d = np.linalg.norm(tahmin - hedef, axis=1)
                gen = np.linalg.norm(hedef[1] - hedef[0])
                pikseller.append(float(d.mean()))
                oranlar.append(float(d.mean() / max(1e-6, gen)))
    return {"oran": float(np.mean(oranlar)),
            "oran_ortanca": float(np.median(oranlar)),
            "piksel": float(np.mean(pikseller)),
            "kotu_005": float(np.mean(np.array(oranlar) > 0.05)),
            "n": len(oranlar)}


def varlik_olc(model, pozitif, negatif, cihaz):
    """Varlik basligi okunur plakayi okunmayandan ayirabiliyor mu.

    AUC: rastgele bir pozitif, rastgele bir negatiften yuksek puan alir mi.
    0.5 bilgi yok demek.
    """
    import torch
    model.eval()
    puan, etiket = [], []
    with torch.no_grad():
        for kume, y in ((pozitif, 1.0), (negatif, 0.0)):
            for i in range(0, len(kume), 32):
                X = []
                for kayit in kume[i:i + 32]:
                    yol = kayit[0] if isinstance(kayit, tuple) else kayit
                    im = cv2.imread(str(yol))
                    if im is None:
                        continue
                    X.append(girdiye(cv2.resize(im, (GENISLIK, YUKSEKLIK),
                                                interpolation=cv2.INTER_AREA)))
                if not X:
                    continue
                _, logit = model(torch.from_numpy(np.stack(X)).to(cihaz))
                puan.extend(logit.cpu().numpy().tolist())
                etiket.extend([y] * len(X))
    puan, etiket = np.array(puan), np.array(etiket)
    n1 = etiket.sum()
    n0 = len(etiket) - n1
    if n1 == 0 or n0 == 0:
        return {"auc": float("nan"), "n": len(etiket)}
    sira = np.argsort(np.argsort(puan)) + 1
    auc = float((sira[etiket == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))
    # Pozitiflerin %95'ini tutan esikte kac negatif geciyor
    esik = np.quantile(puan[etiket == 1], 0.05)
    return {"auc": auc, "n": len(etiket),
            "negatif_sizinti": float((puan[etiket == 0] >= esik).mean()),
            "esik": float(esik)}


def main(argv: list[str] | None = None) -> int:
    import torch
    import torch.nn as nn

    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--crops", type=Path, default=ROOT / "data" / "crops")
    ap.add_argument("--etiket", type=Path, default=ROOT / "data" / "labels.jsonl")
    ap.add_argument("--epoch", type=int, default=120)
    ap.add_argument("--yigin", type=int, default=32)
    ap.add_argument("--lr", type=float, default=2e-3)
    ap.add_argument("--cihaz", default="cpu")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", type=Path, default=ROOT / "runs" / "kose")
    args = ap.parse_args(argv)

    rng = random.Random(args.seed)
    torch.manual_seed(args.seed)
    cihaz = torch.device(args.cihaz)
    args.out.mkdir(parents=True, exist_ok=True)

    kayitlar = kayitlari_oku(args.crops, args.etiket)
    egitim, dogrulama = plakaya_gore_bol(kayitlar)
    secim, rapor = ikiye_bol(dogrulama)
    print(f"egitim {len(egitim):>4} kirpma / {len({k[2] for k in egitim}):>3} plaka")
    print(f"secim  {len(secim):>4} kirpma / {len({k[2] for k in secim}):>3} plaka")
    print(f"rapor  {len(rapor):>4} kirpma / {len({k[2] for k in rapor}):>3} plaka"
          f"   (taniyicinin rapor kumesiyle ayni plakalar)")

    negatifler = negatifleri_oku(args.crops, args.etiket)
    n_egitim, n_dogrulama = negatif_bol(negatifler)
    n_secim, n_rapor = n_dogrulama[::2], n_dogrulama[1::2]
    print(f"\nnegatif (plakasiz + okunmaz): {len(negatifler)} kirpma")
    print(f"  egitim {len(n_egitim)}, secim {len(n_secim)}, "
          f"rapor {len(n_rapor)}   (kare bloguna gore bolundu)\n")

    # Onbellek: goruntuler bellege sigar, her epoch diskten okumak bosuna.
    # Negatiflerde kose hedefi YOK; None ile isaretleniyor ve kose kaybi
    # onlarda hesaplanmiyor.
    onbellek = []
    for yol, kose, metin in egitim:
        im, k, _ = hazirla(yol, kose)
        if im is not None:
            onbellek.append((im, k))
    n_onbellek = []
    for yol in n_egitim:
        im = cv2.imread(str(yol))
        if im is not None:
            n_onbellek.append(cv2.resize(im, (GENISLIK, YUKSEKLIK),
                                         interpolation=cv2.INTER_AREA))
    print(f"{len(onbellek)} pozitif + {len(n_onbellek)} negatif "
          f"goruntu bellege alindi\n")

    model = model_kur().to(cihaz)
    n_par = sum(p.numel() for p in model.parameters())
    print(f"model {n_par/1e6:.2f}M parametre\n")
    opt = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=1e-4)
    plan = torch.optim.lr_scheduler.CosineAnnealingLR(
        opt, T_max=args.epoch * max(1, len(onbellek) // args.yigin))

    en_iyi = (float("inf"), float("inf"))
    gecmis = []
    basladi = time.perf_counter()
    for epoch in range(1, args.epoch + 1):
        model.train()
        # Pozitif ve negatifler birlikte karistiriliyor. Negatif sayisi
        # pozitifin iki kati; oranin kendisi VERININ orani ve degistirilmiyor:
        # hasat edilen kirpmalarin %38'inde okunur plaka var, model o
        # dagilimda calisacak.
        sira = ([("p", j) for j in range(len(onbellek))]
                + [("n", j) for j in range(len(n_onbellek))])
        rng.shuffle(sira)
        toplam = adim = 0
        for i in range(0, len(sira) - 1, args.yigin):
            X, Y, M, E = [], [], [], []
            for tur, j in sira[i:i + args.yigin]:
                if tur == "p":
                    im, k = artir(onbellek[j][0], onbellek[j][1], rng)
                    Y.append(k / [GENISLIK, YUKSEKLIK])
                    M.append(1.0)
                    E.append(1.0)
                else:
                    im, _ = artir(n_onbellek[j],
                                  np.zeros((4, 2), np.float32), rng)
                    Y.append(np.zeros((4, 2), np.float32))
                    M.append(0.0)      # kose kaybi maskeleniyor
                    E.append(0.0)
                X.append(girdiye(im))
            x = torch.from_numpy(np.stack(X)).to(cihaz)
            y = torch.from_numpy(np.stack(Y).astype(np.float32)).to(cihaz)
            m = torch.tensor(M, dtype=torch.float32, device=cihaz)
            e = torch.tensor(E, dtype=torch.float32, device=cihaz)

            kose_t, logit = model(x)
            # Kose kaybi YALNIZCA pozitiflerde: negatifin kose hedefi yok.
            kose_kayip = ((kose_t - y).abs().mean(dim=(1, 2)) * m).sum() \
                / m.sum().clamp(min=1)
            varlik_kayip = nn.functional.binary_cross_entropy_with_logits(
                logit, e)
            kayip = kose_kayip + varlik_kayip
            opt.zero_grad(set_to_none=True)
            kayip.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 5.0)
            opt.step()
            plan.step()
            toplam += kayip.item()
            adim += 1

        if epoch % 5 == 0 or epoch == args.epoch:
            o = degerlendir(model, secim, cihaz)
            v = varlik_olc(model, secim, n_secim, cihaz)
            o = {**o, **{f"varlik_{k}": val for k, val in v.items()}}
            gecmis.append({"epoch": epoch, "kayip": toplam / max(1, adim), **o})
            print(f"epoch {epoch:>4}  kayip {toplam/max(1,adim):>7.4f}  "
                  f"ortanca {o['oran_ortanca']:>6.3f}  "
                  f">%5 {o['kotu_005']:>5.3f}  "
                  f"varlik AUC {v['auc']:>5.3f}  "
                  f"sizinti {v['negatif_sizinti']:>5.3f}  "
                  f"{(time.perf_counter()-basladi)/60:>5.1f} dk", flush=True)
            durum = {"model": model.state_dict(), "girdi": [YUKSEKLIK, GENISLIK],
                     "epoch": epoch, **o}
            torch.save(durum, args.out / "son.pt")
            # Secim olcutu ORTALAMA DEGIL. Ortalama birkac felaket vakadan
            # sisiyor ve epoch'lar arasinda ziplayarak yanlis agirligi
            # seciyor: ilk kosuda ortalamaya gore epoch 50 secildi, oysa
            # epoch 150 ortancada 0.022'ye karsi 0.030 ve %5 ustu oranda
            # 0.136'ya karsi 0.205 ile belirgin daha iyiydi. Aradaki fark
            # uctan uca bir plaka.
            #
            # Dogru olcut asagi akistan geliyor: okuma dogrulugu tam 0.05'te
            # cokuyor (0.03-0.05 bandinda 0.696, 0.05-0.10 bandinda 0.400).
            # Yani onemli olan ortalama hata degil, esigi ASAN kirpmalarin
            # orani. Esitlikte ortanca ayiriyor.
            aday = (o["kotu_005"], o["oran_ortanca"])
            if aday < en_iyi:
                en_iyi = aday
                torch.save(durum, args.out / "best.pt")

    (args.out / "gecmis.json").write_text(
        json.dumps(gecmis, indent=2, ensure_ascii=False), encoding="utf-8")

    model.load_state_dict(torch.load(args.out / "best.pt", map_location=cihaz,
                                     weights_only=False)["model"])
    r = degerlendir(model, rapor, cihaz)
    rv = varlik_olc(model, rapor, n_rapor, cihaz)
    print("\n" + "=" * 66)
    print(f"RAPOR KUMESI - hicbir karara girmedi ({r['n']} kirpma)")
    print("=" * 66)
    print(f"  ortanca kose hatasi    {r['oran_ortanca']:.3f}  "
          f"(plaka genisliginin orani)")
    print(f"  ortalama               {r['oran']:.3f}  "
          f"(birkac felaket vakadan siser, secimde kullanilmiyor)")
    print(f"  piksel cinsinden       {r['piksel']:.2f} px")
    print(f"  hatasi %5'i asan       {r['kotu_005']:.3f}")
    print(f"\n  Karsilastirma: uretec taniyiciyi KOSE_HATASI = 0.05 ile")
    print(f"  egitti. Bu esigin altindaki hata taniyicinin gordugu")
    print(f"  bozulma araliginda kaliyor; ustundeki gormedigi bolge.")
    print(f"\n  VARLIK BASLIGI (okunur plaka var mi)")
    print(f"    AUC                    {rv['auc']:.3f}   "
          f"[0.5 = bilgi yok]")
    print(f"    pozitiflerin %95'ini tutan esikte gecen negatif: "
          f"{rv['negatif_sizinti']:.3f}")
    print(f"    ({rv['n']} kirpma: {len(rapor)} pozitif, {len(n_rapor)} negatif)")
    print(f"\n  Asil sayi bu degil: python scripts/end_to_end.py")
    print(f"\nagirlik -> {args.out / 'best.pt'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
