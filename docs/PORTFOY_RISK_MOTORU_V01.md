# INVEST_AI — Portföy Risk Motoru v0.1

**Amaç:** Tekil hisse analizinin ötesinde, *gerçek adetler ve aynı tarihteki USD fiyatlar* biliniyorsa portföy ağırlıklarını, sektör yoğunlaşmasını, kullanıcı tanımlı ortak temaları ve senaryo duyarlılığını hesaplamak.

**Dosyalar:** `portfoy_risk.py`, `tests/test_portfoy_risk.py` ve `ornekler/portfoy_risk_SENTETIK_8_HISSE.json`.

**Kurulum:** Python 3.11+; yalnız standart kütüphane. İnternet veya ücretli hizmet gerekmez.

## Çalıştırma

Windows PowerShell veya komut isteminde depo kökünden:

```powershell
python portfoy_risk.py --portfolio ornekler/portfoy_risk_SENTETIK_8_HISSE.json --out raporlar/portfoy_risk_ornek.json
python -m unittest discover -s tests -p test_portfoy_risk.py -v
python -m unittest discover -s tests -v
```

**Dikkat:** Örnekte gerçek hisse kodları bulunsa bile *adetler, fiyatlar, alış maliyetleri ve stres oranları tamamen sentetiktir*. Çıktı gerçek portföy performansı veya güncel piyasa analizi değildir.

## Girdi sözleşmesi

```json
{
  "schema_version": "invest-ai-portfolio-0.1",
  "base_currency": "USD",
  "as_of": "2026-10-24",
  "cash_usd": 100,
  "positions": [
    {
      "ticker": "NVDA",
      "quantity": "0.75",
      "cost_per_share_usd": 185.25,
      "price_usd": 210.96,
      "price_date": "2026-10-23",
      "price_source": "manual broker statement",
      "instrument_type": "equity",
      "sector": "semiconductors",
      "themes": ["ai_chips"]
    }
  ],
  "theme_unions": {"ai_connected": ["ai_chips", "ai_infrastructure", "ai_energy"]},
  "scenarios": []
}
```

- `quantity`: tam veya **kesirli hisse**. Hassasiyet için `"0.75"` gibi sayısal dizge kullanabilirsiniz; 0 veya negatif miktar reddedilir.
- `price_usd`: bir hisse başına **USD** fiyatı. Kaynak doğrulaması kullanıcıya aittir. Gelecek tarihe ait fiyat kabul edilmez; 7 günden eski fiyat uyarı üretir.
- `cost_per_share_usd`: bilinmiyorsa alanı atlayın. Eksik maliyet 0 kabul edilmez; toplam gerçekleşmemiş kâr/zarar `null` olur. Komisyonlar maliyete ayrıca eklenmediyse hesap bunları içermez.
- `cash_usd`: alım için elde tutulan USD nakit; toplam servet paydasında yer alır. Nakit portföy stresinde değişmez kabul edilir.
- `instrument_type`: `equity` veya `fund`. ETF'nin içindeki şirketleri **ayrıştırmayız**; bunu raporda açıkça belirtiriz.
- `sector`, `themes`: **analistin manuel sınıflandırması**dır, kesin ekonomik beta veya nedensel ilişki değildir. Temalar örtüşebilir.
- `theme_unions`: AI ile ilişkili ayrı temalardan seçilen şirketleri **bir kez** sayar. Tekil tema yüzdelerini toplamayın; örneğin NVDA hem `ai_chips` hem `ai_infrastructure` etiketli olabilir.
- `fx_usdtry` (isteğe bağlı): `{"rate": 49.6, "date": "2026-10-23"}`; tek bir tarihte USD cinsinden toplamı TL'ye çevirir. Geçmiş USD alım maliyetlerini bugünkü kurla çarpmak **gerçek TL kârı vermez**; motor TL kârı üretmez.
- `scenarios` (isteğe bağlı): `name`, `horizon`, `rationale` ve `shocks_pct` içerir. Her senaryoda tüm hisse kodlarına ait ayrı ayrı varsayımsal değişim oranları *zorunludur*. Eksik şirket %0 şok varsayılmaz.

## Çıktılar ve yorum

| Alan | Yorum |
|---|---|
| `total_market_value_usd` | USD menkul kıymet piyasa değeri + USD nakit |
| `weight_total_pct` | Bir şirketin nakit dahil toplam portföydeki payı |
| `weight_invested_pct` | Bir şirketin yalnızca yatırım yapılmış portföydeki payı |
| `unrealized_pnl_usd` | Tam maliyet verisi varsa mevcut piyasa değeri eksi USD alış maliyetleri |
| `largest_holding_pct_of_invested` | En büyük şirket yoğunlaşması |
| `top_three_pct_of_invested` | En büyük üç pozisyonun toplam payı |
| `hhi_invested` | Pozisyon paylarının kareleri toplamı, 0–1 arası |
| `effective_number_of_positions` | 1/HHI; **bağımsız ekonomik risklerin sayısı değildir** |
| `sector_allocation` | Tek sektör/pozisyon sınıflandırmasına dayanan paylar |
| `theme_exposures` | Örtüşebilen etiketsel tema ağırlıkları; toplamları %100'ü geçebilir |
| `theme_unions` | Aynı şirketi yalnız bir kez sayan birleşik yatırım temaları |
| `theme_coverage_pct_of_invested` | En az bir kullanıcı etiketi bulunan varlık payı |
| `scenarios` | Kullanıcı tarafından yazılan şok varsayımlarının portföyde oluşturacağı mekanik değişim |

Bu rapor, kaç adet hisse bulunduğundan fazlasını söyler; ancak bir sektörün gerçek beta katsayısını, tarihsel korelasyonlarını veya çöküş olasılığını hesaplamaz. Ayrıca hisse önerisi/satış kararı **üretmez**.

## Örnek, sadece matematik gösterimi

Örnekte sentetik sekiz şirket + 30 USD nakit vardır. Sonuç:

- Yatırım piyasa değeri: **2.970 USD**; nakit dahil toplam **3.000 USD**.
- Manuel sınıflandırılmış AI ile ilişkili altı şirketin benzersiz birleşik payı: **2.370 USD (%79 toplam portföy)**.
- USD gerçekleşmemiş kâr/zarar: **252,50 USD** (yalnız örnek maliyet varsayımı).
- Temel stres varsayımıyla etki: **−681,50 USD**, nakit dahil toplam üzerinde yaklaşık **−%22,72**. Bu bir olasılık veya tahmin değil, tamamen örnek senaryo aritmetiğidir.

## Bilinen eksikler / sonraki sürüm

1. Broker CSV'sinden otomatik, güvenli içe aktarma; maliyetin çok lotlu/komisyonlu hesaplanması.
2. Ticker/CIK eşlemesi, fonların gerçek güncel içeriklerinin kaynaklı olarak incelenmesi.
3. Tarihli fiyat veri kaynağı ve split/temettü muhasebesi.
4. Tarihsel korelasyon, risk katkısı, drawdown, likidite ve beta; **yeterli veri olmadan tahmin edilmeyecek**.
5. Veri güvenilirliği ve analist etiketi onay süreçleri; alım/satım önerisi motoru değil, araştırma aracı.

Finansal tavsiye değildir.
