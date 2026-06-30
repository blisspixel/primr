"""Canonical A2A skill ids and scope groups."""

from __future__ import annotations

A2A_MONITOR_READ_SKILLS = frozenset(
    {
        "estimate_research",
        "check_jobs",
        "system_health",
    }
)

A2A_COMPACT_RESOURCE_READ_SKILLS = frozenset(
    {
        "read_calibration_summary_by_job",
        "read_artifacts_by_job",
        "read_qa_summary_by_job",
        "read_usage_summary_by_job",
        "read_source_summary_by_job",
        "read_trace_summary_by_job",
        "read_verification_summary_by_job",
        "read_stage_scorecard",
    }
)

A2A_REPORT_RESOURCE_READ_SKILLS = frozenset({"read_report_by_job"})

A2A_READ_SKILLS = A2A_MONITOR_READ_SKILLS | A2A_COMPACT_RESOURCE_READ_SKILLS
A2A_RESEARCH_SKILLS = frozenset({"research_company", "run_qa", "cancel_task"})
A2A_RESOURCE_READ_SKILLS = A2A_COMPACT_RESOURCE_READ_SKILLS | A2A_REPORT_RESOURCE_READ_SKILLS
