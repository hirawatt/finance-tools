# Portfolio Analyzer

## Bringing your portfolio in

Open **Import Portfolio**, drop the holdings statement from your broker, and the
page reads it, matches every holding to an NSE symbol and shows a preview before
you commit.

- **Zerodha** — Console → Portfolio → Holdings → download the XLSX. The five
  quantity buckets (available, long-term, pledged) are summed for you.
- **Groww** — Stocks → Holdings → download the statement.
- **Dhan** — Portfolio → Holdings → export the CSV/XLSX.
- **Angel One** — Portfolio → Holdings → download the statement.
- **Anything else** — drop the sheet, pick *Generic*, and point each field at the
  column it lives in; the mapping can be saved and reused.
- **Every broker at once** — drop a **CAS** PDF (Consolidated Account Statement
  from [CDSL](https://www.cdslindia.com/) or [NSDL](https://nsdl.co.in/)) and
  enter its password (usually PAN + date of birth). One statement covers every
  demat account and broker. A CAS has no purchase price, so invested value and
  P&L read flat — positions and weights are still exact.
- **Zerodha, live** — when the deployment is set up with Kite Connect
  credentials, the page shows *Connect Zerodha*: you sign in on Kite's own page
  and holdings are pulled straight from the account, no file. The token is
  stored on the machine, owner-readable only, and expires each morning.

Symbols are matched by **ISIN** first (the same key at every broker), then by the
trading symbol, then by company name. Rows that cannot be matched are listed —
never silently dropped — so you can fix them.

**Privacy.** Your file is read in memory for the session and is not uploaded
anywhere. *Use this portfolio* analyses it without touching disk; *Save locally*
is the only action that writes, and it writes to the git-ignored `portfolios/`
directory on this machine. A PocketBase backend with auth is the intended home
for a book of clients later.

Once you have saved portfolios, the Co-Pilot's sidebar **Portfolio** picker
switches between them — the sample, any saved client, and the file you imported
this session — so a book of clients is one dropdown away.

```mermaid
flowchart TD
    A(Co-Pilot) --> B(Analyze) & C(Optimize)
    B --> D(Sector Weightage) & E(Stock Weightage) & J(Correlation Matrix) & K(Beta vs NIFTY 50)
    C --> F(Rebalance) & G(Reduce Risk) & H(Maximize Returns)
    G & H --> I["Sharpe Ratio and Treynor Ratio Comparison"]
```

## Portfolio Analytics

Below the allocation charts, the **Portfolio Analytics** sections pull data for your
holdings from Yahoo Finance and NSE:

- **Correlation** — a heatmap of how your holdings move together, plus the most
  correlated pairs, to spot concentration risk.
- **Beta & Risk** — each holding's beta versus NIFTY 50, with a value-weighted
  risk/return summary for the whole portfolio.
- **Valuation** — trailing/forward P/E, P/B, EPS and market cap per holding,
  with the portfolio's value-weighted P/E (total value ÷ total earnings).
- **Risk Flags** — a rule-based screen over reported fundamentals (leverage,
  earnings, cash flow, margins, valuation); Altman Z-score default-risk zones;
  and NSE ASM/GSM surveillance-list membership.
- **Rebalance** — target allocations (equal weight, inverse volatility, risk
  parity) with an optional per-holding cap, shown against your current mix as a
  buy/sell trade list in shares and rupees.
- **Outlook** — upcoming earnings dates and a Monte Carlo projection of the
  portfolio value (a scenario range, not a prediction).
- **Tearsheet** — the full [quantstats](https://github.com/ranaroussi/quantstats)
  metrics table (Sharpe, Sortino, Calmar, drawdown, etc.).

You can change the lookback period; symbols without enough history are skipped
automatically.

## Due Diligence

**Due Diligence** screens the market — not just your holdings — for surprises,
using the nightly snapshot only. There is no live fetch on this page: an
after-close job writes the data once, and every screen reads it, so the results
are as fresh as the last snapshot and never depend on a provider being up.

Pick an **Universe** in the sidebar (a curated watchlist or all of them), then a
check:

- **Options pricing mismatch** — put-call parity breaks in an index's end-of-day
  option chain: a strike whose `strike + call - put` sits away from its expiry's
  forward (the futures close where one traded, else the median of its liquid
  strikes). Index options are European, so a gap is a real mispricing or a stale
  quote, not an early-exercise artifact.
- **Unusual moves in pairs** — same-industry pairs whose hedged log-price spread
  has stretched beyond a z-score threshold; a rich leg against a cheap one is a
  relative-value candidate to investigate.
- **Unusual volume in stocks** — cash-market names trading far above their own
  trailing average, with the session's return and turnover so a spike can be read
  against the price move.
- **Unusual volume in options** — the strikes with the heaviest fresh positioning
  (change in open interest and volume, expressed as a buildup ratio), plus the
  put-call ratio by expiry.

If the nightly job has not covered a universe yet, the page shows an empty state
and says so rather than reaching for live data.
