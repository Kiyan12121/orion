set -e
export DEBIAN_FRONTEND=noninteractive LANG=C.UTF-8
apt-get install -y -q --no-install-recommends gstreamer1.0-plugins-base gstreamer1.0-plugins-good gstreamer1.0-libav gstreamer1.0-pipewire \
  scrot python3-xlib python3-tk python3-dev gcc 2>&1 | tail -1
pip3 install --break-system-packages -q pywebview edge-tts pyperclip sounddevice pyttsx3 pyautogui 2>&1 | tail -2
apt-get purge -y -q python3-dev gcc >/dev/null 2>&1 || true; apt-get autoremove -y -q >/dev/null 2>&1 || true
# ---- the ORION user (auto-login, can use sudo without a password: it's a single-user live system)
id orion >/dev/null 2>&1 || useradd -m -s /bin/bash -G sudo,audio,video,plugdev,netdev,input -c "ORION" orion
echo "orion:orion" | chpasswd
echo "orion ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/orion; chmod 440 /etc/sudoers.d/orion
touch /etc/orion-os; echo "ORION OS 1.0" > /etc/orion-os
chown -R orion:orion /opt/orion
mkdir -p /opt/orion/data && chown orion:orion /opt/orion/data
# ---- casper: use our user + hostname
cat > /etc/casper.conf <<'X'
export USERNAME="orion"
export USERFULLNAME="ORION"
export HOST="orion-os"
export BUILD_SYSTEM="Ubuntu"
export FLAVOUR="ORION OS"
X
# ---- auto-login on tty1, then straight into the ORION desktop
mkdir -p /etc/systemd/system/getty@tty1.service.d
cat > /etc/systemd/system/getty@tty1.service.d/autologin.conf <<'X'
[Service]
ExecStart=
ExecStart=-/sbin/agetty --autologin orion --noclear %I $TERM
X
cat > /home/orion/.bash_profile <<'X'
[ -f ~/.bashrc ] && . ~/.bashrc
if [ -z "$DISPLAY" ] && [ "$(tty)" = "/dev/tty1" ]; then
  exec startx -- -nolisten tcp vt1 >~/.xsession.log 2>&1
fi
X
cat > /home/orion/.xinitrc <<'X'
#!/bin/sh
xsetroot -solid "#03060c"
xset s off -dpms 2>/dev/null
setxkbmap gb 2>/dev/null
exec openbox-session
X
chmod +x /home/orion/.xinitrc
mkdir -p /home/orion/.config/openbox /home/orion/Desktop /home/orion/Documents /home/orion/Downloads /home/orion/Music /home/orion/Pictures /home/orion/Videos
cat > /home/orion/.config/openbox/autostart <<'X'
# ORION is the desktop: start it, and bring it back if it ever closes
export ORION_OS=1 GDK_BACKEND=x11 WEBKIT_DISABLE_COMPOSITING_MODE=1
(while true; do python3 /opt/orion/ORION.pyw >>~/.orion-session.log 2>&1; sleep 1; done) &
X
cp /etc/xdg/openbox/rc.xml /home/orion/.config/openbox/rc.xml
python3 - <<'P'
p="/home/orion/.config/openbox/rc.xml"; h=open(p).read()
h=h.replace("<keyboard>","""<keyboard>
    <keybind key="W-space"><action name="Execute"><command>wmctrl -a ORION</command></action></keybind>
    <keybind key="Super_L"><action name="Execute"><command>wmctrl -a ORION</command></action></keybind>
    <keybind key="Print"><action name="Execute"><command>python3 /opt/orion/core/osshot.py</command></action></keybind>
    <keybind key="W-q"><action name="Close"/></keybind>""",1)
h=h.replace("<applications>","""<applications>
    <application class="*"><decor>yes</decor><maximized>true</maximized></application>
    <application title="ORION*"><decor>no</decor><fullscreen>yes</fullscreen></application>""",1)
import re
h=re.sub(r"<theme>\s*<name>[^<]*</name>","<theme>\n    <name>Onyx</name>",h,1)
h=re.sub(r"<number>\d+</number>","<number>1</number>",h,1)
open(p,"w").write(h)
P
chown -R orion:orion /home/orion
# ---- quieter boot + our splash
update-alternatives --install /usr/share/plymouth/themes/default.plymouth default.plymouth /usr/share/plymouth/themes/orion/orion.plymouth 300
update-alternatives --set default.plymouth /usr/share/plymouth/themes/orion/orion.plymouth
mkdir -p /etc/NetworkManager/conf.d
printf '[main]\nplugins=keyfile\n[keyfile]\nunmanaged-devices=none\n' > /etc/NetworkManager/conf.d/orion.conf
systemctl enable NetworkManager >/dev/null 2>&1 || true
systemctl mask systemd-networkd-wait-online.service NetworkManager-wait-online.service >/dev/null 2>&1 || true
rm -f /usr/sbin/policy-rc.d
update-initramfs -u -k all 2>&1 | tail -2
apt-get clean; rm -rf /var/lib/apt/lists/* /tmp/* /root/.cache
echo STAGE2_DONE
