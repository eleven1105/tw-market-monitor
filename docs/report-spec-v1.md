# Daily Taiwan Listed Common-Stock Monitor Report — Specification v1.0

**Status:** Baseline specification; implementation and data validation are pending.
**Project:** `eleven1105/tw-market-monitor`
**Target branch:** `research/tw-listed-common-stocks`

## 1. Purpose and scope

Produce a daily market-research and monitoring report for Taiwan Stock Exchange listed ordinary shares only. Exclude OTC securities, ETFs, warrants, and other non-target instruments.

This report is for research and monitoring. It must not issue unverified buy/sell instructions.

## 2. Report sections

1. **Market overview:** valid universe count, advances/declines/unchanged, advance-decline ratio, average return, volume context, data coverage.
2. **Bull/bear breadth:** advancing and declining participation, strength/weakness counts, concentration, and whether prior moves are continuing or reversing.
3. **Sector/industry strength:** ranked groups with return, breadth, and momentum context. Do not publish rankings where classification or sample coverage is inadequate.
4. **Return distributions:** 5-, 20-, and 250-trading-day return distributions, with sample counts and clear period definitions.
5. **Swing-watch candidates:** a concise shortlist with trend, price/volume, momentum, chip-data availability/status, risks, follow-up conditions, and invalidation conditions. Candidate status is research-only, not a trade instruction.
6. **Data quality and exceptions:** universe validation, download coverage, OHLC anomalies, official-source reconciliation, stale/missing dates, and chip-data coverage.
7. **Daily conclusion and next-session watchlist:** evidence-based summary of market direction, breadth, leading/weak groups, priority symbols, and conditions to monitor.

## 3. Data and interpretation rules

- The current run's validated universe manifest is the authoritative analysis allowlist. Cached files must never expand the universe.
- Missing, stale, malformed, or unreconciled data must be identified and excluded or explicitly marked; never silently treated as valid.
- Do not automatically rewrite suspicious vendor prices without narrowly scoped official-source verification and an audit trail.
- Distinguish downloaded rows, usable rows, latest-session rows, and quality-approved rows. Do not conflate these counts.
- Every percentage or ranking must disclose its denominator/sample count where relevant.
- Industry comparisons require a validated and consistently applied classification source.
- Chip data is supplementary. Its absence must not corrupt or silently invalidate the core price/market-breadth pipeline.
- A report section with insufficient valid evidence must say “資料不足／待驗證” rather than infer a conclusion.

## 4. Acceptance gates

The following are separate gates and must be reported independently:

1. **Execution reliability:** scheduled/manual workflow completes; tests pass; report/artifacts/notifications behave as configured.
2. **Data quality:** listed-common-stock universe is correct; coverage, freshness, OHLC validation, and official reconciliation are auditable.
3. **Analytical validity:** breadth, sector, momentum, and return-distribution calculations are checked against independently reproducible samples.
4. **Strategy validity:** any future signal or strategy requires historical testing, out-of-sample or walk-forward checks where appropriate, and realistic transaction-cost/slippage evaluation.

Passing an earlier gate does not imply passing a later gate.

## 5. Versioning and change control

- Treat this document as the v1.0 structural baseline.
- Preserve the original upstream project and keep all changes in the dedicated fork/research branch.
- Before changing existing pipeline behavior, inspect current implementation and tests for conflicts.
- Prefer additive, reversible changes. Record the reason, affected files, tests, and acceptance evidence.
- Do not broaden scope into the separate AI Trading Desk's master universe, database, strategy engine, or backtest framework.
- After the first end-to-end report has been validated, refine fields and presentation using actual usage feedback. Until then, avoid unnecessary redesign of the report structure.

## 6. Initial implementation priority

1. Stabilize the existing Taiwan-only daily pipeline.
2. Complete stock-universe and price-data quality validation.
3. Connect validated data to the report sections above.
4. Verify report delivery and downloadable artifacts.
5. Refine candidate research and notifications only after the underlying data is trustworthy.

## 7. Report status vocabulary

Use explicit labels such as:
- **已驗收** — acceptance evidence exists for the stated scope and revision.
- **待驗收** — implemented or proposed, but acceptance evidence is not yet available.
- **資料不足** — the required evidence/sample is insufficient.
- **不適用** — the item does not apply to the current run.

Never describe a proposed template or an older successful workflow run as proof that the latest code or data has passed validation.
