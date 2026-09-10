// Arac kirpmasindan plakaya - PyTorch, OpenCV ve Python olmadan.
//
// Ne yapiyor
// ----------
//   arac kirpmasi -> yeniden boyutlandir -> KOSE MODELI (ONNX)
//     -> varlik kapisi -> perspektif duzeltme -> gri + boyutlandir
//     -> TANIYICI (ONNX) -> kisitli isin aramasi -> plaka + guven
//
// Yani boru hattinin, projenin kendi yazdigi her adimi. YOLO disarida:
// bolum 22'de ONNX'te YAVASLADIGI olculdu (0.71x) ve zaten hazir bir model.
//
// Neden bagimlilik yok
// --------------------
// ONNX Runtime'in C API'si tek bir disa aktarilmis fonksiyon uzerinden
// calisiyor (OrtGetApiBase), gerisi islev isaretcisi tablosu. DLL calisma
// aninda aciliyor: import kutuphanesi gerekmiyor, C API oldugu icin
// MinGW/MSVC ABI sorunu da yok.
//
// OpenCV yok. Yeniden boyutlandirma (alan ortalamasi) ve perspektif
// donusumu burada yazili. Bunun BEDELI var ve olculuyor: OpenCV
// diklestirmede INTER_CUBIC kullaniyor, burada iki dogrusal ara deger var.
// Piksel piksel ayni olmayacak; onemli olan okunan PLAKANIN ayni olup
// olmadigi ve bunu scripts/compare_cpp.py sayiyor.
//
// Derleme:
//   g++ -O2 -std=c++17 -o cpp/pipeline.exe cpp/pipeline.cpp -Icpp/dis
//
// Calistirma:
//   cpp/pipeline.exe <manifest.txt> <onnx-klasoru> <kalibrasyon.json> <cikti.tsv>
//   manifest: satir basina bir goruntu yolu

#include "decoder.hpp"

#define STB_IMAGE_IMPLEMENTATION
#define STBI_ONLY_JPEG
#define STBI_ONLY_PNG
#include "stb_image.h"

// Sira onemli: MinGW'nin sal.h'si SAL aciklamalarini tanimliyor, ONNX
// basligi da ayni adlari kosulsuz bos olarak yeniden tanimliyor. Once
// ONNX gelirse windows.h'nin guardlari devreye giriyor ve uyari cikmiyor.
#include "onnxruntime_c_api.h"

#include <windows.h>

#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <sstream>
#include <string>
#include <vector>

namespace {

// train_corners.py ve train_recognizer.py ile ayni olmali.
constexpr int KOSE_G = 288, KOSE_Y = 96;
constexpr int DIK_G = 256, DIK_Y = 64;      // export_plates.py
constexpr int TAN_G = 128, TAN_Y = 32;

struct Goruntu {
    int g = 0, y = 0, k = 0;                 // genislik, yukseklik, kanal
    std::vector<unsigned char> p;            // satir sirali, BGR
    unsigned char at(int yy, int xx, int c) const {
        return p[(size_t)(yy * g + xx) * k + c];
    }
};

// stb RGB veriyor, Python tarafi cv2 ile BGR okuyor. Kanal sirasi
// modelin gordugu seyi degistirir; burada BGR'ye ceviriliyor.
bool goruntu_oku(const std::string& yol, Goruntu& out) {
    int g, y, k;
    unsigned char* v = stbi_load(yol.c_str(), &g, &y, &k, 3);
    if (!v) return false;
    out.g = g; out.y = y; out.k = 3;
    out.p.assign((size_t)g * y * 3, 0);
    for (size_t i = 0; i < (size_t)g * y; i++) {
        out.p[i * 3 + 0] = v[i * 3 + 2];     // B
        out.p[i * 3 + 1] = v[i * 3 + 1];     // G
        out.p[i * 3 + 2] = v[i * 3 + 0];     // R
    }
    stbi_image_free(v);
    return true;
}

// Alan ortalamasiyla kucultme - cv2.INTER_AREA'nin yaptigi is. Her hedef
// piksel, kaynaktaki dikdortgeninin agirlikli ortalamasi. Iki dogrusal ara
// deger kucultmede takma ad (aliasing) birakiyor ve plaka karakterleri tam
// da o olcekte.
//
// AYRILABILIR yazildi: once yatay, sonra dikey. Ilk surum her hedef piksel
// icin kaynak dikdortgenini iki katli dolasiyordu ve kirpma basina 6.17 ms
// tutuyordu - boru hattinin en pahali adimi, ONNX cagrilarinin toplamindan
// fazla. Agirliklar ayrica satir/sutun basina BIR KEZ hesaplaniyor; onceki
// surum her kanal icin yeniden hesapliyordu.
// Agirliklar TEK bir tamponda. Ilk surumde her hedef piksel icin ayri bir
// vector<float> vardi: kirpma basina ~800 kucuk yigin tahsisi, ve kucultmenin
// maliyetinin buyuk kismi oradan geliyordu - hesaptan degil tahsisten.
struct Tablo {
    std::vector<int> bas, adet;
    std::vector<float> w;         // bas[i]..bas[i]+adet[i] araligi w'de sirali
    std::vector<int> ofset;
};

Tablo agirlik_tablosu(int kaynak, int hedef) {
    Tablo t;
    t.bas.resize(hedef); t.adet.resize(hedef); t.ofset.resize(hedef);
    t.w.reserve((size_t)hedef * 4);
    const double olcek = (double)kaynak / hedef;
    for (int i = 0; i < hedef; i++) {
        const double a = i * olcek, b = (i + 1) * olcek;
        const int i0 = std::max(0, (int)a);
        const int i1 = std::max(std::min(kaynak, (int)std::ceil(b)), i0 + 1);
        t.bas[i] = i0;
        t.adet[i] = i1 - i0;
        t.ofset[i] = (int)t.w.size();
        double toplam = 0;
        for (int j = i0; j < i1; j++) {
            const double p = std::max(0.0, std::min<double>(b, j + 1)
                                          - std::max<double>(a, j));
            t.w.push_back((float)p);
            toplam += p;
        }
        if (toplam > 0)
            for (int n = 0; n < t.adet[i]; n++)
                t.w[t.ofset[i] + n] = (float)(t.w[t.ofset[i] + n] / toplam);
    }
    return t;
}

Goruntu alan_kucult(const Goruntu& im, int hg, int hy) {
    Goruntu o; o.g = hg; o.y = hy; o.k = im.k;
    o.p.assign((size_t)hg * hy * im.k, 0);
    const int k = im.k;
    const auto tx = agirlik_tablosu(im.g, hg);
    const auto ty = agirlik_tablosu(im.y, hy);

    // 1) yatay gecis -> (im.y satir) x (hg sutun)
    std::vector<float> ara((size_t)im.y * hg * k, 0.0f);
    for (int y = 0; y < im.y; y++) {
        const unsigned char* satir = &im.p[(size_t)y * im.g * k];
        float* cikti = &ara[(size_t)y * hg * k];
        for (int x = 0; x < hg; x++) {
            const int bas = tx.bas[x], adet = tx.adet[x];
            const float* w = &tx.w[tx.ofset[x]];
            for (int c = 0; c < k; c++) {
                float v = 0;
                for (int n = 0; n < adet; n++)
                    v += w[n] * satir[(size_t)(bas + n) * k + c];
                cikti[(size_t)x * k + c] = v;
            }
        }
    }
    // 2) dikey gecis
    //
    // Sira onemli: disda KAYNAK SATIRI, icde sutun. Tersi (sabit sutun icin
    // satirlar arasinda adimlamak) her erisimde hg*k kadar atliyor ve
    // onbellek satirini isabetsiz birakiyor. Bu tek degisiklik kucultmeyi
    // 4.02 ms'den asagi cekti.
    std::vector<float> biriktir((size_t)hg * k);
    for (int y = 0; y < hy; y++) {
        std::fill(biriktir.begin(), biriktir.end(), 0.0f);
        for (int n = 0; n < ty.adet[y]; n++) {
            const float w = ty.w[ty.ofset[y] + n];
            const float* satir = &ara[(size_t)(ty.bas[y] + n) * hg * k];
            for (size_t i = 0; i < biriktir.size(); i++)
                biriktir[i] += w * satir[i];
        }
        unsigned char* cikti = &o.p[(size_t)y * hg * k];
        for (size_t i = 0; i < biriktir.size(); i++)
            cikti[i] = (unsigned char)std::lround(
                std::min(255.0f, std::max(0.0f, biriktir[i])));
    }
    return o;
}

// Dort nokta esleniginden homografi. Hedef dikdortgenden KAYNAGA
// esliyoruz: her hedef pikselin kaynaktaki yerini dogrudan bulmak icin.
bool homografi(const double s[4][2], const double h[4][2], double M[9]) {
    double A[8][9] = {};
    for (int i = 0; i < 4; i++) {
        const double x = h[i][0], y = h[i][1], u = s[i][0], v = s[i][1];
        double* r0 = A[i * 2];
        double* r1 = A[i * 2 + 1];
        r0[0] = x; r0[1] = y; r0[2] = 1; r0[6] = -x * u; r0[7] = -y * u; r0[8] = u;
        r1[3] = x; r1[4] = y; r1[5] = 1; r1[6] = -x * v; r1[7] = -y * v; r1[8] = v;
    }
    for (int c = 0; c < 8; c++) {                       // Gauss elemesi
        int en = c;
        for (int r = c + 1; r < 8; r++)
            if (std::fabs(A[r][c]) > std::fabs(A[en][c])) en = r;
        if (std::fabs(A[en][c]) < 1e-12) return false;
        if (en != c) for (int k = 0; k < 9; k++) std::swap(A[c][k], A[en][k]);
        for (int r = 0; r < 8; r++) {
            if (r == c) continue;
            const double f = A[r][c] / A[c][c];
            for (int k = c; k < 9; k++) A[r][k] -= f * A[c][k];
        }
    }
    for (int i = 0; i < 8; i++) M[i] = A[i][8] / A[i][i];
    M[8] = 1.0;
    return true;
}

// Perspektif duzeltme. cv2 INTER_CUBIC kullaniyor, burada iki dogrusal;
// fark olculuyor (bkz. scripts/compare_cpp.py).
Goruntu diklestir(const Goruntu& im, const double kose[4][2], int hg, int hy) {
    Goruntu o; o.g = hg; o.y = hy; o.k = im.k;
    o.p.assign((size_t)hg * hy * im.k, 0);
    const double hedef[4][2] = {{0, 0}, {(double)hg - 1, 0},
                                {(double)hg - 1, (double)hy - 1},
                                {0, (double)hy - 1}};
    double M[9];
    if (!homografi(kose, hedef, M)) return o;
    for (int y = 0; y < hy; y++) {
        for (int x = 0; x < hg; x++) {
            const double w = M[6] * x + M[7] * y + M[8];
            if (std::fabs(w) < 1e-12) continue;
            const double sx = (M[0] * x + M[1] * y + M[2]) / w;
            const double sy = (M[3] * x + M[4] * y + M[5]) / w;
            const int x0 = (int)std::floor(sx), y0 = (int)std::floor(sy);
            const double fx = sx - x0, fy = sy - y0;
            for (int c = 0; c < im.k; c++) {
                double v = 0;
                for (int dy = 0; dy < 2; dy++) {
                    for (int dx = 0; dx < 2; dx++) {
                        const int xx = std::min(std::max(x0 + dx, 0), im.g - 1);
                        const int yy = std::min(std::max(y0 + dy, 0), im.y - 1);
                        v += (dx ? fx : 1 - fx) * (dy ? fy : 1 - fy)
                           * im.at(yy, xx, c);
                    }
                }
                o.p[(size_t)(y * hg + x) * im.k + c] =
                    (unsigned char)std::lround(std::min(255.0, std::max(0.0, v)));
            }
        }
    }
    return o;
}

// cv2.COLOR_BGR2GRAY ile ayni katsayilar.
std::vector<unsigned char> griye(const Goruntu& im) {
    std::vector<unsigned char> o((size_t)im.g * im.y);
    for (int y = 0; y < im.y; y++)
        for (int x = 0; x < im.g; x++)
            o[(size_t)y * im.g + x] = (unsigned char)std::lround(
                0.114 * im.at(y, x, 0) + 0.587 * im.at(y, x, 1)
                + 0.299 * im.at(y, x, 2));
    return o;
}

// ---------------------------------------------------------------- ONNX
const OrtApi* g_ort = nullptr;

void ort_kontrol(OrtStatus* s) {
    if (!s) return;
    std::fprintf(stderr, "ONNX hatasi: %s\n", g_ort->GetErrorMessage(s));
    g_ort->ReleaseStatus(s);
    std::exit(1);
}

std::wstring genise(const std::string& s) {
    int n = MultiByteToWideChar(CP_UTF8, 0, s.c_str(), -1, nullptr, 0);
    std::wstring w(n, 0);
    MultiByteToWideChar(CP_UTF8, 0, s.c_str(), -1, w.data(), n);
    if (!w.empty() && w.back() == 0) w.pop_back();
    return w;
}

struct Oturum {
    OrtSession* s = nullptr;
    OrtMemoryInfo* bellek = nullptr;

    void ac(OrtEnv* env, OrtSessionOptions* ayar, const std::string& yol) {
        ort_kontrol(g_ort->CreateSession(env, genise(yol).c_str(), ayar, &s));
        ort_kontrol(g_ort->CreateCpuMemoryInfo(OrtArenaAllocator,
                                               OrtMemTypeDefault, &bellek));
    }

    // Tek girdi, N cikti. Ciktilarin ham isaretcileri donuyor; cagiran
    // OrtValue'lari serbest birakmali.
    void calistir(const char* girdi_ad, std::vector<float>& girdi,
                  const std::vector<int64_t>& sekil,
                  const std::vector<const char*>& cikti_ad,
                  std::vector<OrtValue*>& cikti) {
        OrtValue* t = nullptr;
        ort_kontrol(g_ort->CreateTensorWithDataAsOrtValue(
            bellek, girdi.data(), girdi.size() * sizeof(float),
            sekil.data(), sekil.size(),
            ONNX_TENSOR_ELEMENT_DATA_TYPE_FLOAT, &t));
        cikti.assign(cikti_ad.size(), nullptr);
        const char* girdiler[1] = {girdi_ad};
        ort_kontrol(g_ort->Run(s, nullptr, girdiler, (const OrtValue* const*)&t,
                               1, cikti_ad.data(), cikti_ad.size(),
                               cikti.data()));
        g_ort->ReleaseValue(t);
    }
};

// Kalibrasyon agirliklari (runs/kalibrasyon.json). Tam bir JSON
// cozumleyiciye gerek yok: uc sayi araniyor.
bool agirlik_oku(const std::string& yol, double& sabit, double& marj,
                 double& lp) {
    std::ifstream f(yol);
    if (!f) return false;
    std::stringstream ss;
    ss << f.rdbuf();
    const std::string s = ss.str();
    auto bul = [&](const char* ad, double& hedef) {
        const size_t i = s.find(std::string("\"") + ad + "\"");
        if (i == std::string::npos) return false;
        const size_t j = s.find(':', i);
        if (j == std::string::npos) return false;
        hedef = std::atof(s.c_str() + j + 1);
        return true;
    };
    return bul("sabit", sabit) && bul("marj", marj) && bul("lp", lp);
}

}  // namespace

int main(int argc, char** argv) {
    if (argc < 5) {
        std::fprintf(stderr,
            "kullanim: pipeline.exe <manifest.txt> <onnx-klasoru> "
            "<kalibrasyon.json> <cikti.tsv> [isin=32] [aday=8]\n");
        return 1;
    }
    const std::string manifest = argv[1], onnx_kok = argv[2];
    const std::string kalib = argv[3], cikti_yol = argv[4];
    const int isin = argc > 5 ? std::atoi(argv[5]) : 32;
    const int aday = argc > 6 ? std::atoi(argv[6]) : 8;

    // --- ONNX Runtime'i calisma aninda ac -------------------------------
    //
    // DLL ACIK YOLLA aciliyor. Ciplak "onnxruntime.dll" ile acmak yanlis
    // surumu yukluyor: LoadLibrary once System32'ye bakiyor ve Windows'un
    // kendi getirdigi bir onnxruntime.dll orada duruyor (1.17.1), PATH'teki
    // 1.29 hic sirasi gelmeden. Belirti de yaniltici: "API version 29 is
    // not available" - sanki derleme hatasi gibi gorunuyor.
    const char* dll_yolu = std::getenv("PLAKA_ORT_DLL");
    HMODULE dll = LoadLibraryA(dll_yolu ? dll_yolu : "onnxruntime.dll");
    if (!dll) {
        std::fprintf(stderr,
            "onnxruntime.dll acilamadi%s%s\n"
            "PLAKA_ORT_DLL ile tam yolu verin, ornegin:\n"
            "  <venv>/Lib/site-packages/onnxruntime/capi/onnxruntime.dll\n",
            dll_yolu ? ": " : "", dll_yolu ? dll_yolu : "");
        return 1;
    }
    auto taban_fn = (const OrtApiBase* (*)(void))
        GetProcAddress(dll, "OrtGetApiBase");
    if (!taban_fn) { std::fprintf(stderr, "OrtGetApiBase yok\n"); return 1; }
    const OrtApiBase* taban = taban_fn();

    // Bu dosya ORT_API_VERSION'a gore derlendi ama DLL daha eski olabilir.
    // Kullanilan cagrilarin hepsi uzun suredir API'de; en yuksekten asagi
    // inip calisan ilk surumu aliyoruz.
    int api_surumu = 0;
    for (int v = ORT_API_VERSION; v >= 11 && !g_ort; v--) {
        g_ort = taban->GetApi(v);
        if (g_ort) api_surumu = v;
    }
    if (!g_ort) {
        std::fprintf(stderr, "OrtApi alinamadi. DLL surumu: %s\n",
                     taban->GetVersionString());
        return 1;
    }
    if (api_surumu != ORT_API_VERSION)
        std::fprintf(stderr, "not: API %d yerine %d kullaniliyor (DLL %s)\n",
                     ORT_API_VERSION, api_surumu, taban->GetVersionString());

    OrtEnv* env = nullptr;
    ort_kontrol(g_ort->CreateEnv(ORT_LOGGING_LEVEL_ERROR, "plakatanima", &env));
    OrtSessionOptions* ayar = nullptr;
    ort_kontrol(g_ort->CreateSessionOptions(&ayar));
    ort_kontrol(g_ort->SetIntraOpNumThreads(ayar, 0));   // 0 = tum cekirdekler

    Oturum kose_o, tan_o;
    kose_o.ac(env, ayar, onnx_kok + "/kose.onnx");
    tan_o.ac(env, ayar, onnx_kok + "/taniyici.onnx");

    double w_sabit = 0, w_marj = 0, w_lp = 0;
    if (!agirlik_oku(kalib, w_sabit, w_marj, w_lp)) {
        std::fprintf(stderr, "kalibrasyon okunamadi: %s\n", kalib.c_str());
        return 1;
    }

    // --- girdi listesi ---------------------------------------------------
    std::vector<std::string> yollar;
    {
        std::ifstream f(manifest);
        if (!f) { std::fprintf(stderr, "manifest yok: %s\n", manifest.c_str()); return 1; }
        std::string satir;
        while (std::getline(f, satir)) {
            while (!satir.empty() && (satir.back() == '\r' || satir.back() == '\n'))
                satir.pop_back();
            if (!satir.empty()) yollar.push_back(satir);
        }
    }

    std::ofstream cikti(cikti_yol);
    if (!cikti) { std::fprintf(stderr, "yazilamadi: %s\n", cikti_yol.c_str()); return 1; }

    std::vector<float> kose_girdi((size_t)3 * KOSE_Y * KOSE_G);
    std::vector<float> tan_girdi((size_t)TAN_Y * TAN_G);
    const std::vector<int64_t> kose_sekil = {1, 3, KOSE_Y, KOSE_G};
    const std::vector<int64_t> tan_sekil = {1, 1, TAN_Y, TAN_G};
    const std::vector<const char*> kose_ciktilari = {"kose", "varlik"};
    const std::vector<const char*> tan_ciktilari = {"logit"};

    int okunamayan = 0;
    // Adim adim zamanlama: "C++ yavas" yeterli bir cevap degil, NEREDE
    // yavas oldugu lazim. Bu sayilar olmadan elle yazilan goruntu
    // islemleriyle ONNX cagrilarini ayirt edemeyiz.
    double t_oku = 0, t_kucult = 0, t_kose = 0, t_dik = 0, t_tan = 0, t_coz = 0;
    auto simdi = [] { return std::chrono::steady_clock::now(); };
    auto gecen = [](auto a, auto b) {
        return std::chrono::duration<double, std::milli>(b - a).count();
    };
    const auto basladi = simdi();

    for (size_t i = 0; i < yollar.size(); i++) {
        auto t0 = simdi();
        Goruntu im;
        if (!goruntu_oku(yollar[i], im)) { okunamayan++; continue; }
        auto t1 = simdi();
        t_oku += gecen(t0, t1);

        // 1) kose modeli girdisi
        const Goruntu kucuk = alan_kucult(im, KOSE_G, KOSE_Y);
        for (int c = 0; c < 3; c++)
            for (int y = 0; y < KOSE_Y; y++)
                for (int x = 0; x < KOSE_G; x++)
                    kose_girdi[((size_t)c * KOSE_Y + y) * KOSE_G + x] =
                        (float)(kucuk.at(y, x, c) / 127.5 - 1.0);

        auto t2 = simdi();
        t_kucult += gecen(t1, t2);

        std::vector<OrtValue*> kose_cikti;
        kose_o.calistir("kirpma", kose_girdi, kose_sekil, kose_ciktilari,
                        kose_cikti);
        float* kose_ham = nullptr;
        float* varlik_ham = nullptr;
        ort_kontrol(g_ort->GetTensorMutableData(kose_cikti[0], (void**)&kose_ham));
        ort_kontrol(g_ort->GetTensorMutableData(kose_cikti[1], (void**)&varlik_ham));

        double kose[4][2];
        for (int k = 0; k < 4; k++) {
            kose[k][0] = kose_ham[k * 2 + 0] * im.g;   // 0-1 -> ORIJINAL olcek
            kose[k][1] = kose_ham[k * 2 + 1] * im.y;
        }
        const double varlik = 1.0 / (1.0 + std::exp(-(double)varlik_ham[0]));
        g_ort->ReleaseValue(kose_cikti[0]);
        g_ort->ReleaseValue(kose_cikti[1]);

        auto t3 = simdi();
        t_kose += gecen(t2, t3);

        // 2) diklestir -> gri -> kucult
        const Goruntu dik = diklestir(im, kose, DIK_G, DIK_Y);
        Goruntu gri; gri.g = DIK_G; gri.y = DIK_Y; gri.k = 1;
        gri.p = griye(dik);
        const Goruntu tan_im = alan_kucult(gri, TAN_G, TAN_Y);
        for (int y = 0; y < TAN_Y; y++)
            for (int x = 0; x < TAN_G; x++)
                tan_girdi[(size_t)y * TAN_G + x] =
                    (float)(tan_im.at(y, x, 0) / 127.5 - 1.0);

        auto t4 = simdi();
        t_dik += gecen(t3, t4);

        // 3) taniyici
        std::vector<OrtValue*> tan_cikti;
        tan_o.calistir("plaka", tan_girdi, tan_sekil, tan_ciktilari, tan_cikti);
        float* logit = nullptr;
        ort_kontrol(g_ort->GetTensorMutableData(tan_cikti[0], (void**)&logit));

        OrtTensorTypeAndShapeInfo* bilgi = nullptr;
        ort_kontrol(g_ort->GetTensorTypeAndShape(tan_cikti[0], &bilgi));
        size_t boyut_n = 0;
        ort_kontrol(g_ort->GetDimensionsCount(bilgi, &boyut_n));
        std::vector<int64_t> boyut(boyut_n);
        ort_kontrol(g_ort->GetDimensions(bilgi, boyut.data(), boyut_n));
        g_ort->ReleaseTensorTypeAndShapeInfo(bilgi);
        const int T = (int)boyut[0], C = (int)boyut[2];   // (T, B=1, C)

        // log_softmax: cozumleyici log olasilik bekliyor.
        std::vector<float> logp((size_t)T * C);
        for (int t = 0; t < T; t++) {
            const float* satir = logit + (size_t)t * C;
            float en = satir[0];
            for (int c = 1; c < C; c++) en = std::max(en, satir[c]);
            double toplam = 0;
            for (int c = 0; c < C; c++) toplam += std::exp(satir[c] - en);
            const double log_toplam = en + std::log(toplam);
            for (int c = 0; c < C; c++)
                logp[(size_t)t * C + c] = (float)(satir[c] - log_toplam);
        }
        g_ort->ReleaseValue(tan_cikti[0]);

        auto t5 = simdi();
        t_tan += gecen(t4, t5);

        // 4) kisitli cozumleme + guven
        const Sonuc r = kisitli(logp.data(), T, C, isin, aday);
        t_coz += gecen(t5, simdi());
        double marj = 30.0;
        if (std::isfinite(r.ikinci_lp))
            marj = std::min(30.0, r.en_iyi_lp - r.ikinci_lp);
        const double lp = std::max(-30.0, r.en_iyi_lp);
        const double z = w_sabit + w_marj * marj + w_lp * lp;
        const double guven = 1.0 / (1.0 + std::exp(-std::max(-30.0,
                                                   std::min(30.0, z))));

        cikti << i << '\t' << yollar[i] << '\t' << r.en_iyi << '\t'
              << guven << '\t' << varlik << '\n';
    }

    const double sn = std::chrono::duration<double>(
        std::chrono::steady_clock::now() - basladi).count();
    const size_t n = yollar.size() - okunamayan;
    const double d = n ? (double)n : 1.0;
    std::fprintf(stderr,
                 "%zu kirpma islendi (%d okunamadi)\n"
                 "toplam %.2f sn  ->  kirpma basina %.2f ms\n\n"
                 "  adim basina (ms):\n"
                 "    JPEG cozme          %6.2f\n"
                 "    kucultme (elle)     %6.2f\n"
                 "    kose modeli (ONNX)  %6.2f\n"
                 "    diklestirme (elle)  %6.2f\n"
                 "    taniyici (ONNX)     %6.2f\n"
                 "    kisitli cozumleme   %6.2f\n"
                 "    -------------------------\n"
                 "    ONNX toplam         %6.2f\n"
                 "    elle yazilan islem  %6.2f\n"
                 "-> %s\n",
                 n, okunamayan, sn, n ? sn * 1000 / n : 0.0,
                 t_oku / d, t_kucult / d, t_kose / d, t_dik / d, t_tan / d,
                 t_coz / d, (t_kose + t_tan) / d, (t_kucult + t_dik) / d,
                 cikti_yol.c_str());

    g_ort->ReleaseSessionOptions(ayar);
    g_ort->ReleaseEnv(env);
    return 0;
}
