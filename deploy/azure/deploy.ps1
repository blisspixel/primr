<#
.SYNOPSIS
    Deploy Primr to Azure (single persistent MCP controller, BYOK)
.DESCRIPTION
    Creates all Azure resources for a team-tier Primr deployment using Bicep templates.
    Primr is CLI-first, local-first. This is the optional cloud scaling path.
.PARAMETER DeploymentName
    Name for this deployment (lowercase, 3-24 chars). Default: test
.PARAMETER Region
    Azure region. Default: eastus
.PARAMETER Destroy
    Tear down all resources instead of deploying
.EXAMPLE
    .\deploy.ps1
    .\deploy.ps1 -DeploymentName prod -Region westus2
    .\deploy.ps1 -Destroy
#>
param(
    [string]$DeploymentName = "test",
    [string]$Region = "eastus",
    [string]$Tier = "team",
    [switch]$Destroy,
    [switch]$Validate,
    [switch]$SkipSmokeTest
)

$ErrorActionPreference = "Continue"

# Naming
$ResourceGroup = "primr-$DeploymentName-rg"
$AcrName = "primr$($DeploymentName)acr" -replace '-',''
$ContainerAppName = "primr-$DeploymentName-api"
$ImageName = "primr-runner"
$ImageTag = $DeploymentName
$BicepFile = Join-Path $PSScriptRoot "bicep\main.bicep"

Write-Host ""
Write-Host "  Primr Azure Deployment" -ForegroundColor Cyan
Write-Host "  Deployment: $DeploymentName" -ForegroundColor Gray
Write-Host "  Region:     $Region" -ForegroundColor Gray
Write-Host "  Tier:       $Tier" -ForegroundColor Gray
Write-Host ""

# --- DESTROY ---
if ($Destroy) {
    Write-Host "[*] Destroying resource group: $ResourceGroup" -ForegroundColor Yellow
    $confirm = Read-Host "  Are you sure? (yes/no)"
    if ($confirm -ne "yes") { Write-Host "  Aborted."; exit 0 }
    az group delete --name $ResourceGroup --yes --no-wait
    Write-Host "[OK] Destroy initiated (running in background)" -ForegroundColor Green
    exit 0
}

# --- VALIDATE ---
if ($Validate) {
    Write-Host "[*] Validating deployment..." -ForegroundColor Cyan
    $errors = 0

    $resources = @(
        @{ Name = "Resource Group"; Args = @("group", "show", "--name", $ResourceGroup, "-o", "none") },
        @{ Name = "ACR"; Args = @("acr", "show", "--name", $AcrName, "--resource-group", $ResourceGroup, "-o", "none") },
        @{ Name = "Container App"; Args = @("containerapp", "show", "--name", $ContainerAppName, "--resource-group", $ResourceGroup, "-o", "none") }
    )

    foreach ($r in $resources) {
        $resourceArgs = [string[]]$r.Args
        & az @resourceArgs 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) {
            Write-Host "  $($r.Name): OK" -ForegroundColor Green
        } else {
            Write-Host "  $($r.Name): MISSING" -ForegroundColor Red
            $errors++
        }
    }

    if (-not $SkipSmokeTest) {
        Write-Host "[*] Running smoke test..." -ForegroundColor Cyan
        try {
            $fqdn = az containerapp show --name $ContainerAppName --resource-group $ResourceGroup --query "properties.configuration.ingress.fqdn" -o tsv 2>$null
            $fqdnLookupSucceeded = $LASTEXITCODE -eq 0
            if ($fqdnLookupSucceeded -and -not [string]::IsNullOrWhiteSpace($fqdn)) {
                # Health check
                try {
                    $health = Invoke-RestMethod -Uri "https://$fqdn/healthz" -TimeoutSec 30
                    Write-Host "  /healthz: PASS ($($health.status))" -ForegroundColor Green
                } catch {
                    Write-Host "  /healthz: FAIL ($($_.Exception.Message))" -ForegroundColor Red
                    $errors++
                }
                # Readiness check
                try {
                    $readiness = Invoke-RestMethod -Uri "https://$fqdn/readyz" -TimeoutSec 30
                    Write-Host "  /readyz: PASS ($($readiness.status))" -ForegroundColor Green
                } catch {
                    Write-Host "  /readyz: FAIL ($($_.Exception.Message))" -ForegroundColor Red
                    $errors++
                }
            } else {
                Write-Host "  Smoke test: FAIL (Container App FQDN unavailable)" -ForegroundColor Red
                $errors++
            }
        } catch {
            Write-Host "  Smoke test: FAIL ($($_.Exception.Message))" -ForegroundColor Red
            $errors++
        }
    }

    if ($errors -eq 0) {
        Write-Host "[OK] All checks passed" -ForegroundColor Green
    } else {
        Write-Host "[FAIL] $errors check(s) failed" -ForegroundColor Red
        exit 1
    }
    exit 0
}

# --- DEPLOY ---

# 1. Prerequisites
Write-Host "[1/6] Checking prerequisites..." -ForegroundColor Cyan
az version | Out-Null
if ($LASTEXITCODE -ne 0) { Write-Host "  ERROR: az CLI not found" -ForegroundColor Red; exit 1 }
docker --version | Out-Null
if ($LASTEXITCODE -ne 0) { Write-Host "  ERROR: Docker not found" -ForegroundColor Red; exit 1 }
Write-Host "  OK" -ForegroundColor Green

# 2. Resource Group
Write-Host "[2/6] Creating resource group: $ResourceGroup" -ForegroundColor Cyan
$rgExists = $null
try { $rgExists = az group exists --name $ResourceGroup 2>&1 } catch {}
if ($rgExists -eq "true") {
    Write-Host "  Already exists" -ForegroundColor Gray
} else {
    az group create --name $ResourceGroup --location $Region --tags "Deployment=$DeploymentName" -o none
    Write-Host "  Created" -ForegroundColor Green
}

# 3. ACR + Image
Write-Host "[3/6] Setting up container registry and image..." -ForegroundColor Cyan
$acrExists = $null
try { $acrExists = az acr show --name $AcrName --resource-group $ResourceGroup -o none 2>&1 } catch {}
if (-not $acrExists -or $LASTEXITCODE -ne 0) {
    az acr create --name $AcrName --resource-group $ResourceGroup --sku Basic -o none
    Write-Host "  ACR created: $AcrName" -ForegroundColor Green
} else {
    Write-Host "  ACR exists: $AcrName" -ForegroundColor Gray
}

Write-Host "  Building image in Azure (ACR Tasks)..." -ForegroundColor Gray
$FullImage = "${ImageName}:${ImageTag}"

# Stage only the files the Dockerfile needs into a temp directory to avoid OneDrive locks
$stageDir = Join-Path $env:TEMP "primr-acr-build-$(Get-Random)"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
New-Item -ItemType Directory -Path $stageDir -Force | Out-Null

# Copy only what the Dockerfile references
Copy-Item (Join-Path $repoRoot "pyproject.toml") $stageDir
Copy-Item (Join-Path $repoRoot "README.md") $stageDir
if (Test-Path (Join-Path $repoRoot "MANIFEST.in")) { Copy-Item (Join-Path $repoRoot "MANIFEST.in") $stageDir }
Copy-Item (Join-Path $repoRoot "src") (Join-Path $stageDir "src") -Recurse -ErrorAction SilentlyContinue
Copy-Item (Join-Path $repoRoot "deploy") (Join-Path $stageDir "deploy") -Recurse -ErrorAction SilentlyContinue
Copy-Item (Join-Path $repoRoot "deploy\Dockerfile") (Join-Path $stageDir "Dockerfile")

Push-Location $stageDir
try {
    # Start build without streaming logs (avoids Windows Unicode crash)
    az acr build --registry $AcrName --image $FullImage --file Dockerfile . --no-logs 2>&1 | Out-Null
    
    # Poll for completion
    Write-Host "  Build queued, waiting for completion..." -ForegroundColor Gray
    do {
        Start-Sleep -Seconds 15
        $buildStatus = az acr task list-runs --registry $AcrName --top 1 --query "[0].status" -o tsv 2>$null
        Write-Host "    Build status: $buildStatus" -ForegroundColor DarkGray
    } while ($buildStatus -eq "Running" -or $buildStatus -eq "Queued")
    
    if ($buildStatus -ne "Succeeded") {
        Write-Host "  ERROR: ACR build failed (status: $buildStatus)" -ForegroundColor Red
        exit 1
    }
} finally {
    Pop-Location
    Remove-Item -Recurse -Force $stageDir -ErrorAction SilentlyContinue
}
Write-Host "  Image built: $AcrName.azurecr.io/$FullImage" -ForegroundColor Green

# 4. Bicep deployment
Write-Host "[4/6] Deploying infrastructure via Bicep..." -ForegroundColor Cyan
if (-not (Test-Path $BicepFile)) {
    Write-Host "  ERROR: Bicep file not found: $BicepFile" -ForegroundColor Red
    exit 1
}

$BudgetAmount = if ($Tier -eq "organization") { 200 } else { 50 }

# Get deployer's principal ID for Key Vault access
Write-Host "  Getting deployer identity..." -ForegroundColor Gray
$DeployerPrincipalId = az ad signed-in-user show --query id -o tsv 2>$null
if (-not $DeployerPrincipalId) { $DeployerPrincipalId = "" }

$bicepParams = @(
    "deploymentName=$DeploymentName",
    "location=$Region",
    "resourcePrefix=primr-$DeploymentName",
    "tier=$Tier",
    "minReplicas=1",
    "maxReplicas=1",
    "budgetAmount=$BudgetAmount",
    "acrLoginServer=$AcrName.azurecr.io",
    "imageName=$ImageName",
    "imageTag=$ImageTag",
    "contactEmails=[`"$DeploymentName@primr.dev`"]",
    "llmRoutingMode=direct",
    "deployerPrincipalId=$DeployerPrincipalId"
)

$deployName = "$DeploymentName-$(Get-Date -Format 'yyyyMMddHHmmss')"
az deployment group create `
    --resource-group $ResourceGroup `
    --template-file $BicepFile `
    --parameters $bicepParams `
    --name $deployName `
    -o none

if ($LASTEXITCODE -ne 0) {
    Write-Host "  ERROR: Bicep deployment failed" -ForegroundColor Red
    Write-Host "  Check: az deployment group show --name $deployName --resource-group $ResourceGroup --query properties.error" -ForegroundColor Yellow
    exit 1
}
Write-Host "  Infrastructure deployed" -ForegroundColor Green

# 5. Post-deployment summary
Write-Host "[5/6] Post-deployment summary" -ForegroundColor Cyan
$fqdn = az containerapp show --name "$ContainerAppName" --resource-group $ResourceGroup --query "properties.configuration.ingress.fqdn" -o tsv 2>$null
if (-not $fqdn) { $fqdn = "pending (Container App may still be starting)" }

Write-Host ""
Write-Host "  MCP Server:    https://$fqdn" -ForegroundColor White
Write-Host "  MCP Endpoint:  https://$fqdn/mcp" -ForegroundColor White
Write-Host "  Liveness:      https://$fqdn/healthz" -ForegroundColor White
Write-Host "  Readiness:     https://$fqdn/readyz" -ForegroundColor White
Write-Host "  Auth Method:   API Key (Bearer token)" -ForegroundColor White
Write-Host "  LLM Routing:   direct (BYOK)" -ForegroundColor White
Write-Host "  Tier:          $Tier" -ForegroundColor White
Write-Host "  Replicas:      1 persistent MCP controller" -ForegroundColor White
Write-Host ""

# 6. Next steps
Write-Host "[6/6] Next steps" -ForegroundColor Cyan
Write-Host "  1. Set your LLM API keys:" -ForegroundColor Gray
Write-Host "     az keyvault secret set --vault-name primr-$DeploymentName-kv --name XAI-API-KEY --value <your-key>" -ForegroundColor DarkGray
Write-Host "  2. Validate the deployment:" -ForegroundColor Gray
Write-Host "     .\deploy.ps1 -Validate" -ForegroundColor DarkGray
Write-Host "  3. When done testing, destroy:" -ForegroundColor Gray
Write-Host "     .\deploy.ps1 -Destroy" -ForegroundColor DarkGray
Write-Host ""
Write-Host "[OK] Deployment complete!" -ForegroundColor Green
