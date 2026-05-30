"""Stateful property test for the per-host tier circuit breaker (`HostState`).

The circuit breaker decides whether to keep retrying a scraping tier for a host.
A wrong transition is costly in both directions: skip a tier that still works and
primr loses content; keep hammering a permanently-broken tier and runs waste
time/money. This `RuleBasedStateMachine` drives arbitrary sequences of
attempt(success|failure) and asserts the breaker's invariants hold throughout:

  1. recorded failures never exceed recorded attempts;
  2. once any attempt has succeeded, the tier is never skipped (per the
     "20-40% failure is expected" rationale — any success is worth retrying);
  3. a tier is skipped only after >= threshold attempts that were ALL failures.
"""

from __future__ import annotations

from hypothesis import strategies as st
from hypothesis.stateful import RuleBasedStateMachine, invariant, rule

from primr.data.scraping.models import HostState

_TIER = "playwright"
_THRESHOLD = 3


class CircuitBreakerMachine(RuleBasedStateMachine):
    def __init__(self):
        super().__init__()
        self.state = HostState(host="example.com")
        self.attempts = 0
        self.failures = 0
        self.any_success = False

    @rule(success=st.booleans())
    def record_attempt(self, success):
        self.state.record_tier_attempt(_TIER, success)
        self.attempts += 1
        if success:
            self.any_success = True
        else:
            self.failures += 1

    @invariant()
    def failures_never_exceed_attempts(self):
        a = self.state.tier_attempts.get(_TIER, 0)
        f = self.state.tier_failures.get(_TIER, 0)
        assert f <= a
        # Model and object agree.
        assert (a, f) == (self.attempts, self.failures)

    @invariant()
    def any_success_means_never_skipped(self):
        if self.any_success:
            assert not self.state.should_skip_tier(_TIER, threshold=_THRESHOLD)

    @invariant()
    def skip_implies_all_failures_past_threshold(self):
        if self.state.should_skip_tier(_TIER, threshold=_THRESHOLD):
            assert self.attempts >= _THRESHOLD
            assert not self.any_success
            assert self.failures == self.attempts


TestCircuitBreaker = CircuitBreakerMachine.TestCase
