#!/usr/bin/env bash
set -euo pipefail

# ── Colors ────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
DIM='\033[2m'
NC='\033[0m'

ok()    { echo -e "  ${GREEN}✓${NC} $1"; }
warn()  { echo -e "  ${YELLOW}!${NC} $1"; }
fail()  { echo -e "  ${RED}✗${NC} $1"; }
info()  { echo -e "  ${DIM}$1${NC}"; }
ask()   { echo -en "  ${BOLD}$1${NC}"; }

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

ENV_FILE="$SCRIPT_DIR/.env"
CONFIG_FILE="$SCRIPT_DIR/config.yaml"

# ── Banner ────────────────────────────────────────────────────────
clear
echo ""
echo -e "${CYAN}${BOLD}  ┌─────────────────────────────────────┐${NC}"
echo -e "${CYAN}${BOLD}  │         CMAS Setup Wizard           │${NC}"
echo -e "${CYAN}${BOLD}  │   Cognitive Multi-Agent System      │${NC}"
echo -e "${CYAN}${BOLD}  └─────────────────────────────────────┘${NC}"
echo ""

# ── Disclaimer ────────────────────────────────────────────────────
echo -e "${RED}${BOLD}  DISCLAIMER & ASSUMPTION OF RISK${NC}"
echo -e "${DIM}  ─────────────────────────────────────────────────────────────${NC}"
echo -e "  This script installs software, creates a Python virtual environment,"
echo -e "  writes configuration files, and may execute shell commands on your system."
echo ""
echo -e "  ${BOLD}By continuing, you acknowledge and agree that:${NC}"
echo ""
echo -e "  ${DIM}1.${NC} You are running this script voluntarily on a system you own or"
echo -e "     have explicit authorization to modify."
echo -e "  ${DIM}2.${NC} CMAS executes AI-generated code, shell commands, and file operations"
echo -e "     autonomously. You are responsible for supervising its actions."
echo -e "  ${DIM}3.${NC} The authors and contributors of CMAS bear no liability for any"
echo -e "     damage, data loss, security incidents, or unintended consequences"
echo -e "     arising from the use of this software."
echo -e "  ${DIM}4.${NC} This software is provided AS-IS under the PolyForm Noncommercial"
echo -e "     License 1.0.0, with no warranty of any kind, express or implied."
echo -e "  ${DIM}5.${NC} You assume full and sole responsibility for any outcome."
echo ""
echo -e "${DIM}  ─────────────────────────────────────────────────────────────${NC}"
echo ""
ask "  Type  YES  to accept and continue, or press Ctrl+C to exit: "
read -r ACCEPT
echo ""
if [ "$ACCEPT" != "YES" ]; then
    fail "Setup cancelled. You must type YES (all caps) to proceed."
    exit 1
fi
ok "Disclaimer accepted."
echo ""

# ── Security Warning ──────────────────────────────────────────────
echo -e "${YELLOW}${BOLD}  SECURITY NOTICE: Keys are stored exclusively in '.env' and are completely ignored by git. NEVER share or commit your .env file!${NC}"
echo ""

# ── Step 1: Check Python ─────────────────────────────────────────
echo -e "${BLUE}${BOLD}  [1/6] Checking Python...${NC}"

if ! command -v python3 &> /dev/null; then
    fail "Python 3 not found. Install Python 3.9+ and try again."
    exit 1
fi

PY_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
PY_MAJOR=$(python3 -c 'import sys; print(sys.version_info.major)')
PY_MINOR=$(python3 -c 'import sys; print(sys.version_info.minor)')

if [ "$PY_MAJOR" -lt 3 ] || ([ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 9 ]); then
    fail "Python $PY_VERSION found, but 3.9+ is required."
    exit 1
fi
ok "Python $PY_VERSION"

# ── Step 2: Virtual Environment & Dependencies ───────────────────
echo ""
echo -e "${BLUE}${BOLD}  [2/6] Setting up environment...${NC}"

if [ ! -d ".venv" ]; then
    info "Creating virtual environment..."
    python3 -m venv .venv
    ok "Virtual environment created"
else
    ok "Virtual environment exists"
fi

source .venv/bin/activate
info "Installing dependencies..."
pip install -q -r requirements.txt 2>&1 | tail -1 || true
ok "Dependencies installed"

# ── Step 3: API Keys ─────────────────────────────────────────────
echo ""
echo -e "${BLUE}${BOLD}  [3/6] API Keys${NC}"
echo ""

EXISTING_OPENAI=""
EXISTING_TAVILY=""
if [ -f "$ENV_FILE" ]; then
    EXISTING_OPENAI=$(grep -E "^OPENAI_API_KEY=" "$ENV_FILE" 2>/dev/null | cut -d= -f2- || true)
    EXISTING_TAVILY=$(grep -E "^TAVILY_API_KEY=" "$ENV_FILE" 2>/dev/null | cut -d= -f2- || true)
fi

if [ -n "$EXISTING_OPENAI" ] && [ "$EXISTING_OPENAI" != "sk-your-key-here" ]; then
    ok "OpenAI API key already configured"
    OPENAI_KEY="$EXISTING_OPENAI"
else
    info "Powers all AI responses (https://platform.openai.com/api-keys)"
    ask "OpenAI API Key: "
    read -rs OPENAI_KEY
    echo ""
    if [ -z "$OPENAI_KEY" ]; then
        fail "OpenAI API key is required. Re-run setup when you have one."
        exit 1
    fi
    ok "OpenAI key set"
fi

# Tavily (optional)
if [ -n "$EXISTING_TAVILY" ] && [ "$EXISTING_TAVILY" != "tvly-your-key-here" ]; then
    ok "Tavily API key already configured"
    TAVILY_KEY="$EXISTING_TAVILY"
else
    info "Enables web search for research tasks (https://tavily.com)"
    ask "Tavily API Key (Enter to skip): "
    read -rs TAVILY_KEY
    echo ""
    if [ -n "$TAVILY_KEY" ]; then
        ok "Tavily key set"
    else
        warn "Skipped — web search will be disabled"
        TAVILY_KEY=""
    fi
fi

# ── Step 4: Model Configuration ──────────────────────────────────
echo ""
echo -e "${BLUE}${BOLD}  [4/6] Model Selection${NC}"
echo "  [1] gpt-4.1-nano (Recommended — Fast & Efficient)"
echo "  [2] gpt-4.1-mini (Advanced — Best for complex research)"
echo "  [3] Custom Model String"
ask "  Select default model [1]: "
read -r MODEL_CHOICE

case "$MODEL_CHOICE" in
    2) DEFAULT_MODEL="gpt-4.1-mini" ;;
    3) ask "     Type model name: "; read -r DEFAULT_MODEL ;;
    *) DEFAULT_MODEL="gpt-4.1-nano" ;;
esac
ok "Default Model set to $DEFAULT_MODEL"

# ── Step 5: Channels (Multiple Select) ───────────────────────────
echo ""
echo -e "${BLUE}${BOLD}  [5/6] Channels${NC}"
echo "  Select the channels you want to enable. (Web UI is always on)"
echo "  [1] Discord Bot"
echo "  [2] WhatsApp (via Twilio)"
echo ""
ask "  Enter your choices separated by space (or press Enter to skip): "
read -r CHANNEL_CHOICES

DISCORD_ENABLED="false"
DISCORD_TOKEN=""
WHATSAPP_ENABLED="false"
TWILIO_SID=""
TWILIO_TOKEN=""
TWILIO_PHONE=""

for choice in $CHANNEL_CHOICES; do
    case $choice in
        1)
            echo ""
            info "Discord Setup (https://discord.com/developers/applications)"
            ask "  Bot Token: "
            read -rs DISCORD_TOKEN
            echo ""
            if [ -n "$DISCORD_TOKEN" ]; then
                DISCORD_ENABLED="true"
                pip install -q "discord.py>=2.3"
                ok "Discord Enabled"
            else
                warn "Empty token, skipping Discord."
            fi
            ;;
        2)
            echo ""
            info "WhatsApp Setup (https://www.twilio.com)"
            ask "  Twilio Account SID: "
            read -r TWILIO_SID
            ask "  Twilio Auth Token: "
            read -rs TWILIO_TOKEN
            echo ""
            ask "  Twilio WhatsApp Number: "
            read -r TWILIO_PHONE
            if [ -n "$TWILIO_SID" ]; then
                WHATSAPP_ENABLED="true"
                pip install -q "twilio>=8.0"
                ok "WhatsApp Enabled"
            fi
            ;;
    esac
done

# ── Step 6: Write Configurations ─────────────────────────────────
echo ""
echo -e "${BLUE}${BOLD}  [6/6] Finalizing...${NC}"

# Autodetect timezone
DETECTED_TZ=$(python3 -c "try:
    import time; offset = time.timezone if time.daylight == 0 else time.altzone
    print(f'UTC{-offset//3600:+d}')
except: print('UTC')" 2>/dev/null || echo "UTC")

# Write .env
cat > "$ENV_FILE" << ENVEOF
# CMAS Environment Keys
# !DO NOT COMMIT THIS FILE!

OPENAI_API_KEY=${OPENAI_KEY}
TAVILY_API_KEY=${TAVILY_KEY}
ENVEOF

if [ "$DISCORD_ENABLED" = "true" ]; then
    echo "DISCORD_TOKEN=${DISCORD_TOKEN}" >> "$ENV_FILE"
fi
if [ "$WHATSAPP_ENABLED" = "true" ]; then
    cat >> "$ENV_FILE" << ENVEOF
TWILIO_ACCOUNT_SID=${TWILIO_SID}
TWILIO_AUTH_TOKEN=${TWILIO_TOKEN}
TWILIO_WHATSAPP_NUMBER=${TWILIO_PHONE}
ENVEOF
fi
echo "CMAS_TIMEZONE=${DETECTED_TZ}" >> "$ENV_FILE"
ok ".env saved securely."

# Write config.yaml
cat > "$CONFIG_FILE" << CFGEOF
server:
  host: "0.0.0.0"
  port: 8080

model:
  default: "${DEFAULT_MODEL}"
  research: "gpt-4.1-mini"

timezone: "${DETECTED_TZ}"

channels:
  web:
    enabled: true
  discord:
    enabled: ${DISCORD_ENABLED}
  whatsapp:
    enabled: ${WHATSAPP_ENABLED}

memory:
  vector_db_path: "./data/vectors"
  sqlite_path: "./data/cmas.db"
  max_context_messages: 50

scheduler:
  enabled: true
  proactive_interval: 300
CFGEOF
ok "config.yaml saved."

mkdir -p data/vectors data/projects workspace
chmod -R 700 data workspace

echo ""
echo -e "${GREEN}${BOLD}  ┌─────────────────────────────────────┐${NC}"
echo -e "${GREEN}${BOLD}  │          Setup Complete!            │${NC}"
echo -e "${GREEN}${BOLD}  └─────────────────────────────────────┘${NC}"
echo "  Run ./start.sh to boot the AGI framework."
echo ""
