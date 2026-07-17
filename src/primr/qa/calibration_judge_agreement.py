"""Value objects for cloud-vs-local calibration judge agreement."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class JudgeDisagreement:
    """Body-free pointer to one cloud-vs-local verdict disagreement."""

    claim_index: int
    cloud_verdict: str
    local_verdict: str

    def to_dict(self) -> dict[str, int | str]:
        """Serialize without copying claim text or source material."""
        return {
            "claim_index": self.claim_index,
            "cloud_verdict": self.cloud_verdict,
            "local_verdict": self.local_verdict,
        }


@dataclass(frozen=True)
class JudgeAgreement:
    """Cloud-vs-local agreement over claims both judges could decide."""

    compared: int
    agreed: int
    local_model: str
    disagreements: tuple[JudgeDisagreement, ...] = ()

    @property
    def agreement(self) -> float | None:
        """Return the agreement fraction, or no value without comparisons."""
        if not self.compared:
            return None
        return self.agreed / self.compared
