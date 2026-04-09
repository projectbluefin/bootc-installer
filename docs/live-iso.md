# Building a bootc Live ISO with tuna-installer

This document explains how to build a bootable live ISO that auto-launches
tuna-installer for offline installation of a bootc image. It documents the
configuration conventions the installer expects, and the OS-image-side setup
needed to make everything work end-to-end.

The reference implementation is [tuna-os/dakota-iso](https://github.com/tuna-os/dakota-iso).

---

## Overview

A live ISO built for tuna-installer must:

1. Embed the target OCI image in the squashfs (as VFS containers-storage).
2. Auto-start the installer Flatpak as the live user.
3. Configure the installer via `/etc/bootc-installer/` so it skips steps that
   are only meaningful during a normal (non-live) install (user creation, image
   selection).
4. Set up polkit so the live user can run fisherman without a password prompt.
5. Redirect write-heavy scratch paths to the target disk to work around the
   size-limited live overlay.

---

## Installer configuration files

All files live in `/etc/bootc-installer/` on the live squashfs.

### `live-iso-mode` flag file

```
/etc/bootc-installer/live-iso-mode
```

An **empty file**. Its presence tells the installer it is running on a live ISO
and activates offline install mode. When running inside a Flatpak sandbox the
installer looks for this file at `/run/host/etc/bootc-installer/live-iso-mode`.

### `images.json`

Locks the installer to a specific image and provides image-specific defaults so
the user is not asked questions the ISO already knows the answers to.

```json
{
  "default_image": "ghcr.io/your-org/your-image:latest",
  "fallback_flatpaks": [],
  "images": [
    {
      "name": "My OS",
      "imgref": "ghcr.io/your-org/your-image:latest",
      "desc": "Brief description shown in the installer",
      "icon": "resource:///org/bootcinstaller/Installer/images/my-os.png",
      "bootloader": "systemd",
      "filesystem": "btrfs",
      "composefs": true,
      "needs_user_creation": false,
      "flatpak_var_path": "state/os/default/var"
    }
  ]
}
```

Key fields:

| Field | Purpose |
|---|---|
| `bootloader` | `"systemd"` or `"grub2"` — passed to fisherman's recipe |
| `filesystem` | `"btrfs"` or `"xfs"` |
| `composefs` | `true` for composefs-native images (GNOME OS, Project Bluefin/Dakota) |
| `needs_user_creation` | `false` on a live ISO — skips the user creation screen |
| `flatpak_var_path` | Relative path to writable `/var` inside the installed target. For composefs-native images: `"state/os/default/var"` |

When `needs_user_creation` is `false`, the installer skips the user creation
screen entirely. The installed system's first-boot experience (e.g. GNOME
initial-setup) handles account creation.

### `recipe.json`

Provides branding (distro name, tour slides) and the default install recipe
sent to fisherman.

```json
{
  "distro_name": "My OS",
  "distro_version": "latest",
  "tour_slides": [],
  "steps": []
}
```

Refer to the tuna-installer source for the full schema.

---

## Autostart `.desktop` entry

The installer must be started automatically when the live user logs in via GDM.
Place a `.desktop` file in `/etc/xdg/autostart/`:

```ini
[Desktop Entry]
Name=My OS Installer
Exec=flatpak run --env=VANILLA_CUSTOM_RECIPE=/run/host/etc/bootc-installer/recipe.json org.bootcinstaller.Installer
Icon=/usr/share/pixmaps/my-os.png
Type=Application
X-GNOME-Autostart-enabled=true
```

**Important:** pass `VANILLA_CUSTOM_RECIPE` at the `/run/host/etc/...` path.
Inside the Flatpak sandbox, the host `/etc` is bind-mounted at `/run/host/etc`;
the installer's recipe loader uses this prefix automatically when the
`live-iso-mode` flag is present.

For the development channel build (`org.bootcinstaller.Installer.Devel`) use
the Devel app ID instead.

---

## Polkit setup

fisherman runs via `pkexec` and requires polkit approval. On a live ISO,
liveuser must be allowed to trigger this without a password.

### The exec action ID issue

tuna-installer copies the fisherman binary from the Flatpak bundle to a
**temporary path** (e.g. `/var/home/liveuser/.cache/bootc-installer/fisherman`)
and calls `pkexec` on that path. Because the path does not match any
`org.freedesktop.policykit.exec.path` annotation, polkit fires the generic
**`org.freedesktop.policykit.exec`** action instead of
`org.tunaos.Installer.install`.

The custom polkit action definition (with `exec.path=/usr/local/bin/fisherman`)
therefore **never fires** in practice. The JS rules approach below is what
actually grants passwordless execution.

### 1. Create the action policy (for completeness)

Write the polkit action definition so it is not dependent on the Flatpak being
installed at build time:

```xml
<!-- /usr/share/polkit-1/actions/org.bootcinstaller.Installer.policy -->
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE policyconfig PUBLIC
  "-//freedesktop//DTD PolicyKit Policy Configuration 1.0//EN"
  "http://www.freedesktop.org/standards/PolicyKit/1/policyconfig.dtd">
<policyconfig>
  <action id="org.tunaos.Installer.install">
    <description>Install an operating system to disk</description>
    <message>Authentication is required to install an operating system</message>
    <icon_name>drive-harddisk</icon_name>
    <defaults>
      <allow_any>no</allow_any>
      <allow_inactive>no</allow_inactive>
      <allow_active>yes</allow_active>
    </defaults>
    <annotate key="org.freedesktop.policykit.exec.path">/usr/local/bin/fisherman</annotate>
    <annotate key="org.freedesktop.policykit.exec.allow_gui">true</annotate>
  </action>
</policyconfig>
```

### 2. JS rules — the effective grant

A JS rule is required to cover both `org.tunaos.Installer.install` **and**
`org.freedesktop.policykit.exec` (the action actually fired when pkexec is
called on the temp fisherman path):

```javascript
// /etc/polkit-1/rules.d/99-live-installer.rules
polkit.addRule(function(action, subject) {
    if ((action.id === "org.tunaos.Installer.install" ||
         action.id === "org.freedesktop.policykit.exec") &&
            subject.user === "liveuser" && subject.local) {
        return polkit.Result.YES;
    }
});
```

> **Security note:** Granting `org.freedesktop.policykit.exec` to liveuser is
> safe on a live ISO — liveuser already has passwordless sudo in the live
> session, and the session is ephemeral and single-purpose.

### 3. Symlink fisherman to `/usr/local/bin`

```bash
INSTALLER_APP_DIR=$(find /var/lib/flatpak/app/org.bootcinstaller.Installer \
    -name fisherman -type f 2>/dev/null | head -1 | xargs dirname 2>/dev/null)
ln -sf "${INSTALLER_APP_DIR}/fisherman" /usr/local/bin/fisherman
```

---

## VFS containers-storage

The target OCI image must be pre-pulled into the squashfs as VFS
containers-storage at `/var/lib/containers/storage`. fisherman detects an
offline install when `CheckImage` finds the image locally and the registry is
unreachable.

Configure podman to use the VFS driver so it finds the pre-embedded image:

```toml
# /etc/containers/storage.conf
[storage]
driver = "vfs"
runroot = "/run/containers/storage"
graphroot = "/var/lib/containers/storage"
```

Without this, podman initialises with the overlay driver at first boot and
creates a `db.sql` that conflicts with VFS access.

---

## Disk space: redirecting scratch to the target disk

The live rootfs overlay is typically only 1–2 GiB. fisherman's offline install
path needs roughly 20 GiB of scratch space across three operations:

| Operation | Writes to | Size |
|---|---|---|
| `skopeo copy` temp files (`container_images_*`) | `/var/tmp` | ~8 GiB |
| OCI cache output | `/var/fisherman-tmp` | ~3.5 GiB |
| bootc VFS layer writes | `/var/lib/containers/storage` | ~8 GiB |

The solution is to redirect all of these to a btrfs `@scratch` subvolume
created on the target disk, which fisherman has already partitioned and mounted
by the time skopeo runs.

### How it works

Wrap `/usr/bin/skopeo` with a shell script that, immediately before delegating
to the real `skopeo`, creates a `@scratch` btrfs subvolume on the target disk
and sets up the following mounts:

```
@scratch/var-tmp   →  bind mount over /var/tmp          (skopeo temp files)
@scratch/var-tmp   →  bind mount over /var/fisherman-tmp (OCI cache)
@scratch/cs-upper  →  overlay upperdir over /var/lib/containers/storage
                       (lowerdir = squashfs VFS storage, read-only)
```

Mounting `@scratch` as a mount point on the target satisfies bootc's
*"Verifying empty rootfs: Requiring directory contains only mount points"*
check — mount points are explicitly permitted.

```bash
#!/bin/bash
# /usr/bin/skopeo  (wrapper — real binary at /usr/bin/skopeo.real)

# Strip double transport prefix (fisherman bug workaround — fixed upstream)
ARGS=()
for arg in "$@"; do
    ARGS+=("${arg/containers-storage:containers-storage:/containers-storage:}")
done

for target in /mnt/fisherman-target /var/mnt/fisherman-target; do
    if mountpoint -q "$target" 2>/dev/null; then
        SCRATCH="$target/@scratch"
        [ -d "$SCRATCH" ] || btrfs subvolume create "$SCRATCH"
        DEV=$(findmnt -n -o SOURCE "$target" | head -1)
        mount -o subvol=@scratch "$DEV" "$SCRATCH"

        mkdir -p "$SCRATCH/var-tmp"
        mount --bind "$SCRATCH/var-tmp" /var/tmp
        [ -d /var/fisherman-tmp ] && mount --bind "$SCRATCH/var-tmp" /var/fisherman-tmp

        CS=/var/lib/containers/storage
        LOWER=/run/rootfsbase/var/lib/containers/storage
        if [ -d "$LOWER" ] && ! mountpoint -q "$CS" 2>/dev/null; then
            mkdir -p "$SCRATCH/cs-upper" "$SCRATCH/cs-work"
            mount -t overlay overlay \
                -o "lowerdir=$LOWER,upperdir=$SCRATCH/cs-upper,workdir=$SCRATCH/cs-work" \
                "$CS"
        fi
        break
    fi
done
exec /usr/bin/skopeo.real "${ARGS[@]}"
```

Also wrap `/usr/bin/podman` as a pass-through so that fisherman's cleanup code
cannot accidentally unmount `/var/tmp` and break mount propagation to
`/var/fisherman-tmp`:

```bash
#!/bin/bash
# /usr/bin/podman  (wrapper — real binary at /usr/bin/podman.real)
exec /usr/bin/podman.real "$@"
```

> **Why the podman wrapper matters:** fisherman bind-mounts `/var/fisherman-tmp`
> onto `/var/tmp`, then the skopeo wrapper bind-mounts `@scratch/var-tmp` onto
> `/var/tmp`. Due to mount propagation, `/var/fisherman-tmp` now also points to
> `@scratch`. If the podman wrapper were to unmount `/var/tmp` after the OCI
> export, that propagated mount would be removed, making the OCI cache invisible
> to bootc inside the podman container. The pass-through wrapper prevents this.

### Memory: don't use a tmpfs upperdir

Using a tmpfs as the overlay upperdir for `/var/lib/containers/storage` is
tempting but will OOM the guest — the VFS storage is 8+ GiB and a tmpfs
consumes guest RAM. Always use a real disk (the target btrfs partition) as the
upperdir.

---

## Lock screen and sleep disable

On a live ISO the screen should never lock (the user has not set a password and
a locked screen is unrecoverable). Also disable sleep/suspend so a long install
is not interrupted.

**Important:** Check which system-db name your base image's dconf profile uses.
Project Bluefin / Dakota uses `system-db:distro`, so overrides must go in
`/etc/dconf/db/distro.d/`. Writing to `local.d/` will be silently ignored if
the profile does not reference `system-db:local`. Do **not** overwrite the
profile file — that would lose the base image's own dconf settings.

```bash
# Check the base image profile to find the right db name:
#   cat /etc/dconf/profile/user  → look for "system-db:XXX"
DB_NAME=distro   # or "local" depending on your base image

mkdir -p /etc/dconf/db/${DB_NAME}.d /etc/dconf/db/${DB_NAME}.d/locks

cat > /etc/dconf/db/${DB_NAME}.d/50-live-iso << 'EOF'
[org/gnome/desktop/screensaver]
lock-enabled=false
idle-activation-enabled=false

[org/gnome/desktop/session]
idle-delay=uint32 0

[org/gnome/settings-daemon/plugins/power]
sleep-inactive-ac-type='nothing'
sleep-inactive-battery-type='nothing'
sleep-inactive-ac-timeout=0
sleep-inactive-battery-timeout=0
EOF

cat > /etc/dconf/db/${DB_NAME}.d/locks/live-iso << 'EOF'
/org/gnome/desktop/screensaver/lock-enabled
/org/gnome/desktop/screensaver/idle-activation-enabled
/org/gnome/desktop/session/idle-delay
/org/gnome/settings-daemon/plugins/power/sleep-inactive-ac-type
/org/gnome/settings-daemon/plugins/power/sleep-inactive-battery-type
EOF

dconf update

# Also mask systemd sleep targets as belt-and-suspenders
systemctl mask sleep.target suspend.target hibernate.target hybrid-sleep.target
```

---

## GDM autologin

```ini
# /etc/gdm/custom.conf
[daemon]
AutomaticLoginEnable=True
AutomaticLogin=liveuser
```

---

## Summary checklist

- [ ] `/etc/bootc-installer/live-iso-mode` (empty flag file)
- [ ] `/etc/bootc-installer/images.json` with `needs_user_creation: false` and correct `bootloader`/`filesystem`/`composefs`/`flatpak_var_path`
- [ ] `/etc/bootc-installer/recipe.json` with distro branding
- [ ] `/etc/xdg/autostart/tuna-installer.desktop` with `VANILLA_CUSTOM_RECIPE=/run/host/etc/...`
- [ ] `/usr/share/polkit-1/actions/org.bootcinstaller.Installer.policy`
- [ ] `/etc/polkit-1/rules.d/99-live-installer.rules` JS rule covering **both** `org.tunaos.Installer.install` and `org.freedesktop.policykit.exec`
- [ ] `/usr/local/bin/fisherman` symlink into Flatpak bundle
- [ ] `/etc/containers/storage.conf` with `driver = "vfs"`
- [ ] `/usr/bin/skopeo` wrapper redirecting scratch to target `@scratch` btrfs subvolume
- [ ] `/usr/bin/podman` pass-through wrapper
- [ ] `/var/fisherman-tmp` pre-created directory
- [ ] dconf lock-screen/sleep keys disabled (in the correct `distro.d/` or `local.d/` for your base image)
- [ ] systemd sleep targets masked
- [ ] GDM autologin configured for `liveuser`
- [ ] `org.gnome.Tour.desktop` removed to prevent gnome-tour interfering with installer
