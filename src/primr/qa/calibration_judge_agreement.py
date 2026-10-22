"""Claim-aligned cloud/local calibration comparison and agreement values."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from primr.qa.label_calibration import CalibrationReport


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


def compare_calibration_reports(
    cloud_report: CalibrationReport,
    local_report: CalibrationReport,
    *,
    local_model: str,
) -> JudgeAgreement:
    """Compare verdicts only when both reports describe the same sampled claims."""
    compared = agreed = 0
    disagreements: list[JudgeDisagreement] = []
    for index, (cloud, local) in enumerate(
        zip(cloud_report.results, local_report.results, strict=True)
    ):
        if cloud.claim != local.claim:
            raise ValueError("Judge comparison requires identical sampled claims")
        if cloud.verdict not in {"traceable", "untraceable"} or local.verdict not in {
            "traceable",
            "untraceable",
        }:
            continue
        compared += 1
        if cloud.verdict == local.verdict:
            agreed += 1
        else:
            disagreements.append(JudgeDisagreement(index, cloud.verdict, local.verdict))
    return JudgeAgreement(compared, agreed, local_model, tuple(disagreements))
