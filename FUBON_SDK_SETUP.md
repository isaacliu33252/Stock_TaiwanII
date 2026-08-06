# Fubon SDK Setup

This repo already contains a local Fubon wheel and the current machine can import `fubon_neo`.

## Current status

- Import check: `fubon_neo 2.2.8`
- Local wheel: `fubon_neo-2.2.8-cp37-abi3-manylinux_2_17_x86_64.manylinux2014_x86_64.whl`
- Project bridge CLI: [`fubon_sdk_bridge.py`](fubon_sdk_bridge.py)

## What was enabled

- `check`: verify SDK importability, credential completeness, and optional signal JSON shape.
- `preview-orders`: convert `signal_group_a*.json` or `signal_group_b*.json` into Fubon order preview JSON/CSV.
- `login-check`: explicit login test entrypoint that prints account payload and does not place orders.

The bridge does not auto-submit real orders.

## Credential setup

Use the example file:

```bash
cp config/fubon_sdk.env.example .fubon.env
```

Fill in non-password fields only:

- `FUBON_PERSONAL_ID`
- `FUBON_CERT_PATH`
- optional `FUBON_ACCOUNT`

Do not store `FUBON_PASSWORD` or `FUBON_CERT_PASSWORD` in `.fubon.env`.
Login commands prompt for the Fubon login password and certificate password
manually at runtime. The GroupA+ read-only snapshot loader also ignores
password fields stored in the local `C:\fubon` AES config.

Load them into your shell before testing:

```bash
set -a
source .fubon.env
set +a
```

## Health check

Basic readiness check:

```bash
python3 fubon_sdk_bridge.py check --require-credentials
```

Check with a signal file too:

```bash
python3 fubon_sdk_bridge.py check \
  --signal-json results/signal_group_a_20260526_000026.json \
  --require-credentials
```

## Order preview from a signal

Single-step preview:

```bash
python3 fubon_sdk_bridge.py preview-orders \
  --signal-json results/signal_group_a_20260526_000026.json
```

Three-step build preview, first step:

```bash
python3 fubon_sdk_bridge.py preview-orders \
  --signal-json results/signal_group_a_20260526_000026.json \
  --steps 3 \
  --step-index 1 \
  --output-prefix group_a_fubon_step1
```

Output files are written under `results/`:

- `*.json`: ticker-level order plan
- `*.csv`: Fubon-friendly market rows, split into `Common` and `IntradayOdd` when needed

## Login test

After non-password credentials are loaded:

```bash
python3 fubon_sdk_bridge.py login-check
```

This prompts for the Fubon login password and certificate password. It only
tests login and prints the returned account payload. It does not place orders.

## Runtime note

On this WSL/Linux workspace, a direct `FubonSDK()` probe crashed once with a segmentation fault during runtime probing. Because of that:

- use `check` and `preview-orders` here safely
- run `login-check` only when you are ready to test the broker runtime explicitly
- prefer your broker-supported native runtime for live login or later order submission tests
