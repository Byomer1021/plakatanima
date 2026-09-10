r"""Plaka dilbilgisi testi - eksik duzen bir kez gercekten olduysa bir daha olmasin.

DUZENLER listesinde (3, 3) YOKTU. 272 gercek plakanin 146'si, yani %54'u tam
olarak o duzende. Sonuclari:

  - Uretec bugune kadar tek bir 3harf-3rakam plaka uretmedi; sentetigin
    uzunluk dagilimi (%75 yedi karakterli) gercegin tersiydi (%87 sekiz).
  - Eksiklik bolum 11'de BELIRTI olarak goruldu ("etiket dagilimi farki"),
    sebebi bulunmadi.
  - Kisitli cozumleyici o dilbilgisiyle yazilsaydi gercek plakalarin
    %54'unu reddederdi - doguluk artmaz, coker.

Bu hata sessiz: uretec calisir, egitim calisir, sayilar cikar. Yalnizca
dagilim karsilastirilirsa gorulur. Test onu zorunlu kiliyor.

Ayrica C++ tarafindaki dilbilgisi ile buradaki DUZENLER'in ayni seyi
soylemesi gerekiyor; ikisi ayri dilde ve birbirinden habersiz sapabilir.
decode.exe derlenmisse o da sinaniyor.

Calistirmak icin:
    python tests\test_dilbilgisi.py
"""

from __future__ import annotations

import random
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from generate_plates import (DUZENLER, DUZEN_YEDEK, HARFLER,  # noqa: E402
                             gercek_duzenler, plaka_metni)

BICIM = re.compile(r"(\d{2})([A-Z]+)(\d+)")


def duzeni(p: str):
    m = BICIM.fullmatch(p)
    return None if m is None else (len(m.group(2)), len(m.group(3)))


def test_olculen_duzenler_listede():
    """Gercek veride gorulen her duzen uretecte de olmali.

    DUZEN_YEDEK gercek 272 plakadan olculdu. Bir duzen oradan cikip
    DUZENLER'e girmezse uretec o plakalari hic uretmez.
    """
    eksik = [d for d, _ in DUZEN_YEDEK if d not in DUZENLER]
    assert not eksik, f"olculen ama uretilmeyen duzen: {eksik}"
    assert (3, 3) in DUZENLER, "(3, 3) en yaygin gercek duzen; listeden dusmus"


def test_uretilen_metinler_gecerli():
    rng = random.Random(0)
    havuz = [d for d, n in DUZEN_YEDEK for _ in range(n)]
    for _ in range(3000):
        p = plaka_metni(rng, havuz)
        m = BICIM.fullmatch(p)
        assert m, f"bicime uymuyor: {p}"
        il = int(m.group(1))
        assert 1 <= il <= 81, f"il araligi disinda: {p}"
        assert all(c in HARFLER for c in m.group(2)), f"alfabe disi harf: {p}"
        assert (len(m.group(2)), len(m.group(3))) in DUZENLER, \
            f"listede olmayan duzen uretildi: {p}"


def test_alfabe_qwx_icermiyor():
    for c in "QWX":
        assert c not in HARFLER, f"{c} Turk plakasinda yok"


def test_uzunluk_dagilimi_gercege_yakin():
    """Sekiz karakterli plakalarin payi olculene yakin cikmali.

    Gercekte %87. Bu test sayinin kendisini degil, dagilimin CIDDI
    sekilde kaymadigini tutuyor - (3, 3) dustugu anda %13'e iner.
    """
    rng = random.Random(1)
    # Uretecin GERCEKTE kullandigi havuz; elle kurulan bir havuz DUZENLER'i
    # atlar ve testi hatanin gorunmedigi bir yoldan gecirir.
    c = Counter(len(plaka_metni(rng, gercek_duzenler())) for _ in range(5000))
    sekiz = c[8] / sum(c.values())
    assert 0.75 <= sekiz <= 0.95, \
        f"sekiz karakterli orani {sekiz:.2f}; gercekte 0.87 olculdu"


def test_cpp_dilbilgisi_ayni_seyi_soyluyor():
    """decode.exe derlenmisse, iki dildeki dilbilgisi ayni mi.

    C++ tarafi kendi dilbilgisini ayri yaziyor. Ikisi sapabilir ve sapma
    sessiz olur: cozumleyici gecerli bir plakayi reddeder, sebebi
    modelde aranir.
    """
    exe = ROOT / "cpp" / "decode.exe"
    if not exe.is_file():
        print("  (decode.exe yok, C++ dilbilgisi sinanmadi)")
        return

    import struct
    import tempfile

    import numpy as np

    # Her duzenden bir plaka uret, o plakayi KESIN okuyacak bir olasilik
    # matrisi kur, cozumleyicinin aynen geri vermesini bekle.
    alfabe = "ABCDEFGHIJKLMNOPRSTUVYZ0123456789"
    ornekler = []
    rng = random.Random(2)
    for d in DUZENLER:
        while True:
            p = plaka_metni(rng, [d])
            if duzeni(p) == d:
                break
        ornekler.append(p)

    T, C = 32, len(alfabe) + 1
    with tempfile.TemporaryDirectory() as gecici:
        gecici = Path(gecici)
        with (gecici / "logits.bin").open("wb") as f:
            f.write(b"PLKA")
            f.write(struct.pack("<iii", len(ornekler), T, C))
            for p in ornekler:
                m = np.full((T, C), -20.0, dtype=np.float32)
                m[:, 0] = -0.01                       # varsayilan blank
                # Karakterleri araya blank koyarak yerlestir.
                for i, ch in enumerate(p):
                    t = 2 * i + 1
                    assert t < T, "plaka T'ye sigmiyor"
                    m[t, 0] = -20.0
                    m[t, alfabe.index(ch) + 1] = -0.01
                f.write(np.ascontiguousarray(m).tobytes())
        cikti = gecici / "cozum.tsv"
        subprocess.run([str(exe), str(gecici / "logits.bin"), str(cikti)],
                       check=True, capture_output=True)
        satirlar = [s.split("\t") for s in
                    cikti.read_text(encoding="utf-8").splitlines() if s.strip()]

    assert len(satirlar) == len(ornekler)
    # decode.exe satiri: indeks, greedy, kisitli, en_iyi_lp, ikinci, ikinci_lp
    # Guven sutunlari sonradan eklendi; ilk uc alan alinarak sabit tutuluyor.
    for (_, greedy, kisitli, *_kalan), beklenen in zip(satirlar, ornekler):
        assert greedy == beklenen, f"C++ greedy: {greedy} != {beklenen}"
        assert kisitli == beklenen, \
            (f"C++ dilbilgisi '{beklenen}' plakasini reddetti "
             f"(duzen {duzeni(beklenen)}), '{kisitli}' dondu")


def main() -> int:
    testler = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    hata = 0
    for t in testler:
        try:
            t()
            print(f"  gecti  {t.__name__}")
        except AssertionError as e:
            hata += 1
            print(f"  KALDI  {t.__name__}: {e}")
    print(f"\n{len(testler) - hata}/{len(testler)} gecti")
    return 1 if hata else 0


if __name__ == "__main__":
    raise SystemExit(main())
