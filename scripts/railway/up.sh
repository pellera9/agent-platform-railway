#!/bin/bash

############################################################################
#
#    Agno Railway Setup (first-time provisioning)
#
#    Usage:     ./scripts/railway/up.sh
#    Redeploy:  ./scripts/railway/redeploy.sh
#    Sync env:  ./scripts/railway/env-sync.sh
#
#    Prerequisites:
#      - Railway CLI installed
#      - Logged in via `railway login`
#      - OPENAI_API_KEY set in environment (or .env / .env.production)
#
############################################################################

set -e

# Colors
ORANGE='\033[38;5;208m'
DIM='\033[2m'
BOLD='\033[1m'
NC='\033[0m'

echo ""
echo -e "${ORANGE}"
cat << 'BANNER'
     █████╗  ██████╗ ███╗   ██╗ ██████╗
    ██╔══██╗██╔════╝ ████╗  ██║██╔═══██╗
    ███████║██║  ███╗██╔██╗ ██║██║   ██║
    ██╔══██║██║   ██║██║╚██╗██║██║   ██║
    ██║  ██║╚██████╔╝██║ ╚████║╚██████╔╝
    ╚═╝  ╚═╝ ╚═════╝ ╚═╝  ╚═══╝ ╚═════╝
BANNER
echo -e "${NC}"

# Persist a resolved value back into the env file so it stays a faithful record
# of the deploy (and env-sync.sh keeps managing it). Replaces an existing
# commented-or-uncommented `KEY=` line in place; appends if the key is absent.
# Rewrites via the original file (not `mv`) so the file keeps its inode +
# permissions. The `|` sed delimiter avoids clashing with URL slashes. No-op
# when the file is missing.
persist_env_var() {
    local key="$1" value="$2" file="$3" tmp
    [[ -z "$file" || ! -f "$file" ]] && return
    if grep -qE "^[#[:space:]]*${key}=" "$file"; then
        tmp="$(mktemp)"
        if sed -E "s|^[#[:space:]]*${key}=.*|${key}=${value}|" "$file" > "$tmp"; then
            cat "$tmp" > "$file"
        fi
        rm -f "$tmp"
    else
        printf '\n%s=%s\n' "$key" "$value" >> "$file"
    fi
}

# Load env file — .env.production preferred for Railway, .env as fallback.
# Parsed line-by-line (not `source`d) so an unquoted multi-line PEM
# JWT_VERIFICATION_KEY isn't interpreted as shell. Mirrors the parser in
# env-sync.sh so both scripts read .env files identically.
ENV_FILE=""
[[ -f .env.production ]] && ENV_FILE=".env.production"
[[ -z "$ENV_FILE" && -f .env ]] && ENV_FILE=".env"

if [[ -n "$ENV_FILE" ]]; then
    current_key=""
    current_value=""
    while IFS= read -r line || [[ -n "$line" ]]; do
        if [[ -z "$current_key" ]]; then
            [[ -z "$line" || "$line" =~ ^[[:space:]]*# ]] && continue
        fi

        if [[ -z "$current_key" ]]; then
            current_key="${line%%=*}"
            current_value="${line#*=}"
        else
            current_value="${current_value}
${line}"
        fi

        # Still inside a PEM block — keep accumulating lines.
        if [[ "$current_value" == *"-----BEGIN"* && "$current_value" != *"-----END"* ]]; then
            continue
        fi

        # Strip surrounding quotes if present
        current_value="${current_value#\"}"
        current_value="${current_value%\"}"
        current_value="${current_value#\'}"
        current_value="${current_value%\'}"

        export "${current_key}=${current_value}"

        current_key=""
        current_value=""
    done < "$ENV_FILE"
    echo -e "${DIM}Loaded ${ENV_FILE}${NC}"
fi

# Preflight
if ! command -v railway &> /dev/null; then
    echo "Railway CLI not found. Install: https://docs.railway.app/guides/cli"
    exit 1
fi

if [[ -z "$OPENAI_API_KEY" ]]; then
    echo "OPENAI_API_KEY not set. Add to .env (or .env.production) or export it."
    exit 1
fi

echo -e "${BOLD}Initializing project...${NC}"
echo ""
railway init -n "agent-platform"

echo ""
echo -e "${BOLD}Deploying PgVector database...${NC}"
echo ""
railway add -s pgvector -i agnohq/pgvector:18 \
    -v "POSTGRES_USER=${DB_USER:-ai}" \
    -v "POSTGRES_PASSWORD=${DB_PASS:-ai}" \
    -v "POSTGRES_DB=${DB_DATABASE:-ai}"

echo ""
echo -e "${BOLD}Adding database volume...${NC}"
railway service link pgvector
railway volume add -m /var/lib/postgresql 2>/dev/null || echo -e "${DIM}Volume already exists or skipped${NC}"

echo ""
echo -e "${DIM}Waiting 15s for database...${NC}"
sleep 15

echo ""
echo -e "${BOLD}Creating application service...${NC}"
echo ""
# Forward every relevant env var the first deploy might need. Optional
# keys are only included when set — Railway CLI rejects empty values.
# Use ./scripts/railway/env-sync.sh to sync the rest from .env later.
RAILWAY_VARS=(
    -v "DB_USER=${DB_USER:-ai}"
    -v "DB_PASS=${DB_PASS:-ai}"
    -v "DB_HOST=pgvector.railway.internal"
    -v "DB_PORT=${DB_PORT:-5432}"
    -v "DB_DATABASE=${DB_DATABASE:-ai}"
    -v "DB_DRIVER=postgresql+psycopg"
    -v "WAIT_FOR_DB=True"
    -v "PORT=8000"
    -v "OPENAI_API_KEY=${OPENAI_API_KEY}"
)
[[ -n "$PARALLEL_API_KEY" ]] && RAILWAY_VARS+=(-v "PARALLEL_API_KEY=${PARALLEL_API_KEY}")
# Forward AGENTOS_URL only if the env file already pinned one; otherwise it's
# derived from the fresh domain below.
[[ -n "$AGENTOS_URL" ]] && RAILWAY_VARS+=(-v "AGENTOS_URL=${AGENTOS_URL}")

railway add -s agent-os "${RAILWAY_VARS[@]}"

# Domain before deploy — capture it so AGENTOS_URL is set on the service
# *before* it serves, and so os.agno.com can mint JWT_VERIFICATION_KEY against
# the real domain.
echo ""
echo -e "${BOLD}Creating domain...${NC}"
echo ""
DOMAIN_OUTPUT="$(railway domain --service agent-os 2>&1 || true)"
echo "$DOMAIN_OUTPUT"
APP_URL="$(grep -oE 'https://[A-Za-z0-9.-]+|[A-Za-z0-9-]+\.up\.railway\.app' <<< "$DOMAIN_OUTPUT" | head -1)"
[[ -n "$APP_URL" && "$APP_URL" != https://* ]] && APP_URL="https://${APP_URL}"

# The scheduler reaches AgentOS over its public URL. Without AGENTOS_URL it
# defaults to http://127.0.0.1:8000, so scheduled jobs silently never fire in
# prod. Default it to the fresh domain (unless the env file pinned one), and
# write it back into the env file so .env.production stays a faithful record
# and env-sync.sh keeps managing it.
AGENTOS_URL_PERSISTED=""
if [[ -z "$AGENTOS_URL" && -n "$APP_URL" ]]; then
    railway variables --set "AGENTOS_URL=${APP_URL}" --service agent-os > /dev/null
    persist_env_var AGENTOS_URL "$APP_URL" "$ENV_FILE"
    [[ -n "$ENV_FILE" ]] && AGENTOS_URL_PERSISTED=1
    echo -e "${DIM}Set AGENTOS_URL=${APP_URL} (Railway${AGENTOS_URL_PERSISTED:+ + ${ENV_FILE}})${NC}"
fi

echo ""
echo -e "${BOLD}Deploying application...${NC}"
echo ""
railway up --service agent-os -d

echo ""
echo -e "${BOLD}Done.${NC} Domain may take ~5 minutes."
[[ -n "$APP_URL" ]] && echo -e "${DIM}URL:            ${APP_URL}${NC}"
echo -e "${DIM}Logs:           railway logs --service agent-os${NC}"
echo -e "${DIM}Sync env vars:  ./scripts/railway/env-sync.sh  (defaults to .env.production)${NC}"
echo ""
