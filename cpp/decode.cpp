// Turk plakasi icin KISITLI CTC cozumleyici.
//
// Neden kisit
// -----------
// Ince ayardan sonra ortalama duzenleme mesafesi 0.37: hatalarin cogu artik
// TEK karakter. Boyle bir hata cogu zaman gecersiz bir plaka uretiyor -
// "34KF27I8" gibi. Gecerli plaka dilbilgisi disina cikan yollari aramadan
// elemek, o hatalarin bir kismini modelin ikinci tercihine cevirir.
//
// Dilbilgisi (272 gercek plaka uzerinde dogrulandi)
// -------------------------------------------------
//   il      : iki hane, 01-81
//   harf    : 1-3 harf, 23 harflik alfabe (Q, W, X yok)
//   rakam   : 2-4 hane
//   gecerli (harf, rakam) ciftleri: (1,4) (2,3) (2,4) (3,2) (3,3)
//
// (3,3) bu listeye SONRADAN eklendi. Uretecte yoktu ve 272 gercek plakanin
// 146'si (%54) tam olarak o duzende. Bu dilbilgisiyle olcum yapmadan once
// gercek etiketlere karsi sinandi: 272 plakanin 270'ini kabul ediyor.
// Kabul etmedigi ikisi '013426' ve 'E83KZV' - hicbir Turk plakasi bicimine
// uymuyorlar, muhtemelen etiketleme hatasi. Kisitin bedeli bu: bicime
// uymayan plaka ASLA dogru okunamaz. %0.7 ve bilerek odendi.
//
// Derleme:
//   g++ -O2 -std=c++17 -o cpp/decode.exe cpp/decode.cpp

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <string>
#include <unordered_map>
#include <vector>

namespace {

const std::string ALFABE = "ABCDEFGHIJKLMNOPRSTUVYZ0123456789";
constexpr int BLANK = 0;

inline bool harf_mi(char c) { return c >= 'A' && c <= 'Z'; }
inline bool rakam_mi(char c) { return c >= '0' && c <= '9'; }

// Bir on ekin dilbilgisindeki durumu: kac harf, kac rakam (il kodundan sonra).
struct Durum {
    int harf = 0;
    int rakam = 0;
    bool gecerli = true;
};

Durum durumu_bul(const std::string& p) {
    Durum d;
    if (p.size() <= 2) return d;
    size_t i = 2;
    while (i < p.size() && harf_mi(p[i])) { d.harf++; i++; }
    while (i < p.size() && rakam_mi(p[i])) { d.rakam++; i++; }
    if (i != p.size()) d.gecerli = false;
    return d;
}

// harf sayisina gore izin verilen rakam sayilari
int rakam_ust(int harf) {
    switch (harf) {
        case 1: return 4;
        case 2: return 4;
        case 3: return 3;
        default: return 0;
    }
}
bool bitis_mi(int harf, int rakam) {
    switch (harf) {
        case 1: return rakam == 4;
        case 2: return rakam == 3 || rakam == 4;
        case 3: return rakam == 2 || rakam == 3;
        default: return false;
    }
}

// Bu on ekten sonra hangi karakterler gelebilir.
bool izinli(const std::string& p, char c) {
    if (p.empty()) return c >= '0' && c <= '8';          // il ilk hanesi
    if (p.size() == 1) {                                  // il 01-81
        if (!rakam_mi(c)) return false;
        int il = (p[0] - '0') * 10 + (c - '0');
        return il >= 1 && il <= 81;
    }
    Durum d = durumu_bul(p);
    if (!d.gecerli) return false;
    if (harf_mi(c)) return d.rakam == 0 && d.harf < 3;
    if (rakam_mi(c)) return d.harf >= 1 && d.rakam < rakam_ust(d.harf);
    return false;
}

bool tam_mi(const std::string& p) {
    if (p.size() < 5) return false;
    Durum d = durumu_bul(p);
    return d.gecerli && bitis_mi(d.harf, d.rakam);
}

inline double log_topla(double a, double b) {
    if (a == -INFINITY) return b;
    if (b == -INFINITY) return a;
    double m = a > b ? a : b;
    return m + std::log1p(std::exp(-std::fabs(a - b)));
}

struct Olasilik {
    double bos = -INFINITY;     // blank ile biten yollar
    double dolu = -INFINITY;    // karakterle biten yollar
    double toplam() const { return log_topla(bos, dolu); }
};

// Kisitsiz greedy - matrisin dogru okundugunu Python tarafiyla
// karsilastirarak dogrulamak icin de duruyor.
std::string greedy(const float* L, int T, int C) {
    std::string out;
    int onceki = -1;
    for (int t = 0; t < T; t++) {
        int en = 0;
        for (int c = 1; c < C; c++)
            if (L[t * C + c] > L[t * C + en]) en = c;
        if (en != onceki && en != BLANK) out += ALFABE[en - 1];
        onceki = en;
    }
    return out;
}

// Cozumun kendisi ve GUVEN icin gereken ham sayilar.
//
// Guven neden iki sayi: mutlak olasilik tek basina yaniltici - uzun plaka
// her zaman daha dusuk log olasilik alir, cunku daha cok carpan var. Ikinci
// en iyi TAM plakaya olan fark (marj) uzunluktan bagimsiz ve "model bu
// okumada ne kadar kararli" sorusuna daha dogrudan cevap veriyor.
struct Sonuc {
    std::string en_iyi;
    double en_iyi_lp = -INFINITY;
    std::string ikinci;
    double ikinci_lp = -INFINITY;
    bool tam = false;
};

// Kisitli CTC on ek isini aramasi.
Sonuc kisitli(const float* L, int T, int C, int genislik, int aday) {
    std::unordered_map<std::string, Olasilik> isin;
    isin[""].bos = 0.0;

    std::vector<int> sira(C);
    for (int t = 0; t < T; t++) {
        // Her adimda yalnizca en olasi birkac etiket denenir; gerisi
        // isin genisligini doldurup hesabi yavaslatmaktan baska ise
        // yaramiyor.
        for (int c = 0; c < C; c++) sira[c] = c;
        std::partial_sort(sira.begin(), sira.begin() + std::min(aday, C),
                          sira.end(), [&](int a, int b) {
                              return L[t * C + a] > L[t * C + b];
                          });

        std::unordered_map<std::string, Olasilik> yeni;
        for (const auto& [onek, o] : isin) {
            // 1) blank ekle - on ek degismez
            {
                Olasilik& h = yeni[onek];
                h.bos = log_topla(h.bos, o.toplam() + L[t * C + BLANK]);
            }
            for (int k = 0; k < std::min(aday, C); k++) {
                int c = sira[k];
                if (c == BLANK) continue;
                char ch = ALFABE[c - 1];
                double p = L[t * C + c];

                // 2) son karakterin tekrari - on ek yine degismez
                if (!onek.empty() && onek.back() == ch) {
                    Olasilik& h = yeni[onek];
                    h.dolu = log_topla(h.dolu, o.dolu + p);
                    // Tekrari AYIRMAK icin araya blank girmesi gerekir;
                    // o yol asagida yeni on ek olarak ele aliniyor.
                    if (izinli(onek, ch)) {
                        Olasilik& g = yeni[onek + ch];
                        g.dolu = log_topla(g.dolu, o.bos + p);
                    }
                    continue;
                }
                // 3) yeni karakter - dilbilgisi izin veriyorsa
                if (!izinli(onek, ch)) continue;
                Olasilik& g = yeni[onek + ch];
                g.dolu = log_topla(g.dolu, o.toplam() + p);
            }
        }

        std::vector<std::pair<std::string, Olasilik>> liste(yeni.begin(),
                                                            yeni.end());
        if ((int)liste.size() > genislik) {
            std::partial_sort(liste.begin(), liste.begin() + genislik,
                              liste.end(), [](const auto& a, const auto& b) {
                                  return a.second.toplam() > b.second.toplam();
                              });
            liste.resize(genislik);
        }
        isin.clear();
        for (auto& x : liste) isin.emplace(std::move(x.first), x.second);
    }

    // Yalnizca TAM plakalar aday. En iyi IKI tanesi aliniyor: marj guven
    // sinyalinin asil tasiyicisi.
    Sonuc r;
    for (const auto& [onek, o] : isin) {
        if (!tam_mi(onek)) continue;
        double p = o.toplam();
        if (p > r.en_iyi_lp) {
            r.ikinci = r.en_iyi; r.ikinci_lp = r.en_iyi_lp;
            r.en_iyi = onek; r.en_iyi_lp = p;
        } else if (p > r.ikinci_lp) {
            r.ikinci = onek; r.ikinci_lp = p;
        }
    }
    if (!r.en_iyi.empty()) { r.tam = true; return r; }

    // Hicbir tam plaka uretilemediyse en olasi on ek doner; guven dusuk
    // isaretlenebilsin diye tam=false kaliyor.
    for (const auto& [onek, o] : isin)
        if (o.toplam() > r.en_iyi_lp) {
            r.en_iyi_lp = o.toplam();
            r.en_iyi = onek;
        }
    return r;
}

}  // namespace

int main(int argc, char** argv) {
    const char* girdi = argc > 1 ? argv[1] : "paket/logits.bin";
    const char* cikti = argc > 2 ? argv[2] : "paket/cozum.tsv";
    int genislik = argc > 3 ? std::atoi(argv[3]) : 32;
    int aday = argc > 4 ? std::atoi(argv[4]) : 8;

    std::ifstream f(girdi, std::ios::binary);
    if (!f) { std::fprintf(stderr, "acilamadi: %s\n", girdi); return 1; }
    char sihir[4];
    f.read(sihir, 4);
    if (std::memcmp(sihir, "PLKA", 4) != 0) {
        std::fprintf(stderr, "bicim taninmadi\n"); return 1;
    }
    int32_t n, T, C;
    f.read(reinterpret_cast<char*>(&n), 4);
    f.read(reinterpret_cast<char*>(&T), 4);
    f.read(reinterpret_cast<char*>(&C), 4);
    if (C != (int)ALFABE.size() + 1) {
        std::fprintf(stderr, "alfabe uyusmuyor: C=%d\n", C); return 1;
    }
    std::vector<float> veri((size_t)n * T * C);
    f.read(reinterpret_cast<char*>(veri.data()),
           (std::streamsize)veri.size() * sizeof(float));

    std::ofstream g(cikti);
    if (!g) { std::fprintf(stderr, "yazilamadi: %s\n", cikti); return 1; }
    int eksik = 0;
    for (int i = 0; i < n; i++) {
        const float* L = veri.data() + (size_t)i * T * C;
        std::string a = greedy(L, T, C);
        Sonuc r = kisitli(L, T, C, genislik, aday);
        if (!r.tam) eksik++;
        // indeks, greedy, kisitli, en_iyi_lp, ikinci, ikinci_lp
        g << i << '\t' << a << '\t' << r.en_iyi << '\t' << r.en_iyi_lp
          << '\t' << (r.ikinci.empty() ? "-" : r.ikinci) << '\t'
          << r.ikinci_lp << '\n';
    }
    std::fprintf(stderr,
                 "%d ornek cozuldu (T=%d C=%d, isin %d, aday %d)\n"
                 "dilbilgisine uyan tam plaka uretilemeyen: %d\n"
                 "-> %s\n",
                 n, T, C, genislik, aday, eksik, cikti);
    return 0;
}
