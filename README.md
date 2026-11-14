# MobileOptimizer

Android telefonunuzu USB ile bağlayıp, root gerektirmeden ve her adımı geri alınabilir şekilde
performans, pil ve temizlik ayarları uygulayan ücretsiz masaüstü aracı.

- Samsung (One UI), Xiaomi / Redmi / POCO (MIUI, HyperOS) için özel ayarlar; diğer markalar için genel Android ayarları.
- Hazır ayar setleri: **Maks Performans**, **Maks Pil**, **Dengeli**, ya da **Özel** seçim.
- Her oturumdan önce eski değerler kaydedilir (bilgisayarda ve telefonda `/sdcard/MobileOptimizer/`).
  "Geri al / Geçmiş" ekranından tek tuşla geri alınır. Kayıt kaybolursa **Kurtarma** kullanılabilir.
- İnternete bağlanmaz, veri toplamaz.

> Program fotoğraf, rehber ve mesaj gibi verilerinizi **yedeklemez**. İşlemden önce kendi yedeğinizi alın.

## İndirme ve kurulum (Windows)

1. Sürümler sayfasından `MobileOptimizer-<sürüm>-windows.zip` ve `.sha256` dosyasını indirin.
2. SHA-256 değerini kontrol edin: `certutil -hashfile MobileOptimizer-<sürüm>-windows.zip SHA256`
3. Zip'i bir klasöre çıkarın ve `MobileOptimizer.exe`'yi açın.
4. Windows uyarı verirse: [Windows uyarısı rehberi](docs/windows-uyari-rehberi.md).

Telefonda **Geliştirici seçenekleri > USB hata ayıklama** açık olmalıdır. Xiaomi'de ayrıca
**USB hata ayıklama (Güvenlik ayarları)** gerekir. Ayrıntılı adımlar uygulamanın **Yardım** menüsündedir.

## Geliştirme

```bash
python -m venv .venv && .venv/bin/pip install -e ".[dev]"
QT_QPA_PLATFORM=offscreen .venv/bin/pytest
.venv/bin/python -m mobileoptimizer.app.main
```

Bir profili telefonda salt-okunur kontrol etmek (hiçbir şey değiştirmez):

```bash
python -m mobileoptimizer.tools.verify_profile --serial <seri> --profile samsung
```

`OK` görünen ve telefonda uygula + geri al denemesi geçen işlemler `verified: true` yapılabilir.
Hazır ayar setlerine yalnızca `risk: safe` ve `verified: true` işlemler girebilir.

Paketleme:

```bash
python scripts/fetch_platform_tools.py --platform linux --sdk ~/Android/Sdk   # veya Windows'ta indirerek
python scripts/build.py
```

## Lisans ve teşekkür

GPL-3.0. Gereksiz uygulama listelerinin bir kısmı (profillerde `source: uad` olanlar)
Universal Android Debloater listelerinden derlenmiştir. Gömülü `adb`, Android SDK Platform-Tools'tan gelir
(lisansı: `vendor/adb/*/NOTICE.txt`).
