#!/bin/bash
exec > /var/log/gce-startup-script.log 2>&1
set -x
echo "Starting VM initialization: GUI, Miniconda, and Agent Workspace..."

export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get upgrade -y

# ---------------------------------------------------------
# STEP 1: INSTALL GUI (XFCE) AND SYSTEM DEPENDENCIES
# ---------------------------------------------------------
echo "Installing XFCE Desktop, XRDP, and core tools..."
apt-get install -y xfce4 xfce4-goodies xrdp dbus-x11 firefox-esr curl wget git build-essential

echo "xfce4-session" > /etc/skel/.xsession
systemctl enable xrdp

# Create the dedicated RDP user
useradd -m -s /bin/bash highview19
echo "highview19:mubxiG-4" | chpasswd
usermod -aG sudo highview19
systemctl restart xrdp

# ---------------------------------------------------------
# STEP 2: INSTALL NODE.JS & CLAUDE CODE AGENT MANAGER
# ---------------------------------------------------------
echo "Installing Node.js and Anthropic Claude Code CLI..."
# Claude Code requires Node.js to run globally
curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
apt-get install -y nodejs

# Install Claude Code globally via npm
npm install -g @anthropic-ai/claude-code

# ---------------------------------------------------------
# STEP 3: INSTALL MINICONDA
# ---------------------------------------------------------
echo "Installing Miniconda..."
cd /tmp
wget -q https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh -O miniconda.sh
bash miniconda.sh -b -p /opt/miniconda3
rm miniconda.sh

# Add conda to the system path for all users
echo 'export PATH="/opt/miniconda3/bin:$PATH"' > /etc/profile.d/conda.sh

# ---------------------------------------------------------
# STEP 4: CONFIGURE PYTHON ENVIRONMENT & MODULES
# ---------------------------------------------------------
echo "Creating agent_env and installing Python modules..."
/opt/miniconda3/bin/conda create -y -n agent_env python=3.11

# Install scientific computing and agentic development modules
/opt/miniconda3/envs/agent_env/bin/pip install \
    numpy pandas scipy matplotlib scikit-learn jupyterlab \
    anthropic openai langchain pydantic

# ---------------------------------------------------------
# STEP 5: PERMISSIONS
# ---------------------------------------------------------
echo "Applying user permissions..."
# Grant the RDP user full read/write access to manage Conda environments
chmod -R a+rwX /opt/miniconda3

echo "Startup script completed successfully!"