# Amazon Bedrock access for primr (governance + least-privilege IaC)

Unlike Azure Foundry, Bedrock **foundation models are on-demand** — there is no
per-model deployment resource to create. So the right IaC provisions
*governance and least-privilege access*, and you invoke models on-demand via the
`converse` API. This CloudFormation stack creates a scoped invoke policy and a
content-filter **guardrail**. Verified end-to-end on 2026-07-21.

## Prerequisites

- AWS CLI configured: `aws sts get-caller-identity` and a default region
  (`aws configure get region`). primr's provider honors that region, or set
  `AWS_REGION`.
- Model access enabled for the models you plan to call (Amazon Nova is broadly
  available; Anthropic Claude may require requesting access in the console).
- primr's Bedrock extra: `pip install 'primr[bedrock]'` (installs `boto3`).

## 1. Confirm invokable models (authoritative, free)

```bash
aws bedrock list-inference-profiles --region us-west-2 \
  --query "inferenceProfileSummaries[?contains(inferenceProfileId,'nova')].inferenceProfileId" \
  --output text
```

`us.amazon.nova-micro-v1:0` is the cheapest good default for testing.

## 2. Deploy the governance stack

```bash
aws cloudformation deploy \
  --template-file bedrock.yaml \
  --stack-name primr-bedrock \
  --region us-west-2 \
  --capabilities CAPABILITY_NAMED_IAM

aws cloudformation describe-stacks --stack-name primr-bedrock \
  --region us-west-2 --query "Stacks[0].Outputs"
```

Outputs: `InvokePolicyArn` (attach to the IAM principal primr runs as) and
`GuardrailId` (pass as `guardrailIdentifier` on `converse` for governed calls).

## 3. Point primr at it

primr's `BedrockProvider` uses the standard AWS credential chain (env keys,
profile, SSO, or a Bedrock API key `AWS_BEARER_TOKEN_BEDROCK`) and resolves the
region from `AWS_REGION` or `aws configure`. No base URL needed.

```bash
primr keys test bedrock     # free, auth-only: "authenticated; N foundation models visible"
```

This validates the deployment (credentials, region, and visible foundation
models). Note that full research-pipeline routing through Bedrock is **not yet
wired**: the model-name→provider router has no Bedrock branch, so a Bedrock
model id set via `AI_REASONING_MODEL` (e.g. `us.amazon.nova-lite-v1:0`) is not
recognized as a Bedrock model — it falls through to the first-party xAI path and
the run cannot even be priced. To route utility-tier inference through a custom
endpoint today, use the OpenAI-compatible gateway seam (`LOCAL_LLM_BASE_URL` /
`LOCAL_LLM_API_KEY`).

## 4. Clean up

IAM policies and guardrails have no standing cost, but delete when done:

```bash
aws cloudformation delete-stack --stack-name primr-bedrock --region us-west-2
aws cloudformation wait stack-delete-complete --stack-name primr-bedrock --region us-west-2
```

## Note: Bedrock lags the first-party API too

Like Azure Foundry, the Bedrock catalog trails the model vendors' own APIs by
weeks. Use Bedrock for cost, consolidation under one AWS key, and the cheap
open-weight/Nova tiers; use first-party APIs for the newest models.
