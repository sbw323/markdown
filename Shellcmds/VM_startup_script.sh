#!/bin/bash
exec > /var/log/gce-startup-script.log 2>&1
set -x
echo "Starting VM initialization: GUI, MATLAB/Simulink, and Python..."

export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get upgrade -y

# ---------------------------------------------------------
# STEP 1: INSTALL GUI (XFCE) AND RDP SERVER (xrdp)
# ---------------------------------------------------------
echo "Installing XFCE Desktop, XRDP, and Firefox..."
# dbus-x11 is necessary for remote desktop sessions to spawn correctly in Debian
apt-get install -y xfce4 xfce4-goodies xrdp dbus-x11 firefox-esr

# Configure xRDP to use XFCE by default for all new users
echo "xfce4-session" > /etc/skel/.xsession
systemctl enable xrdp

# Create a dedicated user for your Remote Desktop login
# Google Cloud VMs use SSH keys by default, but RDP requires a real password.
useradd -m -s /bin/bash highview19
echo "highview19:mubxiG-4" | chpasswd
usermod -aG sudo highview19
systemctl restart xrdp

# ---------------------------------------------------------
# STEP 2: INSTALL MATLAB DEPENDENCIES
# ---------------------------------------------------------
echo "Installing dependencies for MATLAB & Simulink..."
apt-get install -y wget curl unzip git xvfb ca-certificates \
    libxext6 libxtst6 libxrender1 libxt6 libxi6 libxrandr2 \
    libxcursor1 libxinerama1 libasound2 libatk1.0-0 \
    libatk-bridge2.0-0 libcups2 libdrm2 libgbm1 libnspr4 \
    libnss3 libpango-1.0-0 libpangocairo-1.0-0

# ---------------------------------------------------------
# STEP 3: AUTOMATICALLY DOWNLOAD & INSTALL MATLAB
# ---------------------------------------------------------
echo "Downloading MPM and Installing MATLAB (R2024a)..."
mkdir -p /opt/mathworks
cd /opt/mathworks
wget -q https://www.mathworks.com/mpm/glnxa64/mpm
chmod +x mpm

# Change the release below (e.g., R2023b, R2024a) to match your MathWorks license!
MATLAB_RELEASE="R2024a"
MATLAB_DIR="/usr/local/MATLAB/$MATLAB_RELEASE"

./mpm install \
    --release=$MATLAB_RELEASE \
    --destination=$MATLAB_DIR \
    --products MATLAB Simulink

ln -s $MATLAB_DIR/bin/matlab /usr/local/bin/matlab

# ---------------------------------------------------------
# STEP 4: INSTALL MINICONDA & PYTHON ENGINE
# ---------------------------------------------------------
echo "Installing Miniconda (PEP 668 compliance)..."
cd /tmp
wget -q https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh -O miniconda.sh
bash miniconda.sh -b -p /opt/miniconda3
rm miniconda.sh
echo 'export PATH="/opt/miniconda3/bin:$PATH"' > /etc/profile.d/conda.sh

echo "Setting up Python Environment (bsm_env)..."
/opt/miniconda3/bin/conda create -y -n bsm_env python=3.11 numpy pandas scipy

# Install MATLAB Engine for Python
cd $MATLAB_DIR/extern/engines/python
/opt/miniconda3/envs/bsm_env/bin/python -m pip install .

# Grant your RDP user full read/write access to the Conda environment
chmod -R a+rwX /opt/miniconda3

echo "Startup script completed successfully!"