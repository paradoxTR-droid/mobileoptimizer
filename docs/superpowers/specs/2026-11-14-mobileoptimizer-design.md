# MobileOptimizer — Tasarım Dokümanı

Tarih: 2026-11-14
Durum: Onaylandı (2026-11-14)

## 1. Amaç ve neden

İnsanlar belli fiyatlara telefon alıyor. Telefonlar üretici ayarlarıyla gelince her zaman en iyi performansı ve pil ömrünü vermiyor. Kasma oluyor, pil çabuk bitiyor, reklamlar ve gereksiz uygulamalar çıkıyor.

MobileOptimizer bir PC uygulaması. Kullanıcı telefonunu USB ile bağlıyor. Uygulama markayı ve modeli tanıyor. Kullanıcı hazır bir profil seçiyor ya da ayarları tek tek seçiyor. Uygulama ayarları ADB ile telefona uyguluyor.

Proje kâr amaçlı değil. Herkese açık ve ücretsiz bir iyilik aracı olacak.

## 2. Hedefler

- İlk sürüm üç derdi birlikte çözer:
  1. **Kasma/yavaşlık:** animasyon hızları, arka plan süreç limiti, uygulama derleme (`cmd package compile`), yenileme hızı.
  2. **Pil:** Doze/App Standby ayarları, arka plan kısıtları, gereksiz servislerin kapatılması, pil tasarrufu ayarları.
  3. **Reklam ve gereksiz uygulamalar:** marka bazlı bloatware/reklam/analitik paketlerinin kaldırılması veya devre dışı bırakılması.
- Markaya özel profiller:
  - Samsung (One UI)
  - Xiaomi / Redmi / POCO (MIUI / HyperOS)
  - Diğer tüm markalar: genel Android profili
- Hazır profiller: **Maks Performans**, **Maks Pil**, **Dengeli**. Ayrıca kullanıcının her ayarı tek tek seçtiği **Özel** mod.
- Teknik bilgisi az kullanıcı kullanabilmeli: bağla, otomatik tanı, profil seç, uygula.
- Her değişiklik geri alınabilmeli.

## 3. Hedef olmayanlar (ilk sürümde yok)

- Root gerektiren her şey: CPU/GPU frekansı, governor, kernel ayarları. Bu ikinci sürüme kalır.
- Telefonda çalışan uygulama (Shizuku vb.).
- Kullanıcı verisinin (fotoğraf, dosya, mesaj) yedeklenmesi. Bunun yerine kullanıcı uyarılır.
- Kablosuz ADB eşleştirme. İlk sürüm yalnızca USB kullanır.
- macOS desteği garanti değil. Python/Qt sayesinde çalışabilir ama test edilmez.

## 4. Anti-hedefler (çalışsa bile başarısızlık sayılır)

- Telefonun açılmama döngüsüne (bootloop) girmesi veya temel bir işlevin bozulması: arama, SMS, kamera, Wi-Fi, mobil veri, bildirimler, kilit ekranı, güncellemeler.
- Geri alınamayan bir değişiklik yapılması.
- Kullanıcının ne yapıldığını bilmeden ayarlarının değiştirilmesi.
- Kullanıcı verisinin herhangi bir yere gönderilmesi. Uygulama telemetri toplamaz, internete veri göndermez.

## 5. Kısıtlar

- **Root yok.** Yalnızca ADB shell yetkisi (`shell` kullanıcısı) ile yapılabilenler kullanılır.
- Kullanıcı telefonda Geliştirici Seçenekleri'ni ve USB hata ayıklamayı açmalı. Uygulama bunu marka bazlı resimli adımlarla anlatır. Xiaomi'de ayrıca "USB hata ayıklama (Güvenlik ayarları)" seçeneği gerekir. Bu seçenek Mi hesabı ve SIM ister. Uygulama bunu ayrıca anlatır.
- Hedef Android sürümü: Android 10 ve üstü. Daha eski sürümlerde uygulama uyarı verir ve yalnızca genel, güvenli ayarları sunar.
- Platform: Windows 10/11 öncelikli, Linux ikincil.
- `adb` uygulamanın içinde gelir. Kullanıcı ayrıca kurmaz. Windows'ta USB sürücüsü gerekebilir. Uygulama bunu tespit edip Google USB Driver / marka sürücüsü için yönlendirir.
- Arayüz dili ilk sürümde Türkçe. Metinler çeviri dosyasında tutulur, İngilizce sonra eklenir.

## 6. Yaklaşımlar

Değerlendirilen yollar:

1. **Python + PySide6 (Qt) masaüstü — SEÇİLDİ.**
   Tek dil. Profiller veri dosyası olduğu için gönüllüler kod yazmadan marka ekleyebilir. PyInstaller ile tek `.exe` üretilir. Eksisi: ~60–80 MB kurulum, arayüz web kadar modern durmaz.
2. **Tauri (Rust + web arayüzü).** Küçük kurulum ve şık arayüz sunar. Ama iki dil kullanılır, geliştirme ve katkı almak zorlaşır.
3. **Electron.** ~150 MB kurulum ve yüksek RAM kullanımı. Tauri'ye göre bir artısı yok.
4. **Telefonda çalışan uygulama (Shizuku).** Elendi. Kablosuz hata ayıklama eşleştirmesi hedef kitleye zor gelir. Kullanıcı da "PC'ye bağlama" akışını istedi.

Kullanıcı 1. yolu onayladı.

## 7. Kararlaştırılan tasarım

### 7.1 Genel yapı

```
mobileoptimizer/
  app/            # PySide6 arayüz
  core/
    adb.py        # adb sürecini çalıştırma, cihaz listesi, shell komutu
    device.py     # marka/model/Android/ROM tespiti
    actions.py    # işlem türleri: setting, package, compile, ...
    snapshot.py   # işlem öncesi durum kaydı ve geri alma
    profiles.py   # profil dosyalarını yükleme ve doğrulama
  profiles/       # veri: marka profilleri ve paket listeleri (YAML)
    generic.yaml
    samsung.yaml
    xiaomi.yaml
  vendor/adb/     # gömülü platform-tools (Windows + Linux)
```

Çekirdek (`core/`) arayüzden bağımsızdır ve testlerle çalışır. Testlerde sahte bir `adb` kullanılır.

### 7.2 Cihaz tespiti

`adb shell getprop` ile şunlar okunur:

- `ro.product.manufacturer`, `ro.product.brand`, `ro.product.model`
- `ro.build.version.release`, `ro.build.version.sdk`
- ROM: Samsung için `ro.build.version.oneui`; Xiaomi için `ro.miui.ui.version.name` / `ro.mi.os.version.name` (HyperOS)

Marka eşleşmezse genel profil kullanılır. Arayüz tespit edilen bilgiyi gösterir: "Samsung Galaxy A54 — One UI 6.1 — Android 14".

### 7.3 İşlem türleri

Her ayar bir **işlem**dir. İşlem verisi profil dosyasında tanımlanır. Desteklenen türler:

| Tür | Uygulama | Geri alma |
|-----|----------|-----------|
| `setting` | `settings put <global/system/secure> <key> <value>` | Eski değer `settings get` ile kaydedilir. Değer `null` ise geri almada `settings delete` çalışır. |
| `package_disable` | `pm disable-user --user 0 <pkg>` | `pm enable <pkg>` |
| `package_uninstall` | `pm uninstall -k --user 0 <pkg>` | `cmd package install-existing <pkg>` |
| `appops` | `cmd appops set <pkg> <op> <mode>` | Eski mod `cmd appops get` ile kaydedilir. |
| `standby_bucket` | `am set-standby-bucket <pkg> <bucket>` | Eski bucket kaydedilir. |
| `compile` | `cmd package compile -m speed-profile -a` (veya seçili paketler) | Geri alma gerekmez. İsteğe bağlı `cmd package compile --reset`. |
| `device_config` | `device_config put <ns> <key> <value>` | Eski değer kaydedilir. |

**Kalıcılık:** `standby_bucket`, `device_config` ve `compile` kalıcı değildir. Bucket'lar kullanım ile kayar, `device_config` Google sunucu senkronizasyonuyla ezilebilir, derleme arka plan optimizasyonuyla değişebilir. Bu işlemler arayüzde "geçici" rozetiyle gösterilir. Rapor bunları "uygulandı (zamanla sıfırlanabilir)" diye yazar. Uygulama her bağlantıda son profili kontrol eder. Sapma varsa "Yeniden uygula" düğmesi sunar. Telefonda arka planda yeniden uygulama yapılmaz.

Rastgele shell komutu çalıştıran bir işlem türü **yoktur**. Profil dosyası yalnızca yukarıdaki türleri kullanabilir. Bu kural güvenlik ve geri alınabilirlik içindir.

Her işlemin alanları:

- `id`, `title`, `description` (kullanıcıya gösterilir)
- `category`: performans / pil / temizlik
- `risk`: güvenli / dikkatli / uzman
- `min_sdk`, `max_sdk` (isteğe bağlı)
- `rom` koşulu (isteğe bağlı, ör. yalnızca HyperOS)

### 7.4 Risk seviyeleri ve paket listeleri

- **güvenli:** Kaldırılınca hiçbir temel işlev etkilenmez. Hazır profiller yalnızca bu seviyeyi kullanır.
- **dikkatli:** Bazı kullanıcılar için bir özelliği kapatabilir (ör. marka bulut yedekleme, tema mağazası). Yalnızca Özel modda, açıklamasıyla gösterilir.
- **uzman:** Yanlış kullanımda sorun çıkarabilir. Özel modda ayrı bir onayla açılır.

**Kaldırma ve devre dışı bırakma:** Hazır profiller ve "güvenli"/"dikkatli" seviyeleri yalnızca `package_disable` kullanır. `package_uninstall` yalnızca "uzman" seviyede bulunur. Sebep: güncellemesi yüklü bir sistem uygulaması kaldırılıp `install-existing` ile geri getirilirse fabrika sürümü gelir, güncellemeler kaybolur. Bu "geri alınamaz değişiklik yok" anti-hedefiyle çelişir. Uzman onay ekranı bunu açıkça yazar.

Kritik paketler üç katmanla korunur:

1. **Kod içi çekirdek kara liste:** marka bağımsız paketler. Örnek: `com.android.systemui`, `com.android.settings`, `com.android.phone`, `com.google.android.gms`, `com.android.vending`, paket yükleyici.
2. **Marka dosyası kara liste ekleri:** marka profili kendi kritik paketlerini (launcher, dialer, updater vb.) ekleyebilir. Profil dosyası kara listeye **yalnızca ekleme** yapabilir, çekirdek listeden çıkarma yapamaz.
3. **Cihazdan çalışma anında tespit:** varsayılan telefon, SMS, launcher ve klavye uygulaması cihazdan okunur (`cmd role get-role-holders`, `settings get secure default_input_method`, `cmd package resolve-activity` HOME). Bunlar otomatik kara listeye girer.

Profil bunlardan birine dokunmaya çalışırsa yükleme hata verir ya da işlem atlanır.

Paket listelerinin içeriği topluluk kaynaklarından (ör. Universal Android Debloater listeleri) derlenir. Her paket için risk etiketi ve kısa açıklama olur. Lisans uyumu kontrol edilir.

### 7.5 Hazır profiller

- **Maks Performans:** animasyon ölçekleri 0.5 (0 değil, çünkü bazı uygulamalar bozulabilir), en yüksek yenileme hızı (destekleniyorsa), arka plan derleme (`speed-profile`), güvenli bloatware kaldırma, marka performans modları (ör. Samsung'da işlemci "Performans" profili ayarı varsa).
- **Maks Pil:** standart yenileme hızı (60 Hz), agresif arka plan kısıtı (standby bucket), gereksiz reklam/analitik servislerinin kapatılması, Doze ayarları, güvenli bloatware kaldırma.
- **Dengeli:** temizlik + animasyon 0.5 + derleme. Pil ve yenileme hızına dokunmaz.

Kesin değerler marka profil dosyalarında durur. Değerlerin seçimi geliştiricinin işidir (bkz. bölüm 8).

### 7.6 Yedek ve geri alma

1. Herhangi bir işlemden önce uygulama bir uyarı ekranı gösterir: "Önemli verilerinizi (fotoğraf, rehber, mesaj) yedekleyin." Kullanıcı "Yedek aldım / anladım" kutusunu işaretlemeden devam edemez.
2. Her uygulama oturumundan önce **snapshot** alınır. Snapshot, dokunulacak her ayarın eski değerini ve her paketin eski durumunu (etkin/devre dışı/kurulu) içerir.
3. Snapshot PC'de JSON olarak saklanır. Konum: kullanıcı veri klasörü (`%APPDATA%/MobileOptimizer/snapshots/<cihaz-seri>/<tarih>.json`, Linux'ta `~/.local/share/...`).
4. Geri alma **katı sırayla** çalışır (son giren ilk çıkar). Kullanıcı bir snapshot seçerse, ondan sonraki tüm snapshot'lar da sondan başa geri alınır. Ekran bunu önceden gösterir: "Bu işlem 3 oturumu geri alacak." Tek işlem geri alma yalnızca o işleme sonraki oturumlar dokunmadıysa sunulur.
5. **"Fabrika ayarına dön"** seçeneği tüm snapshot'ları sondan başa geri alır.
6. **Snapshot kaybolursa yedek yol:** PC değişirse ya da uygulama silinirse "Kurtarma" seçeneği kullanılır. Bu seçenek o markanın tüm paket listelerindeki devre dışı paketleri yeniden etkinleştirir (`pm enable`). Kaldırılmış paketleri `install-existing` ile geri getirir. Animasyon ölçeklerini 1.0'a döndürür. Bu yol snapshot gerektirmez. Snapshot'ın bir kopyası ayrıca telefona da yazılır: `/sdcard/MobileOptimizer/`.
7. Bir işlem başarısız olursa o oturumun o ana kadar yaptığı işlemler sorulmadan geri alınmaz. Kullanıcıya rapor gösterilir ve geri alma önerilir.
8. Sistem güncellemesinden sonra snapshot cihazla uyuşmayabilir. Geri alma, cihazda artık olmayan paketleri ve anahtarları atlar ve raporda bunu belirtir.
9. Her işlem sonrası doğrulama yapılır: değer okunur ve beklenenle karşılaştırılır. Rapor her işlemi "uygulandı / atlandı (desteklenmiyor) / başarısız" olarak gösterir.

### 7.7 Arayüz akışı

```
[1 Bağlan]  ->  [2 Cihaz]  ->  [3 Profil]  ->  [4 Önizleme]  ->  [5 Uygula]  ->  [6 Rapor]
 USB rehberi    Samsung A54     ( ) Maks Perf    12 ayar          ilerleme       11 uygulandı
 cihaz bekle    One UI 6.1      ( ) Maks Pil     8 paket          çubuğu         1 atlandı
                Android 14      ( ) Dengeli      [Ayrıntı]                       [Geri al]
                                ( ) Özel
```

- **Önizleme** ekranı neyin değişeceğini açıkça listeler. Kullanıcı onaylamadan hiçbir şey uygulanmaz.
- **Özel** mod: kategori sekmeleri (Performans / Pil / Temizlik), her işlem için açıklama ve risk rozeti.
- Ana ekranda her zaman "Geri al / Geçmiş" düğmesi bulunur.
- Cihaz bağlantısı koparsa uygulama durur ve yarım kalan oturumu rapor eder.

### 7.8 Güvenlik ve gizlilik

- İnternet erişimi yoktur. Telemetri yoktur.
- Profil dosyaları uygulamanın içinde gelir. İlk sürümde internetten profil indirilmez.
- Kara liste ve izin verilen işlem türleri kodla zorunlu kılınır.
- Kaynak kod açık olacak. Lisans: **GPL-3.0** (sahibi onayladı). Bu lisans Universal Android Debloater listelerinin kullanılmasına izin verir. Kaynak her pakette belirtilir.

### 7.9 Dağıtım ve imzasız .exe

- Kod imzalama bütçesi yok. `.exe` imzasız dağıtılır.
- İndirme sayfasında ve uygulama içinde resimli bir **"Windows uyarısı" rehberi** bulunur: SmartScreen'de "Ek bilgi" ve ardından "Yine de çalıştır" adımları anlatılır. Antivirüs engellerse ne yapılacağı da anlatılır.
- Her sürümün SHA-256 özeti yayınlanır. Kullanıcı dosyanın değiştirilmediğini kontrol edebilir.
- Antivirüs yanlış alarmını azaltmak için PyInstaller `--onedir` (klasör + zip) tercih edilir, `--onefile` kullanılmaz. Her sürüm yayın öncesi VirusTotal'da taranır. Yanlış alarm veren üreticilere bildirim gönderilir.

### 7.10 Test cihazları

- **Samsung Galaxy A25** (One UI, Android 14/15): Samsung profili bu cihazda doğrulanır.
- **Redmi Note 14 4G** (HyperOS): Xiaomi profili bu cihazda doğrulanır.
- Genel profil Android emülatöründe (API 29, 34, 35) doğrulanır.
- Bu iki cihazda doğrulanmamış işlemler (ör. yalnızca eski MIUI'de olan anahtarlar) profilde "doğrulanmamış" olarak işaretlenir. Hazır profillere girmez, yalnızca Özel modda görünür.

## 8. Geliştiriciye bırakılanlar

- Her marka için kesin ayar anahtarları ve değerleri. Kaynak araştırılmalı, gerçek cihazda veya emülatörde doğrulanmalı.
- Paket listelerinin derlenmesi ve risk etiketlemesi.
- Arayüz görsel tasarımı (Qt widget'ları veya QML).
- Kodlama düzeni, test yapısı, paketleme betikleri.
- Windows USB sürücüsü tespitinin nasıl yapılacağı.

## 9. Açık sorular

Bu kararları ben (Claude) verdim, sahibi kontrol etmeli:

- Geçici işlemler için "geçici" rozeti ve "Yeniden uygula" düğmesi (7.3).
- Hazır profiller yalnızca devre dışı bırakma kullanır, kaldırma uzman seviyede (7.4).
- Üç katmanlı kara liste: kod + marka dosyası ekleri + cihazdan tespit (7.4).
- Katı sıralı geri alma, kurtarma yolu, telefonda snapshot kopyası (7.6).

Sahibinin cevapları (2026-11-14):

- Test cihazları: Samsung Galaxy A25, Redmi Note 14 4G (7.10).
- Lisans: GPL-3.0 (7.8).
- Kod imzalama bütçesi yok. Rehber eklenecek (7.9).

Açık soru kalmadı.
