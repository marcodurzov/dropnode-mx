
# Rocket Trader — Traditional Research v0.9

## Objective

Independently audit existing research reports and trade ledgers before
using their results to make strategy-selection decisions.

This release is an audit utility. It is not a new strategy, a profitability
claim, or authorization to trade with real money.

## Safety

- Research only.
- No broker integration.
- No order submission.
- No live trading.
- No leverage, margin, futures, or short selling.
- `orders_enabled=false`.
- `orders_submitted=0`.

## Files

- `rocket_trader_traditional_research_v0_9.py`
  JSON report and CSV ledger auditor.
- `.github/workflows/rocket-trader-traditional-research-v0.9.yml`
  GitHub Actions workflow.
- `README_ROCKET_TRADER_RESEARCH_V0_9.md`
  This document.

## Input data

Place the existing research JSON reports and trade-ledger CSV files under:

`research_artifacts/`

The audit searches subdirectories recursively.

CSV ledgers should preferably include:

- `trade_id`
- `symbol`
- `entry_signal_timestamp`
- `entry_timestamp`
- `entry_price`
- `exit_signal_timestamp`
- `exit_timestamp`
- `exit_price`
- `quantity`
- `return_pct`

The auditor recognizes several common aliases, but it cannot infer missing
fields or guarantee that an arbitrary CSV represents a complete ledger.

Keep original artifacts unchanged. Store audit output separately.

## Run locally

Run built-in unit tests:

```bash
python rocket_trader_traditional_research_v0_9.py --run-tests
```

Run the audit:

```bash
python rocket_trader_traditional_research_v0_9.py \
  --input-dir research_artifacts \
  --output research_artifacts/v0_9_audit_report.json
```

The command returns a nonzero exit status when ERROR findings are detected.

## Checks

- JSON readability.
- Reports indicating orders are enabled or submitted.
- Duplicate trade identifiers.
- Invalid prices or quantities.
- Unparseable timestamps.
- Entry execution earlier than the recorded signal.
- Exit execution earlier than the recorded exit signal or entry.
- Ledger rows out of chronological order.
- Basic reconciliation of reported trade return versus gross long-only
  entry/exit price return.

## Severity

- ERROR: a condition that invalidates or blocks the audit.
- WARN: an inconsistency requiring investigation.
- PASS: no findings were detected by the checks implemented here.
- PASS_WITH_WARNINGS: no ERROR findings, but warnings remain.

A PASS means only that the implemented checks found no errors. It does
not establish that all timestamps are correct or that a strategy is profitable.

## Required follow-up before strategy approval

1. Reconstruct the reported TSLA SMA 20/100 return from the original ledger.
2. Independently reproduce every trade from the source market bars.
3. Verify signal availability, order timing, and executable prices.
4. Recalculate fees, slippage, position sizing, equity curve, and drawdown.
5. Investigate the v0.7 versus v0.8 volatility calculation difference.
6. Validate on untouched out-of-sample data.
7. Stress-test assumptions and compare against buy-and-hold.

## Limitations

This version does not independently fetch historical market data or rebuild
strategies from bars. It does not certify accounting conventions, corporate
actions, market-session completeness, or profitability. Those require a
separate reproducible backtest and the original data.

No strategy is automatically promoted by this tool.
