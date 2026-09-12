# Group A+ Broker Export Request

- Status: `required`
- Live effect: `none`
- Current reconciliation: `blocked`
- Template: `/mnt/c/Users/isaac/Downloads/Stock_taiwan2-main/Stock_taiwan2-main/report/group_a_plus/latest/broker_authoritative_export_template.csv`

## Current Blockers

- `authoritative_broker_export_missing`
- `transaction_sample_has_negative_positions`
- `confirmed_holdings_mismatch_transaction_sample`

## Required Fields

- `as_of_date`
- `account_id_or_alias`
- `ticker`
- `shares`
- `market_value`
- `cash_balance`
- `currency`
- `source_file_name`
- `export_generated_at`

## Acceptance Criteria

- export as_of_date matches the intended execution date
- cash_balance is explicit and non-null
- all Group A+ tickers are present with zero shares when absent from the account
- no negative long-only ETF share positions unless separately documented as short inventory
- broker reconciliation can be rerun without authoritative_broker_export_missing
