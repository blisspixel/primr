# Open Claw Integration Guide

This guide covers integrating Primr with [Open Claw](https://openclaw.dev), a local-first agentic AI runtime.

## Prerequisites

- Python 3.10+
- Primr installed (`pip install primr`)
- Open Claw runtime installed
- API keys configured (GEMINI_API_KEY, SEARCH_API_KEY, SEARCH_ENGINE_ID)

## Installation

### 1. Install Primr

```bash
pip install primr
```

Verify the MCP server is available:

```bash
primr-mcp --help
```

### 2. Copy Configuration Files

Copy the Open Claw configuration files to your Open Claw config directory:

```bash
# Linux/macOS
cp -r openclaw/* ~/.openclaw/

# Windows
xcopy /E openclaw %USERPROFILE%\.openclaw\
```

### 3. Configure Environment Variables

The integration uses environment variable passthrough. Set these in your shell or `.env` file:

```bash
export GEMINI_API_KEY="your-gemini-api-key"
export SEARCH_API_KEY="your-google-search-api-key"
export SEARCH_ENGINE_ID="your-search-engine-id"
```

Alternatively, configure per-skill environment overrides in `openclaw.json`:

```json
{
  "skills": {
    "entries": {
      "primr-research": {
        "env": {
          "GEMINI_API_KEY": "${GEMINI_API_KEY}",
          "SEARCH_API_KEY": "${SEARCH_API_KEY}",
          "SEARCH_ENGINE_ID": "${SEARCH_ENGINE_ID}"
        }
      }
    }
  }
}
```

### 4. Verify Installation

Run the Primr doctor command to verify everything is configured:

```bash
primr doctor
```

## Skills Overview

The integration provides three skills:

| Skill | Purpose | Tools |
|-------|---------|-------|
| primr-research | Company research workflows | estimate_run, research_company, check_jobs, cancel_job |
| primr-strategy | Strategy document generation | generate_strategy |
| primr-qa | Quality assessment | run_qa, doctor |

## Workflows

### Research Pipeline

The `research-pipeline.yaml` workflow orchestrates the complete research flow:

1. **Estimate** - Get cost/time estimate
2. **Approval** - Request user approval (required for cost-incurring operations)
3. **Research** - Execute the research job
4. **Monitor** - Poll for completion
5. **Retrieve** - Get the results


## Troubleshooting

### Common Issues

#### Missing Binary: `primr-mcp not found`

Ensure Primr is installed and the binary is in your PATH:

```bash
# Check if primr-mcp is available
which primr-mcp  # Linux/macOS
where primr-mcp  # Windows

# If not found, reinstall Primr
pip install --upgrade primr
```

#### Missing API Keys

If you see "No API key configured" errors:

1. Verify environment variables are set:
   ```bash
   echo $GEMINI_API_KEY
   echo $SEARCH_API_KEY
   ```

2. Run `primr doctor` to check configuration:
   ```bash
   primr doctor
   ```

3. Ensure keys are passed through in `openclaw.json`

#### Connection Errors

If the MCP server fails to connect:

1. Check the server is running:
   ```bash
   primr-mcp --stdio
   ```

2. Use Open Claw's debug mode:
   ```bash
   pnpm gateway:watch --raw-stream
   ```

3. Check logs in `~/.openclaw/logs/`

#### Research Job Stuck

If a research job appears stuck:

1. Check job status:
   ```bash
   # Via MCP resource
   primr://research/status
   ```

2. Cancel if needed:
   ```bash
   # Via MCP tool
   cancel_job
   ```

3. Check for `possibly_stuck: true` in status response

### Using `primr doctor`

The `primr doctor` command provides system health diagnostics:

```bash
primr doctor
```

Output includes:
- API key configuration status
- Output directory status
- Configuration validity
- Warnings for common issues

## Example Agent Prompts

### Research Workflow

Start a company research:

```
Research Acme Corp at https://acme.com
```

The agent will:
1. Get a cost estimate
2. Ask for approval
3. Execute the research
4. Return the report location

### Strategy Generation

Generate a strategy document from an existing report:

```
Generate an AI strategy from the latest report
```

Available strategy types:
- AI Strategy (requires cloud vendor)
- Customer Experience Strategy
- Security & Compliance Strategy
- Data Fabric Strategy

### QA and Refinement

Run quality assessment on a report:

```
Run QA on the report and suggest improvements
```

The QA system provides:
- Overall score (0-100)
- Category scores (completeness, accuracy, clarity, actionability)
- Improvement suggestions

Score interpretation:
- 85+: Excellent quality
- 70-84: Good, minor improvements needed
- Below 70: Needs significant revision

## Memory Subsystem Integration

Primr integrates with Open Claw's Memory Subsystem to persist learnings across sessions.

### How It Works

When you encounter and solve issues, record them in MEMORY.md:

```markdown
## Primr Research Learnings

### SSRF Protection Workaround
- **Issue**: URL blocked by SSRF protection
- **Solution**: Use `deep` mode instead of `scrape` mode
- **Context**: Some corporate sites block direct scraping

### API Rate Limits
- **Issue**: Gemini API rate limit exceeded
- **Solution**: Wait 60 seconds and retry, or reduce research scope
- **Context**: Full mode uses more API calls
```

### Memory Entry Format

```markdown
### [Issue Title]
- **Issue**: Brief description of the problem
- **Solution**: How to resolve it
- **Context**: When this applies
```

The agent will reference these learnings in future sessions to avoid repeating mistakes.

## Docker Sandbox

For enhanced security, Primr can run in a Docker sandbox:

```bash
# Build the container
docker build -f openclaw/Dockerfile.primr -t primr-sandbox .

# Run with environment variables
docker run -e GEMINI_API_KEY -e SEARCH_API_KEY -e SEARCH_ENGINE_ID \
  -v ./output:/home/primr/output \
  primr-sandbox
```

Security features:
- Non-root user execution
- No credential mounts
- Read-only documentation mount
- Health check via `primr doctor`

## Resources

- [Primr Documentation](./README.md)
- [MCP Server API](./API.md)
- [Architecture Overview](./ARCHITECTURE.md)
- [Open Claw Documentation](https://openclaw.dev/docs)
