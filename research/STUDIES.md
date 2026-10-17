# FRONTIER-5 bot design studies

Data through 2026-10-16; OOS = 2016-01-01 onward (the verdict's holdout).

## 1. Timing: where the verdict's 'execute next close' label sits

| Fill assumption | OOS CAGR | Sharpe | MaxDD |
|---|---|---|---|
| lag 1 (verdict base case): trade AT the close that produced the signal | 27.44% | 1.65 | -22.59% |
| lag 2 (verdict '+1-bar delay'): trade at the NEXT close | 24.96% | 1.51 | -24.01% |

## 2. Sleeve A alert band

| Band | OOS CAGR (lag 1) | Sharpe | MaxDD | A target changes / yr |
|---|---|---|---|---|
| 0.00 | 27.44% | 1.65 | -22.59% | 175 |
| 0.05 | 27.47% | 1.65 | -22.52% | 56 |
| 0.10 | 27.47% | 1.65 | -22.49% | 32 |
| 0.15 | 27.50% | 1.65 | -22.50% | 21 |
| 0.20 | 27.45% | 1.65 | -22.58% | 16 |
| 0.25 | 27.67% | 1.65 | -22.91% | 13 |

## 3. Rebalancing the five sleeves

| Policy | OOS CAGR | Sharpe | MaxDD |
|---|---|---|---|
| Daily to target weights (research backtest, zero cost) | 27.44% | 1.65 | -22.59% |
| Monthly rebalance (5 bp / 15 bp BTC on traded amount) | 27.87% | 1.63 | -23.62% |
| Quarterly rebalance | 31.67% | 1.65 | -26.79% |
| Yearly rebalance (BTC drifts far above 20% in between) | 35.42% | 1.52 | -32.85% |

Yearly is the longest period the helper supports; with BTC drifting far above its 20% target the drawdown rises.

## 4. Alert frequency (bot logic replayed bar by bar, 2016+)

| Sleeve | Alerts / yr | Meaning |
|---|---|---|
| A | 21.3 | exposure moved >= 15 points |
| B | 5.9 | monthly rotation changed the top-5 set |
| C | 56.0 | an asset's 126d trend flipped |
| D | 5.4 | BTC crossed its 100d average |
| E | 99.9 | IBS entry or exit |
| all | 188.5 | plus one status message per month |
