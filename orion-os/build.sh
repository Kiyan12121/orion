#!/bin/bash
# Builds ORION OS (a live USB image) from scratch on Ubuntu 24.04. Needs root, ~12 GB free and an internet connection.
#   sudo ./build.sh            → orion-os.iso
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"; W="${WORK:-$HERE/work}"; C="$W/chroot"; I="$W/iso"
apt-get install -y debootstrap squashfs-tools xorriso grub-pc-bin grub-efi-amd64-bin mtools dosfstools
mkdir -p "$W"
[ -d "$C/usr" ] || debootstrap --arch=amd64 --variant=minbase --components=main,universe,restricted,multiverse noble "$C" http://archive.ubuntu.com/ubuntu/
cp /etc/resolv.conf "$C/etc/resolv.conf"
cat > "$C/etc/apt/sources.list" <<X
deb http://archive.ubuntu.com/ubuntu noble main restricted universe multiverse
deb http://archive.ubuntu.com/ubuntu noble-updates main restricted universe multiverse
deb http://security.ubuntu.com/ubuntu noble-security main restricted universe multiverse
X
for d in proc sys dev dev/pts run; do mountpoint -q "$C/$d" || mount --bind "/$d" "$C/$d"; done
trap 'for d in run dev/pts dev sys proc; do umount -lf "$C/$d" 2>/dev/null; done' EXIT
mkdir -p "$C/usr/share/plymouth/themes/orion" "$C/opt/orion"
cp "$HERE"/plymouth/* "$C/usr/share/plymouth/themes/orion/"
(cd "$HERE/.." && tar cf - --exclude=./data --exclude=./projects --exclude=./skills --exclude=./config.json --exclude='__pycache__' \
   --exclude=./mobile-app --exclude=./orion-os --exclude='*.bat' .) | (cd "$C/opt/orion" && tar xf -)
cp "$HERE/stage1-packages.sh" "$C/root/stage1.sh"; cp "$HERE/stage2-setup.sh" "$C/root/stage2.sh"
chroot "$C" /bin/bash /root/stage1.sh
chroot "$C" /bin/bash /root/stage2.sh
chroot "$C" pip3 install --break-system-packages -q pywebview edge-tts pyperclip sounddevice pyttsx3 pyautogui || true
: > "$C/etc/resolv.conf"
for d in run dev/pts dev sys proc; do umount -lf "$C/$d" 2>/dev/null; done; trap - EXIT
mkdir -p "$I/casper" "$I/boot/grub" "$I/.disk" "$I/EFI/BOOT"
K=$(ls "$C"/boot/vmlinuz-* | sort -V | tail -1); cp "$K" "$I/casper/vmlinuz"; cp "$C/boot/initrd.img-${K##*vmlinuz-}" "$I/casper/initrd"
cp "$HERE/grub/grub.cfg" "$I/boot/grub/grub.cfg"
echo "ORION OS 1.0 - amd64 ($(date +%Y%m%d))" > "$I/.disk/info"
grub-mkstandalone -O x86_64-efi -o "$I/EFI/BOOT/BOOTX64.EFI" --modules="part_gpt part_msdos fat iso9660 search search_fs_file configfile linux normal all_video gfxterm echo test" "boot/grub/grub.cfg=$HERE/grub/embed.cfg"
mksquashfs "$C" "$I/casper/filesystem.squashfs" -comp xz -b 1M -Xdict-size 100% -noappend
du -sx --block-size=1 "$C" | cut -f1 > "$I/casper/filesystem.size"
grub-mkrescue -o "$HERE/orion-os.iso" "$I" -- -volid ORION_OS
echo "Done: $HERE/orion-os.iso"
