// Kisitli CTC cozumleyici - dosyadan okuyup dosyaya yazan tek basina ikili.
//
// Dilbilgisi ve isin aramasi decoder.hpp'de; boru hatti (pipeline.cpp) da
// ayni basligi kullaniyor.
//
// Derleme:
//   g++ -O2 -std=c++17 -o cpp/decode.exe cpp/decode.cpp

#include "decoder.hpp"

#include <cstdio>
#include <cstring>
#include <fstream>
#include <vector>

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
