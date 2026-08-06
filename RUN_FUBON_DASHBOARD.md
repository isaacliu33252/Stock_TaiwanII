# Run Fubon Dashboard

Use this when you want to manually refresh Fubon holdings/cash and rebuild the local dashboard.

Windows:

```text
run_fubon_dashboard.bat
```

WSL/Linux:

```bash
./run_fubon_dashboard.sh
```

The command asks for the Fubon login password and certificate password. Passwords are not saved.

Output:

- `data/private/holdings_fubon_latest.json`
- `data/private/rebalance_plan_latest.json`
- `data/private/group_a_plus_dashboard.html`

Safety:

- reads holdings
- reads cash
- does not place orders
- does not auto-trade
