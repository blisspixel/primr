# Runtime and Language Boundaries

Status: ACTIVE decision record. This document defines how Primr chooses
Python, native code, worker processes, and services. It complements the
[Engineering Standards](https://github.com/blisspixel/primr/blob/main/ROADMAP.md#engineering-standards--toolchain)
and the [Concurrency Model](../CONCURRENCY.md).

## Decision

Primr is Python-first because its product is a changing research workflow built
on Python-native AI, scraping, document, and automation ecosystems. Python-first
is not Python-only. A different language is welcome when one bounded capability
has measured requirements that Python cannot meet cleanly and the operational
benefit exceeds the permanent integration cost.

The target architecture is deliberately small:

| Layer | Default | Specialization rule |
|-------|---------|---------------------|
| Research, provider, and report logic | Python | Keep product judgment and rapidly changing workflow code here |
| Job execution and isolation | One Python process per job where cancellation or failure isolation matters | Prefer a process boundary before introducing a service or FFI boundary |
| Deterministic CPU-heavy kernel | Optimized Python first | Rust may replace one versioned capability after differential and end-to-end gates pass |
| Multi-user cloud admission | Thin Python control plane today | Go is eligible only after measured control-plane load, not because jobs are long-running |
| Local model execution | External OpenAI-compatible server | Mojo or MAX is an external runtime experiment unless Primr later owns a measured numerical kernel |

This is not a commitment to use every eligible language. The exceptional
outcome is the smallest architecture that makes correctness, performance,
cost, and recovery explicit.

## Decision order

Every performance or language proposal follows this order:

1. **Harden correctness.** Cancellation, spend limits, checkpointing, input
   bounds, timeouts, and failure reporting must be truthful before throughput
   work begins.
2. **Measure the complete path.** Record wall time, p50/p95/p99 where useful,
   peak memory, failure rate, queue delay, provider wait, and cost on
   production-shaped inputs.
3. **Simplify the current implementation.** Remove duplicate work, batch calls,
   cache stable results, overlap independent phases, and bound concurrency.
4. **Choose the smallest isolation boundary.** A child process is preferred
   when the goal is cancellation, crash containment, or resource limits. Use a
   service only when independent lifecycle, scaling, or multiple clients
   justify it.
5. **Extract one capability.** The new boundary must be narrow, deterministic,
   versioned, independently tested, observable, and reversible.
6. **Keep it only if the product improves.** A faster microbenchmark is not a
   ship decision when report quality, installation, reliability, or total run
   time gets worse.

## Current workload map

The dominant full-run costs are browser and network access, search, provider
latency, and model generation. Those paths benefit most from bounded
concurrency, pipeline overlap, retries, and durable recovery. Rewriting their
orchestration in Rust, Go, or Mojo would not shorten the external wait.

Primr already delegates substantial work to native implementations through
Playwright and browser engines, PyMuPDF, pandas and NumPy, curl-cffi,
cryptography, lxml, msgpack, and pydantic-core. The relevant question is not
whether native code is acceptable. It is whether Primr should own another
native component and its platform-specific release burden.

The strongest current local-compute candidate is HTML analysis. A successful
page can currently be parsed repeatedly for access classification, reader-mode
text, aggressive and conservative text, structured blocks, boilerplate, and
link discovery. Before considering Rust, the Python implementation should
provide one canonical parse-and-analyze facade and reuse its result.

## Immediate architecture work

### 1. Truthful job cancellation through process isolation

An asyncio task can cancel coroutine coordination, but it cannot stop blocking
work already running in `asyncio.to_thread()` or a thread-pool worker. Marking a
job cancelled while its scrape or provider call continues is not acceptable,
especially when the call can spend money.

The preferred execution shape is:

```text
CLI, MCP, A2A, or hosted control plane
    -> versioned job specification
    -> one Python child process or one-job container
    -> progress events and checkpoints
    -> manifest committed after owned artifacts are durable
```

The controller retains the process or container handle. Cancellation first
requests graceful termination, then uses a bounded forced termination if the
worker does not exit. The worker remains Python because the research ecosystem
and business logic remain there. The existing deployment runner, job
specification, event, and manifest contracts should be reused rather than
inventing a second protocol.

Core Primr remains single-job and does not become a scheduler or daemon.
Consumers may queue or resubmit jobs outside the worker boundary.

### 2. Production-shaped performance baseline

The benchmark suite must distinguish external wait from Primr-owned work. At a
minimum, record:

- phase wall time and overlap;
- fetch, browser, parse, extraction, and document-generation time;
- provider wait, retries, tokens, and estimated cost;
- queue and admission delay on hosted surfaces;
- peak resident memory and maximum page size;
- cancellation latency and orphaned-work count;
- success, fallback, checkpoint, and recovery outcomes.

Microbenchmarks remain useful for diagnosing a candidate, but adoption gates
use a warm, network-free collection benchmark plus an end-to-end representative
run or replay. Benchmark fixtures must use synthetic or approved sanitized
content, never real company data committed to the repository.

### 3. Overlap independent pipeline phases

External research can begin after the homepage and initial company context are
available. It does not need to wait for every first-party page. Early
extraction can also overlap later page retrieval when the checkpoint contract
can prove all required inputs completed before downstream synthesis.

This should use the existing asyncio and thread-pool seams. It does not justify
a workflow framework or another language.

### 4. Parse HTML once

Introduce a versioned, immutable analysis result behind the existing Python
public functions. A representative internal contract is:

```python
def analyze_html_v1(
    raw_html: bytes,
    *,
    base_url: str,
    max_input_bytes: int,
) -> HtmlAnalysis:
    ...
```

The result may include decode status, parse warnings, title and metadata,
landmark counts, text variants, structured blocks, quality primitives, and
link candidates collected from the same document analysis.

The facade does not own network access, retries, block policy, URL scope,
quality thresholds, persistence, or model calls. Those remain Python policy.
The boundary must reject or safely truncate oversized input according to one
documented policy before parsing.

## Rust eligibility

Rust is the first native language to evaluate because a deterministic parser or
sanitizer can benefit from predictable memory use, parallel native execution,
fuzzing, and safe handling of untrusted bytes. This is eligibility, not a ship
decision.

### Candidate order

1. Single-pass HTML analysis.
2. Prompt-content sanitization, if production profiles show material cost after
   HTML consolidation.
3. Cross-page boilerplate fingerprints only as part of the HTML component or
   after a separate profile proves it matters.

Provider clients, browser automation, report writing, model orchestration,
SSRF policy, and job scheduling are not native-extension candidates.

### Adoption gates

A native HTML implementation ships only when all of these are true:

- the parse-once Python reference exists first;
- the differential corpus produces identical public text, metadata, links,
  block order, classifications, and error behavior;
- native throughput is at least 2 times the optimized Python reference across
  the full corpus;
- p95 analysis latency improves at least 3 times on 128 KB pages and 4 times on
  1 MB pages relative to the current repeated-parse path;
- peak memory falls at least 30 percent on 1 MB and 2 MB inputs;
- a 30-page, three-worker scrape-analysis replay improves at least 25 percent;
- a warm, network-free `primr prep` collection improves end to end at least
  10 percent;
- small pages regress no more than 10 percent;
- fuzzing finds no panic, process exit, unbounded allocation, or superlinear
  scaling on bounded input;
- every supported platform has a tested wheel; and
- the Python implementation remains complete and usable.

If parse-once Python comes within 20 percent of the native candidate, HTML
analysis is under 10 percent of measured scrape-stage wall time, or any
supported platform lacks a wheel, stop the extraction.

### Packaging and rollout

The main `primr` package remains fully functional as a universal Python wheel.
An accepted native component should initially ship as an optional,
version-locked accelerator package, exposed through one extra and one facade.
Installing base Primr must never require a Rust compiler.

Rollout states are centralized rather than scattered through call sites:

- `off`: Python only;
- `shadow`: run both, compare result hashes and behavior, return Python;
- `on`: prefer native and fail open to Python; and
- `auto`: use a qualified installed accelerator, otherwise Python.

Telemetry records engine version, duration, fallback class, and result hashes,
not page bodies. An environment-level kill switch must disable the accelerator
without a package downgrade.

## Go eligibility

Go is not a core-pipeline candidate. Its possible future boundary is a thin,
stateless hosted admission service in front of a durable queue and isolated
Python workers.

Go becomes eligible only after all of these are true:

- hosted multi-user mode has one canonical durable queue and job store;
- one process or container owns each research job;
- the Python control plane is packaged independently from the research runtime;
- request duration, event-loop lag, queue latency, cold start, memory, and error
  rates are wired and measured;
- Python dispatch, rather than the queue, store, provider, or browser, is the
  demonstrated p95 or p99 bottleneck; and
- async SDKs, thread offload for blocking SDKs, and ordinary horizontal scaling
  cannot restore the target margin.

If a spike becomes eligible, it must reuse a versioned OpenAPI or JSON Schema
contract. It must not duplicate lifecycle aliases, approval semantics, or
status rules by hand. Go communicates with Python through a queue or explicit
network protocol, not in-process FFI.

## Python 3.14 free-threading

Standard Python 3.14 remains supported. A free-threaded build is an
informational compatibility and benchmark lane, not a default or product
promise.

The decision is based on measured value and full platform validation, not a
categorical claim that every dependency lacks compatible wheels. Before
promotion, run the full suite under the free-threaded interpreter, verify which
extensions re-enable the GIL, audit shared state and process-wide environment
mutation, and benchmark representative single-job and multi-worker workloads.

Free-threading does not provide crash isolation, durable queueing, or the
ability to terminate blocking work. Process isolation remains the appropriate
answer to those requirements.

## Mojo and MAX eligibility

Primr currently owns no tensor, numerical, GPU, or accelerator kernel. Mojo is
therefore not an embedded dependency or a general Python replacement.

The lower-risk experiment is an operator-installed MAX or other inference
server behind Primr's existing OpenAI-compatible HTTP boundary. Compare the
same model and quantization against the current local runtime using report
quality, stage success, time to first token, throughput, peak VRAM, cold start,
p95 latency, busy and out-of-memory behavior, and total run duration.

Embedding or bundling waits for a measured Primr-owned kernel, stable and
supportable packaging across Primr's platforms, acceptable licensing, and a
clear maintenance owner. Current language, compiler, platform, and license
facts must be reverified from official sources when that gate is reached.

## Zero-cost and busy capacity

Language choice must preserve hard-zero behavior. Local inference capacity has
explicit `available`, `busy`, `unavailable`, and observation-failure semantics.
A busy result returns bounded `retry_after_seconds` and `retry_at` guidance. It
does not sleep for hours inside Primr, poll continuously, terminate another
user's process, or fall through to a paid provider.

If the host supports scheduled continuation, it may submit one later job after
rechecking capacity. If it cannot schedule, Primr reports the suggested retry
time honestly. This control contract is language-neutral and remains outside
the core worker.

## Validation cost

Free validation covers deterministic unit and property tests, differential
fixtures, fuzzing, synthetic benchmarks, replay benchmarks, strict docs, and
platform wheel installation tests. No provider call is needed to decide
whether a parser is correct or faster.

Paid or scarce-resource validation is limited to a pre-registered end-to-end
run or local GPU comparison after the free gates pass. It requires an estimate,
explicit approval where spend is possible, a fixed corpus, and recorded
hardware and runtime context.

## Explicitly not

- No wholesale rewrite of Primr.
- No language quota or aspiration to use Python, Rust, Go, and Mojo together.
- No extraction selected by filename, line count, popularity, or benchmark
  marketing.
- No permanent service for a capability that a bounded child process can own.
- No Rust compiler required to install base Primr.
- No Go scheduler inside the single-job core.
- No Mojo business logic or speculative GPU kernel.
- No broad speedup claim without named inputs, hardware, implementation,
  correctness checks, tail latency, memory, and end-to-end impact.
- No native implementation allowed to bypass SSRF, prompt fencing, spend,
  checkpoint, or artifact-ownership policy.

## Primary references

- Python free-threading: <https://docs.python.org/3/howto/free-threading-python.html>
- Python free-threaded extensions: <https://docs.python.org/3/howto/free-threading-extensions.html>
- PyO3 free-threading: <https://pyo3.rs/main/free-threading>
- Maturin packaging: <https://www.maturin.rs/distribution.html>
- Go diagnostics: <https://go.dev/doc/diagnostics>
- Go profile-guided optimization: <https://go.dev/doc/pgo>
- Mojo roadmap: <https://mojolang.org/docs/roadmap/>
- Mojo Python interoperability: <https://mojolang.org/docs/manual/python/>
- Mojo platform requirements: <https://mojolang.org/docs/requirements/>
- MAX serving: <https://docs.modular.com/max/cli/serve/>
- Modular Community License: <https://www.modular.com/legal/community>
