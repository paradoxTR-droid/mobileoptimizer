# Windows uyarısı rehberi

MobileOptimizer ücretsiz ve açık kaynaklıdır. Dijital imza sertifikası için bütçe olmadığından program imzasızdır.
Bu yüzden Windows ve bazı antivirüs programları ilk açılışta uyarı gösterebilir.

## "Windows bilgisayarınızı korudu" (SmartScreen)

1. İndirdiğiniz `MobileOptimizer-<sürüm>-windows.zip` dosyasını bir klasöre çıkarın.
2. Klasördeki `MobileOptimizer.exe` dosyasını açın.
3. Mavi uyarı penceresinde **Ek bilgi** yazısına tıklayın.
4. Çıkan **Yine de çalıştır** düğmesine tıklayın.

Bu adım yalnızca ilk açılışta gerekir.

## Antivirüs dosyayı karantinaya aldıysa

1. Antivirüs programınızda **Karantina** (veya "Tehdit geçmişi") bölümünü açın.
2. MobileOptimizer dosyalarını **Geri yükle** ile geri alın.
3. MobileOptimizer klasörünü **İstisnalar** / **Dışlamalar** listesine ekleyin.

Yalnızca dosyayı bu projenin resmi indirme sayfasından aldıysanız ve SHA-256 değeri tuttuysa bunu yapın.

## Dosyanın değiştirilmediğini kontrol etme (SHA-256)

Komut İstemi'ni (cmd) açın ve zip dosyasının bulunduğu klasörde çalıştırın:

```
certutil -hashfile MobileOptimizer-<sürüm>-windows.zip SHA256
```

Çıkan değer, indirme sayfasındaki `MobileOptimizer-<sürüm>-windows.zip.sha256` dosyasındaki değerle
**birebir aynı** olmalıdır. Farklıysa dosyayı açmayın ve silin.

## Yayınlayan için

- Her sürüm `python scripts/build.py` ile üretilir; `.sha256` dosyası otomatik yazılır.
- Yayından önce zip dosyası [VirusTotal](https://www.virustotal.com/)'e yüklenir. Yanlış alarm veren
  üreticiler sürüm notlarında belirtilir ve üreticiye yanlış alarm bildirimi gönderilir.
