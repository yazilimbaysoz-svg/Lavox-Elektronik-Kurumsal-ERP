<div align="center">

# LAVOX Elektronik Kurumsal ERP

**Kurumsal iş akışları tek, Türkçe ve yerel bir çalışma alanında.**

*BAYSÖZ YAZILIM · Windows masaüstü deneyimi · ERP v2.0*

</div>

[![İndir: v2.0.0](https://img.shields.io/github/v/release/yazilimbaysoz-svg/Lavox-Elektronik-Kurumsal-ERP?label=Lavox_ERP_Setup.exe&color=0078d4)](https://github.com/yazilimbaysoz-svg/Lavox-Elektronik-Kurumsal-ERP/releases/tag/v2.0.0)

**📦 [Windows Kurulum Sihirbazı v2.0.0 indir](https://github.com/yazilimbaysoz-svg/Lavox-Elektronik-Kurumsal-ERP/releases/tag/v2.0.0)** — `Lavox_ERP_Setup.exe` doğrudan [v2.0.0 Release sayfası](https://github.com/yazilimbaysoz-svg/Lavox-Elektronik-Kurumsal-ERP/releases/tag/v2.0.0) üzerinden indirilebilir.

---

## Proje hakkında

LAVOX Elektronik Kurumsal ERP; elektronik perakende, stok ve teknik servis süreçleri için geliştirilen Türkçe bir işletme uygulamasıdır. Kontrol panelinden envantere, POS satışından teklif ve raporlamaya kadar günlük operasyonları tek arayüzde bir araya getirir.

Arayüz, uygulamanın yerel FastAPI servisi üzerinden çalışır ve işletme verilerini SQLite veritabanında saklar. Windows kullanıcıları için masaüstü başlatıcısı ve adım adım kurulum sihirbazı da kaynak koda dahildir. Kurulum sihirbazı, kurumsal Windows ERP kurulum deneyimlerinden ilham alan bağımsız bir BAYSÖZ YAZILIM ürünüdür; Akınsoft ile bir bağlantısı veya onayı olduğu iddia edilmez.

### Öne çıkanlar

- **10 çalışma alanı:** Yönetim paneli, envanter, seri numarası ve garanti, teknik servis, POS, satın alma, cari hesaplar, finans, teklifler/faturalar ve analitik.
- **Hızlı komut araması:** `Ctrl+K` (macOS'ta `⌘K`) ile ürün, seri numarası, cari ve servis kayıtlarına erişim.
- **Windows dağıtımı:** Yerel masaüstü başlatıcısı ve `Lavox_ERP_Setup.exe` üreten kurulum sihirbazı kaynakları.
- **Türkçe arayüz:** Varsayılan çeviriler `locales/tr.json` ve `frontend/locales/tr.json` içinde tutulur.
- **KVKK odaklı yardımcılar:** Parola özeti, kişisel alanlar için maskeleme yardımcıları ve denetim kayıtları. Bunlar tek başına mevzuata uygunluk sertifikası değildir.
- **Yerel veri:** Veritabanı uygulama çalışma alanında tutulur; dondurulmuş Windows uygulamasında kullanıcı veri dizinine yönlendirilir.

### 10 kurumsal modül

| # | Modül | Kapsam |
|---:|---|---|
| 1 | Kontrol Paneli | Günlük/aylık KPI'lar, satış özeti ve operasyon uyarıları |
| 2 | Stok Yönetimi | Ürün kataloğu, depo stokları ve kritik seviye takibi |
| 3 | Seri No ve Garanti | Seri/IMEI takibi, garanti sorgusu ve depolar arası transfer |
| 4 | Teknik Servis | Servis kabulü, iş emirleri, durum ve parça takibi |
| 5 | POS Satış | Satış kalemleri, ödeme yöntemleri ve işlem geçmişi |
| 6 | Satın Alma | Tedarikçi siparişleri ve teslim alma |
| 7 | Cari Hesaplar | Müşteri ve tedarikçi kartları |
| 8 | Kasa ve Banka | Hesap bakiyeleri ve finansal hareketler |
| 9 | Teklif ve Fatura | Belge oluşturma, takip ve teklifi faturaya dönüştürme |
| 10 | Analitik ve Raporlar | Kâr-zarar, tahsilat ve ürün kalite göstergeleri |

## Kurulum ve çalıştırma (Windows)

### Gereksinimler

- Windows 10/11
- Python 3.10 veya üzeri
- Masaüstü paketlemesi için Windows .NET Framework C# derleyicisi

### Kaynaktan çalıştırma

PowerShell'i proje klasöründe açın:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-runtime.txt
```

İlk açılışta güvenli yönetici hesabı oluşturulmalıdır. `LAVOX_INITIAL_ADMIN_USERNAME`, `LAVOX_INITIAL_ADMIN_EMAIL` ve en az 14 karakterli `LAVOX_INITIAL_ADMIN_PASSWORD` değerlerini yalnızca geçerli PowerShell oturumunda veya kurumunuzun gizli bilgi yöneticisinde tanımlayın. Parolayı kaynak koda, komut dosyalarına, `.env` dosyasına ya da Git geçmişine eklemeyin. Başlangıç verisi gerçek kişi veya varsayılan parola içermez; mevcut kullanıcı bulunan veritabanları değiştirilmez.

İlk veritabanı kurulumundan sonra uygulamayı başlatın:

```powershell
.\LAVOX_BASLAT.bat
```

Uygulama varsayılan olarak `http://127.0.0.1:8010` adresinde yalnızca bu bilgisayardan erişilebilir şekilde çalışır. Mevcut kullanıcı kayıtları varsa ilk kurulum değişkenlerine gerek kalmaz.

### Windows kurulum paketi

Masaüstü uygulamasını ve sihirbazı üretmek için:

```powershell
python -m pip install -r requirements-desktop.txt
python build_exe.py
.\build_native_setup.ps1
```

`build_native_setup.ps1`, `Lavox_ERP_Setup.exe` dosyasını Windows masaüstünüze üretir. Kurulum paketi ve derlenmiş uygulama dosyaları yeniden üretilebilir çıktılardır; bu Git deposuna eklenmez.

### Testler

```powershell
python -m unittest discover -s tests -v
```

## KVKK ve güvenli kullanım

`backend/kvkk_security.py`, parola saklama ve maskeleme yardımcılarını, rol kontrolü ve denetim kayıtlarını içerir. Hassas üretim verisini yalnızca yetkili sistemlerde işleyin; erişim, yedekleme, saklama süresi, aydınlatma/açık rıza gereklilikleri ve ihlal süreçleri kurumunuz tarafından ayrıca değerlendirilmelidir.

Bu uygulama yerel masaüstü kullanımı için yapılandırılmıştır. Ağ arayüzünü değiştirmeden dahi kurumsal güvenlik incelemesi yapın; uygulamayı internete veya güvenilmeyen bir ağa açmayın. Örnek/yerel veritabanları, yedekler, günlükler, kimlik bilgileri ve derlenmiş dosyalar `.gitignore` ile dışarıda tutulur.

## Technical architecture

### Runtime components

- **API and business logic:** Python 3, FastAPI, Pydantic request models, and service modules under `backend/services/`.
- **Persistence:** SQLite with schema initialization, foreign keys, transactional connection handling, and parameterized SQL statements.
- **Web interface:** Semantic HTML, CSS, and vanilla JavaScript; Turkish strings are loaded from the locale JSON files.
- **Windows desktop:** `desktop_app.py` hosts the local API and opens the UI in `pywebview`. The C# launcher and installer wizard sources package the Windows experience.
- **Packaging:** `build_exe.py` invokes PyInstaller; `build_native_setup.ps1` compiles the launcher and wizard using the Windows .NET Framework compiler.

### Repository layout

```text
backend/                 API, database, security helpers, and business services
frontend/                Turkish ERP interface and static assets
locales/                 Desktop and shared Turkish translations
tests/                   Focused desktop and bootstrap tests
assets/                  Application icon
desktop_app.py           Windows desktop runtime
build_exe.py             PyInstaller build entry point
build_native_setup.ps1   Native Windows setup package build
```

### Development notes

- Keep customer databases, real identifiers, credentials, logs, and build outputs out of source control.
- Run the focused unittest suite before packaging or publishing changes.
- The project does not include a license grant. Add a license explicitly before granting reuse rights.
