PROJECT_ROOT="$HOME/bsm-aeration-agent"

# --- Top-level structure ---
mkdir -p "$PROJECT_ROOT"/{config,logs}

# --- Reference materials (read-only source of truth) ---
mkdir -p "$PROJECT_ROOT"/reference/{codebase,stubs,docs}

# --- Sprint directories are created by the orchestrator at runtime,
#     but you can pre-create the top-level folder ---
mkdir -p "$PROJECT_ROOT"/sprints

# --- Checkpoint archive ---
mkdir -p "$PROJECT_ROOT"/checkpoints

# --- Copy your existing MATLAB files into reference/codebase/ ---
# Adjust the source path to wherever your BSM project lives
BSM_SRC="/path/to/your/ASM3/project"

cp "$BSM_SRC/main_sim.m"                "$PROJECT_ROOT/reference/codebase/"
cp "$BSM_SRC/effluent_data_writer.m"    "$PROJECT_ROOT/reference/codebase/"
cp "$BSM_SRC/run_campaign.m"            "$PROJECT_ROOT/reference/codebase/"
cp "$BSM_SRC/ssASM3_influent_sampler.m" "$PROJECT_ROOT/reference/codebase/"
cp "$BSM_SRC/ssInfluent_writer.m"       "$PROJECT_ROOT/reference/codebase/"

# --- Copy the header-only stub ---
cp "$BSM_SRC/generate_KLa_timeseries.m" "$PROJECT_ROOT/reference/stubs/"

# --- Copy design documents ---
# Adjust paths to where you saved these
cp "BSM_Dynamic_Aeration_Experiment___Refactoring_Plan_v2.md" "$PROJECT_ROOT/reference/docs/"
cp "BSM_Dynamic_Control_Modeling_Best_Practices.md"           "$PROJECT_ROOT/reference/docs/"
cp "BSM_Agent_Orchestrator_Plan.md"                           "$PROJECT_ROOT/reference/docs/"

# --- Python project setup ---
cd "$PROJECT_ROOT"

cat > pyproject.toml << 'EOF'
[project]
name = "bsm-aeration-agent"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "claude-agent-sdk>=0.1.44",
    "python-dotenv>=1.0.0",
]

[project.scripts]
run-pipeline = "orchestrator:main"
EOF

cat > .env << 'EOF'
ANTHROPIC_API_KEY=sk-ant-REPLACE_WITH_YOUR_KEY
EOF

# --- Create placeholder Python files ---
touch "$PROJECT_ROOT/orchestrator.py"
touch "$PROJECT_ROOT/config/sprints.py"
touch "$PROJECT_ROOT/config/prompts.py"
touch "$PROJECT_ROOT/config/tools.py"
touch "$PROJECT_ROOT/config/__init__.py"

echo "Workspace scaffolded at $PROJECT_ROOT"
echo "Next steps:"
echo "  1. Edit .env with your Anthropic API key"
echo "  2. Update BSM_SRC path in this script and re-run if files weren't copied"
echo "  3. cd $PROJECT_ROOT && pip install -e ."
echo "  4. Verify MATLAB is on PATH: matlab -batch \"disp('ok')\""