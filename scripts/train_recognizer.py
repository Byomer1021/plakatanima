"""Faz 2: CTC ile plaka tanima modeli.

Bulutta calisacak (Kaggle / Colab / kiralik GPU). Yerel GTX 1080 agir yuk
altinda DORT kez dustu ve 100k ornek CPU'da haftalar surerdi.

Cihaz varsayilani CPU - "varsa cuda" DEGIL
------------------------------------------
Bu betigin ilk surumu `cuda if torch.cuda.is_available() else cpu` diyordu ve
duman testinde makineyi resetletti: CUDA error, ardindan sistem cokusu. Bu
dorduncu dususSu ve onceki projede dedektor tam bu yuzden CPU varsayilanina
cekilmisti - sonra ayni tuzaga yeniden dusuldu.

"Varsa kullan" saglikli bir GPU icin dogru varsayilan. Bu makinede degil:
burada GPU'nun varligi kullanilabilirligi anlamina gelmiyor. Varsayilan CPU,
GPU acikca istenirse `--cihaz cuda`. Bulut kutusunda `--cihaz cuda` verilecek
ve orada dogru davranis bu.

ALTIN KURAL: dogrulama YALNIZCA gercek veride
----------------------------------------------
Sentetik veride olculen dogruluk hicbir sey ifade etmez - kendi urettigin
dagilimda kendi modelini test etmis olursun. Bu betik sentetik veriyi yalnizca
egitimde kullanir; her epoch sonunda olculen sayi gercek plakalardan gelir.

Bu kural onceki projede ogrenildi: orada bolme sizintisi yuzunden model
dogrulama karesini egitimde gormustu ve bildirilen mAP anlamsizdi. Hicbir hata
mesaji cikmamisti.

Mimari: tam konvolusyonel, tekrarlayan katman YOK
-------------------------------------------------
Klasik CRNN (CNN + BiLSTM + CTC) biraz daha dogru ama LSTM nicemlemede
sorunlu. Faz 4'te INT8'e gecilecek ve orada tekrarlayan katmanlarla bogusmak
istenmiyor. Tam konvolusyonel govde + CTC basligi seciliyor; karsilastirma
icin bir kez CRNN egitip INT8'de nasil bozuldugunu olcmek ogretici olur ama
varsayilan bu degil.

Girdi 32x128: yukseklik 32 olunca govde genisligi 32 zaman adimina indiriyor
ve en uzun plaka 9 karakter. CTC'nin tekrarlanan karakterleri ayirmak icin
araya blank sokmasi gerektiginden zaman adimi karakter sayisinin en az iki
katı olmali; 32 >> 18, rahat.

Iki veri kaynagi: klasor ya da paket
------------------------------------
Yerelde JPEG klasorlerinden okunuyor. Bulutta ise `--paket` ile onceden
paketlenmis dizilerden: 100k dosya acmak yerine tek dosya. Egitim zaten her
goruntuyu 32x128 gri tonlamaya indirdigi icin donusum bir kez paketleme
sirasinda yapiliyor ve her epoch'ta tekrarlanmiyor.

Kullanim:
    python scripts/train_recognizer.py --epoch 20
    python scripts/train_recognizer.py --paket paket --cihaz cuda --epoch 20
"""

from __future__ import annotations

import argparse
import json
import random
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent

#: 23 harf + 10 rakam. Blank CTC icin 0 indeksinde, alfabe 1'den basliyor.
ALFABE = "ABCDEFGHIJKLMNOPRSTUVYZ0123456789"
BLANK = 0
SINIF_SAYISI = len(ALFABE) + 1

GENISLIK, YUKSEKLIK = 128, 32


def kodla(metin: str) -> list[int]:
    return [ALFABE.index(c) + 1 for c in metin if c in ALFABE]


def coz_greedy(logits: np.ndarray) -> str:
    """CTC greedy cozumleme: tekrarlari birlestir, blank'leri at."""
    yol = logits.argmax(axis=-1)
    cikti, onceki = [], -1
    for k in yol:
        if k != onceki and k != BLANK:
            cikti.append(ALFABE[k - 1])
        onceki = k
    return "".join(cikti)


def duzenleme_mesafesi(a: str, b: str) -> int:
    if len(a) < len(b):
        a, b = b, a
    onceki = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        simdi = [i]
        for j, cb in enumerate(b, 1):
            simdi.append(min(onceki[j] + 1, simdi[j - 1] + 1,
                             onceki[j - 1] + (ca != cb)))
        onceki = simdi
    return onceki[-1]


# --------------------------------------------------------------------------
# Veri
# --------------------------------------------------------------------------

def sentetik_liste(kok: Path) -> list[tuple[Path, str]]:
    """Sentetik ornekler ZORLUK SIRASINDA doner - mufredat icin.

    generate_plates.py dosyalari sirali uretiyor (00000000, 00000001, ...) ve
    o sira zorluk sirasi. Karistirmak mufredati iptal eder.
    """
    tsv = kok.parent / "synth.tsv"
    if tsv.is_file():
        satirlar = [l.split("\t") for l in
                    tsv.read_text(encoding="utf-8").splitlines() if l.strip()]
        return [(kok / s[0], s[1]) for s in satirlar if (kok / s[0]).is_file()]
    return [(p, p.stem.split("_", 1)[1]) for p in sorted(kok.glob("*.jpg"))]


def gercek_liste(kok: Path) -> list[tuple[Path, str, str]]:
    """(yol, metin, plaka_kimligi) - kimlik bolme icin."""
    manifest = kok.parent / "plates.jsonl"
    if not manifest.is_file():
        raise SystemExit(f"plates.jsonl yok: once scripts/export_plates.py")
    out = []
    for satir in manifest.read_text(encoding="utf-8").splitlines():
        if not satir.strip():
            continue
        k = json.loads(satir)
        yol = kok / k["dosya"]
        if yol.is_file():
            out.append((yol, k["metin"], k["metin"]))
    return out


def gercek_bol(kayitlar, val_oran=0.25, seed=0):
    """PLAKAYA gore boler, kirpmaya gore degil.

    Ayni plaka onlarca kirpmada geciyor (en cok tekrarlanan 82 kez). Kirpmaya
    gore bolunurse ayni plaka hem egitimde hem dogrulamada olur, model onu
    ezberler ve dogruluk sisir. Onceki projede tam olarak bu oldu ve
    bildirilen sayi anlamsizdi.
    """
    plakalar = sorted({k[2] for k in kayitlar})
    random.Random(seed).shuffle(plakalar)
    kesim = int(len(plakalar) * (1 - val_oran))
    egitim_p = set(plakalar[:kesim])
    egitim = [k for k in kayitlar if k[2] in egitim_p]
    dogrulama = [k for k in kayitlar if k[2] not in egitim_p]
    return egitim, dogrulama


def paketi_ac(kok: Path):
    """Paketlenmis dizileri (sentetik, gercek) olarak dondurur.

    Sentetik dizinin sirasi ZORLUK sirasi ve korunuyor; gercek tarafta her
    ornegin plaka metni var, bolme ona gore yapilacak.
    """
    sentetik = np.load(kok / "sentetik.npz", allow_pickle=True)
    gercek = np.load(kok / "gercek.npz", allow_pickle=True)
    sx, sy = sentetik["x"], [str(v) for v in sentetik["y"]]
    gx, gy = gercek["x"], [str(v) for v in gercek["y"]]
    if sx.shape[1:] != (YUKSEKLIK, GENISLIK):
        raise SystemExit(
            f"Paket {sx.shape[1]}x{sx.shape[2]} boyutunda ama model "
            f"{YUKSEKLIK}x{GENISLIK} bekliyor. Paketi yeniden uretin: "
            f"python scripts/paketle.py --yukseklik {YUKSEKLIK} "
            f"--genislik {GENISLIK}"
        )
    return (sx, sy), (gx, gy)


def diziden(x: np.ndarray) -> np.ndarray:
    """Paketten gelen uint8 goruntuyu modelin bekledigi bicime cevirir."""
    return (x.astype(np.float32) / 127.5 - 1.0)[None]


def yukle(yol: Path):
    import cv2
    im = cv2.imread(str(yol), cv2.IMREAD_GRAYSCALE)
    if im is None:
        return None
    im = cv2.resize(im, (GENISLIK, YUKSEKLIK), interpolation=cv2.INTER_AREA)
    return (im.astype(np.float32) / 127.5 - 1.0)[None]   # (1, H, W)


# --------------------------------------------------------------------------
# Model
# --------------------------------------------------------------------------

def model_kur():
    import torch.nn as nn

    def blok(gir, cik, havuz):
        return nn.Sequential(
            nn.Conv2d(gir, cik, 3, padding=1, bias=False),
            nn.BatchNorm2d(cik), nn.ReLU(inplace=True),
            nn.Conv2d(cik, cik, 3, padding=1, bias=False),
            nn.BatchNorm2d(cik), nn.ReLU(inplace=True),
            nn.MaxPool2d(havuz),
        )

    class Taniyici(nn.Module):
        """Tam konvolusyonel; yukseklik 1'e iner, genislik zaman ekseni olur."""

        def __init__(self):
            super().__init__()
            self.govde = nn.Sequential(
                blok(1, 32, (2, 2)),      # 32x128 -> 16x64
                blok(32, 64, (2, 2)),     # -> 8x32
                blok(64, 128, (2, 1)),    # -> 4x32   genislik korunuyor
                blok(128, 192, (2, 1)),   # -> 2x32
            )
            self.baslik = nn.Sequential(
                nn.Conv2d(192, 192, (2, 3), padding=(0, 1), bias=False),
                nn.BatchNorm2d(192), nn.ReLU(inplace=True),
                nn.Conv2d(192, SINIF_SAYISI, 1),
            )

        def forward(self, x):
            x = self.baslik(self.govde(x))        # (B, C, 1, T)
            return x.squeeze(2).permute(2, 0, 1)  # (T, B, C) - CTC bekliyor

    return Taniyici()


# --------------------------------------------------------------------------
# Degerlendirme
# --------------------------------------------------------------------------

def degerlendir(model, kayitlar, cihaz, yigin=64) -> dict:
    import torch
    model.eval()
    dogru = toplam = karakter_dogru = karakter_toplam = 0
    mesafeler = []
    with torch.no_grad():
        for i in range(0, len(kayitlar), yigin):
            parca = kayitlar[i:i + yigin]
            X, hedefler = [], []
            for kayit in parca:
                im = (diziden(kayit[0]) if isinstance(kayit[0], np.ndarray)
                      else yukle(kayit[0]))
                if im is None:
                    continue
                X.append(im)
                hedefler.append(kayit[1])
            if not X:
                continue
            x = torch.from_numpy(np.stack(X)).to(cihaz)
            logits = model(x).permute(1, 0, 2).cpu().numpy()  # (B, T, C)
            for L, hedef in zip(logits, hedefler):
                tahmin = coz_greedy(L)
                toplam += 1
                dogru += tahmin == hedef
                d = duzenleme_mesafesi(tahmin, hedef)
                mesafeler.append(d)
                karakter_toplam += len(hedef)
                karakter_dogru += max(0, len(hedef) - d)
    return {
        "tam_dizi": dogru / max(1, toplam),
        "karakter": karakter_dogru / max(1, karakter_toplam),
        "duzenleme": sum(mesafeler) / max(1, len(mesafeler)),
        "n": toplam,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--synth", type=Path, default=ROOT / "data" / "synth")
    parser.add_argument("--real", type=Path, default=ROOT / "data" / "plates")
    parser.add_argument("--epoch", type=int, default=20)
    parser.add_argument("--yigin", type=int, default=128)
    parser.add_argument("--lr", type=float, default=3e-4)
    parser.add_argument(
        "--cihaz", default="cpu",
        help="Varsayilan cpu: bu makinedeki GPU dort kez dustu. "
             "Bulut kutusunda --cihaz cuda verin.")
    parser.add_argument("--out", type=Path, default=ROOT / "runs" / "taniyici")
    parser.add_argument("--paket", type=Path, default=None,
                        help="Paketlenmis diziler (scripts/paketle.py ciktisi); "
                             "verilirse --synth/--real yok sayilir")
    parser.add_argument("--limit", type=int, default=None,
                        help="Sentetikten yalnizca ilk N ornek (deneme icin)")
    args = parser.parse_args(argv)

    import torch
    import torch.nn as nn

    cihaz = args.cihaz
    if cihaz.startswith("cuda") and not torch.cuda.is_available():
        raise SystemExit("--cihaz cuda verildi ama CUDA yok.")
    print(f"cihaz: {cihaz}")
    if cihaz == "cpu":
        print("(GPU icin acikca --cihaz cuda verin; bu makinede otomatik "
              "secilmiyor, sebebi modul aciklamasinda)")

    if args.paket:
        (sx, sy), (gx, gy) = paketi_ac(args.paket)
        sentetik = list(zip(sx, sy))
        gercek = [(gx[i], gy[i], gy[i]) for i in range(len(gy))]
        print(f"paket: {args.paket}")
    else:
        sentetik = sentetik_liste(args.synth)
        gercek = gercek_liste(args.real)
    if args.limit:
        sentetik = sentetik[:args.limit]
    if not sentetik:
        raise SystemExit("Sentetik ornek yok.")

    g_egitim, g_dogrulama = gercek_bol(gercek)
    print(f"{len(sentetik)} sentetik (zorluk sirali)")
    print(f"{len(gercek)} gercek kirpma, "
          f"{len({k[2] for k in gercek})} farkli plaka")
    print(f"  egitim  {len(g_egitim):>4} kirpma / "
          f"{len({k[2] for k in g_egitim})} plaka")
    print(f"  DOGRULAMA {len(g_dogrulama):>4} kirpma / "
          f"{len({k[2] for k in g_dogrulama})} plaka  <- olcum burada")
    print("\nDogrulama YALNIZCA gercek veride. Sentetikte olculen dogruluk")
    print("kendi urettigin dagilimda kendini test etmektir.\n")

    model = model_kur().to(cihaz)
    ctc = nn.CTCLoss(blank=BLANK, zero_infinity=True)
    opt = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=1e-4)
    plan = torch.optim.lr_scheduler.OneCycleLR(
        opt, max_lr=args.lr * 3,
        total_steps=args.epoch * max(1, len(sentetik) // args.yigin))

    args.out.mkdir(parents=True, exist_ok=True)
    gecmis = []
    en_iyi = -1.0

    for epoch in range(1, args.epoch + 1):
        model.train()
        basladi = time.perf_counter()
        toplam_kayip = adim = 0

        # Mufredat: sentetik sirali okunuyor, KARISTIRILMIYOR.
        for i in range(0, len(sentetik) - args.yigin + 1, args.yigin):
            parca = sentetik[i:i + args.yigin]
            X, hedef, uzunluk = [], [], []
            for yol, metin in parca:
                im = (diziden(yol) if isinstance(yol, np.ndarray) else yukle(yol))
                if im is None:
                    continue
                kod = kodla(metin)
                if not kod:
                    continue
                X.append(im)
                hedef.extend(kod)
                uzunluk.append(len(kod))
            if len(X) < 2:
                continue

            x = torch.from_numpy(np.stack(X)).to(cihaz)
            logits = model(x)                       # (T, B, C)
            logp = logits.log_softmax(2)
            girdi_uz = torch.full((len(X),), logits.shape[0],
                                  dtype=torch.long, device=cihaz)
            kayip = ctc(logp,
                        torch.tensor(hedef, dtype=torch.long, device=cihaz),
                        girdi_uz,
                        torch.tensor(uzunluk, dtype=torch.long, device=cihaz))
            opt.zero_grad(set_to_none=True)
            kayip.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 5.0)
            opt.step()
            plan.step()
            # detach: gradyan tasiyan tensoru dogrudan float()'a
            # cevirmek torch uyarisi uretiyor ve grafigi gereksiz
            # yere canli tutuyor. Burada sadece sayi lazim.
            toplam_kayip += kayip.detach().item()
            adim += 1

        olcum = degerlendir(model, g_dogrulama, cihaz)
        gecmis.append({"epoch": epoch, "kayip": toplam_kayip / max(1, adim),
                       **olcum})
        print(f"epoch {epoch:>3}  kayip {toplam_kayip/max(1,adim):>7.3f}  "
              f"tam dizi {olcum['tam_dizi']:>6.3f}  "
              f"karakter {olcum['karakter']:>6.3f}  "
              f"duzenleme {olcum['duzenleme']:>5.2f}  "
              f"{(time.perf_counter()-basladi)/60:>5.1f} dk", flush=True)

        if olcum["tam_dizi"] > en_iyi:
            en_iyi = olcum["tam_dizi"]
            torch.save({"model": model.state_dict(), "alfabe": ALFABE,
                        "girdi": [YUKSEKLIK, GENISLIK], "epoch": epoch,
                        "tam_dizi": en_iyi}, args.out / "best.pt")

    (args.out / "gecmis.json").write_text(
        json.dumps(gecmis, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nen iyi tam dizi dogrulugu: {en_iyi:.3f}")
    print(f"agirlik -> {args.out / 'best.pt'}")
    print(f"\nNot: dogrulama {len(g_dogrulama)} kirpma / "
          f"{len({k[2] for k in g_dogrulama})} plaka. Gercek payda plaka")
    print("sayisi; ayni plakanin birden fazla kirpmasi bagimsiz olcum degil.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
