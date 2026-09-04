"""Plaka kirpmalarini etiketler: dort kose + metin.

trafikisaret'in etiketleme aracindan devralindi ama iki temel farki var:

1. **Kutu degil dort kose.** Plaka egik duruyor ve tanima modeline dik bir
   goruntu vermek gerekiyor; dort kose homografi icin yeterli veriyi tasiyor,
   eksenlere hizali bir kutu tasimiyor.
2. **Metin var.** Yani harf ve rakam tuslari ETIKET ICERIGI, komut degil.

Ikinci fark tuz haritasini yeniden dusunmeyi gerektirdi. trafikisaret'te tus
haritasi uc kez bozuldu ve hepsinin kaynagi ayniydi: sinif tuslariyla komut
tuslari ayni uzayi paylasiyordu. Burada catisma kacinilmaz - plakada A'dan
Z'ye her harf ve her rakam gecebiliyor, yani serbest birakilacak komut tusu
kalmiyor.

Cozum KIP (modal) olmak: kose isaretleme kipinde tuslar komut, metin kipinde
tuslar metin. Iki kip arasinda gecis tek tus (Enter) ve durum cubugunda hangi
kipte oldugun yaziyor. Boylece "hangi tus neye gidiyor" sorusu hic dogmuyor.

Bulaniklik OLCULUYOR, sorulmuyor
--------------------------------
Kapsam belgesi keskin ve bulanik plakalarda dogrulugu ayri raporlamayi
soz veriyor. Bunu insana sormak yerine Laplacian varyansi ile olcuyoruz:
nesnel, tekrarlanabilir ve etiketleyene sifir maliyet. Insanin "bu bulanik mi"
kararindaki tutarsizlik da olcume karismiyor.

Cikti: data/labels.jsonl - satir basina bir kirpma.

    {"dosya": "maltepe_00004_2.jpg", "kose": [[x,y],...], "metin": "34AEM481",
     "keskinlik": 118.4, "durum": "ok"}

`durum` alani su degerleri alabilir:

    ok          tek satirli plaka, kose ve metin girildi
    plakasiz    hasatci vurdu ama kirpmada plaka yok
    okunmaz     plaka var ama karakterler secilemiyor
    iki_satirli motosiklet/kare plaka - KAYDEDILIR AMA BU MODELE GIRMEZ

Son ucu de veri: ilk ikisi hasatcinin isabet oranini veriyor, ucuncusu ise
kapsam disi biraktigimiz bir plaka ailesinin ne siklikta gectigini.

Neden iki satirli ayri tutuluyor
--------------------------------
Plan yalnizca tek satirli 520x110 formatini modelliyor: sentetik uretec tek
satir uretiyor, tanima modeli 32x128 gibi yatay bir seride CTC calistiriyor ve
4.7:1 en-boy orani bu varsayima dayaniyor. Motosiklet plakasi iki satir
("34 HNU" ustte, "227" altta) ve ayni tanima kafasina verilirse cop cikar -
model iki satiri yan yana okumaya calisir.

Silmek yerine isaretlemek daha dogru: veri elde kaliyor, kapsam disi oldugu
kayitli, ve ileride iki satirli icin ayri bir kafa egitilmek istenirse ornekler
hazir. Kapsami daraltmak ile veriyi atmak ayni sey degil.

Kullanim:
    python scripts/label_plates.py
    python scripts/label_plates.py --start 200
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent.parent

PENCERE = "plaka etiketleme"

#: Kirpma ekranda bu genislige buyutulur. Karakterlerin okunabilmesi sart.
GORUNTU_GENISLIGI = 1100

#: Turk plakasinda Q, W, X yok ve Turkce'ye ozgu harfler de yok.
#: Alfabeyi burada kisitlamak, etiketleme sirasinda yanlis harf girilmesini
#: engelliyor - ve ayni kisit sonra cozumleyiciye de gidecek.
ALFABE = "ABCDEFGHIJKLMNOPRSTUVYZ0123456789"

KOSE_ADLARI = ["sol ust", "sag ust", "sag alt", "sol alt"]


def keskinlik(gri: np.ndarray) -> float:
    """Laplacian varyansi - yuksek deger keskin, dusuk bulanik.

    Mutlak degeri tek basina anlamli degil (sahneye ve kontrasta bagli), ama
    ayni kaynaktan gelen kirpmalar arasinda siralamak icin yeterli. Kapsam
    belgesindeki "keskin vs bulanik" kesiti bu sayiyla ayrilacak; esik
    dagilima bakilarak sonra secilecek, simdi tahmin edilmeyecek.
    """
    return float(cv2.Laplacian(gri, cv2.CV_64F).var())


class PlakaEtiketleyici:
    def __init__(self, images: list[Path], out: Path, start: int = 0) -> None:
        self.images = images
        self.out = out
        self.index = max(0, min(start, len(images) - 1))
        self.kayitlar: dict[str, dict] = {}
        if out.is_file():
            for satir in out.read_text(encoding="utf-8").splitlines():
                if satir.strip():
                    kayit = json.loads(satir)
                    self.kayitlar[kayit["dosya"]] = kayit
        self.frame: np.ndarray | None = None
        self.olcek = 1.0
        self.koseler: list[tuple[int, int]] = []
        self.metin = ""
        self.metin_kipi = False
        self._yukle()

    # ---------- dosya ----------

    @property
    def ad(self) -> str:
        return self.images[self.index].name

    def _yukle(self) -> None:
        self.frame = cv2.imread(str(self.images[self.index]))
        self.koseler = []
        self.metin = ""
        self.metin_kipi = False
        if self.frame is None:
            return
        self.olcek = GORUNTU_GENISLIGI / self.frame.shape[1]

        # Onceki etiket varsa geri yukle - duzeltmek icin.
        onceki = self.kayitlar.get(self.ad)
        if onceki and onceki.get("durum") == "ok":
            self.koseler = [tuple(k) for k in onceki["kose"]]
            self.metin = onceki["metin"]

    def kaydet(self, durum: str) -> None:
        if self.frame is None:
            return
        gri = cv2.cvtColor(self.frame, cv2.COLOR_BGR2GRAY)
        kayit = {
            "dosya": self.ad,
            "durum": durum,
            "kose": [list(k) for k in self.koseler] if durum == "ok" else [],
            "metin": self.metin if durum == "ok" else "",
            "keskinlik": round(keskinlik(gri), 1),
        }
        self.kayitlar[self.ad] = kayit
        # Butun kayitlari yeniden yaz: duzeltme yapildiginda eski satirin
        # dosyada kalmamasi gerekiyor. Dosya kucuk, maliyeti onemsiz.
        self.out.write_text(
            "\n".join(json.dumps(k, ensure_ascii=False)
                      for k in self.kayitlar.values()) + "\n",
            encoding="utf-8",
        )

    # ---------- goruntu ----------

    def ciz(self) -> np.ndarray:
        view = cv2.resize(
            self.frame,
            (GORUNTU_GENISLIGI, int(self.frame.shape[0] * self.olcek)),
            interpolation=cv2.INTER_CUBIC,
        )
        for i, (x, y) in enumerate(self.koseler):
            p = (int(x * self.olcek), int(y * self.olcek))
            cv2.circle(view, p, 5, (60, 220, 60), -1)
            cv2.putText(view, str(i + 1), (p[0] + 8, p[1] - 8),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (60, 220, 60), 2, cv2.LINE_AA)
        if len(self.koseler) == 4:
            pts = np.array([[int(x * self.olcek), int(y * self.olcek)]
                            for x, y in self.koseler], np.int32)
            cv2.polylines(view, [pts], True, (60, 220, 60), 2)
        return np.vstack([view, self._durum_cubugu(view.shape[1])])

    def _durum_cubugu(self, genislik: int) -> np.ndarray:
        bar = np.zeros((104, genislik, 3), np.uint8)
        islenen = len(self.kayitlar)
        kip = "METIN" if self.metin_kipi else "KOSE"
        renk = (0, 215, 255) if self.metin_kipi else (60, 220, 60)

        cv2.putText(bar, f"[{kip} KIPI]", (10, 26),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, renk, 2, cv2.LINE_AA)
        cv2.putText(bar, f"{self.metin or '...'}", (200, 28),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.9, (235, 235, 235), 2, cv2.LINE_AA)
        cv2.putText(
            bar,
            f"{self.index + 1}/{len(self.images)}   islenen {islenen}   "
            f"kose {len(self.koseler)}/4   {self.ad}",
            (10, 56), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1, cv2.LINE_AA)

        if self.metin_kipi:
            yardim = ("harf/rakam yaz   BACKSPACE sil   ENTER kaydet+ilerle   "
                      "ESC kose kipine don")
        else:
            yardim = ("sol tik: 4 koseyi sirayla (sol ust -> saat yonu)   "
                      "z geri al   ENTER metin kipi   x plakasiz   "
                      "u okunmaz   i iki satirli   n/p kare   q cik")
        cv2.putText(bar, yardim, (10, 82), cv2.FONT_HERSHEY_SIMPLEX,
                    0.45, (140, 140, 150), 1, cv2.LINE_AA)

        if not self.metin_kipi and len(self.koseler) < 4:
            cv2.putText(bar, f"sirada: {KOSE_ADLARI[len(self.koseler)]}",
                        (genislik - 260, 26), cv2.FONT_HERSHEY_SIMPLEX,
                        0.7, (0, 215, 255), 2, cv2.LINE_AA)
        return bar

    # ---------- girdi ----------

    def fare(self, event: int, x: int, y: int, flags: int, param) -> None:
        if self.metin_kipi or event != cv2.EVENT_LBUTTONDOWN:
            return
        if len(self.koseler) >= 4:
            return
        self.koseler.append((int(x / self.olcek), int(y / self.olcek)))

    def _ilerle(self, delta: int) -> None:
        self.index = max(0, min(self.index + delta, len(self.images) - 1))
        self._yukle()

    def tus(self, key: int) -> bool:
        """Tek tus islemi. True donerse dongu biter."""
        char = chr(key) if 32 <= key < 127 else ""

        if self.metin_kipi:
            if key in (13, 10):                       # Enter: kaydet, ilerle
                if self.metin:
                    self.kaydet("ok")
                    self._ilerle(1)
                return False
            if key == 27:                             # Esc: kose kipine don
                self.metin_kipi = False
                return False
            if key == 8:                              # Backspace
                self.metin = self.metin[:-1]
                return False
            # Alfabe kisitli: Q, W, X ve Turkce harfler plakada yok.
            buyuk = char.upper()
            if buyuk in ALFABE:
                self.metin += buyuk
            return False

        # --- kose kipi ---
        if char == "q":
            return True
        if key in (13, 10):
            if len(self.koseler) == 4:
                self.metin_kipi = True
            return False
        if char == "z" and self.koseler:
            self.koseler.pop()
        elif char == "x":
            self.kaydet("plakasiz")
            self._ilerle(1)
        elif char == "u":
            self.kaydet("okunmaz")
            self._ilerle(1)
        elif char == "i":
            # Iki satirli (motosiklet/kare) plaka: kayda gecer, bu modelin
            # egitim kumesine girmez.
            self.kaydet("iki_satirli")
            self._ilerle(1)
        elif char == "n":
            self._ilerle(1)
        elif char == "p":
            self._ilerle(-1)
        return False

    def calistir(self) -> None:
        cv2.namedWindow(PENCERE, cv2.WINDOW_AUTOSIZE)
        cv2.setMouseCallback(PENCERE, self.fare)
        while True:
            if self.frame is None:
                self._ilerle(1)
                continue
            cv2.imshow(PENCERE, self.ciz())
            key = cv2.waitKeyEx(20)
            if key in (-1, 255):
                continue
            if self.tus(key):
                break
        cv2.destroyAllWindows()
        self.rapor()

    def rapor(self) -> None:
        durumlar: dict[str, int] = {}
        for k in self.kayitlar.values():
            durumlar[k["durum"]] = durumlar.get(k["durum"], 0) + 1
        toplam = sum(durumlar.values())
        print(f"\n{toplam}/{len(self.images)} kirpma islendi")
        for d, n in sorted(durumlar.items(), key=lambda kv: -kv[1]):
            print(f"  {d:<10}{n:>5}  (%{100*n/toplam:.0f})")
        if durumlar.get("ok"):
            print(f"\nHasatci isabet orani: %{100*durumlar['ok']/toplam:.0f}")
            print("(plakasiz + okunmaz oranlari hasatci filtresinin ne kadar")
            print(" ise yaradigini soyleyen sayilar - onlar da veri.)")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--crops", type=Path, default=ROOT / "data" / "crops")
    parser.add_argument("--out", type=Path, default=ROOT / "data" / "labels.jsonl")
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--yeni", action="store_true",
                        help="Yalnizca hic islenmemis kirpmalari gez")
    args = parser.parse_args(argv)

    images = sorted(args.crops.glob("*.jpg"))
    if not images:
        raise SystemExit(f"Kirpma bulunamadi: {args.crops}\n"
                         f"Once: python scripts/harvest_plates.py <video>")

    islenmis: set[str] = set()
    if args.out.is_file():
        for satir in args.out.read_text(encoding="utf-8").splitlines():
            if satir.strip():
                islenmis.add(json.loads(satir)["dosya"])
    if args.yeni:
        images = [p for p in images if p.name not in islenmis]
        if not images:
            raise SystemExit("Islenmemis kirpma kalmadi.")

    print(f"{len(images)} kirpma, {len(islenmis)} tanesi zaten etiketli\n")
    print("  KOSE KIPI")
    print("    sol tik x4  : sol ust -> sag ust -> sag alt -> sol alt")
    print("    z           : son koseyi geri al")
    print("    ENTER       : 4 kose tamamsa metin kipine gec")
    print("    x           : bu kirpmada plaka yok")
    print("    u           : plaka var ama okunmuyor")
    print("    i           : iki satirli plaka (motosiklet) - kapsam disi")
    print("    n / p       : sonraki / onceki")
    print("    q           : cik")
    print("  METIN KIPI")
    print("    harf/rakam  : plakayi yaz (Q, W, X yok - plakada kullanilmiyor)")
    print("    BACKSPACE   : sil")
    print("    ENTER       : kaydet ve ilerle")
    print("    ESC         : kose kipine don\n")

    PlakaEtiketleyici(images, args.out, args.start).calistir()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
