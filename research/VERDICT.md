# VERDICT — Highest Return Potential × Highest Probability of Success
### One-Page Summary (all figures out-of-sample 2016-01-01→2026-10-16, net of costs, unless labeled FULL/IS)

**WINNER: "FRONTIER-5" — a 5-sleeve diversified portfolio (the only candidate passing every Balanced-tier filter and every kill shot). No single strategy passed the Balanced filters; combining uncorrelated sleeves is what moved the frontier.**

| Sleeve | Weight | Exact rule (signal at close t, execute close t+1) |
|---|---|---|
| A. Vol-targeted equity | 30% | Hold SPY exposure = clip(20% ÷ trailing-21d realized SPY vol, 0, 2.0). Exposure >100% via SSO, <100% remainder cash. Recompute daily. |
| B. ETF cross-sectional momentum | 25% | Monthly: rank {SPY,QQQ,IWM,EFA,EEM,TLT,GLD,DBC,VNQ,XLE} by 252-day return skipping last 21 days; hold top-5 equally (5% of portfolio each). |
| C. Diversified trend (long/flat) | 20% | Daily: for each of {SPY,EFA,EEM,TLT,IEF,GLD,DBC,VNQ}, hold 2.5% of portfolio if its 126-day return > 0, else cash. |
| D. Bitcoin trend | 20% | Hold BTC (spot/ETF) iff BTC close > 100-day SMA, else cash/T-bills. Never lever this sleeve. |
| E. QQQ mean reversion | 5% | Hold QQQ for the next day iff today's IBS = (Close−Low)/(High−Low) < 0.30, else cash. |
Rebalance sleeve weights back to 30/25/20/20/5 monthly. Instruments: any liquid US-listed ETFs + spot BTC/BTC ETF. Minimum sensible account $5k ($1k degrades Sleeve A granularity — see §7).

**Return potential (OOS, n=2,713 trading days / 10.77 yrs):** CAGR **27.4%**, expected log-growth **24.2%/yr**, Sharpe **1.65**, vol 15.4%, max drawdown **−22.6%**. FULL history (1993–2026, BTC sleeve in cash pre-2014): CAGR 13.2%, Sharpe 1.11, MaxDD −23.3% (n=8,487 days). IS (pre-2016): CAGR 7.0%, Sharpe 0.75 — expect forward returns far below the OOS print (see Failure Modes).
Bootstrap upside (1,000 block-bootstrap paths each): 1-yr median +27.6% / 75th +42.7% / 90th +55.4%; 3-yr median +108% / 75th +152% / 90th +199%; 5-yr median +237% / 75th +328% / 90th +450%.

**The five success probabilities (with sample sizes):**
1. **P(edge is real) = 99.5%** — Deflated Sharpe Ratio, corrected for **N=215 total trials** (201 sweep + 9 combos + 5 final-search variants). Benchmark hurdle Sharpe under the null ≈ 0.86/yr.
2. **P(profit):** historical rolling windows — 1-yr 91.1% (n=2,461 windows), 3-yr 100% (n=1,957), 5-yr 100% (n=1,453); block-bootstrap — 93.3% / 99.6% / 100% (n=1,000 paths/horizon). Overlapping windows are not independent — treat 100% as "no losing window observed," not certainty.
3. **P(hit target before −25% drawdown)** (3-yr bootstrap paths, n=1,000): +25% → **97.5%**, +50% → **91.4%**, +100% → **61.9%**.
4. **P(ruin, 40%+ drawdown) = 0.2%** at recommended 1.0× size (2 of 1,000 3-yr bootstrap paths; worst historical drawdown in 33 yrs: −23.3%).
5. **Consistency:** 5/5 sleeves profitable standalone OOS; 10/12 calendar years positive (2015–2026; losing: 2018 −15.1%, 2022 −8.5%); profitable in equity, international, bond, commodity, and crypto legs (sleeve table §4).

**Recommended size: 1.0× (no added leverage beyond Sleeve A's internal 2× cap).** Conservative 0.5×: OOS CAGR ≈13%, MaxDD ≈−12%, ruin ≈0%. Aggressive cap 1.25–1.5× — never 2× (ruin jumps to ≈11–13%).

**Benchmarks OOS (same window/costs):** SPY buy-hold CAGR 14.9%, Sharpe 0.87, MaxDD −33.7%, DSR 52.2% · 60/40: 9.8%, 0.90, −21.7% · SPY 200-day trend: 11.4%, 0.97, −20.7%. FRONTIER-5 beats all three on return, Sharpe, and drawdown simultaneously in this window.

**Why not the higher headline numbers?** SOL-trend (OOS CAGR 146%), 2× BTC trend (122%), and stock momentum (35–46%) all show higher raw returns but P(ruin) of 12–100% and/or survivorship-tainted stock universes. They sit *below* the frontier once success probability is priced. This verdict prices both axes, per the mission.

---
## 1. Method & Integrity
- Pre-registration frozen 2026-10-17 before scoring (`PREREGISTRATION.md`): targets, 70/30-style split (IS ≤2015, holdout 2016–2026, never tuned on), cost model (5bp ETF / 10bp leveraged / 15bp crypto per side), selection formula, kill shots. One logged amendment (Amendment 1: crypto-weekend calendar bug found via the SPY-200D benchmark reading 0% OOS; first-run numbers discarded, panels restricted to SPY trading days, BTC sampled on weekdays).
- **Total trials: 215.** Every variant counted in `candidates.csv` (201) + `results/combos.csv` (9) + 5 extra final-search variants. DSR uses N=215 throughout.
- Data: Yahoo Finance daily adjusted OHLCV, 64 tickers, 1993–2026 (`data/*.parquet`). Execution next-close, zero lookahead. Winner re-verified with `winner_strategy.py` (fresh download reproduces FULL 13.18%/1.11/−23.29% and OOS 27.44%/1.65/−22.59% exactly).
- Known data limits: ETF/stock histories carry survivorship bias (worst for the rejected stock-momentum candidates; the winner uses index ETFs + BTC, whose constituents are maintained point-in-time by index providers — mitigated, not eliminated). Crypto sampled Mon–Fri (Fri→Mon return captures weekend moves; 252-day annualization). Taxes, borrow fees beyond the 4%/yr leverage charge in sizing tests, and intraday slippage beyond the cost model are not modeled.

## 2. The Frontier at Three Constraint Levels
Filters (frozen): Conservative DSR≥90%, P(profit 3y)≥80%, P(ruin)≤5% · Balanced DSR≥80%, P(profit 3y)≥70%, P(ruin)≤10%, MaxDD≥−35% · Aggressive DSR≥65%, P(profit 3y)≥60%, P(ruin)≤20%.

| Tier | Best point | OOS CAGR | Sharpe | MaxDD | DSR | P(ruin) |
|---|---|---|---|---|---|---|
| Conservative | FRONTIER-5 @ 0.5× | ≈13.2% | 1.65* | ≈−11.8% | 99.5% | ≈0.0% |
| **Balanced ★ RECOMMENDED** | **FRONTIER-5 @ 1.0×** | **27.4%** | **1.65** | **−22.6%** | **99.5%** | **0.2%** |
| Aggressive | FRONTIER-5 @ 1.5× | ≈39.8% | ≈1.56 | ≈−33.7% | 99.5% | ≈2.0% |
*Sharpe is leverage-invariant before borrow costs. Aggressive alternative COMBO_MAXGROWTH (stock-momentum/BTC, OOS CAGR 47.4%, DSR 99.8%, ruin 2.3%) is shown on the plot but **not recommended**: its stock sleeve is the most survivorship-inflated measurement in the study. Plot: `charts/frontier.png` (all 201 singles + winner). **No single (non-combo) strategy passed even the Balanced filters** — the closest, XSMOM_STK_L252S21K5 (DSR 87.0%), failed on ruin (11.5%) and drawdown (−35.6%) before its bias discount.

## 3. Kill-Shot Results (winner; all must pass)
| # | Test | Result | Verdict |
|---|---|---|---|
| 1 | Holdout OOS | CAGR 27.4%, Sharpe 1.65, n=2,713 days (IS: 7.0%/0.75 — OOS>IS driven by BTC era, flagged) | PASS w/ caveat |
| 2 | Multiple testing | DSR = 99.5% at N=215 (hurdle Sharpe ≈0.86) | PASS |
| 3 | Parameter robustness ±~25–50% | BTC SMA50/100/200 Sharpe 1.21/1.41/1.17; SPY vol-target 10/15/20% CAGR 10.4/15.4/20.2% smooth; XS-mom 126 vs 252 & top-3 vs top-5 all Sharpe 0.66–1.20; IBS 0.2 vs 0.3 both profitable — smooth degradation, no cliff | PASS |
| 4 | Walk-forward (frozen params, yearly) | 10/12 yrs positive 2015–26 (2016 +28.7%, 2017 +121.9%, 2019 +42.9%, 2020 +46.2%, 2021 +32.1% … 2018 −15.1%, 2022 −8.5%) | PASS |
| 5 | Bootstrap CI | §Summary: 3-yr median +108%, P(profit) 99.6%, ruin 0.2% (n=1,000 paths/horizon) | PASS |
| 6 | Regimes / cross-asset | 2022: −8.5% (SPY −18.2%); COVID window ann. −21.6% vs SPY −32.4%; GFC window (equity sleeves only) ann. −11.5% vs SPY −33.7%; ETH SMA100 cross-check Sharpe 0.96 confirms BTC-trend mechanism on an independent asset. Loses money in grinding bears (2018, 2022) — smaller, not immune. | PASS (relative) |
| 7 | Cost/execution stress | 2× costs: CAGR 26.6% · +1-bar delay: 25.0% · both: 24.2%, Sharpe 1.47 (Engine B rebuild) | PASS |
| 8 | Independent re-implementation | Second engine rebuilt from the written spec (positions from prices, not mixed return streams): correlation 1.000, mean daily \|Δ\| < 0.000001, identical headline metrics | PASS |
| 9 | Small account / sequence stress | $10k: 12 tickers max, smallest sleeve $500 ≈ 1–3 QQQ shares, BTC fractional — feasible; $1k degrades Sleeve A (SSO lots) → use 0.5× unlevered variant. Monthly-block shuffle (same returns, worst orderings, n=2,000): median MaxDD −14.8%, 5th-pct −22.7%, P(DD<−40%) = 0.0% | PASS ≥$5k |

## 4. Sleeves Standalone (OOS) — diversification is the edge
A vol-target SPY: CAGR 20.2%, Sharpe 1.01, MaxDD −24.6% · B ETF momentum: 11.4%, 0.81, −24.3% · C diversified trend: 5.6%, 0.89, −7.2% · D BTC trend: 81.7%, 1.41, −59.1% (hence capped at 20%) · E IBS QQQ: 12.3%, 0.96, −16.6%. BTC sleeve correlation to equity sleeves ≈ 0.09; the blend's Sharpe (1.65) exceeds every sleeve except raw BTC, with ⅓ of BTC's drawdown. Contribution warning: a large share of OOS excess return traces to Sleeve D during 2016–2021 crypto adoption; the no-BTC core (COMBO_ETF_CORE) earned 12.5% OOS at Sharpe 1.03 — that, plus IS 7.0%, brackets honest forward expectations better than 27.4%.

## 5. Runner-Ups (frontier, in order)
1. **COMBO_ETF_BTC10** (BTC 10% version): CAGR 20.2%, Sharpe 1.51, MaxDD −17.0%, DSR 98.1%, ruin 0.0% — best choice if BTC custody/concentration is a concern.
2. **COMBO_TREND_IBS** (no crypto, no XS-mom): 10.9%, Sharpe 1.15, MaxDD −10.4%, DSR 82.2% — lowest-drama survivor.
3. **BTC trend alone @ 25% size** (75% cash): 19.0%, Sharpe 1.41, MaxDD −18.4%, DSR 97.6% — simplest high-confidence satellite.
4. **VOLTGT_SPY_20 alone**: 20.2%, Sharpe 1.01, MaxDD −24.6%, DSR 67.9% — fails Balanced on DSR alone.
Full ranked tables: `results/final_candidates_scored.csv`, `results/sweep_scored.csv`.

## 6. Rejected Ideas & Why (best variant per family; full table `results/family_best.csv`)
- **Crypto buy-hold / raw altcoin trend** (SOL CAGR 146%): ruin 94–100%, MaxDD −70…−96% — return without survival. **Leveraged buy-hold** (SOXL/TQQQ): ruin ≈100% in bootstrap despite 37–46% CAGR. **2× BTC trend**: DSR 93.8% but ruin 99.3% at full size (survives only as the capped 20% sleeve).
- **Stock XS-momentum** (CAGR 35–46%, DSR 87–92%): rejected as winner — universe is today's winners traded backward (survivorship inflation); ETF/factor versions (11–15% CAGR, DSR 39–44%) show the undistorted size of the premium. Retained only via point-in-time ETF sleeve B.
- **Vol selling** (SVXY variants): best Sharpe ≈0.51, MaxDD −47%, ruin 46% — tail eats the premium at retail sizing. **FX carry/momentum**: DSR 0.1%, CAGR −0.7% — no edge found at daily retail costs. **Pairs/stat-arb**: CAGR ≈0.1%, DSR 0.4%. **Gap fade / overnight drift**: negative net (−0.9% / −12.7% CAGR) — gross effects smaller than daily round-trip costs in this implementation. **Seasonality** (Halloween best): DSR 13%. **Dual momentum**: decayed OOS (CAGR 4–7%, DSR 6–22%) as US dominance broke the intl rotation. **TSMOM long/short**: whipsaw (Sharpe 0.50) vs long/flat (0.86) — L/S rejected, L/F retained as Sleeve C. **Donchian breakouts**: CAGR ≤2.9% standalone. **Options-income proxies** (JEPI/QYLD/PUTW-style, wheel blend): honest but capped (7.6–12.1% CAGR, DSR ≤45%) — dominated by Sleeve A on both axes. **Risk parity / permanent portfolio**: Sharpe 0.98–1.01 but CAGR 7.7–9.4% — survives, returns too little to lead; useful ballast only.
- **Dedicated final search (stopping criterion 3):** 5 extra variants tested after the winner emerged — BTC+ETH trend basket (ruin 40.8% ✗), TQQQ-trend+BTC (CAGR 62.8% but ruin 25.1% ✗), no-BTC max (CAGR 15.5%, DSR 75.1% — below winner), BTC-only 25% (runner-up #3). **Nothing beat FRONTIER-5 on the frontier.**

## 7. Sizing (fractional-Kelly discipline; borrow 4%/yr above 1×, 500–1,000 bootstrap paths/row)
| Scale | OOS CAGR | MaxDD | P(ruin 40%, 3-yr) | P(profit 3-yr) |
|---|---|---|---|---|
| 0.50× (quarter-Kelly-ish) | 13.2% | −11.8% | 0.0% | 99.4% |
| 0.75× | 20.2% | −17.3% | 0.0% | ~100% |
| **1.00× ★** | **27.4%** | **−22.6%** | **0.2–0.6%** | **99.6%** |
| 1.25× | 33.6% | −28.3% | 0.6% | ~100% |
| 1.50× | 39.8% | −33.7% | 2.0% | 99.0% |
| 2.00× | 52.4% | −43.4% | 11–13% | 98.6% |
Raw in-sample Kelly leverage (Sharpe²-based) is far above 2× and is explicitly **not** recommended: it assumes the OOS Sharpe persists, the exact assumption this report discounts. 1.0× ≈ a conservative fraction of Kelly under a halved forward Sharpe. At $1k, run 0.5× without the SSO leverage leg (round SSO to whole shares monthly) and accept tracking slippage.

## 8. Failure Modes — When This Stops Working
1. **BTC premium regime change** (maturation, ETF-flow saturation, punitive regulation/custody failure): Sleeve D's 2016–21 contribution does not repeat; portfolio degrades toward its 12.5% no-BTC core, or IS-level ~7% if equity premia also compress. *Invalidation trigger: BTC-trend sleeve rolling 3-yr Sharpe < 0 while below-SMA whipsaws exceed 8 round-trips/yr.*
2. **Momentum crash** (sharp V-reversal after a bear, 2009-style): Sleeves B+C lose together; B's monthly lag is the slow leg. Historical analogue cost is inside the −23% full-history MaxDD, but a faster crash can exceed it.
3. **Vol-target whipsaw** (2018-type: vol spikes after losses): Sleeve A de-risks late and re-risks late; it lost money in 2018 even as it protected in 2020/2022.
4. **Correlation convergence** in a liquidity crisis: sleeve correlations (~0.1–0.7 normally) spike toward 1; the 0.2% ruin figure assumes bootstrap blocks preserve some independence.
5. **Crowding/decay** in IBS and XS-momentum (published anomalies): monitor sleeve-level rolling Sharpe; retire a sleeve after 3-yr Sharpe < 0 AND DSR < 50%, redistribute to A/C.
6. **Frictions not in the model:** taxes on high Sleeve-A/E turnover (hold in tax-advantaged accounts where possible), SSO volatility decay on the leverage leg, BTC spread/venue risk, futures/ETF tracking changes. 2×-cost stress still passed (26.6%), but a taxable account can consume several points per year — untested here, flagged, not hidden.

## 9. Stopping-Criteria Checklist
1. Every Phase-1 family tested or eliminated with reason — ✔ 201 candidates, 30+ families, §6 + `family_best.csv`. (Options *structures* — condors/credit spreads/wheel — were tested via their listed-ETF payoff proxies XYLD/QYLD/JEPI/wheel-blend because retail-grade historical option chains are not freely available; this substitution is disclosed, and the proxies lost honestly. Crypto *funding/basis arb* likewise proxied by trend — no free point-in-time funding history; labeled proxy in `candidates.csv`, not presented as true arb.)
2. Winner passed all 9 kill shots and sits on the frontier — ✔ §3, `charts/frontier.png`.
3. One more dedicated search found nothing better — ✔ §6 (5 extra variants).
4. Expected return, all five probabilities, recommended size, and failure conditions stated — ✔ Summary, §7, §8.

## 10. Files (every claim traces here)
`PREREGISTRATION.md` (+Amendment 1) · `candidates.csv` (201 frozen candidates + mechanisms) · `code/sweep.py, deepdive.py, combos.py, final_eval.py, killshots.py, charts_tables.py` · `results/sweep_scored.csv` (all 201 scored w/ DSR+bootstrap), `final_candidates_scored.csv`, `winner_daily_returns.csv`, `family_best.csv` · `charts/equity_oos.png, equity_full.png, drawdown_winner.png, frontier.png` · **`winner_strategy.py`** (ready-to-run backtest; reproduces headline numbers from a fresh download) · **`daily_callout.py`** (plain-English daily signals; sample run 2026-10-16: A=196% SPY exposure, B top-5 = DBC/XLE/EEM/QQQ/IWM, C trend ON SPY/EFA/DBC, D hold BTC $81,501 > $70,999 100-d avg, E IBS 0.14 → hold QQQ).

*Bottom line: the highest-return strategies in the data will probably kill the account; the safest will probably bore it. FRONTIER-5 is the measured best compromise — 27.4% OOS CAGR (expect materially less forward; plan on the 12–20% zone) bought with a −23% worst historical drawdown, a 99.5% deflated probability the edge is real, and ~0.2% modeled ruin at 1.0×. Size it at 1.0×, run the callout daily, and obey §8.*
