exec > /var/log/gce-startup-script.log 2>&1
set -x
echo "Starting VM initialization: GUI, MATLAB/Simulink, and Python..."

export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get upgrade -y

# ---------------------------------------------------------
# STEP 1: INSTALL GUI (XFCE), RDP SERVER (xrdp), AND PYTHON
# ---------------------------------------------------------
echo "Installing XFCE Desktop, XRDP, Firefox, and standard Python 3..."
apt-get install -y xfce4 xfce4-goodies xrdp dbus-x11 firefox-esr python3 python3-pip

echo "xfce4-session" > /etc/skel/.xsession
systemctl enable xrdp

# Create user for RDP access
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
echo "Downloading MPM and Installing MATLAB (R2026a)..."
mkdir -p /opt/mathworks
cd /opt/mathworks
wget -q https://www.mathworks.com/mpm/glnxa64/mpm
chmod +x mpm

# Installing the latest release with the Parallel Computing Toolbox
MATLAB_RELEASE="R2026a"
MATLAB_DIR="/usr/local/MATLAB/$MATLAB_RELEASE"

./mpm install \
    --release=$MATLAB_RELEASE \
    --destination=$MATLAB_DIR \
    --products MATLAB Simulink Parallel_Computing_Toolbox

ln -s $MATLAB_DIR/bin/matlab /usr/local/bin/matlab

echo "Startup script completed successfully!"
