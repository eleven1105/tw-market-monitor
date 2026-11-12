# Wave-Trading Data Policy v1.0

Status: proposed implementation policy for the Taiwan listed common-stock monitor  
Date: 2026-11-12  
Scope: TWSE-listed ordinary shares only

## 1. Operating objective

The system is a short- to medium-term swing-trading research and decision-support system. It is not intended to require a complete multi-decade market archive before daily scanning can run.

Daily operation must prioritize fresh, comparable, and sufficiently complete recent data. A missing or invalid record for one symbol must be isolated and must not block analysis of the remaining universe.

## 2. Data layers

### A. Daily technical-analysis layer

- Retain a rolling history sufficient for at least 250 completed trading sessions plus a small buffer.
- Daily cross-sectional reports must use a common latest market date.
- Core rolling metrics remain 5, 20, and 250 trading sessions where relevant.
- Validate dates and OHLC relationships only over the observations consumed by the active metrics, while retaining broader source history when already available.
- Symbols with insufficient recent history are excluded from the relevant metric, not treated as zero-return observations.

### B. Chip/flow layer

- Target 20, 60, and 120 trading-session windows for institutional flows, broker-branch activity, and concentration metrics, depending on source availability.
- Recent chip/flow data is a separate data domain from price history; do not imply that historical price CSV coverage means chip data is available.
- Missing chip data must be explicitly marked unavailable and must not silently be replaced with zero.
- Intraday 5/15/30-minute data is fetched on demand for shortlisted candidates, not required for the entire market universe.

### C. Research and backtest layer

- Keep the current two-year price-history acquisition as the default daily research reservoir.
- Do not make more than two years of history a prerequisite for daily scanning.
- Extend historical data selectively when a strategy test needs different market regimes or a longer sample.
- Backtests must use point-in-time data and avoid look-ahead bias; a short recent sample must not be presented as robust strategy validation.

## 3. Fault isolation and universe eligibility

- A symbol with a missing official bar, stale date, invalid OHLC, or vendor-specific parsing issue is quarantined individually.
- The system records the ticker, affected date, source, validation rule, and exclusion reason.
- A quarantined symbol does not block the rest of the market pipeline.
- Official exchange data is preferred for resolving material vendor anomalies.
- Do not mix adjusted and unadjusted OHLC fields to force a row to pass validation.
- A daily market-wide snapshot uses a single common trading date; lagging symbols are excluded from that snapshot but remain in the audit list.

## 4. Current implementation alignment

The current Taiwan downloader requests approximately two years of daily history (yfinance history period=2y). The analyzer currently validates and calculates its 5/20/250-session metrics against a recent window of approximately 251 rows. This already broadly matches the intended price-history policy.

The current project has not yet established a validated broker-branch/chip-data ingestion layer. That work must be designed and verified separately; do not assume chip coverage based on price-data coverage.

## 5. Delivery order

1. Preserve stable daily price ingestion and single-symbol fault isolation.
2. Verify the daily technical-analysis window and its output definitions.
3. Add market breadth and momentum candidate ranking.
4. Evaluate chip/flow data providers and build an independent validation pipeline.
5. Add candidate-only intraday confirmation.
6. Backtest only strategies with explicit entry, exit, invalidation, costs, and point-in-time data.

## 6. Non-goals

- No requirement to reconstruct every symbol's full listing-to-date history before launch.
- No requirement to download intraday bars for all listed symbols.
- No use of old chip/branch data as if it described current positioning.
- No claim of strategy profitability based solely on data-pipeline success or indicator backtests.

## 7. Acceptance criteria

- Daily scan can complete when a small number of symbols are quarantined.
- The report distinguishes universe size, fresh-date coverage, valid OHLC coverage, and metric-specific eligibility.
- Daily technical calculations use documented rolling-session windows.
- Chip-data coverage and freshness are reported independently from price data.
- Backtest results disclose sample period, number of trades, costs, slippage assumptions, and out-of-sample results.
