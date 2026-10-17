"""FRONTIER-5 winner — ready-to-run backtest (see research/VERDICT.md for full spec).
Sleeves: A SPY vol-target20 (30%) | B ETF XS-momentum top5 252-21 monthly (25%) |
C diversified TSMOM long/flat 126d (20%) | D BTC SMA100 trend (20%) | E QQQ IBS<0.3 (5%).
Signal close t -> execute close t+1. Costs 5bp ETF / 15bp BTC per unit turnover.
Run: python3 winner_strategy.py  (needs: pip install yfinance pandas numpy pyarrow)
"""
import warnings; warnings.filterwarnings('ignore')
import numpy as np, pandas as pd, yfinance as yf
TICKERS=['SPY','QQQ','IWM','EFA','EEM','TLT','IEF','GLD','DBC','VNQ','XLE','BTC-USD']
def load():
    raw=yf.download(TICKERS,start='1993-01-01',auto_adjust=True,progress=False)
    close=raw['Close'] if 'Close' in raw else raw.xs('Close',axis=1,level=0)
    high=raw['High'] if 'High' in raw else raw.xs('High',axis=1,level=0)
    low=raw['Low'] if 'Low' in raw else raw.xs('Low',axis=1,level=0)
    bdays=close['SPY'].dropna().index
    return close.reindex(bdays), high.reindex(bdays), low.reindex(bdays)
def backtest(cost_mult=1.0, extra_lag=0, data=None):
    close,high,low = data if data else load()
    lag=1+extra_lag
    spy=close['SPY'].dropna(); rspy=spy.pct_change()
    scale=(0.20/(rspy.rolling(21).std()*np.sqrt(252))).clip(0,2)
    posA=scale.shift(lag); retA=posA*rspy-posA.diff().abs().fillna(0)*0.0005*cost_mult
    UNI=['SPY','QQQ','IWM','EFA','EEM','TLT','GLD','DBC','VNQ','XLE']
    mom=close[UNI].pct_change(252).shift(21); mm=mom.resample('ME').last()
    W=pd.DataFrame(0.0,index=mm.index,columns=UNI)
    for d,row in mm.iterrows():
        r=row.dropna().sort_values(ascending=False)
        if len(r)>=5: W.loc[d,r.index[:5]]=0.2
    W=W.resample('D').ffill().reindex(close.index).ffill().fillna(0).shift(lag)
    retB=(W*close[UNI].pct_change()).sum(axis=1)-W.diff().abs().sum(axis=1).fillna(0)*0.0005*cost_mult
    BASK=['SPY','EFA','EEM','TLT','IEF','GLD','DBC','VNQ']
    WC=pd.DataFrame({t:(close[t].pct_change(126)>0).astype(float)/len(BASK) for t in BASK})
    WC=WC.shift(lag).fillna(0)
    retC=(WC*close[BASK].pct_change()).sum(axis=1)-WC.diff().abs().sum(axis=1).fillna(0)*0.0005*cost_mult
    btc=close['BTC-USD'].dropna(); posD=(btc>btc.rolling(100).mean()).astype(float).shift(lag).reindex(close.index).ffill().fillna(0)
    retD=posD*btc.pct_change().reindex(close.index)-posD.diff().abs().fillna(0)*0.0015*cost_mult
    q=close['QQQ'].dropna(); ibs=(q-low['QQQ'].reindex(q.index))/((high['QQQ'].reindex(q.index)-low['QQQ'].reindex(q.index))+1e-12)
    posE=(ibs<0.3).astype(float).reindex(close.index).fillna(0).shift(lag)
    retE=posE*close['QQQ'].pct_change()-posE.diff().abs().fillna(0)*0.0005*cost_mult
    return 0.30*retA.fillna(0)+0.25*retB.fillna(0)+0.20*retC.fillna(0)+0.20*retD.fillna(0)+0.05*retE.fillna(0)
if __name__=='__main__':
    r=backtest(); oos=r[r.index>='2016-01-01'].dropna()
    for lab,s in [('FULL',r.dropna()),('OOS 2016+',oos)]:
        yrs=len(s)/252; cum=(1+s).cumprod()
        print(f"{lab}: CAGR={(cum.iloc[-1]**(1/yrs)-1):.2%} Sharpe={s.mean()*252/(s.std()*np.sqrt(252)):.2f} MaxDD={(cum/cum.cummax()-1).min():.2%} (n={len(s)} days)")
