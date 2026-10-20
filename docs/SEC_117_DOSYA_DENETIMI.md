# SEC gerçek veri arşivi — ilk kapsam denetimi

**Tarih:** 20 Ekim 2026  
**Analiz:** Yerelde mevcut SEC Company Facts arşivindeki 117 adet `CIK*.json.gz` örneği üzerinde normalleştirme testi. Arşiv, SEC'den bu çalışmada yeniden indirilmedi.

## Bulgular

| Kontrol | Adet |
| --- | ---: |
| İncelenen Company Facts kaydı | **117** |
| Seçilen yıllık döneme kaynaklı gelir bulabilen kayıt | **109** |
| Kaynaklı `OperatingIncomeLoss` / faaliyet kârı bulabilen kayıt | **98** |
| Kaynaklı CFO bulabilen kayıt | **109** |
| Kaynaklı CapEx bulabilen kayıt | **91** |
| Son dönem için aynı başlangıç ve bitiş tarihli gelir + EBIT çıkarabilen kayıt | **92** |
| Asgari tarihsel eşleştirmeye ulaşamayan kayıt | **25** |
| Yıllık dönem üretilemeyen kayıt | **8** |

Bu bir **kapsam testi** ve ön kalite taramasıdır; 92 şirketin muhasebe rakamlarının bağımsız doğrulandığı, DCF ile değerlendiği veya tahmin başarı testinden geçtiği anlamına gelmez. `INCOMPLETE_PERIODS` uyarısı 73 kayıt için görüldü; bu uyarı yalnız son dönemi değil, seçilmiş tarihsel dönemlerdeki gelir, EBIT, CFO veya CapEx eksiklerini de kapsayabilir.

## Neden 25 dosyada sonuç üretilmedi?

- Bazı şirketler standart `OperatingIncomeLoss` XBRL etiketini kullanılabilir biçimde raporlamıyor; alternatif şirket etiketleri veya farklı sektör sunumları söz konusu olabilir.
- Bazı şirketler IFRS veya farklı SEC rapor formatını kullanabiliyor; bu sürüm sadece `10-K/10-K/A` US-GAAP yıllık kayıtlarını normalize ediyor.
- Bazı şirketlerde son tarihli gelir/EBIT ikilisi aynı yıllık dönem başlangıcı/bitişiyle bulunmuyor.
- Bazı kayıtlar hiç uygun yıllık veri içermiyor.

Eksik faaliyet kârı için **vergi öncesi kâr veya net kârı sessizce EBIT yerine koymuyoruz**. Bu işletmenin sektörüne ve muhasebesine göre yanlış bir DCF sonucu üretebilir.

## Açık inceleme görevleri

1. Eksik/şirket-özel SEC XBRL kavramlarına kaynak ve sektör onaylı eşleme eklemek.
2. Yıllık dönem eşleştirmesinde 52/53 haftalık finansal yılları ve yeniden düzenlenen verileri özel kontrol etmek.
3. CFO, CapEx ve gelir kavramlarını gerçek 10-K tablolarıyla örnekleme usulü elle karşılaştırmak.
4. Finans kuruluşlarını ayrı modele almak; borç, finansman ve nakit akışı yapıları sanayi şirketlerinden farklıdır.
5. Başlangıç tarihini, hisse adedini ve net borcu denetim izinde ayrı belgelemek.
6. Gözlem örneklemini genişleterek dönem ve para birimi uyumsuzluklarını regresyon testine dönüştürmek.

**Denetim ilkesi:** Eksik veri olduğunda sayı üretmek yerine açık hata/uyarı döndürmek. Sayı üretilebilmesi ekonomik doğruluğu veya yatırım sonucunu kanıtlamaz.

İlgili modüller: [sec_companyfacts.py](../sec_companyfacts.py), [sec_v02_bridge.py](../sec_v02_bridge.py). Test çalıştırma: `python -m unittest discover -s tests -v`.
