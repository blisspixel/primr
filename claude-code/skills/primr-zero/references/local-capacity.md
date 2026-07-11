# Defensive Local Capacity Handling

Treat local inference capacity as a schedulable resource. Primr reports three
normalized states:

- `available`: start the compatible stage;
- `busy`: the service is healthy but does not have enough free capacity now;
- `unavailable`: the service, model, or required hardware is missing;

If the host could not complete the check, record that observation as `unknown`
and do not assume capacity.

For `busy`, preserve the run checkpoint and surface machine-readable capacity
metadata when Primr provides it: reason, observed time, retry-after seconds,
attempt count, and whether the recommendation came from measured workload or a
bounded backoff policy.

Use a one-shot retry. Prefer Primr's supplied `retry_after_seconds`. If no
measured estimate exists, use a conservative sequence such as 30 minutes, two
hours, then six hours, capped rather than growing forever. Tell the user when
the retry is scheduled. If the host cannot schedule continuations, report the
suggested time and stop cleanly.

Do not:

- poll the GPU in a tight loop;
- reserve or kill another user's GPU process;
- retry indefinitely;
- mark a busy service as broken;
- fall through to a paid cloud backend in a hard-zero or explicit local run;
- promise an automatic retry when the host has no scheduling mechanism.

After repeated busy results, offer three choices: wait longer, reduce the local
model or task size if the user approves the quality tradeoff, or keep the
checkpoint for manual resume. A paid route is a separate estimate and approval.
