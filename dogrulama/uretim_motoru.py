"""Independent implementation of frozen 0.1 contract; not imported from reference engine."""
import math

VERSION = 'uretim-0.1.0'

def _sequence(value, length):
    if isinstance(value, (float, int)):
        return [float(value) for _ in range(length)]
    result = list(value)
    if len(result) != length:
        raise ValueError('length mismatch')
    return [float(v) for v in result]

def degerle(girdi):
    p = dict(girdi)
    faults = []
    n = p['yillar']
    r = p['iskonto']; growth_terminal = p['uc_buyume']
    if n < 1: faults.append('YIL_SAYISI_GECERSIZ')
    if r <= 0: faults.append('ISKONTO_GECERSIZ')
    if growth_terminal >= r: faults.append('UC_BUYUME_ISKONTOYU_ASIYOR')
    if growth_terminal > p.get('uc_buyume_tavani', .04): faults.append('UC_BUYUME_TAVAN_USTU')
    if p['uc_roic'] <= 0: faults.append('UC_ROIC_GECERSIZ')
    if p['satis_sermaye'] <= 0: faults.append('SATIS_SERMAYE_GECERSIZ')
    if p['hisse'] <= 0: faults.append('HISSE_GECERSIZ')
    if not (0 <= p['vergi_orani'] < 1): faults.append('VERGI_GECERSIZ')
    mode = p.get('sbc_yontemi', 'gider')
    if mode not in ('gider', 'sulandirma'): faults.append('SBC_YONTEMI_GECERSIZ')
    if mode == 'gider' and p.get('yillik_sulandirma', 0) > 0: faults.append('SBC_CIFT_SAYIM')
    timing = p.get('iskonto_zamani', 'yil_sonu')
    if timing not in ('yil_sonu', 'yil_ortasi'): faults.append('ISKONTO_ZAMANI_GECERSIZ')
    if faults: return {'durum':'gecersiz','hatalar':faults,'uyarilar':[]}
    try:
        growths = _sequence(p['buyume'], n)
        margins = _sequence(p['faaliyet_marji'], n)
    except (ValueError, TypeError):
        return {'durum':'gecersiz','hatalar':['LISTE_UZUNLUGU_UYUMSUZ'],'uyarilar':[]}
    tax = p['vergi_orani']; capital = p['satis_sermaye']
    extra_margin = p.get('sbc_gelire_orani',0.0) if mode == 'sulandirma' else 0.0
    prior_revenue = float(p['gelir_0'])
    rows = []
    operating_pv = 0.0
    for year, (gr, margin) in enumerate(zip(growths, margins), start=1):
        revenue = prior_revenue * (1 + gr)
        operating_profit_after_tax = revenue * (margin + extra_margin) * (1-tax)
        invested = (revenue-prior_revenue)/capital
        cash = operating_profit_after_tax - invested
        exponent = year - (0.5 if timing == 'yil_ortasi' else 0)
        factor = (1+r)**(-exponent)
        present = cash * factor
        operating_pv += present
        rows.append(dict(yil=year,gelir=revenue,nopat=operating_profit_after_tax,
                         yeniden_yatirim=invested,fcff=cash,iskonto_faktoru=factor,bugunku_deger=present))
        prior_revenue = revenue
    terminal_nopat = prior_revenue*(1+growth_terminal)*(margins[-1]+extra_margin)*(1-tax)
    terminal_cash = terminal_nopat*(1-growth_terminal/p['uc_roic'])
    terminal_value = terminal_cash/(r-growth_terminal)
    terminal_pv = terminal_value/(1+r)**n
    enterprise = operating_pv + terminal_pv
    equity = enterprise-p.get('net_borc',0.0)
    share_count = p['hisse'] * (1+p.get('yillik_sulandirma',0.0))**n if mode == 'sulandirma' else p['hisse']
    terminal_share = terminal_pv/enterprise if enterprise>0 else None
    alerts = []
    if any(x>0 for x in growths) and (margins[-1]+extra_margin)*(1-tax)*capital < r: alerts.append('BUYUME_DEGER_YIKIYOR')
    if any(x['fcff']<0 for x in rows): alerts.append('NEGATIF_FCFF_YILLARI')
    if terminal_share is not None and terminal_share>.85: alerts.append('UC_DEGER_BASKIN')
    if p['uc_roic']<r and growth_terminal>0: alerts.append('UC_ROIC_ISKONTO_ALTINDA')
    if equity<0: alerts.append('OZSERMAYE_NEGATIF')
    return dict(durum='gecerli',hatalar=[],uyarilar=alerts,tablo=rows,acik_donem_bd=operating_pv,
                uc_deger=terminal_value,uc_deger_bd=terminal_pv,firma_degeri=enterprise,
                ozsermaye_degeri=equity,hisse_sayisi_kullanilan=share_count,
                hisse_basi_deger=equity/share_count,uc_deger_payi=terminal_share,motor_surumu=VERSION)

def ters_dcf(girdi, fiyat, alt=-.5, ust=1.0, adim=1500):
    fixed = ['faaliyet_marji','satis_sermaye','vergi_orani','iskonto','uc_buyume',
             'uc_roic','net_borc','hisse','sbc_yontemi','iskonto_zamani']
    def residual(rate):
        params = dict(girdi,buyume=rate)
        outcome = degerle(params)
        if outcome['durum'] != 'gecerli':
            raise ValueError(outcome['hatalar'])
        return outcome['hisse_basi_deger']-fiyat
    roots = []
    old_x = alt
    old_y = residual(old_x)
    for i in range(1, adim+1):
        new_x = alt+(ust-alt)*i/adim
        new_y = residual(new_x)
        if old_y == 0:
            roots.append(old_x)
        elif old_y*new_y < 0:
            lo,hi = old_x,new_x
            f_lo = old_y
            for _ in range(100):
                middle = (lo+hi)/2
                f_middle = residual(middle)
                if f_lo*f_middle <= 0:
                    hi = middle
                else:
                    lo,f_lo = middle,f_middle
            roots.append((lo+hi)/2)
        old_x,old_y = new_x,new_y
    if old_y == 0: roots.append(ust)
    status = 'tek_cozum' if len(roots)==1 else 'coklu_cozum' if roots else 'cozum_yok'
    return {'durum':status,'ima_edilen_buyume':roots[0] if len(roots)==1 else None,
            'tum_cozumler':roots,'sabit_tutulanlar':fixed,'arama_araligi':[alt,ust]}
