"""CLI adapters for local research memory and tracked-company profiles."""

from __future__ import annotations

from typing import Any

from primr.utils.console import console
from primr.utils.validators import InputValidationError


def handle_memory(config: Any) -> int:
    """Handle research memory commands."""
    from primr.agentic.memory import ResearchMemory

    try:
        memory = ResearchMemory()
    except Exception as e:
        console.error(f"Failed to initialize research memory: {e}")
        return 1

    if config.memory_list:
        console.banner("Research Memory")
        companies = memory.list_companies()
        if not companies:
            console.info("No research memory found.")
            console.info("Run research to start tracking hypotheses.")
            return 0

        console.info(f"Found {len(companies)} company/companies with research memory:")
        console.blank()
        for company in sorted(companies):
            hypotheses = memory.get_hypotheses(company)
            console.ok(f"  {company}: {len(hypotheses)} hypothesis/hypotheses")
        return 0

    company = config.memory_company
    if not company:
        if config.website:
            company = config.website
        elif config.company_name and config.company_name.lower() != "memory":
            company = config.company_name
        else:
            console.error("Company name required")
            console.info('Usage: primr memory "Company Name"')
            console.info('   or: primr --memory "Company Name"')
            console.info("   or: primr --memory-list")
            return 1

    console.banner(f"Research Memory: {company}")

    hypotheses = memory.get_hypotheses(company)
    if not hypotheses:
        console.info(f"No hypotheses found for {company}")
        console.info("Run research to generate hypotheses.")
        return 0

    console.info(f"Found {len(hypotheses)} hypothesis/hypotheses:")
    console.blank()

    by_confidence: dict[str, list[Any]] = {}
    for hypothesis in hypotheses:
        level = hypothesis.confidence.value
        if level not in by_confidence:
            by_confidence[level] = []
        by_confidence[level].append(hypothesis)

    order = ["validated", "high", "medium", "low"]
    for level in order:
        if level in by_confidence:
            console.step(f"{level.upper()} confidence ({len(by_confidence[level])})")
            for hypothesis in by_confidence[level]:
                console.info(f"  - {hypothesis.statement}")
                if hypothesis.evidence:
                    console.info(f"    Evidence: {hypothesis.evidence[:100]}...")
                if hypothesis.topic:
                    console.info(f"    Topic: {hypothesis.topic}")
            console.blank()

    return 0


def handle_company(config: Any) -> int:
    """Handle tracked-company profile commands."""
    from primr.agentic.company_profiles import CompanyProfileStore

    try:
        store = CompanyProfileStore()
    except Exception as exc:
        console.error(f"Failed to initialize company profile store: {exc}")
        return 1

    if config.company_profile_list:
        return _handle_company_list(store)

    if config.company_profile_track:
        if not config.company_profile_url:
            console.error("Company URL required")
            console.info('Usage: primr company track "Company Name" https://company.com')
            console.info(
                '   or: primr --company-track "Company Name" --company-url https://company.com'
            )
            return 1
        try:
            profile = store.track(config.company_profile_track, config.company_profile_url)
        except InputValidationError as exc:
            console.error(str(exc))
            return 1
        console.ok(f"Tracked company: {profile.name}")
        console.info(f"URL: {profile.url}")
        console.info(f"Profile: {store.profile_dir(profile)}")
        console.info(f"Freshness: {profile.freshness_status}")
        return 0

    if config.company_profile_show:
        try:
            profile = store.get_profile(config.company_profile_show)
        except InputValidationError as exc:
            console.error(str(exc))
            return 1
        if profile is None:
            console.info(f"No tracked company profile found for {config.company_profile_show}")
            return 0
        console.banner(f"Tracked Company: {profile.name}")
        console.info(f"URL: {profile.url}")
        console.info(f"Freshness: {profile.freshness_status}")
        console.info(f"Last run: {profile.last_run_at or 'none'}")
        console.info(f"Run pointers: {len(profile.run_pointers)}")
        console.info(f"Retention: {profile.retention_policy}")
        console.info(f"Profile: {store.profile_dir(profile)}")
        return 0

    console.error("Company command required")
    console.info('Usage: primr company track "Company Name" https://company.com')
    console.info("   or: primr company list")
    console.info('   or: primr company show "Company Name"')
    return 1


def _handle_company_list(store: Any) -> int:
    console.banner("Tracked Companies")
    profiles = store.list_profiles()
    if not profiles:
        console.info("No tracked company profiles found.")
        console.info('Run: primr company track "Company Name" https://company.com')
        return 0

    console.info(f"Found {len(profiles)} tracked company profile(s):")
    console.blank()
    for profile in profiles:
        console.ok(f"  {profile.name}: {profile.url}")
        console.info(f"    Freshness: {profile.freshness_status}")
        console.info(f"    Last run: {profile.last_run_at or 'none'}")
    return 0
