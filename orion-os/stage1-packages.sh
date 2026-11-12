set -e
export DEBIAN_FRONTEND=noninteractive LANG=C.UTF-8
echo orion-os > /etc/hostname
printf '127.0.0.1 localhost\n127.0.1.1 orion-os\n' > /etc/hosts
# never let services start inside the build chroot
printf '#!/bin/sh\nexit 101\n' > /usr/sbin/policy-rc.d; chmod +x /usr/sbin/policy-rc.d
apt-get update -q
apt-get install -y -q --no-install-recommends systemd-sysv dbus sudo locales tzdata keyboard-configuration console-setup \
  linux-generic casper initramfs-tools plymouth plymouth-label lupin-casper 2>/dev/null || \
apt-get install -y -q --no-install-recommends systemd-sysv dbus sudo locales tzdata keyboard-configuration console-setup \
  linux-generic casper initramfs-tools plymouth plymouth-label
apt-get install -y -q --no-install-recommends network-manager wpasupplicant iw wireless-regdb ca-certificates curl \
  xserver-xorg-core xserver-xorg-video-all xserver-xorg-input-all xinit x11-xserver-utils x11-utils openbox wmctrl xdotool xclip \
  pipewire pipewire-pulse wireplumber pulseaudio-utils alsa-utils brightnessctl libportaudio2 espeak-ng \
  python3 python3-pip python3-gi python3-gi-cairo gir1.2-webkit2-4.1 gir1.2-gtk-3.0 python3-psutil python3-requests python3-numpy python3-pil \
  fonts-noto-core fonts-noto-color-emoji fonts-dejavu-core fonts-liberation \
  epiphany-browser pcmanfm lxterminal mousepad ristretto mpv galculator pavucontrol xdg-utils gvfs gvfs-backends \
  adwaita-icon-theme-full gnome-themes-extra dbus-x11 policykit-1 udisks2 ntfs-3g exfatprogs eject \
  less nano htop unzip zip file psmisc
locale-gen en_GB.UTF-8 >/dev/null
update-locale LANG=en_GB.UTF-8
ln -sf /usr/share/zoneinfo/Europe/London /etc/localtime; echo Europe/London > /etc/timezone
sed -i 's/XKBLAYOUT=.*/XKBLAYOUT="gb"/' /etc/default/keyboard || true
apt-get clean
echo STAGE1_DONE
