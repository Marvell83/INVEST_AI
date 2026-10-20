"""Experimental v0.2 primitives. Not wired into the frozen 0.1 engine."""
import math

def vergi_defteri(ebit_serisi, oran, baslangic_zarar=0.0):
    if not 0 <= oran < 1 or baslangic_zarar < 0: raise ValueError('tax inputs')
    balance=float(baslangic_zarar)
    rows=[]
    for year, ebit in enumerate(ebit_serisi,1):
        if ebit < 0:
            balance += -ebit
            used=0.0
            taxable=0.0
        else:
            used=min(balance,ebit)
            balance-=used
            taxable=ebit-used
        rows.append({'yil':year,'ebit':ebit,'kullanilan_zarar':used,
                     'vergilendirilebilir_kar':taxable,'nakit_vergi':taxable*oran,
                     'kalan_zarar':balance})
    return rows

def marj_yolu(baslangic, hedef, yakinlasma, yil):
    if not 0<=yakinlasma<=1 or yil<0: raise ValueError('margin inputs')
    return hedef+(baslangic-hedef)*(1-yakinlasma)**yil

def roiic_tanisi(nopat_serisi, onceki_yatirimlar):
    if len(nopat_serisi)!=len(onceki_yatirimlar)+1: raise ValueError('length')
    return [(nopat_serisi[i+1]-nopat_serisi[i])/yat if yat>0 else None
            for i,yat in enumerate(onceki_yatirimlar)]

def tum_kokler(f, alt, ust, adim=4096, x_tol=1e-10, y_tol=1e-9):
    """Exploratory grid + bracket + tangent detection. Completeness NOT guaranteed."""
    if not alt<ust or adim<3: raise ValueError('bounds')
    points=[alt+(ust-alt)*i/adim for i in range(adim+1)]
    values=[float(f(x)) for x in points]
    if not all(math.isfinite(v) for v in values): raise ValueError('non-finite function')
    roots=[]
    def record(x):
        if abs(f(x))<=y_tol and all(abs(x-old)>max(1e-7,x_tol*10) for old in roots): roots.append(x)
    for i in range(adim+1):
        if abs(values[i])<=y_tol: record(points[i])
    for i in range(adim):
        a,b=points[i],points[i+1]; fa,fb=values[i],values[i+1]
        if fa*fb<0:
            for _ in range(100):
                mid=(a+b)/2; fm=f(mid)
                if abs(fm)<=y_tol or b-a<=x_tol: break
                if fa*fm<=0: b,fb=mid,fm
                else: a,fa=mid,fm
            record(mid)
    # local minima of absolute residual; golden-section minimization
    for i in range(1,adim):
        if values[i-1]*values[i+1]>0 and abs(values[i])<=abs(values[i-1]) and abs(values[i])<=abs(values[i+1]):
            a,b=points[i-1],points[i+1]
            phi=(math.sqrt(5)-1)/2
            c=b-phi*(b-a); d=a+phi*(b-a)
            for _ in range(100):
                if b-a<=x_tol: break
                if abs(f(c))<abs(f(d)):
                    b,d=d,c;c=b-phi*(b-a)
                else:
                    a,c=c,d;d=a+phi*(b-a)
            record((a+b)/2)
    return sorted(roots)
