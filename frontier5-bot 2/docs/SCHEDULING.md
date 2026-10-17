# Scheduling the 3:45 pm ET pre-close run

GitHub's native cron on this account runs hours late (see the 2026-09-25 incident note), and a pre-close run
that starts after the bell is worthless. So the pre-close run is started by the Cloudflare `open-scheduler`
Worker via `workflow_dispatch`, like your other bots, with the bot enforcing its own window as a second guard.

## 1. Add the job to open-scheduler

I have not seen the Worker's source. This entry follows the job fields described in the 2026-10-08 wiring note
(`repo`, `workflow`, `ref`, `at`, `grace`, `watchdog`, `weekdays`, `skip_holidays`); match the names to the real list.
The repo name assumes `samedame/frontier5-bot`; change it if you name the repo differently.

```js
{
  name: "frontier5-preclose",
  repo: "samedame/frontier5-bot",
  workflow: "frontier5-preclose.yml",
  ref: "main",
  at: "15:45",      // ET, Worker handles DST
  grace: 10,        // minutes the Worker keeps retrying; the bot itself refuses to start after 15:58 ET
  watchdog: 4,
  // Mon-Fri; the Worker's holiday table skips market holidays (the bot also skips a day with no session bar)
}
```

The Worker sends `scheduled_for_et` and `trigger` as workflow inputs; `frontier5-preclose.yml` declares both.
Optional second job so the confirmation arrives on time instead of hours late:

```js
{ name: "frontier5-close", repo: "samedame/frontier5-bot", workflow: "frontier5.yml", ref: "main",
  at: "16:30", grace: 90, watchdog: 4 }
```

The native 21:30 UTC cron in `frontier5.yml` stays as a backup. A duplicate is harmless: the bot skips a bar it
already processed.

## 2. Test it by hand first

```bash
gh workflow run frontier5-preclose.yml -f trigger=manual -f skip_window_check=true   # any hour, uses today's partial bar
gh workflow run frontier5-preclose.yml -f trigger=manual                              # enforces the 9:35-15:58 ET window
```

## What the bot does at 15:45

| Situation | Behavior |
|---|---|
| Normal session day | Posts "signal change" (if any) marked PROVISIONAL, saves state with the bar flagged provisional |
| Starts at/after 15:58 ET | Posts "pre-close run missed its window"; no state change; the evening run still posts |
| Market holiday (no bar for today) | Silent skip |
| Weekend or before 9:35 ET | Silent skip |
| Evening `close` run, same bar | "Pre-close signals confirmed", or a CORRECTION for any sleeve whose final-close signal differs |

Trade in the last minutes before 4:00 pm ET (market-on-close orders where your broker supports them).

## How close is a 3:45 reading to the final close?

Measured on the last 60 sessions (2026-07-24 to 2026-10-16) with 15-minute bars, comparing the 3:45 pm reading with the final daily bar:

* **Sleeve E (IBS):** the buy/stay-out decision differed on **7 of 60 days (12%)**. Mean IBS gap 0.076, 90th percentile 0.158. This is the sleeve that will generate CORRECTION messages. It is 5% of the portfolio.
* **Sleeve A:** SPY at 3:45 differed from the close by 0.21% on average (max 0.50%). The 21-day vol input barely moves, so A's target is effectively unchanged.
* **Not measured:** B, C and D. B is decided by a ranking that skips the last 21 days; C and D compare a return or price with a threshold, so they only flip when they are already near it. BTC trades around the clock, so its 3:45 ET reading is not the daily UTC close the backtest used.

Starting later (for example 15:50) shrinks these gaps but leaves less time to place the trade. The window is a constant in `frontier5/run.py` (`PRECLOSE_USABLE_UNTIL`) and the time is the Worker job's `at` field.
