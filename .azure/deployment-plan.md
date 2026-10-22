# Azure Deployment Plan

> **Status:** Deployed

## 1. Project Overview

- **Workspace mode:** Modify an existing application.
- **Application:** `web-app/`, a FastAPI/Uvicorn dashboard with static arcade-style UI and Server-Sent Events.
- **Data dependency:** Tiger Cloud / TimescaleDB, reached through `TIMESCALEDB_URL`.
- **Classification:** Demo / proof of concept.
- **Scale:** Small; one app replica at most, with cold starts accepted.
- **Budget:** Cost-optimized. Container Apps compute scales to zero; the registry remains a recurring cost while provisioned.

## 2. Azure Context

- **Subscription:** Current Azure CLI subscription, Visual Studio Enterprise (subscription ID omitted from the repository).
- **Resource group:** `rg_well_actually` (user requested).
- **Location:** `westus2`, the existing resource group's location.
- **User decisions:** Deploy the demo to this resource group; public HTTPS without application login is acceptable for the MVP; scale-to-zero and cold starts are acceptable.

## 3. Architecture

| Component | Azure service / configuration |
|---|---|
| Dashboard | Azure Container Apps Consumption, 0.25 vCPU / 0.5 GiB, minimum replicas 0, maximum replicas 1 |
| Container image | New private Azure Container Registry Basic in `rg_well_actually`; one demo image |
| Ingress | External HTTPS ingress; no application authentication, per user's MVP decision |
| Registry pull | User-assigned managed identity with `AcrPull` scoped to the new registry; the role assignment is created before the app so private image pulls work on first startup |
| Database | Existing external Tiger Cloud / TimescaleDB; pass `TIMESCALEDB_URL` as a Container App secret and environment reference; never bake it into the image |
| Logs / monitoring | No Log Analytics workspace or Application Insights for this cost-minimized demo; the environment has no app-logs destination configured |

The registry incurs a fixed Basic-tier charge while it exists. The dashboard's Consumption compute can scale to zero. Do not delete the resource group for cleanup: it contains existing Azure Cognitive Services resources. After the demo, remove only resources created for this deployment, after user confirmation.

## 4. Deployment Recipe and Artifacts

- **Recipe:** Standalone Bicep for Azure resources; Azure CLI and Docker for validation, image build, and push. No `azure.yaml` / AZD workflow is needed.
- **Planned artifacts:** `infra/main.bicep`, `infra/main.parameters.json` (validation-only placeholder secret), `web-app/Dockerfile`, and `web-app/.dockerignore` (exclude `.env`).
- **Image build:** Build from `web-app/` for `linux/amd64` using the local Docker Buildx CLI; push to the new private registry.
- **Secret handling:** Read the existing local `web-app/.env` value without printing it; set it as an Azure Container App secret, then reference it in the app environment. Never commit or copy `.env` into build context.
- **Identity permissions:** Grant only `AcrPull` to a dedicated user-assigned identity, scoped to the new registry.
- **Provisioning order:** Deploy the template with dashboard provisioning disabled to create the private registry, identity, and scoped role assignment; build and push the image; then deploy with dashboard provisioning enabled to create the Consumption environment and public Container App.

## 5. Provisioning Limit Checklist

| Resource / limit | Current usage | Planned usage | Limit / check |
|---|---:|---:|---|
| `Microsoft.App/managedEnvironments` in `westus2` | 0 | 1 | Limit 20; 19 available after deployment. Checked using Azure quota data. |
| Container Apps in `westus2` | 0 in target resource group | 1 | No separate Container Apps resource-count quota was reported; target group currently has none. |
| Container Registry | 1 existing in subscription | 1 new (2 total) | Registry quota API returned `BadRequest`; Basic tier includes 10 GiB storage (40 TiB documented maximum per registry). One demo image is planned. Registry name `wellactuallydemo2026` was available when checked. |
| Logs workspaces | 0 planned | 0 | Not applicable; logs destination is disabled for this demo. |

Relevant providers are registered. No existing Container Apps environment or app was found in the target resource group. The current Azure Policy assignment observed was the standard subscription-level Azure Security Center policy; no blocking policy was identified.

## 6. Approval

- **Plan approval:** User requested deployment to `rg_well_actually`, accepted public unauthenticated access and scale-to-zero, and instructed autonomous decision-making when unavailable. Proceeding with the lowest ACR tier and registry-scoped `AcrPull`; the Basic registry has a recurring charge until removed.
- **Deployment authorization:** User-directed.

## 7. Validation Proof

### All validation checks pass

- [x] Bicep compilation
- [x] Resource-group template validation
- [x] What-if preview
- [x] Azure CLI authentication
- [x] Bicep lint
- [x] Azure Policy validation
- [x] Static role assignment review
- [x] Docker image build and content verification

| Check | Command / source | Result |
|---|---|---|
| Bicep compile | `az bicep build --file infra/main.bicep --stdout` | Passed |
| Bicep lint | `az bicep lint --file infra/main.bicep` | Passed |
| Template validation | `az deployment group validate --resource-group rg_well_actually --template-file infra/main.bicep --parameters infra/main.parameters.json provisionDashboard=true timescaleDbUrl=validation-only-not-a-credential` | Succeeded |
| What-if | Same template and parameters with `az deployment group what-if` | Succeeded; preview contains only the intended registry, identity, role assignment, Container Apps environment, and app; existing Cognitive Services resources are ignored |
| Azure authentication | `az account show` | Correct subscription: Visual Studio Enterprise |
| Policy review | `az policy assignment list` at subscription and target resource-group scopes | One inherited ASC default assignment; no direct target-group assignment; resource-group template validation succeeded |
| RBAC role | `az role definition list --name AcrPull`; static review of `infra/main.bicep` | `AcrPull` assigned to the dedicated user-assigned identity at the new registry scope only |
| Application tests | `cd web-app && python3 -m unittest discover -s tests` | 10 passed |
| JavaScript | `node --check web-app/static/app.js` | Passed |
| Container image | `docker build` and container import/context checks | Passed; `.env` and tests are excluded |
| Working tree formatting | `git diff --check` | Passed |

Validation completed 2026-10-22 before deployment. The Basic registry, pull identity, role assignment, Consumption environment, and Container App were subsequently created. The initial revision failed because its image was ARM64; the replacement `linux/amd64` image was pushed and deployed successfully.

## Role Assignment Verification

- **Status:** Verified.
- **Identity:** `well-actually-acr-pull` user-assigned managed identity.
- **Role:** `AcrPull` (`7f951dda-4ed3-4680-a7ca-43fe172d538d`).
- **Scope:** Only the new `wellactuallydemo2026` registry.
- **Other app permissions:** None required; `TIMESCALEDB_URL` is a secret for the external database, not an Azure identity permission.

## Deployment Progress

- [x] Phase 1: create the Basic registry, pull identity, and registry-scoped `AcrPull` role.
- [x] Wait for and verify `AcrPull` propagation.
- [x] Build and push the dashboard image (`demo-2026-10-22-amd64`, `linux/amd64`).
- [x] Phase 2: create the Consumption environment and public Container App with the database URL as a secret.
- [x] Verify HTTPS dashboard, database health endpoint, and SSE stream.

The initial app revision used an ARM64 image and failed. Rebuilt for `linux/amd64` and redeployed successfully; no existing resources were modified.

### Deployment Verification

- **Dashboard:** https://well-actually-dashboard.thankfulmushroom-78eaac4c.westus2.azurecontainerapps.io/
- **Homepage:** HTTP 200.
- **Database health:** `/api/health` returned HTTP 200.
- **Live SSE:** `/api/speech-log/stream` returned HTTP 200 (`text/event-stream`) with 80 speech events and a connected event.
- **Browser update behavior:** deployed frontend mapped a zap update to an existing message and applied the immediate shock animation.
- **Revision:** `well-actually-dashboard--wkkfz1o` (`Provisioned`, active).
- **Live `AcrPull` verification:** the user-assigned identity has `AcrPull` on `wellactuallydemo2026` at registry scope only.

Deployment completed 2026-10-22. The public unauthenticated endpoint and Basic ACR remain provisioned for the demo; the ACR has a recurring charge. Cleanup must target only the demo app, environment, identity, registry, and role assignment after user confirmation—not the resource group.
