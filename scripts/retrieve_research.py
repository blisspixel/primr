"""
Quick script to retrieve a completed Deep Research job by interaction ID.

Usage:
    python retrieve_research.py <interaction_id>
"""

import sys

from primr.ai.deep_research import DeepResearchClient
from primr.ai.job_persistence import acknowledge_pending_job_after_outputs


def retrieve_research(interaction_id: str) -> None:
    """Retrieve and display a completed research job."""
    client = DeepResearchClient()

    print(f"Checking research job: {interaction_id}")
    print("-" * 80)

    result = client.check_job(interaction_id)

    status = result.get("status")
    print(f"Status: {status}")

    if status == "completed":
        content = result.get("content", "")
        citations = result.get("citations", [])

        if not content:
            print("\nResearch completed without content. The pending job was retained for retry.")
            return

        print(f"\nContent length: {len(content)} characters")
        print(f"Citations: {len(citations)}")
        print("\n" + "=" * 80)
        print("RESEARCH CONTENT:")
        print("=" * 80)
        print(content)

        if citations:
            print("\n" + "=" * 80)
            print("CITATIONS:")
            print("=" * 80)
            for i, citation in enumerate(citations, 1):
                print(f"{i}. {citation.get('title', 'Untitled')}")
                print(f"   {citation.get('url', 'No URL')}")
                print()

        # Save to file
        output_file = f"research_{interaction_id[:20]}.md"
        with open(output_file, "w", encoding="utf-8") as f:
            f.write("# Deep Research Report\n\n")
            f.write(f"**Interaction ID:** {interaction_id}\n\n")
            f.write(content)
            if citations:
                f.write("\n\n## Sources\n\n")
                for i, citation in enumerate(citations, 1):
                    f.write(
                        f"{i}. [{citation.get('title', 'Untitled')}]({citation.get('url', '')})\n"
                    )

        print(f"\nSaved to: {output_file}")
        if not acknowledge_pending_job_after_outputs(interaction_id, [output_file]):
            print(
                "Report saved, but its pending job record could not be removed; "
                "a later status check may list it again."
            )

    elif status == "failed":
        error = result.get("error", "Unknown error")
        print(f"\nResearch failed: {error}")

    elif status == "in_progress":
        print("\nResearch is still in progress. Try again later.")

    else:
        error = result.get("error")
        print(f"\nError: {error if error else 'Unknown status'}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python retrieve_research.py <interaction_id>")
        print("\nExample:")
        print(
            "  python retrieve_research.py v1_ChZ4QTF4YVlERUdPLWV6N0lQblBlc1NBEhZ4QTF4YVlERUdPLWV6N0lQblBlc1NB"
        )
        sys.exit(1)

    interaction_id = sys.argv[1]
    retrieve_research(interaction_id)
