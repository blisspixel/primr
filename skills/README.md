# Primr Skills Directory

Skills are documentation files for MCP-connected AI agents. They are **not** runtime code — they provide context, heuristics, and workflow guidance that agents read to make better decisions.

## Design Principles

Based on SkillsBench research (arXiv:2602.12670):

- **Focused > monolithic**: Each skill is 94-116 lines with 2-5 tools. Small, focused skills outperform large composite ones.
- **Human-curated only**: Skills encode domain expertise that models lack. Don't skill what the model already knows.
- **Documentation, not injection**: Skills live in this directory for agents to reference. They are not injected into runtime prompts.

## Current Skills

| Skill | Purpose | Lines |
|-------|---------|-------|
| `company-research` | Full pipeline workflow (modes, cost, phases) | ~100 |
| `scrape-strategy` | Tier selection heuristics and escalation logic | ~95 |
| `hypothesis-tracking` | Confidence level management and evolution | ~115 |
| `qa-iteration` | Section refinement workflow and scoring | ~95 |

## Structure

Each skill directory contains:

```
skills/<skill-name>/
├── SKILL.md              # Main skill document (agent reads this)
└── references/           # Supporting reference material
    └── <topic>.md
```

## Future

- Industry-specific skill templates (healthcare, fintech, etc.)
- Skill versioning aligned with Primr releases
