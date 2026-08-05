# Job Status Contract

Primr exposes one versioned, body-free status shape across the CLI, MCP, A2A,
the hosted control plane, and the application API.

## Schema

The canonical object uses `schema: primr.job-status` and
`schema_version: 1.0`. It contains:

- `job_id`, `source`, `company_name`, and `mode`
- normalized `lifecycle_state`
- `progress.stage`, `progress.percent`, and nullable `progress.possibly_stuck`
- RFC 3339 `timestamps` for submission, start, update, and completion
- nullable `artifacts_available` — for completed jobs, true only when at least
  one path from a transport-specific artifact listing still exists on disk
  (not merely a non-empty path list). The boolean is the only path-related
  signal on the canonical object; the path list itself is not embedded here
- a bounded `error` object, or `null`

It never contains report content, previews, provider response bodies, artifact
URLs, or filesystem paths in the *canonical* object. Path listings used for the
`artifacts_available` existence check, transport-specific resource pointers,
MCP `early_artifact_paths` (body-free working-brief paths while a job runs),
and legacy status fields remain outside the canonical object.

Lifecycle normalization is stable for v1: pending, queued, and accepted become
`queued`; running becomes `in_progress`; complete, completed, and succeeded
become `completed`; provider work paused for caller input becomes
`requires_action`; expired is a failed terminal job; both cancellation
spellings become `cancelled`; unfamiliar states become `unknown`. A
`check_error` is `unknown` with `error.kind: observation`, because a failed
status lookup is not evidence that the underlying job failed.

## Surfaces

```bash
primr --check-jobs --json
```

The CLI emits exactly one `primr.job-status-list` v1.0 object and preserves a
nonzero exit when a provider-terminal failure or observation error is present.
A completed job remains a successful inspection result. Human `--check-jobs`
output is unchanged.

MCP `check_jobs` and `primr://research/status` include the canonical fields
additively. A2A `check_jobs`, hosted `/status/{job_id}`, and the application
`/research` list carry the snapshot under `job_status` because their legacy
top-level `error` or `progress` fields have incompatible types.

Adding nullable fields or source values is compatible within v1. Removing a
field, changing a field type, or changing lifecycle meaning requires v2.
