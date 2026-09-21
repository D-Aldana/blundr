# Deploying Blundr

`docker-compose.prod.yml` runs the stack behind Caddy, which terminates TLS,
serves the built frontend and routes `/api` to the backend. This walks through
a free Oracle Cloud ARM instance; any Linux host with Docker and a public IP
works the same way from [Install Docker](#3-install-docker) onward.

## What the host needs

An analysis is pure CPU: Stockfish at depth 12 on 2 threads for the length of
20 games. Concurrency is therefore bounded by cores, and RAM barely matters —
`MAX_CONCURRENT_ANALYSES` is the dial, at roughly two cores each.

Oracle's Always Free tier gives 4 ARM cores and 24 GB indefinitely, which is
two concurrent analyses and far more memory than the job needs.

## 1. Get the instance

Sign up at [cloud.oracle.com](https://cloud.oracle.com). A card is required
for identity verification. **Your home region is permanent**, so pick one near
you that isn't one of the busiest.

Compute → Instances → Create instance:

- **Image**: Ubuntu 24.04, the `aarch64` build
- **Shape**: Change shape → Ampere → `VM.Standard.A1.Flex` → 4 OCPUs, 24 GB
- **Networking**: assign a public IPv4 address
- **SSH keys**: upload your public key

### When it says "Out of host capacity"

The common outcome, not a mistake on your part — free ARM capacity is
genuinely scarce. In order of effort:

1. Retry, and try each availability domain in the region. Many regions,
   including `ca-toronto-1`, have only one.
2. Ask for less. A 1 OCPU / 6 GB request fills from fragments a 4 OCPU
   request can't use, and A1.Flex resizes later with a reboot.
3. Retry at a quieter hour, scripted rather than by hand. Keep the interval
   at a few minutes — polling every 45 seconds earns `TooManyRequests`, and a
   throttled request never reaches the capacity check at all.
4. Upgrade the account to Pay As You Go. Always Free resources stay free, but
   PAYG accounts reach ARM capacity far more easily. The tradeoff is real: you
   can now be billed if you exceed the free allowances, so check what you're
   running before you take this route.

Set a limit on this before you start. A scripted retry in `ca-toronto-1`
was refused roughly 200 times over 13 hours at 1 OCPU, which is the smallest
shape on offer — a contended region can simply have nothing to give, and no
amount of patience changes that. Nothing below this section is
Oracle-specific, so any host with a public IP and Docker is a drop-in
substitute, including a small ARM VPS for a few euros a month.

## 2. Open both firewalls

Oracle has two, and forgetting the second is the classic failure where
everything runs and nothing answers.

**The VCN security list** — Networking → Virtual Cloud Networks → your VCN →
subnet → security list. Add ingress rules for TCP 80 and 443 from
`0.0.0.0/0`.

**The instance's own iptables** — Oracle's images ship a chain that ends in
REJECT, so the rules must be inserted ahead of it:

```bash
sudo iptables -I INPUT -p tcp --dport 80 -j ACCEPT
sudo iptables -I INPUT -p tcp --dport 443 -j ACCEPT
sudo netfilter-persistent save
```

Without that last line the rules vanish on reboot.

## 3. Install Docker

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
```

Log out and back in so the group membership applies.

## 4. Point a domain at it

Caddy needs a hostname to get a certificate — an IP address won't do. A free
[DuckDNS](https://www.duckdns.org) subdomain pointed at the instance's public
IP works, as does any domain you own. Verify it resolves before continuing:

```bash
dig +short your.duckdns.org
```

If that doesn't print your instance's IP, Caddy's certificate request will
fail and it will keep retrying against Let's Encrypt.

## 5. Configure and start

```bash
git clone https://github.com/D-Aldana/blundr.git
cd blundr
cp .env.example .env
```

Compose reads this same `.env` both for its own `${...}` substitution and for
the backend's environment, so everything goes in one file:

```bash
SITE_ADDRESS=your.duckdns.org     # Caddy's site address; drives automatic TLS
SITE_URL=https://your.duckdns.org # CORS origin
CHESS_COM_CONTACT=you@example.com # Chess.com asks for a real contact
```

Set `CHESS_COM_CONTACT` to an address you actually read. The default is a
placeholder, and hammering their API from a public host without a real contact
is how you get blocked.

An LLM key is optional — without one the closing paragraph falls back to a
deterministic summary and nothing else changes. If you add one,
`SUMMARY_DAILY_BUDGET` caps what a public instance can spend per day.

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

The first build compiles the frontend and installs Stockfish, so give it a few
minutes. Then:

```bash
curl -s https://your.duckdns.org/api/healthz    # {"ok":true}
docker compose -f docker-compose.prod.yml logs -f caddy
```

Certificate issuance takes a few seconds on first start and shows up in
Caddy's log.

## 6. Tune to the hardware

The defaults assume roughly the machine this was developed on. ARM is slower
per core — a generic Debian Stockfish build benchmarks about 30% below a build
tuned for the host chip, before accounting for the core itself. Measure rather
than assume:

```bash
docker compose -f docker-compose.prod.yml exec backend stockfish bench
```

Then compare against a real analysis end to end. Two dials, in `.env`:

- `MAX_CONCURRENT_ANALYSES` — about two cores each. `2` on a 4-core box.
- `ENGINE_DEPTH` — `12` by default. Dropping to `10` roughly halves the time
  per analysis and costs some precision in the classifiers.

`RATE_LIMIT_ANALYZE` is already lowered to 5/IP/hour in the production compose
file, against 50 locally. On a shared host one visitor shouldn't be able to
occupy the queue.

## Updating

```bash
git pull
docker compose -f docker-compose.prod.yml up -d --build
```

Certificates live in a named volume, so they survive a rebuild. Jobs do not —
the job store is in memory, so anything mid-analysis is lost on restart. Run
updates when nobody's waiting.

## What this setup does not do

The backend holds jobs in a process-local dict, so **exactly one backend
instance can run**. A second replica would answer polls for jobs it doesn't
have. Scaling past one machine means moving that state to something shared;
until then, capacity comes from cores on a single box.

The backend deliberately has no published port. Caddy is the only way in, and
that's what makes `TRUST_PROXY_HEADER: "true"` safe — it overwrites
`X-Forwarded-For`, so the address the rate limiter sees can be trusted.
Publishing the backend would let callers forge that header and walk past every
limit.
