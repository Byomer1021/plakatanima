r"""Etiketleme aracinin kip ve tus davranisi testi.

Onceki projede tus haritasi UC kez bozuldu ve hepsi ancak birileri
etiketlemeye oturup klavyeyi olu bulunca fark edildi. Kaynak her seferinde
ayniydi: etiket icerigi ile komutlar ayni tus uzayini paylasiyordu.

Burada catisma kacinilmaz - plakada A'dan Z'ye her harf ve her rakam gecebilir,
yani komuta ayirilacak tus kalmiyor. Cozum kip ayrimi, ve kip ayriminin
sessizce bozulmasi mumkun: metin kipinde 'n' tusu bir kare atlarsa insan
yazdigi plakayi kaybeder ve bunu ancak sonra fark eder.

Bu test tam o senaryoyu tutuyor.

Calistirmak icin:
    python tests\test_etiketleme.py
"""

from __future__ import annotations

import json
import shutil
import sys
import uuid
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.argv = ["label_plates.py"]

import label_plates as lp  # noqa: E402

ENTER, ESC, BACKSPACE = 13, 27, 8


def kur(tmp: Path, adet: int = 3):
    crops = tmp / "crops"
    crops.mkdir(parents=True)
    yollar = []
    for i in range(adet):
        p = crops / f"kirpma_{i:03d}.jpg"
        # Duz gri degil desenli: Laplacian varyansi sifir olmasin.
        im = np.full((120, 400, 3), 60, np.uint8)
        cv2.rectangle(im, (60, 40), (340, 90), (240, 240, 240), -1)
        cv2.putText(im, "34 AB 123", (75, 78), cv2.FONT_HERSHEY_SIMPLEX,
                    1.0, (10, 10, 10), 2)
        cv2.imwrite(str(p), im)
        yollar.append(p)
    return yollar, tmp / "labels.jsonl"


def main() -> int:
    hatalar: list[str] = []
    tmp = ROOT / ".test_tmp" / uuid.uuid4().hex[:10]
    tmp.mkdir(parents=True, exist_ok=True)

    try:
        yollar, out = kur(tmp)
        t = lp.PlakaEtiketleyici(yollar, out)

        # 1) Fare ile dort kose alinmali, besincisi yok sayilmali.
        for x, y in ((10, 10), (390, 10), (390, 110), (10, 110), (200, 60)):
            t.fare(cv2.EVENT_LBUTTONDOWN, int(x * t.olcek), int(y * t.olcek), 0, None)
        if len(t.koseler) != 4:
            hatalar.append(f"kose sayisi 4 olmali, {len(t.koseler)} oldu")

        # 2) Dort kose tamamken ENTER metin kipine gecirmeli.
        t.tus(ENTER)
        if not t.metin_kipi:
            hatalar.append("ENTER metin kipine gecirmedi")

        # 3) METIN KIPINDE 'n' KARE ATLAMAMALI - asil tuzak bu.
        onceki_index = t.index
        t.tus(ord("n"))
        if t.index != onceki_index:
            hatalar.append("metin kipinde 'n' kareyi atladi - yazilan metin kaybolur")
        if t.metin != "N":
            hatalar.append(f"metin kipinde 'n' metne yazilmadi: {t.metin!r}")

        # 4) 'x', 'u', 'z', 'q' metin kipinde KOMUT OLARAK CALISMAMALI.
        #    Ikisi metne gider, ikisi hicbir sey yapmaz - ama hicbiri kare
        #    atlamaz, kayit yapmaz, kose silmez. Olcut bu.
        #
        #    'u' ve 'z' alfabede oldugu icin metne yaziliyor; 'x' ve 'q' ise
        #    Turk plakasinda kullanilmadigi icin alfabede yok ve sessizce
        #    yutuluyor. Ikisi de dogru: komut olarak DAVRANMIYORLAR.
        t.metin = ""
        index_once, kose_once = t.index, len(t.koseler)
        for c in "xuzq":
            t.tus(ord(c))
        if t.metin != "UZ":
            hatalar.append(f"metin kipinde harfler metne gitmedi: {t.metin!r}")
        if t.index != index_once:
            hatalar.append("metin kipinde bir tus kareyi degistirdi")
        if len(t.koseler) != kose_once:
            hatalar.append("metin kipinde 'z' koseyi sildi - komut gibi davrandi")

        # 5) Q, W, X alfabede olmamali: Turk plakasinda bu harfler yok ve
        #    etiketleme sirasinda yanlislikla girilmeleri engellenmeli.
        t.metin = ""
        for c in "QWX":
            t.tus(ord(c))
        if t.metin:
            hatalar.append(f"Q/W/X kabul edildi: {t.metin!r} - plakada bu harfler yok")

        # 6) Backspace silmeli.
        t.metin = "34AB"
        t.tus(BACKSPACE)
        if t.metin != "34A":
            hatalar.append(f"backspace calismadi: {t.metin!r}")

        # 7) ESC kose kipine dondurmeli, metni korumali.
        t.tus(ESC)
        if t.metin_kipi:
            hatalar.append("ESC kose kipine dondurmedi")
        if t.metin != "34A":
            hatalar.append("ESC metni sildi")

        # 8) Kose kipinde 'q' cikis olmali (metin kipinde degildi).
        if not t.tus(ord("q")):
            hatalar.append("kose kipinde 'q' cikis vermedi")

        # 9) Kaydetme: metin, kose ve keskinlik diske yazilmali.
        t.metin_kipi = True
        t.metin = "34AEM481"
        t.tus(ENTER)
        satirlar = [json.loads(s) for s in out.read_text(encoding="utf-8").splitlines() if s.strip()]
        if len(satirlar) != 1:
            hatalar.append(f"bir kayit bekleniyordu, {len(satirlar)} yazildi")
        else:
            k = satirlar[0]
            if k["metin"] != "34AEM481":
                hatalar.append(f"metin yanlis kaydedildi: {k['metin']!r}")
            if len(k["kose"]) != 4:
                hatalar.append("koseler kaydedilmedi")
            if k["keskinlik"] <= 0:
                hatalar.append("keskinlik olculmedi")
            if k["durum"] != "ok":
                hatalar.append(f"durum yanlis: {k['durum']!r}")

        # 10) ENTER kaydettikten sonra bir sonraki kareye gecmeli.
        if t.index != 1:
            hatalar.append(f"kayittan sonra ilerlemedi: index {t.index}")

        # 11) 'x' ve 'u' plakasiz/okunmaz kaydetmeli, metin ve kose bos olmali.
        t.tus(ord("x"))
        t.tus(ord("u"))
        kayitlar = {k["dosya"]: k for k in
                    (json.loads(s) for s in out.read_text(encoding="utf-8").splitlines() if s.strip())}
        durumlar = sorted(k["durum"] for k in kayitlar.values())
        if durumlar != ["ok", "okunmaz", "plakasiz"]:
            hatalar.append(f"durumlar beklenenden farkli: {durumlar}")

        # 12) Yeniden acildiginda onceki etiket geri yuklenmeli (duzeltme icin).
        t2 = lp.PlakaEtiketleyici(yollar, out)
        if t2.metin != "34AEM481" or len(t2.koseler) != 4:
            hatalar.append("onceki etiket geri yuklenmedi - duzeltme yapilamaz")

        # 13) Duzeltme eski satiri birakmamali: dosyada mukerrer kayit olmamali.
        t2.metin_kipi = True
        t2.metin = "34XYZ99"   # X alfabede yok ama dogrudan atandi; kayit testi
        t2.tus(ENTER)
        adlar = [json.loads(s)["dosya"] for s in
                 out.read_text(encoding="utf-8").splitlines() if s.strip()]
        if len(adlar) != len(set(adlar)):
            hatalar.append("duzeltmeden sonra mukerrer kayit kaldi")

    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        kok = ROOT / ".test_tmp"
        if kok.is_dir() and not any(kok.iterdir()):
            kok.rmdir()

    if hatalar:
        print("BASARISIZ")
        for h in hatalar:
            print("  -", h)
        return 1
    print("hepsi gecti - kipler ayri, metin kipinde komut tusu yok, kayit tutarli")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
