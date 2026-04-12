#!/usr/bin/env bash
# ============================================================================
# setup_agent.sh — Environment setup for the lit-review synthesizer agent
# Targets: Debian 13 ARM64, Miniforge3, existing conda env "dspyenv"
#
# Run from the directory containing the framework and pipeline modules:
#   Framework:  config.py, tools.py, prompts.py, sprints.py, orchestrator.py
#   Pipeline:   01_ingest.py .. 06_review.py
#   Spec:       report_synthesizer_v4.md
#
# Usage:
#   chmod +x setup_agent.sh
#   ./setup_agent.sh
# ============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_DIR="${SCRIPT_DIR}/workspace/lit_review_pipeline"
CONDA_ENV="dspyenv"
CONDA_BASE="${HOME}/miniforge3"
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

pass_mark="${GREEN}✓${NC}"
fail_mark="${RED}✗${NC}"
warn_mark="${YELLOW}!${NC}"

echo ""
echo -e "${CYAN}============================================${NC}"
echo -e "${CYAN} Lit-Review Agent — Environment Setup${NC}"
echo -e "${CYAN}============================================${NC}"
echo ""
echo "  Working directory: ${SCRIPT_DIR}"
echo "  Conda env:         ${CONDA_ENV}"
echo "  Workspace:         ${WORKSPACE_DIR}"
echo ""

# ==================================================================
# 1. Activate conda environment
# ==================================================================
echo -e "${CYAN}[1/8] Activating conda environment '${CONDA_ENV}'...${NC}"
if [ ! -d "${CONDA_BASE}" ]; then
    echo -e "  ${fail_mark} Miniforge3 not found at ${CONDA_BASE}"
    echo "      Install from: https://github.com/conda-forge/miniforge"
    exit 1
fi
eval "$(${CONDA_BASE}/bin/conda shell.bash hook)"
if ! conda activate "${CONDA_ENV}" 2>/dev/null; then
    echo -e "  ${fail_mark} Conda env '${CONDA_ENV}' not found."
    echo "      Create it:  conda create -n ${CONDA_ENV} python=3.11 -y"
    exit 1
fi
echo -e "  ${pass_mark} Python $(python --version 2>&1 | cut -d' ' -f2) at $(which python)"

# ==================================================================
# 2. Verify framework and pipeline files
# ==================================================================
echo ""
echo -e "${CYAN}[2/8] Checking framework and pipeline files...${NC}"

FRAMEWORK_FILES=(
    "config.py"
    "tools.py"
    "prompts.py"
    "sprints.py"
    "orchestrator.py"
    "report_synthesizer_v4.md"
)

PIPELINE_FILES=(
    "01_ingest.py"
    "02_parse.py"
    "03_chunk.py"
    "04_index.py"
    "05_query.py"
    "06_review.py"
)

missing_framework=()
for f in "${FRAMEWORK_FILES[@]}"; do
    if [ -f "${SCRIPT_DIR}/${f}" ]; then
        echo -e "  ${pass_mark} ${f}"
    else
        echo -e "  ${fail_mark} ${f}  — MISSING"
        missing_framework+=("${f}")
    fi
done

missing_pipeline=()
for f in "${PIPELINE_FILES[@]}"; do
    if [ -f "${SCRIPT_DIR}/${f}" ]; then
        echo -e "  ${pass_mark} ${f}"
    else
        echo -e "  ${warn_mark} ${f}  — missing (pipeline stage)"
        missing_pipeline+=("${f}")
    fi
done

if [ ${#missing_framework[@]} -gt 0 ]; then
    echo ""
    echo -e "  ${fail_mark} Missing framework files are required. Cannot continue."
    echo "      Missing: ${missing_framework[*]}"
    exit 1
fi

if [ ${#missing_pipeline[@]} -gt 0 ]; then
    echo ""
    echo -e "  ${warn_mark} Missing pipeline files (non-blocking for framework setup):"
    echo "      ${missing_pipeline[*]}"
fi

# ==================================================================
# 3. Check Python module dependencies
# ==================================================================
echo ""
echo -e "${CYAN}[3/8] Checking Python module dependencies...${NC}"

# Each entry: "import_name|pip_package|required_by|required_or_optional"
#
# import_name:          the Python import path to test
# pip_package:          the pip install name (may differ from import)
# required_by:          which project files use it
# required_or_optional: "required" or "optional"

DEPS=(
    "pydantic|pydantic|tools.py, 06_review.py, synthesizer models|required"
    "anthropic|anthropic|05_query.py, 06_review.py, synthesizer LLM calls|required"
    "pymupdf4llm|pymupdf4llm|02_parse.py|required"
    "pymupdf|pymupdf|02_parse.py (pymupdf4llm backend)|required"
    "chromadb|chromadb|04_index.py, 05_query.py|required"
    "rank_bm25|rank-bm25|04_index.py|required"
    "sentence_transformers|sentence-transformers|04_index.py, 05_query.py|required"
    "numpy|numpy|chromadb/sentence-transformers dependency|required"
    "yaml|pyyaml|config utilities|optional"
    "requests|requests|GROBID client, API utilities|optional"
    "bs4|beautifulsoup4|metadata extraction fallback|optional"
    "grobid_client|grobid-client-python|01_ingest.py via utils.metadata|optional"
)

missing_required=()
missing_optional=()
installed_count=0
total_count=${#DEPS[@]}

for entry in "${DEPS[@]}"; do
    IFS='|' read -r import_name pip_pkg used_by req_level <<< "${entry}"

    if python -c "import ${import_name}" 2>/dev/null; then
        # Get version if possible
        ver=$(python -c "
try:
    import ${import_name}
    v = getattr(${import_name}, '__version__', None)
    if v: print(v)
    else: print('ok')
except: print('ok')
" 2>/dev/null)
        echo -e "  ${pass_mark} ${import_name} (${ver})"
        ((installed_count++))
    else
        if [ "${req_level}" = "required" ]; then
            echo -e "  ${fail_mark} ${import_name}  — MISSING [${req_level}]  pip: ${pip_pkg}  (${used_by})"
            missing_required+=("${pip_pkg}")
        else
            echo -e "  ${warn_mark} ${import_name}  — missing [${req_level}]  pip: ${pip_pkg}  (${used_by})"
            missing_optional+=("${pip_pkg}")
        fi
    fi
done

echo ""
echo "  Installed: ${installed_count}/${total_count}"

# ------------------------------------------------------------------
# 3b. Report and optionally install missing modules
# ------------------------------------------------------------------
if [ ${#missing_required[@]} -gt 0 ] || [ ${#missing_optional[@]} -gt 0 ]; then
    echo ""
    echo -e "${CYAN}  ── Missing Module Summary ──${NC}"

    if [ ${#missing_required[@]} -gt 0 ]; then
        echo ""
        echo -e "  ${RED}Required (agent will not function without these):${NC}"
        for pkg in "${missing_required[@]}"; do
            echo "    - ${pkg}"
        done
        echo ""
        echo "  Install command:"
        echo "    pip install ${missing_required[*]}"
    fi

    if [ ${#missing_optional[@]} -gt 0 ]; then
        echo ""
        echo -e "  ${YELLOW}Optional (needed for specific pipeline stages):${NC}"
        for pkg in "${missing_optional[@]}"; do
            echo "    - ${pkg}"
        done
        echo ""
        echo "  Install command:"
        echo "    pip install ${missing_optional[*]}"
    fi

    echo ""
    if [ ${#missing_required[@]} -gt 0 ]; then
        read -rp "  Install all missing required packages now? [Y/n] " install_choice
        install_choice="${install_choice:-Y}"
        if [[ "${install_choice}" =~ ^[Yy]$ ]]; then
            echo ""
            echo "  Installing required packages..."
            pip install -q "${missing_required[@]}"
            echo -e "  ${pass_mark} Required packages installed."
        else
            echo ""
            echo -e "  ${warn_mark} Skipped. The agent will fail on import without these."
        fi
    fi

    if [ ${#missing_optional[@]} -gt 0 ]; then
        read -rp "  Install optional packages too? [y/N] " opt_choice
        opt_choice="${opt_choice:-N}"
        if [[ "${opt_choice}" =~ ^[Yy]$ ]]; then
            echo ""
            echo "  Installing optional packages..."
            pip install -q "${missing_optional[@]}"
            echo -e "  ${pass_mark} Optional packages installed."
        fi
    fi
else
    echo -e "  ${pass_mark} All dependencies satisfied."
fi

# ==================================================================
# 4. Ensure Docker is available and pull GROBID
# ==================================================================
echo ""
echo -e "${CYAN}[4/8] Checking Docker and GROBID image...${NC}"
if ! command -v docker &> /dev/null; then
    echo -e "  ${warn_mark} Docker not found. GROBID (01_ingest.py) will be unavailable."
    echo "      Install: sudo apt-get install docker.io"
    DOCKER_OK=false
else
    if ! systemctl is-active --quiet docker 2>/dev/null; then
        echo "  Starting Docker daemon..."
        sudo systemctl start docker
        sudo systemctl enable docker
    fi
    if ! groups | grep -q docker; then
        sudo usermod -aG docker "$USER"
        echo -e "  ${warn_mark} Added $USER to docker group (log out/in to take effect)."
    fi

    if docker image inspect lfoppiano/grobid:0.8.1 > /dev/null 2>&1; then
        echo -e "  ${pass_mark} GROBID image already present."
    else
        echo "  Pulling lfoppiano/grobid:0.8.1 (may take a few minutes)..."
        sudo docker pull lfoppiano/grobid:0.8.1
        echo -e "  ${pass_mark} GROBID image pulled."
    fi
    DOCKER_OK=true
fi

# ==================================================================
# 5. Create workspace directory structure
# ==================================================================
echo ""
echo -e "${CYAN}[5/8] Creating workspace directories...${NC}"

# Pipeline workspace (stages 01–06)
mkdir -p "${WORKSPACE_DIR}/data/pdfs"
mkdir -p "${WORKSPACE_DIR}/data/parsed"
mkdir -p "${WORKSPACE_DIR}/data/summaries"
mkdir -p "${WORKSPACE_DIR}/vectorstore"
mkdir -p "${WORKSPACE_DIR}/utils"
echo -e "  ${pass_mark} Pipeline workspace: ${WORKSPACE_DIR}"

# Synthesizer module tree (from sprints.py artifacts_in_scope)
SYNTH_DIR="${WORKSPACE_DIR}/synthesizer"
mkdir -p "${SYNTH_DIR}/models"
mkdir -p "${SYNTH_DIR}/loaders"
mkdir -p "${SYNTH_DIR}/validation"
mkdir -p "${SYNTH_DIR}/retrieval"
mkdir -p "${SYNTH_DIR}/prompt"
mkdir -p "${SYNTH_DIR}/extraction"
mkdir -p "${SYNTH_DIR}/assembly"
mkdir -p "${SYNTH_DIR}/orchestrator"
mkdir -p "${SYNTH_DIR}/observability"
mkdir -p "${SYNTH_DIR}/acceptance"
echo -e "  ${pass_mark} Synthesizer module tree: ${SYNTH_DIR}"

# Test directory
mkdir -p "${WORKSPACE_DIR}/tests"
echo -e "  ${pass_mark} Test directory: ${WORKSPACE_DIR}/tests"

# Synthesizer output directory (§15 layout, created at runtime too)
mkdir -p "${WORKSPACE_DIR}/data/synthesis/sections"
mkdir -p "${WORKSPACE_DIR}/data/synthesis/report"
echo -e "  ${pass_mark} Synthesis output scaffold: ${WORKSPACE_DIR}/data/synthesis"

# Write __init__.py files so the synthesizer tree is importable
find "${SYNTH_DIR}" -type d -exec sh -c '
    init="$1/__init__.py"
    if [ ! -f "$init" ]; then touch "$init"; fi
' _ {} \;
if [ ! -f "${WORKSPACE_DIR}/tests/__init__.py" ]; then
    touch "${WORKSPACE_DIR}/tests/__init__.py"
fi
echo -e "  ${pass_mark} __init__.py files written"

# ==================================================================
# 6. Copy framework files into workspace
# ==================================================================
echo ""
echo -e "${CYAN}[6/8] Copying framework and pipeline files to workspace...${NC}"

for f in "${FRAMEWORK_FILES[@]}"; do
    if [ -f "${SCRIPT_DIR}/${f}" ]; then
        cp "${SCRIPT_DIR}/${f}" "${WORKSPACE_DIR}/${f}"
    fi
done

for f in "${PIPELINE_FILES[@]}"; do
    if [ -f "${SCRIPT_DIR}/${f}" ]; then
        cp "${SCRIPT_DIR}/${f}" "${WORKSPACE_DIR}/${f}"
    fi
done

echo -e "  ${pass_mark} Files copied to ${WORKSPACE_DIR}"

# ==================================================================
# 7. Write .env file with configuration
# ==================================================================
echo ""
echo -e "${CYAN}[7/8] API key configuration...${NC}"
ENV_FILE="${WORKSPACE_DIR}/.env"
if [ -f "${ENV_FILE}" ] && grep -q "ANTHROPIC_API_KEY" "${ENV_FILE}"; then
    echo -e "  ${pass_mark} .env already exists with ANTHROPIC_API_KEY — skipping."
else
    echo ""
    read -rp "  Enter your Anthropic API key (or press Enter to skip): " API_KEY
    if [ -n "${API_KEY}" ]; then
        cat > "${ENV_FILE}" <<EOF
# ── Lit-Review Agent Configuration ──
# Generated by setup_agent.sh on $(date -Iseconds)

# Anthropic API
ANTHROPIC_API_KEY=${API_KEY}

# Pipeline paths
WORKSPACE_ROOT=${WORKSPACE_DIR}
GROBID_URL=http://localhost:8070

# Model configuration (DR-16: open — configurable per role)
AGENT_MODEL=claude-sonnet-4-20250514
PIPELINE_MODEL=claude-sonnet-4-20250514
EQUATION_BACKEND=claude_vision

# Synthesizer configuration (§16)
# SYNTHESIZER_REPORT_PLAN_PATH=       # set before running synthesizer
# SYNTHESIZER_STYLE_SHEET_PATH=       # set before running synthesizer
# SYNTHESIZER_OUTPUT_DIR=${WORKSPACE_DIR}/data/synthesis
# SYNTHESIZER_CASCADE_DEPTH_LIMIT=3
# SYNTHESIZER_LAYER1_RETRY_LIMIT=3
# SYNTHESIZER_LAYER2_RETRY_LIMIT=3
# SYNTHESIZER_LAYER3_RETRY_LIMIT=2
# SYNTHESIZER_CLAIM_EXTRACTION_RETRY_LIMIT=1
# SYNTHESIZER_TOKEN_BUDGET_CEILING=   # None = no limit (DR-17)
EOF
        chmod 600 "${ENV_FILE}"
        echo -e "  ${pass_mark} Written to ${ENV_FILE}"
    else
        echo -e "  ${warn_mark} Skipped. Set ANTHROPIC_API_KEY before running the agent."
    fi
fi

# ==================================================================
# 8. Final import verification
# ==================================================================
echo ""
echo -e "${CYAN}[8/8] Running final import verification...${NC}"

VERIFY_RESULT=$(python -c "
import sys

errors = []
warnings = []

# ── Required: stdlib ──
for mod in ['json', 'logging', 'os', 're', 'tempfile', 'time', 'pathlib',
            'collections', 'dataclasses', 'datetime', 'typing', 'argparse', 'pickle']:
    try:
        __import__(mod)
    except ImportError:
        errors.append(f'stdlib {mod}')

# ── Required: third-party ──
required = {
    'pydantic':              'pydantic',
    'anthropic':             'anthropic',
    'pymupdf4llm':           'pymupdf4llm',
    'pymupdf':               'pymupdf',
    'chromadb':              'chromadb',
    'rank_bm25':             'rank-bm25',
    'sentence_transformers': 'sentence-transformers',
    'numpy':                 'numpy',
}
for imp, pip_name in required.items():
    try:
        __import__(imp)
    except ImportError:
        errors.append(f'{imp} (pip install {pip_name})')

# ── Required: framework modules (from workspace) ──
sys.path.insert(0, '${WORKSPACE_DIR}')
for mod in ['tools', 'sprints', 'prompts']:
    try:
        __import__(mod)
    except Exception as e:
        errors.append(f'{mod}.py import: {e}')

# ── Optional ──
for imp, pip_name in [('yaml', 'pyyaml'), ('requests', 'requests'),
                       ('bs4', 'beautifulsoup4'), ('grobid_client', 'grobid-client-python')]:
    try:
        __import__(imp)
    except ImportError:
        warnings.append(f'{imp} (pip install {pip_name})')

# ── Report ──
if errors:
    print('ERRORS')
    for e in errors:
        print(f'  MISSING: {e}')
    sys.exit(1)
elif warnings:
    print('WARNINGS')
    for w in warnings:
        print(f'  optional: {w}')
else:
    print('OK')
" 2>&1) || true

if echo "${VERIFY_RESULT}" | grep -q "^OK"; then
    echo -e "  ${pass_mark} All critical imports verified."
elif echo "${VERIFY_RESULT}" | grep -q "^WARNINGS"; then
    echo -e "  ${pass_mark} All critical imports verified."
    echo "${VERIFY_RESULT}" | tail -n +2 | while read -r line; do
        echo -e "  ${warn_mark} ${line}"
    done
elif echo "${VERIFY_RESULT}" | grep -q "^ERRORS"; then
    echo ""
    echo -e "  ${fail_mark} Import verification failed:"
    echo "${VERIFY_RESULT}" | tail -n +2 | while read -r line; do
        echo -e "  ${fail_mark} ${line}"
    done
    echo ""
    echo "  Fix the errors above and re-run this script."
    exit 1
else
    echo -e "  ${fail_mark} Unexpected verification output:"
    echo "${VERIFY_RESULT}"
    exit 1
fi

# ==================================================================
# Summary
# ==================================================================
echo ""
echo -e "${CYAN}============================================${NC}"
echo -e "${CYAN} Setup Complete${NC}"
echo -e "${CYAN}============================================${NC}"
echo ""
echo "  Workspace:      ${WORKSPACE_DIR}"
echo "  Synthesizer:    ${SYNTH_DIR}"
echo "  Tests:          ${WORKSPACE_DIR}/tests"
echo "  Spec:           ${WORKSPACE_DIR}/report_synthesizer_v4.md"
echo ""
echo "  Directory tree:"
echo ""
echo "  workspace/lit_review_pipeline/"
echo "  ├── config.py, tools.py, prompts.py, sprints.py, orchestrator.py"
echo "  ├── 01_ingest.py .. 06_review.py"
echo "  ├── report_synthesizer_v4.md"
echo "  ├── .env"
echo "  ├── data/"
echo "  │   ├── pdfs/            ← drop PDFs here"
echo "  │   ├── parsed/"
echo "  │   ├── summaries/"
echo "  │   └── synthesis/       ← synthesizer output (§15)"
echo "  ├── vectorstore/"
echo "  ├── utils/"
echo "  ├── synthesizer/"
echo "  │   ├── models/          ← Sprint 1, 2, 3, 4, 5"
echo "  │   ├── loaders/         ← Sprint 1"
echo "  │   ├── validation/      ← Sprint 1, 4"
echo "  │   ├── retrieval/       ← Sprint 3"
echo "  │   ├── prompt/          ← Sprint 3"
echo "  │   ├── extraction/      ← Sprint 5"
echo "  │   ├── assembly/        ← Sprint 5"
echo "  │   ├── orchestrator/    ← Sprint 2, 5, 6"
echo "  │   ├── observability/   ← Sprint 6"
echo "  │   └── acceptance/      ← Sprint 6"
echo "  └── tests/               ← all sprints"
echo ""
echo "  To begin working:"
echo ""
echo "    cd ${WORKSPACE_DIR}"
echo "    conda activate ${CONDA_ENV}"
if [ -f "${ENV_FILE}" ]; then
echo "    set -a && source .env && set +a"
else
echo "    export ANTHROPIC_API_KEY='your-key-here'"
fi
echo ""
echo "  To run the pipeline (stages 01–06):"
echo "    python 01_ingest.py && python 02_parse.py && python 03_chunk.py \\"
echo "      && python 04_index.py && python 05_query.py && python 06_review.py"
echo ""
echo "  To start GROBID (needed for 01_ingest.py):"
if [ "${DOCKER_OK}" = true ]; then
echo "    docker run -d --rm -p 8070:8070 lfoppiano/grobid:0.8.1"
else
echo "    (Docker not available — install Docker first)"
fi
echo ""
echo "  To run sprint generation (after pipeline completes):"
echo "    python -c \"import prompts; print(prompts.build_prompt_for_sprint('sprint_1'))\""
echo ""
echo "  Drop your PDFs into:"
echo "    ${WORKSPACE_DIR}/data/pdfs/"
echo ""