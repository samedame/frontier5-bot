"""FRONTIER-5 daily callout — run after US close: python3 daily_callout.py [account_usd]
Prints today's target positions in plain English. Signals execute NEXT close (t+1) as backtested."""
import warnings; warnings.filterwarnings('ignore')
import sys, numpy as np, pandas as pd, yfinance as yf
ACCT=float(sys.argv[1]) if len(sys.argv)>1 else 10000
TICKERS=['SPY','QQQ','IWM','EFA','EEM','TLT','IEF','GLD','DBC','VNQ','XLE','BTC-USD']
raw=yf.download(TICKERS,period='2y',auto_adjust=True,progress=False)
C=raw['Close'] if 'Close' in raw else raw.xs('Close',axis=1,level=0)
H=raw['High'] if 'High' in raw else raw.xs('High',axis=1,level=0); L=raw['Low'] if 'Low' in raw else raw.xs('Low',axis=1,level=0)
C=C[C['SPY'].notna()]; last=C.index[-1]
print(f"=== FRONTIER-5 CALLOUT — signals as of close {last.date()} (execute next close) | account ${ACCT:,.0f} ===")
spy=C['SPY'].dropna(); vol=spy.pct_change().rolling(21).std().iloc[-1]*np.sqrt(252); lev=float(np.clip(0.20/vol,0,2))
print(f"[A 30%] SPY vol-target: exposure {lev:.0%} (21d vol {vol:.1%} vs 20% target) -> hold ${0.30*lev*ACCT:,.0f} equity exposure (SPY, plus SSO for the part above 100%; rest cash).")
UNI=['SPY','QQQ','IWM','EFA','EEM','TLT','GLD','DBC','VNQ','XLE']
mom=(C[UNI].iloc[-22]/C[UNI].iloc[-274]-1).dropna().sort_values(ascending=False); top=list(mom.index[:5])
print(f"[B 25%] ETF momentum top-5 (monthly): {', '.join(top)} — ${0.25*ACCT/5:,.0f} each (rebalance only at month-end; 12m return ex-last-month ranking: "+", ".join(f'{t} {mom[t]:+.0%}' for t in top)+")")
BASK=['SPY','EFA','EEM','TLT','IEF','GLD','DBC','VNQ']; on=[t for t in BASK if C[t].iloc[-1]/C[t].iloc[-127]-1>0]
print(f"[C 20%] Diversified trend ON for: {', '.join(on) if on else 'none — hold cash'} — ${0.20*ACCT/max(len(on),1):,.0f} in each ON asset, cash otherwise.")
btc=C['BTC-USD'].dropna(); sma=btc.rolling(100).mean().iloc[-1]; inbtc=btc.iloc[-1]>sma
print(f"[D 20%] Bitcoin trend: BTC ${btc.iloc[-1]:,.0f} vs 100d avg ${sma:,.0f} -> {'HOLD $'+f'{0.20*ACCT:,.0f}'+' in BTC' if inbtc else 'NO Bitcoin — hold this 20% in cash/T-bills'}.")
q=C['QQQ'].dropna(); ibs=(q.iloc[-1]-L['QQQ'].reindex(q.index).iloc[-1])/((H['QQQ'].reindex(q.index).iloc[-1]-L['QQQ'].reindex(q.index).iloc[-1])+1e-12)
print(f"[E 5%] QQQ mean-reversion: IBS={ibs:.2f} -> {'BUY/HOLD $'+f'{0.05*ACCT:,.0f}'+' QQQ into tomorrow' if ibs<0.3 else 'no trade — stay in cash on this sleeve'}.")
print("Reminder: 1.0x sizing is the recommended (balanced) point. Do not lever above 1.25x. Rules/failure modes: research/VERDICT.md")
