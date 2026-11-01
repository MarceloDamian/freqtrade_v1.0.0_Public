# Security Baseline — Freqtrade Sandbox

Audit date: 2026-09-20

## Pinned image

```
docker.io/freqtradeorg/freqtrade@sha256:d59109a487ddac94e41ffe55af49f61f500ba621cc88b95180bfdc809cf97c6f
```

| | |
|---|---|
| Tag at audit time | `freqtradeorg/freqtrade:stable` |
| Release | 2026.8 |
| Image built | 2026-08-31 05:15:03 UTC |
| Entrypoint | `freqtrade` (locked — not a shell) |
| Runs as | `ftuser` uid 1000, non-root |
| Python | 3.14.7 |

If a future `podman pull` returns a digest other than the one above, re-run this audit
before using the image.

## What was verified

| Check | Result |
|---|---|
| Withdrawal / transfer API calls in source | **None** |
| Hardcoded crypto wallet addresses | **None** |
| `eval` / `exec` / `base64.b64decode` / `marshal` | **None** (4 hits were PyTorch `model.eval()`) |
| Hardcoded URLs | 24, all documentation or exchange endpoints |
| Sample strategy imports | numpy, pandas, talib, technical — no network modules |
| Host LaunchAgents / crontab / shell rc | Unmodified |
| Container persistence | None — all runs use `--rm` |

### Complete list of exchange API methods Freqtrade calls

Write operations:

```
create_order   cancel_order   set_leverage   set_margin_mode
```

Everything else is `fetch_*` (read-only). `withdraw` and `transfer` appear nowhere in the
codebase. Funds cannot be moved off an exchange by this software.

### Sandbox boundary, verified from inside the container

Not visible: `/Users`, `~/.ssh`, `~/.aws`, `~/Library`, `~/.bitcoin`, `~/.ethereum`, `~/.electrum`

Only writable mount: `/freqtrade/user_data`

## Known limits of this audit

1. ccxt was not audited line by line. It exposes `withdraw()`; Freqtrade never calls it.
2. Transitive Python dependencies in the image were not individually reviewed.
3. The image is not cryptographically signed. Provenance is by publisher reputation.
4. Strategy files are arbitrary Python. A third-party strategy runs with full container
   privileges — that is the main future attack surface, not Freqtrade itself.

## Change log

### 2026-09-20 — API server enabled for FreqUI

`api_server.enabled` changed `false` -> `true`. Posture after the change:

- Container binds `0.0.0.0:8080` inside its own isolated network namespace.
- Host publishes `127.0.0.1:8080:8080` — **loopback only**, unreachable from the LAN.
- Auth verified: unauthenticated `GET /api/v1/status` returns **401**.
- Credentials are random-generated, stored in `user_data/config.json`.
- `./ft-ui trade` aborts unless `dry_run: true`.

If the published port is ever changed away from `127.0.0.1:`, the API becomes reachable
by anything on the local network. Do not do that.

## Standing rules

- `dry_run: true` until a strategy has been watched for a full week.
- Exchange API keys, if ever added: **trade-only, withdrawal disabled, IP-allowlisted**,
  set at the exchange, not in config.
- Never supply a seed phrase or private key. Freqtrade has no use for one.
- Read any third-party strategy before running it.
