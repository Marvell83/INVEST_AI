# INVEST_AI'yi Windows EXE olarak GitHub'dan indirme

BAP uygulamasında denenen GitHub **Actions → Artifacts ZIP** yöntemi INVEST_AI için de kullanılabilir. Bu sürüm **Python kurulu olmadan çalışan**, yerel tarayıcı arayüzünü açan Windows paketidir; yatırım programı exe'de gelen Python motoruyla bilgisayarında çalışır. GitHub Actions üzerindeki Windows derleme/EXE sağlık kontrolü yapılır.

## Windows uygulamasını indirme

1. GitHub deposunda **Actions** sekmesini aç: [INVEST_AI Windows EXE](https://github.com/Marvell83/INVEST_AI/actions/workflows/windows-exe.yml).
2. Solda **INVEST_AI Windows EXE** iş akışını seç.
3. En güncel başarılı (yeşil ✓) **main** çalıştırmasını aç.
4. Sayfa sonundaki **Artifacts** bölümünde **INVEST_AI_Windows_EXE** dosyasını indir.
5. İnen ZIP'e sağ tıkla → **Tümünü ayıkla**.
6. Ayıklanan klasördeki **INVEST_AI.exe** dosyasını çift tıkla. **`_internal` klasörünü silme; EXE tek başına yeterli değil.**
7. Siyah konsol penceresi açık kalır ve tarayıcıda `http://127.0.0.1:RASTGELE_PORT/#araclar` açılır. Konsoldaki **WEB ANALİZ ANAHTARI**'nı analiz formuna yapıştır. Pencereyi kapatınca yerel sunucu durur.

**Yeni EXE gerektiğinde:** Actions → INVEST_AI Windows EXE → **Run workflow** → Branch **main** → Run workflow. Başarılı işlemden sonra Artifacts indir. Bu iş akışı, gerekli dosyalar değiştiğinde main üzerinde de otomatik derlenir. GitHub Actions çalıştırmaları ve artifact saklama plan kotalarına tabidir.

**Güvenlik:** Uygulama sadece `127.0.0.1` adresinde dinler; internette yayınlanmaz. İmzasız Windows EXE olduğundan bazı Windows güvenlik sistemleri dosyayı sorgulayabilir. Kaynağı ve GitHub iş akışını doğrula, antivirüs taramasını yap; güvenlik korumasını genel olarak devre dışı bırakma.

## Verilerin yeri ve kalıcılığı

Windows'ta aşağıdaki klasör otomatik oluşur:

```text
%LOCALAPPDATA%\INVEST_AI\
    index.html
    SEC_USER_AGENT.txt
    veri\
       invest_ai_evren.sqlite3
       sec_ticker_esleme.json
       companyfacts.zip          (isteğe bağlı, yaklaşık 1.4 GB)
    reports\
```

Yükselttiğin EXE'nin yeni klasöre taşınması **veritabanını silmez**. Yazılım, kaynak kodlarındaki küçük HTML örneğini günceller; `veri\` ve `reports\` içeriklerine dokunmaz.

### Codespaces'teki 5.003 şirketlik veritabanını Windows'a taşıma

**GitHub deposunun Code → Download ZIP komutu `veri/` klasörünü içermez**; `.gitignore` ile Git dışındadır.

Yalnız iki dosya yeterlidir:

- `/workspaces/INVEST_AI/veri/invest_ai_evren.sqlite3` — 8.024 kayıt ve finansal rasyoları
- `/workspaces/INVEST_AI/veri/sec_ticker_esleme.json` — ticker/CIK eşleştirmesi

Codespaces'te çalışan SEC taraması varsa bitir; Python web uygulamasını kapat. Ardından aşağıdaki komutla SQLite WAL kayıtlarını ana veritabanına işle:

```bash
cd /workspaces/INVEST_AI
python3 - <<'PY'
import sqlite3
with sqlite3.connect("veri/invest_ai_evren.sqlite3") as db:
    print(db.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone())
PY
```

Codespaces Explorer (`Ctrl+Shift+E`) içinde `veri` klasörüne git. Her iki dosyaya sağ tıkla ve **Download / İndir** seç. Windows'ta `Win+R` → `%LOCALAPPDATA%\INVEST_AI\veri` → Enter; indirdiğin iki dosyayı oraya kopyala. Windows EXE'yi yeniden başlat.

Artık **Analiz Çalıştır → Temel analiz tablosu** bölümünde taşıdığın mevcut SEC verileri görünecek, tekrar 1,4 GB indirme yapman gerekmeyecek. 5.003 `OK` finansal şirketin tabloya aktarılabilir; bu, tüm 50+ finansal oranın her şirkette dolu olduğu anlamına gelmez.

### Büyük SEC ZIP gerekli mi?

**Mevcut oranlarla filtreleme yapmak için HAYIR.** Yalnız SQLite + ticker haritası yeterli. Yeni SEC evreni işlemeyi veya `--retry-errors` benzeri arşiv gerektiren işleri Windows'ta çalıştırmak istersen `companyfacts.zip` dosyasını da aynı `veri` klasörüne ayrıca kopyalayabilir ya da resmî SEC'den indirtebilirsin. GitHub repo/Actions artifact içine 1,4 GB ham veri eklemiyoruz.

### SEC kullanıcı kimliği

Var olan verileri okumak için `SEC_USER_AGENT` gerekmiyor. **Yeni SEC veri indirmek** istersen `Win+R` → `%LOCALAPPDATA%\INVEST_AI\SEC_USER_AGENT.txt` adresindeki son satırı gerçek iletişim e-postanla düzenle:

```text
SEC_USER_AGENT=INVEST_AI Research ad@kurum.gov.tr
```

Bu dosya yalnızca bilgisayarında kalır; kesinlikle GitHub'a yükleme. EXE'yi yeniden başlat.

## Farklar ve sınırlar

- Bu Windows **masaüstü başlatıcısı**, BAP sisteminin Django programı değildir. INVEST_AI'nin kendi yerel Python HTTP sunucusunu paketler.
- Bir uygulama yükleyicisi (MSI), otomatik güncelleme, Windows servis veya uzak sunucu kurmaz.
- **Bir klasör içinde EXE** dağıtır: ZIP içindeki `_internal` silinirse program açılmaz.
- Şirketin fiyatına bağımlı PEG/FK/PD-DD gibi rasyolar, yalnız SEC Company Facts ile otomatik dolmaz; kaynaklı ek fiyat/ileri EPS verisine ihtiyaç var.
- `invest_ai_masaustu.py --self-test`, Windows GitHub Actions derlemesinde gerçek paketlenmiş HTTP sağlık testi yapar.

## Geliştirici için yerel kaynak kullanımı

```bash
python3 -m unittest discover -s tests -p test_invest_ai_masaustu.py -v
python3 invest_ai_masaustu.py --self-test
python3 invest_ai_masaustu.py
```

## Kaynaklar

- GitHub [Manually running a workflow](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/manually-run-a-workflow)
- GitHub [Downloading workflow artifacts](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/download-workflow-artifacts)
- PyInstaller [Run-time information](https://pyinstaller.org/en/stable/runtime-information.html)
