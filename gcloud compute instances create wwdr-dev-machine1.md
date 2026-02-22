gcloud compute instances create wwdr-dev-machine1 \
    --project=wwdr-487920 \
    --zone=us-east4-b \
    --machine-type=e2-custom-4-24576 \
    --network-interface=network-tier=PREMIUM,stack-type=IPV4_ONLY,subnet=default \
    --metadata=^,@^startup-script=\#\!/bin/bash$'\n'exec\ \
\>\ /var/log/gce-startup-script.log\ 2\>\&1$'\n'set\ -x$'\n'echo\ \"Starting\ VM\ initialization:\ GUI,\ MATLAB/Simulink,\ and\ Python...\"$'\n'$'\n'export\ DEBIAN_FRONTEND=noninteractive$'\n'apt-get\ update\ -y$'\n'apt-get\ upgrade\ -y$'\n'$'\n'\#\ \
    ---------------------------------------------------------$'\n'\#\ \
STEP\ 1:\ INSTALL\ GUI\ \(XFCE\)\ AND\ RDP\ SERVER\ \(xrdp\)$'\n'\#\ \
    ---------------------------------------------------------$'\n'echo\ \
\"Installing\ XFCE\ Desktop,\ XRDP,\ and\ Firefox...\"$'\n'\#\ dbus-x11\ is\ necessary\ for\ remote\ desktop\ sessions\ to\ spawn\ correctly\ in\ Debian$'\n'apt-get\ install\ -y\ xfce4\ xfce4-goodies\ xrdp\ dbus-x11\ firefox-esr$'\n'$'\n'\#\ Configure\ xRDP\ to\ use\ XFCE\ by\ default\ for\ all\ new\ users$'\n'echo\ \"xfce4-session\"\ \>\ /etc/skel/.xsession$'\n'systemctl\ enable\ xrdp$'\n'$'\n'\#\ Create\ a\ dedicated\ user\ for\ your\ Remote\ Desktop\ login$'\n'\#\ Google\ Cloud\ VMs\ use\ SSH\ keys\ by\ default,\ but\ RDP\ requires\ a\ real\ password.$'\n'useradd\ -m\ -s\ /bin/bash\ highview19$'\n'echo\ \"highview19:mubxiG-4\"\ \|\ chpasswd$'\n'usermod\ -aG\ sudo\ highview19$'\n'systemctl\ restart\ xrdp$'\n'$'\n'\#\ \
    ---------------------------------------------------------$'\n'\#\ \
STEP\ 2:\ INSTALL\ MATLAB\ DEPENDENCIES$'\n'\#\ \
    ---------------------------------------------------------$'\n'echo\ \
\"Installing\ dependencies\ for\ MATLAB\ \&\ Simulink...\"$'\n'apt-get\ install\ -y\ wget\ curl\ unzip\ git\ xvfb\ ca-certificates\ \\$'\n'\ \ \ \ libxext6\ libxtst6\ libxrender1\ libxt6\ libxi6\ libxrandr2\ \\$'\n'\ \ \ \ libxcursor1\ libxinerama1\ libasound2\ libatk1.0-0\ \\$'\n'\ \ \ \ libatk-bridge2.0-0\ libcups2\ libdrm2\ libgbm1\ libnspr4\ \\$'\n'\ \ \ \ libnss3\ libpango-1.0-0\ libpangocairo-1.0-0$'\n'$'\n'\#\ \
    ---------------------------------------------------------$'\n'\#\ \
STEP\ 3:\ AUTOMATICALLY\ DOWNLOAD\ \&\ INSTALL\ MATLAB$'\n'\#\ \
    ---------------------------------------------------------$'\n'echo\ \
\"Downloading\ MPM\ and\ Installing\ MATLAB\ \(R2024a\)...\"$'\n'mkdir\ -p\ /opt/mathworks$'\n'cd\ /opt/mathworks$'\n'wget\ -q\ https://www.mathworks.com/mpm/glnxa64/mpm$'\n'chmod\ \+x\ mpm$'\n'$'\n'\#\ Change\ the\ release\ below\ \(e.g.,\ R2023b,\ R2024a\)\ to\ match\ your\ MathWorks\ license\!$'\n'MATLAB_RELEASE=\"R2024a\"$'\n'MATLAB_DIR=\"/usr/local/MATLAB/\$MATLAB_RELEASE\"$'\n'$'\n'./mpm\ install\ \\$'\n'\ \ \ \ \
    --release=\$MATLAB_RELEASE\ \
\\$'\n'\ \ \ \ \
    --destination=\$MATLAB_DIR\ \
\\$'\n'\ \ \ \ \
    --products\ \
MATLAB\ Simulink$'\n'$'\n'ln\ -s\ \$MATLAB_DIR/bin/matlab\ /usr/local/bin/matlab$'\n'$'\n'\#\ \
    ---------------------------------------------------------$'\n'\#\ \
STEP\ 4:\ INSTALL\ MINICONDA\ \&\ PYTHON\ ENGINE$'\n'\#\ \
    ---------------------------------------------------------$'\n'echo\ \
\"Installing\ Miniconda\ \(PEP\ 668\ compliance\)...\"$'\n'cd\ /tmp$'\n'wget\ -q\ https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh\ -O\ miniconda.sh$'\n'bash\ miniconda.sh\ -b\ -p\ /opt/miniconda3$'\n'rm\ miniconda.sh$'\n'echo\ \'export\ PATH=\"/opt/miniconda3/bin:\$PATH\"\'\ \>\ /etc/profile.d/conda.sh$'\n'$'\n'echo\ \"Setting\ up\ Python\ Environment\ \(bsm_env\)...\"$'\n'/opt/miniconda3/bin/conda\ create\ -y\ -n\ bsm_env\ python=3.11\ numpy\ pandas\ scipy$'\n'$'\n'\#\ Install\ MATLAB\ Engine\ for\ Python$'\n'cd\ \$MATLAB_DIR/extern/engines/python$'\n'/opt/miniconda3/envs/bsm_env/bin/python\ -m\ pip\ install\ .$'\n'$'\n'\#\ Grant\ your\ RDP\ user\ full\ read/write\ access\ to\ the\ Conda\ environment$'\n'chmod\ -R\ a\+rwX\ /opt/miniconda3$'\n'$'\n'echo\ \"Startup\ script\ completed\ successfully\!\" \
    --maintenance-policy=MIGRATE \
    --provisioning-model=STANDARD \
    --service-account=658743401414-compute@developer.gserviceaccount.com \
    --scopes=https://www.googleapis.com/auth/devstorage.read_only,https://www.googleapis.com/auth/logging.write,https://www.googleapis.com/auth/monitoring.write,https://www.googleapis.com/auth/service.management.readonly,https://www.googleapis.com/auth/servicecontrol,https://www.googleapis.com/auth/trace.append \
    --create-disk=auto-delete=yes,boot=yes,device-name=WWDR_Development_Machine_Debian13trixie,image=projects/debian-cloud/global/images/debian-13-trixie-v20260210,mode=rw,size=100,type=pd-ssd \
    --no-shielded-secure-boot \
    --shielded-vtpm \
    --shielded-integrity-monitoring \
    --labels=goog-ec-src=vm_add-gcloud \
    --reservation-affinity=any \
&& \
gcloud compute resource-policies create snapshot-schedule default-schedule-1 \
    --project=wwdr-487920 \
    --region=us-east4 \
    --max-retention-days=14 \
    --on-source-disk-delete=keep-auto-snapshots \
    --daily-schedule \
    --start-time=23:00 \
&& \
gcloud compute disks add-resource-policies WWDR_Development_Machine_Debian13trixie \
    --project=wwdr-487920 \
    --zone=us-east4-b \
    --resource-policies=projects/wwdr-487920/regions/us-east4/resourcePolicies/default-schedule-1