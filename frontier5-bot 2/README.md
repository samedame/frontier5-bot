# FRONTIER-5 bot

One bot for the five-sleeve portfolio in `research/VERDICT.md`. It runs after the US close on GitHub Actions, computes all five signals, and posts to Discord only when something changes (plus a monthly status/rebalance message and a weekly heartbeat). The signal math is the research code, verified to match it to machine precision (`tests/test_parity.py`).

| Sleeve | Weight | Rule | Alerts when |
|---|---|---|---|
| A · Vol-targeted SPY | 30% | SPY exposure = clip(20% ÷ 21-day realized vol, 0, 2×). Above 100% is held as SPY + SSO | target exposure moves ≥ 15 points |
| B · ETF momentum | 25% | Monthly: top 5 of 10 ETFs by 252-day return skipping the last 21 days | the top-5 set changes (announced on the month's last trading day) |
| C · Diversified trend | 20% | 2.5% of the portfolio in each of 8 ETFs whose 126-day return is > 0, else cash | an asset flips ON/OFF |
| D · Bitcoin trend | 20% | Hold BTC iff close > 100-day average (weekday-sampled) | BTC crosses the average |
| E · QQQ mean reversion | 5% | Hold QQQ into tomorrow iff IBS < 0.30 | entry or exit |

Defaults you should know about: **sleeve B is in shadow mode** (it alerts, but is left out of the dollar table, so its 25% shows as cash) because it overlaps your 12-1 momentum sleeve and inherits that sleeve's open bootstrap question. Turn it live with `FRONTIER5_SHADOW=none`.

## Setup (10 minutes)

1. Create a private GitHub repo and push this folder (`git init && git add -A && git commit -m init && git remote add origin … && git push -u origin main`).
2. Repo → Settings → Secrets and variables → Actions:
   * Secret `DISCORD_WEBHOOK_URL`: a Discord channel webhook.
   * Variable `FRONTIER5_ACCOUNT_USD`: the capital you are allocating (for example `10000`). **Left unset on purpose**: the bot shows % of portfolio until you set it and never guesses a size.
   * Optional variables: `FRONTIER5_SHADOW` (default `B`; `none` for no shadow sleeves), `FRONTIER5_ENABLED` (default `ABCDE`), `FRONTIER5_A_BAND` (default `0.15`), `FRONTIER5_FRACTIONAL` (default `true`; `false` rounds to whole shares).
3. Settings → Actions → General → Workflow permissions → **Read and write** (the job commits `state/state.json`).
4. Actions → frontier5 → Run workflow. The first run posts "initial targets" (nothing is a change yet). After that it runs Mon–Fri at 21:30 UTC.
5. Run the dry run anywhere first if you like: `pip install -r requirements.txt && python -m frontier5.run --dry-run` (prints, never posts or writes state).

## Timing: read this before trading

The verdict labels its base case "signal at close t, execute close t+1". The code does something different: it takes the position **at the same close that produced the signal** (market-on-close with a near-final price). The verdict's "+1-bar delay" stress is the true next-close case. Measured in `research/STUDIES.md`:

| Fill | OOS CAGR | Sharpe | MaxDD |
|---|---|---|---|
| At the signal close (verdict headline) | 27.44% | 1.65 | -22.59% |
| At the next close | 24.96% | 1.51 | -24.01% |

The default `close` run posts after the final close, so trade at the **next trading day's close** and expect the second row. For the headline timing there is a **pre-close run at 3:45 pm ET** (`frontier5-preclose.yml`): it posts provisional signals from the in-progress bar, you trade the last minutes before 4:00, and the evening `close` run either confirms ("agrees with the pre-close alert") or posts a labelled CORRECTION. It is started by your `open-scheduler` Worker, not GitHub cron (late runs are useless; the bot refuses to start after 15:58 ET and skips holidays). Setup and the job entry are in `docs/SCHEDULING.md`.

## What reaches Discord

Measured by replaying the bot's own logic over 2016–2026 (`research/STUDIES.md`):

| Sleeve | Alerts / yr | Note |
|---|---|---|
| A | 21 | a 15-point band cut this from 175/yr with no change in results (27.5% OOS CAGR) |
| B | 6 | monthly |
| C | 56 | each flip is a 2.5%-of-portfolio trade |
| D | 5 | rare |
| E | 100 | about 50 round trips a year in a 5% sleeve; set `FRONTIER5_ENABLED=ABCD` to drop it |

Plus one status/rebalance message a month (target table, sleeve health, rebalance reminder) and a heartbeat after 7 quiet days. Delivery failures do not advance state, so the next run retries; any crash posts a red "bot error" message.

## Kill-switches (`frontier5/monitor.py`)

From VERDICT §8, computed on the model portfolio from the bot's own return series:

* **Bitcoin invalidation**: sleeve D 3-year Sharpe < 0 and more than 8 round trips in the last year.
* **Sleeve retirement**: any sleeve with 3-year Sharpe < 0 and deflated-Sharpe probability < 50% (hurdle Sharpe 0.86 at N=215).
* **Added by me, not in the verdict**: model-portfolio drawdown alerts at -15%, -20%, -25% from the trailing 3-year peak. It tracks the model, not your account, so compare the two.

Each fires once on entering the bad state.

## Known differences from the research scripts

* `research/daily_callout_original.py` sizes sleeve C at 20% ÷ (number of ON assets). The verdict says 2.5% per ON asset with the rest in cash; with 3 ON that is $75 per $1,000, not $200. The bot follows the verdict (`test_c_sleeve_sizing_is_one_eighth_per_asset`).
* The callout's sleeve B line is the ranking **as of today**. The sleeve actually holds the **month-end** ranking. Today those differ (GLD vs QQQ); the bot shows the held set and prints today's ranking as "if the month ended today".
* The monthly rebalance matters less than feared: monthly gives 27.9% OOS CAGR vs 27.4% for the verdict's daily-constant weights (Sharpe 1.63 vs 1.65). Yearly rebalancing lets BTC drift and takes drawdown to -33%.
* Sleeve A's leverage is idealized in the backtest. SSO volatility decay and its real expense ratio are not modeled; the verdict flags this.

## Limits you inherit

BTC's 2016–2021 run supplies most of the OOS excess return (no-BTC core: 12.5% CAGR, Sharpe 1.03); plan on the verdict's 12–20% zone, not 27%. Taxes are not modeled and sleeves A and E trade daily, so prefer a tax-advantaged account. B and C hold 2.5–5% slices, so confirm fractional-share support (the whole-share rounding option exists but degrades small accounts). The BTC bar for the current day is still forming at run time, so a crossing within 1.5% of the average is flagged "marginal".

## Layout

```
frontier5/   config · data · signals · engine (backtest) · events · portfolio · monitor · notify · state · run
tests/       parity vs research code, alert logic, kill-switches, Discord payloads, end-to-end run
research/    VERDICT.md inputs: winner_strategy.py (oracle), daily_callout_original.py, studies.py -> STUDIES.md
state/       state.json is created and committed by the workflow
```

`pip install -r requirements-dev.txt && pytest -q` runs 30 tests (point `FRONTIER5_PARQUET` at the research `data/` folder to include the real-data parity test).
