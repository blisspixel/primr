# Primr Concurrency Model

This document describes the live concurrency model, its safety limits, and the
difference between coroutine cancellation and actually stopping a research
job. The standing language and extraction policy is in
[`design/runtime-language-boundaries.md`](design/runtime-language-boundaries.md).

## Scope

Primr has two distinct concurrency levels:

1. **Inside one research job:** bounded asyncio tasks and thread pools overlap
   independent external waits and selected blocking operations.
2. **Across research jobs:** the core remains single-job. A consumer or hosted
   control plane may queue several jobs, but each long job should be owned by a
   separate supervised process or one-job container when cancellation and
   isolation matter.

These levels must not share budgets, browser environment mutation, mutable
scrape state, or terminal status by accident.

## Design rules

- Classify the operation before choosing a primitive.
- Await natively asynchronous I/O.
- Put bounded blocking I/O in the existing async bridge or an explicitly owned
  small thread pool.
- Use a child process when work must be terminable, crash-contained, or
  resource-limited.
- Bound every pool, semaphore, queue, input, timeout, and retry policy.
- Preserve target-host courtesy limits even when more local workers are idle.
- Do not infer that a cancelled asyncio task stopped a running thread or remote
  provider operation.
- Measure block rate, p95 latency, memory, queueing, and end-to-end time before
  changing worker counts.

## Live concurrency inside one job

### Website corpus collection

The canonical production path is `fetch_web_content()` in
`src/primr/data/scrape.py`. `data/parallel_scraper.py` is a standalone helper;
its default worker count is not the production site-corpus policy.

The live path is deliberately staged:

1. The homepage is fetched and classified first.
2. Up to `SCRAPE_PILOT_COUNT` pages, default 10, run sequentially. This pilot
   learns access quality, duplicate behavior, effective tiers, and whether the
   crawl should stop defensively.
3. Remaining selected pages run through
   `ThreadPoolExecutor(max_workers=3)`.
4. Every tier request still passes through the shared per-host limiter.

The default `RateLimitConfig` is three concurrent requests per host and 20
requests per minute. The live corpus orchestrator keeps the three-request cap
but currently uses a 30-request-per-minute override and 0.5 second token-wait
jitter. The token bucket starts full, so the rate is not an evenly spaced
delay. Live 429 handling records a persistent host cooldown; the lower-level
limiter's exponential-backoff methods are not currently the production 429
path.

The worker pool is therefore an upper bound, not permission to send three
requests continuously. Tokens, backoff, slow browser tiers, sticky-tier state,
and circuit breakers may reduce effective concurrency.

### Other bounded pools

The codebase uses separate limits for separate resources:

| Capability | Live pattern | Reason |
|------------|--------------|--------|
| Post-pilot site pages | 3 worker threads | Conservative same-host collection |
| Raw scrape persistence | 1 writer thread | Keep disk writes out of the page path |
| Standard section writing | Up to 4 worker threads | Bounded writes within the rolling-context and whole-document coherence pipeline |
| Premium accordion writing | One section at a time | Preserve the report argument arc and prior-section continuity |
| Gap-research queries | 3 worker threads | Bounded external search/model work |
| Strategy platforms | Up to 3 worker threads | Independent platform artifacts |
| URL existence verification | Configurable, default 10 threads | Conditional guessed-link verification fanout |
| Browser hard-timeout wrapper | 1 worker in the specific Drission path | Isolate one blocking browser call |

These limits are local to their capability. They must not be copied into
another path without a production-shaped load and block-rate measurement.

`ResearchExecutor` still contains a compatibility chapter fan-out with an
async semaphore of two. It is not part of the active Standard or Premium
production topology and must not be described as the Premium concurrency
policy. Premium uses one Deep Research dossier followed by sequential section
writes.

Conditional guessed-link verification currently receives no shared limiter
from the live discovery callers, so it falls back to a no-op limiter. That
10-worker same-host fanout is a documented hardening gap, not a concurrency
budget to emulate. It should reuse the corpus limiter or an explicit
verification budget before wider crawl concurrency is considered.

The browser timeout wrapper deserves a specific warning: timing out a future
does not terminate a browser call already running in its thread. It bounds how
long the caller waits, not how long the underlying thread can exist.

### Async provider and research work

Async paths use semaphores and `asyncio.gather()` for independent operations.
Some are natively asynchronous, such as citation resolution. Others wrap or
call synchronous provider SDK methods and may still occupy the event loop or a
thread briefly. An `async def` declaration alone is not proof that the work is
nonblocking.

`asyncio.gather()` is appropriate only when:

- tasks do not mutate the same unguarded state;
- each task has its own timeout and retry policy;
- provider and host quotas remain bounded;
- exceptions are handled explicitly; and
- downstream stages wait for every required result or record an intentional
  partial outcome.

Pipeline overlap may start external research after the homepage and initial
context exist, but it must not let final synthesis consume an uncommitted
partial corpus as if collection had completed.

## Async and sync boundaries

Use the existing `primr.utils.async_utils` seam.

### Synchronous caller, async implementation

Use `run_sync()`:

```python
from primr.utils.async_utils import run_sync

result = run_sync(fetch_async())
```

`run_sync()` creates the loop when no loop is running and refuses nested-loop
use. Code already inside an async function should `await` directly.

Do not add new copies of `get_event_loop().run_until_complete()` or bare
`asyncio.run()` outside the boundary helper.

### Async caller, bounded blocking implementation

Use `run_async()` for ordinary blocking library calls:

```python
from primr.utils.async_utils import run_async

result = await run_async(parse_or_fetch_sync, argument)
```

The shared bridge has a bounded four-worker executor. A capability may own a
smaller explicit pool when it has a different resource budget or ordered
shutdown requirement.

Existing MCP pipeline work uses `asyncio.to_thread()` for long synchronous
research entry points. That keeps the event loop responsive, but it does not
make the work safely cancellable. Local MCP and A2A jobs therefore place the
whole runner behind the supervised process boundary below.

## Job ownership and cancellation

There are three different cancellation meanings:

| Boundary | What cancellation can guarantee |
|----------|---------------------------------|
| Coroutine | Stops future coroutine progress at cancellation points |
| Running thread | Cannot be forcibly terminated safely by Python |
| Owned child process or container | Can be asked to stop, then terminated after a bounded grace period |

A terminal `cancelled` job state must not be written merely because a client
requested cancellation. It is terminal only after Primr observes that the
worker it owns has exited or after the job is reconciled to a documented remote
state.

The shipped local MCP/A2A long-job pattern is:

```text
control surface
    -> retained job-id to process handle
    -> cooperative stop request
    -> bounded wait
    -> terminate, then kill if required
    -> preserve partial artifacts
    -> commit terminal status and cancellation method
```

Provider-side work may be non-interruptible. Primr must record that separately
and never imply that stopping a local worker cancelled a remote provider task
unless the provider confirmed it.

`mcp_server.worker_protocol` is the packaged local contract. The parent accepts
only schema-valid, sequenced, job-bound events. It rejects malformed, regressive,
cross-job, and late snapshots, preserves canonical identity, and replaces
worker-reported heartbeat, stage-transition, and completion clocks with its own
observation timestamps. It commits terminal state only after exit and writes a
worker-exit manifest for failed or cancelled exits with a retained supervisor
handle. Spawn failures and restart reconciliation remain journal-only. The
deployment runner predates this contract and should converge on it rather than
being copied into the package.

Workers inherit only an explicit research-provider and runtime environment
allowlist. Control-plane, cloud-identity, telemetry, and CI secrets are removed
and cannot be restored by lazy `.env` loading. Supervised `.env` parsing
disables interpolation and rejects interpolation-bearing assignments. Control
commands and lifecycle
events move to private, non-inheritable descriptors before pipeline imports;
ordinary stdin becomes `DEVNULL` and ordinary stdout becomes worker-log output.
This prevents normal native writes from corrupting JSONL and normal exec-based
descendants from retaining the protocol pipes.

Exactly one controller owns a journal through a non-blocking OS lease. MCP,
co-hosted A2A, and standalone A2A share one reference-counted controller
lifecycle. After lease acquisition, the controller reloads the journal before
restart reconciliation. Final lifecycle exit runs shielded, bounded
cooperative, terminate, and kill phases and releases the lease only after all
retained workers are reaped and descendant cleanup is confirmed. A cleanup
failure retains the worker handle and is retried; lifecycle exit fails and
retains the lease so another controller cannot reconcile a possibly live
worker.

On Windows, the worker joins a named Job Object before it emits `ready`; closing
the controller's sole long-lived handle removes the worker tree. On POSIX, the
worker starts in a new session, receives bounded group termination, and uses a
parent-disconnect watchdog. Linux covers the bootstrap transition with
`PR_SET_PDEATHSIG`, then clears the worker-only signal after the control reader
starts so pipe EOF can kill the complete process group. This POSIX crash path is
best effort if native code holds the GIL long enough to starve that reader or a
descendant deliberately escapes through `setsid()` or a new process group.
Recovered active journals have no retained handle and reconcile to
`failed/server_restart` only after the next controller acquires the lease.

## Shared state

### State that is synchronized

- Per-host rate-limiter tokens, backoff counters, and semaphore creation are
  protected by a lock; concurrency slots use per-host semaphores.
- Circuit-breaker state uses guarded per-key state.
- Request-scoped correlation uses `contextvars`, not a process-wide mutable
  request identifier.
- MCP job-store methods serialize journal access with a lock for the supported
  single-job process model. Mutable job objects and cross-thread status
  notification still require care.

### State that is not a multi-job contract

- `ScrapeOrchestrator` maintains mutable per-host state.
- Adaptive browser execution temporarily changes process environment values.
- Orchestrator singleton construction and scrape trace appends are not explicit
  cross-thread synchronization contracts.
- Some usage and budget state assumes one research job per process.
- Browser, cache, and provider SDK objects may have thread-affinity or
  undocumented thread-safety constraints.

Ordinary dictionary operations are not a substitute for a compound-state
locking policy. Do not share one orchestrator or process-global budget across
concurrent research jobs. Process isolation is the preferred way to keep these
ownership assumptions explicit.

## Python 3.14 free-threading

Standard Python 3.14 is supported. Free-threaded 3.14t remains an informational
compatibility and benchmark lane.

Removing the GIL does not supply cancellation, queue durability, browser
isolation, or provider parallelism. It can also expose races in mutable state,
and an extension that is not free-threading-aware may restore the GIL at import.

Before any promotion:

- run the full suite on every supported platform;
- record which extensions preserve or restore free-threading;
- audit process-wide environment mutation, caches, budgets, and host state;
- compare representative one-job and multi-worker throughput;
- measure CPU, p95, peak memory, failures, and report outcomes; and
- adopt only if the complete workload shows material value.

## Overload and backpressure

Exceptional behavior under load matters more than maximum worker count:

- Keep queues bounded.
- Reject or defer work before exhausting browser or model capacity.
- Propagate deadlines and budget checkpoints.
- Honor provider `Retry-After` where supported.
- Treat a healthy local model server that lacks capacity as `busy`, not broken.
- Return bounded `retry_after_seconds` and `retry_at` guidance instead of
  sleeping for hours in the worker.
- Never fall through to paid cloud execution during a hard-zero run.

Core Primr does not poll indefinitely or schedule its own later retry. A host or
external scheduler may submit one later job after rechecking capacity.

## Observability

Implemented signals include correlation and request identifiers, run-state
events, scrape trace records, provider usage and cost metadata where available,
job heartbeats, and control-plane audit projections.

The following are required before concurrency or service-language decisions,
but should not be described as fully wired today:

- event-loop lag;
- active and queued work per pool;
- queue depth and admission latency;
- per-phase p50, p95, and p99 duration;
- cancellation request-to-worker-exit latency;
- orphaned worker count;
- peak resident memory; and
- block, 429, fallback, and recovery rates by concurrency profile.

Telemetry remains body-free by default. Do not record page bodies, prompts,
reports, credentials, raw endpoint URLs, or installed local model names merely
to tune concurrency.

## Contributor checklist

Before adding or changing concurrency:

1. Identify the constrained resource: target host, browser, provider quota,
   local model, CPU, memory, disk, or control-plane dependency.
2. Record the current production-shaped baseline.
3. Reuse the existing async, rate-limit, job, and logging seams.
4. Define queue and pool bounds, timeout, retry, cancellation, and shutdown.
5. Prove shared-state ownership.
6. Add deterministic failure and timeout tests.
7. Measure p95, failures, block rate, memory, and end-to-end time.
8. Update this document if the live policy changed.

## Explicitly not

- No unbounded `gather()`, pool, or queue.
- No new event-loop helper.
- No assumption that a timeout killed a thread.
- No global worker-count constant reused across unrelated capabilities.
- No concurrent research jobs sharing one in-process budget or scrape
  orchestrator.
- No Go rewrite to obtain process isolation already available through the
  runner protocol.
- No free-threaded default based only on a CPU microbenchmark.

## Version history

| Version | Changes |
|---------|---------|
| 2.0 | Reconciled the document with the live pilot plus three-worker corpus path, the shared async seam, truthful cancellation, process isolation, and measured runtime policy |
| 1.0 | Initial documentation |
