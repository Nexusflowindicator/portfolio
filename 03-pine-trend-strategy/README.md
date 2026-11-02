# Trend Pullback Pro (TradingView Pine Script v6)

A trend-following strategy for TradingView with professional risk management, built to give
**honest** backtests: no repainting, no lookahead, and trading costs included by default.

![cover](screenshots/cover.png)

## Logic
- **Trend:** fast EMA (21) above slow EMA (55), price above the slow EMA, and the higher-timeframe
  close above its own EMA (auto HTF = 4× the chart timeframe). Mirror rules for shorts.
- **Entry:** price pulled back to the fast EMA within the last N bars, then a bar closes above the
  previous bar's high and back above the fast EMA (the pullback is ending).
- **Initial stop:** 1.5 × ATR from the signal close.
- **Exit:** ATR trailing stop (3 × ATR from the best close since entry). The stop only moves in
  the trade's favour. Optional fixed take profit (R multiple) and optional breakeven with a small
  offset that covers commissions; both are off by default.
- **Sizing:** each trade risks a fixed % of equity (default 1%), capped at 1× equity (no leverage).
- **Non-repainting:** the HTF filter reads only the previous, fully closed HTF bar
  (`close[1]` with `lookahead_on`, the documented safe pattern). Orders fill on the next bar's open.
- **Costs:** 0.05% commission per side and 2 ticks slippage by default.
- **Backtest window:** start and end date inputs for out-of-sample checks.
- **Alerts:** `alert()` messages with ticker, entry and stop, ready for webhooks or trading bots.
- **Panel:** closed trades, win rate, profit factor, net profit %, max drawdown %, risk per trade
  and current trend on the chart.

## How it behaves (independent cross-check)
The rules were replicated in Python (next-bar-open fills, intrabar stop handling, commission on
both sides) and run on public sample data. TradingView's own data feed and fill model differ a
little, so treat these as indications, not promises.

| Market (sample) | Timeframe | Net | Profit factor | Max DD | Trades |
|---|---|---|---|---|---|
| BTCUSD 2020–2026 | 1D | +54% | 2.01 | 9.9% | 63 |
| GOOG 2004–2013 | 1D | +35% | 1.84 | 7.7% | 53 |
| BTCUSDT 2020 (4 months) | 1H | +19% | 1.53 | 8.5% | 69 |
| BTCUSDT 2025–2026 (bear phase) | 4H | +8% | 1.43 | 11.4% | 26 |
| SPY 2008–2017 | 1D | +1% | 1.02 | 17.4% | 76 |
| BTCUSDT 2026 | 15m | −8% | 0.21 | 10.2% | 26 |
| EURUSD / GBPUSD 2017–2020 (0.005% cost) | 1H | −1% to −4% | 0.91–0.95 | up to 7.7% | 145–388 |

What this shows, plainly:
- It works where markets trend (crypto, trending stocks on 4H/1D) and does **not** beat buy and
  hold in a strong bull market. Its job is to cut the drawdown, not to outrun the market.
- It is flat on a choppy index, loses on 15-minute charts (the commission is too large compared
  with the stop distance) and has no edge on forex H1, even with low forex costs. That is a
  property of trend following on those markets, not a bug.
- Results were stable when the stop (1.5–2 ATR) and trailing distance (2.5–3.5 ATR) were changed,
  so the defaults are not curve-fitted to one lucky setting.

The previous version (RSI trigger, fixed 2R target, breakeven at exactly +1R) lost money on most
of these samples: breakeven exits at the entry price still paid two commissions, and the fixed
target cut the large winners a trend system lives on. It was replaced by this version.

## Use it
TradingView → Pine Editor → paste `trend_pullback_pro.pine` → *Add to chart*.
Recommended start: BTCUSD or a trending stock on the 4H or 1D chart. Set commission and slippage
(*Settings → Properties*) to your broker's real values before judging results.

This is a demonstration of strategy engineering, not financial advice. Past results do not
guarantee future returns.
