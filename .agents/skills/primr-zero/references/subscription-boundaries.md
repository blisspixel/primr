# Subscription and Authentication Boundaries

The zero-spend workflow runs inside an official host surface. It does not turn
a consumer subscription into a general-purpose API.

Allowed patterns:

- a host-native Agent Skill;
- an official non-interactive CLI command documented for scripting;
- an official plugin, connector, or automation surface;
- a user-operated research UI with an uploaded Primr packet.

Forbidden patterns:

- copying or relaying OAuth tokens;
- extracting browser cookies or local session databases;
- browser automation against consumer chat pages;
- unofficial subscription proxies or private endpoints;
- silently using API keys when a host allowance is exhausted;
- enabling paid overages, credits, or auto-refill without explicit approval.

Keep confidential customer material within a host and plan whose data controls
the user has reviewed. Public company evidence is still untrusted content and
must remain fenced from instructions.
