/**
 * TypeScript adapter for parsing primr://research/status resource.
 * 
 * This adapter transforms raw MCP resource responses into structured
 * summaries suitable for the Open Claw agent.
 * 
 * Requirements: FR-4.1, FR-4.2, FR-4.3
 */

// Type definitions matching Primr MCP types
interface ResearchStatus {
  status: "idle" | "in_progress" | "completed" | "failed" | "cancelled";
  job_id?: string;
  company_name?: string;
  company_url?: string;
  mode?: "scrape" | "deep" | "full";
  progress?: number;
  current_stage?: string;
  started_at?: string;
  completed_at?: string;
  error_message?: string;
  possibly_stuck?: boolean;
  artifacts?: string[];
}

// Output contract per design document
interface StatusSummary {
  status: "success" | "error";
  summary: string;
  action_required?: string;
  details: ResearchStatus;
}

interface ErrorOutput {
  status: "error";
  message: string;
  code?: string;
  action_required?: string;
}

/**
 * Build a human-readable summary for each status type.
 */
function buildSummary(status: ResearchStatus): string {
  switch (status.status) {
    case "idle":
      return "No active research job. Ready to start new research.";
    
    case "in_progress": {
      const progress = status.progress !== undefined ? `${status.progress}%` : "unknown";
      const stage = status.current_stage || "processing";
      const company = status.company_name || "unknown company";
      return `Researching ${company}: ${progress} complete (${stage})`;
    }
    
    case "completed": {
      const company = status.company_name || "unknown company";
      const artifacts = status.artifacts?.length || 0;
      return `Research complete for ${company}. ${artifacts} artifact(s) generated.`;
    }
    
    case "failed": {
      const company = status.company_name || "unknown company";
      const error = status.error_message || "Unknown error";
      return `Research failed for ${company}: ${error}`;
    }
    
    case "cancelled":
      return "Research job was cancelled. No charges incurred.";
    
    default:
      return `Unknown status: ${(status as ResearchStatus).status}`;
  }
}

/**
 * Detect if job is possibly stuck and suggest action.
 */
function detectPossiblyStuck(status: ResearchStatus): string | undefined {
  if (status.possibly_stuck) {
    return "Job appears stuck. Consider cancelling with cancel_job and retrying.";
  }
  
  // Additional heuristic: in_progress for >60 minutes without progress update
  if (status.status === "in_progress" && status.started_at) {
    const startTime = new Date(status.started_at).getTime();
    const now = Date.now();
    const elapsedMinutes = (now - startTime) / (1000 * 60);
    
    if (elapsedMinutes > 60 && (status.progress === undefined || status.progress < 10)) {
      return "Job has been running for over 60 minutes with minimal progress. Consider checking logs or cancelling.";
    }
  }
  
  return undefined;
}

/**
 * Get suggested action for failed status.
 */
function getFailureAction(status: ResearchStatus): string | undefined {
  if (status.status !== "failed") return undefined;
  
  const error = status.error_message?.toLowerCase() || "";
  
  if (error.includes("ssrf") || error.includes("blocked")) {
    return "URL was blocked for security. Try using mode='deep' which uses external sources only.";
  }
  
  if (error.includes("api") || error.includes("rate limit")) {
    return "API error encountered. Wait a few minutes and retry, or check API key validity with 'doctor'.";
  }
  
  if (error.includes("timeout")) {
    return "Request timed out. The target site may be slow or blocking requests. Try mode='deep'.";
  }
  
  return "Check error details and consider retrying with different parameters.";
}

/**
 * Main entry point: parse status and return structured summary.
 */
function processStatus(input: string): void {
  try {
    const parsed = JSON.parse(input);

    // Validate parsed input is a non-null object (not array, number, string, etc.)
    if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
      throw new Error("Input must be a JSON object, got " + (Array.isArray(parsed) ? "array" : typeof parsed));
    }

    const status: ResearchStatus = parsed;

    const summary = buildSummary(status);
    const stuckAction = detectPossiblyStuck(status);
    const failureAction = getFailureAction(status);
    
    const output: StatusSummary = {
      status: "success",
      summary,
      details: status,
    };
    
    // Add action_required if applicable
    if (stuckAction) {
      output.action_required = stuckAction;
    } else if (failureAction) {
      output.action_required = failureAction;
    } else if (status.status === "completed") {
      output.action_required = "Retrieve results with primr://output/latest or offer to run QA.";
    }
    
    // Output to stdout (valid JSON only)
    console.log(JSON.stringify(output, null, 2));
    
  } catch (error) {
    const errorOutput: ErrorOutput = {
      status: "error",
      message: error instanceof Error ? error.message : "Unknown error parsing status",
      code: "PARSE_ERROR",
      action_required: "Check that primr://research/status returns valid JSON.",
    };
    
    // Error output to stderr
    console.error(JSON.stringify(errorOutput, null, 2));
    process.exit(1);
  }
}

// Read from stdin or command line argument
const input = process.argv[2] || "";

if (!input && process.stdin.isTTY === false) {
  // Read from stdin
  let data = "";
  process.stdin.setEncoding("utf8");
  process.stdin.on("data", (chunk) => { data += chunk; });
  process.stdin.on("end", () => { processStatus(data); });
} else if (input) {
  processStatus(input);
} else {
  const errorOutput: ErrorOutput = {
    status: "error",
    message: "No input provided. Pass JSON as argument or pipe to stdin.",
    code: "NO_INPUT",
  };
  console.error(JSON.stringify(errorOutput, null, 2));
  process.exit(1);
}
