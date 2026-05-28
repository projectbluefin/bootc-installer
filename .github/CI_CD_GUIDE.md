# GitHub Actions CI/CD Guide

Automated building and releasing of all three bootc-installer variants (GNOME, XFCE, KDE).

## Workflows

### 1. `build-flatpaks.yml` - Multi-Variant Flatpak Builder

**Triggers:**
- Pushes to `dev` or `prod` branches
- Any tag matching `v*`
- Manual dispatch via GitHub Actions UI

**What it does:**
- Builds all three variants in parallel:
  - **GNOME**: `org.bootcinstaller.Installer`
  - **XFCE**: `org.xfceinstaller.Installer`
  - **KDE**: `org.kdeinstaller.Installer`
- Exports Flatpaks to `.flatpak` files
- Creates/updates GitHub releases with tags:
  - `continuous` (releases on prod branch)
  - `continuous-dev` (releases on dev branch)
  - `v*` (tagged releases)
- Uploads artifacts to:
  - GitHub Releases (as release assets)
  - GitHub Actions artifacts (30-day retention)

**Release Asset Naming:**
```
org.bootcinstaller.Installer.flatpak       # GNOME
org.xfceinstaller.Installer.flatpak        # XFCE
org.kdeinstaller.Installer.flatpak         # KDE
```

**Usage Example:**

```bash
# Automatic on push to dev
git push origin dev

# Automatic on push to prod
git push origin prod

# Automatic on tag
git tag v0.2.0
git push origin v0.2.0

# Manual trigger via GitHub UI
# Actions > Build Multi-Variant Flatpaks > Run workflow
```

### 2. `validate-flatpak.yml` - Manifest Validation

**Triggers:**
- Pull requests modifying Flatpak configs
- Pushes to `dev` or `prod` branches
- Manual dispatch via GitHub Actions UI

**What it does:**
- Validates JSON syntax in all manifests
- Checks required fields (app-id, runtime, command)
- Verifies variant consistency:
  - GNOME has correct app-id
  - XFCE has correct app-id
  - KDE has correct app-id
- Posts validation results as PR comments

**Validations:**
```
✓ JSON syntax valid
✓ All required fields present
✓ app-id matches variant
✓ runtime is specified
✓ command is specified
```

## Workflow Outputs

### Build Artifacts

**Immediate downloads** (30 days):
- GitHub Actions artifacts tab
- `.flatpak` files ready for distribution

**Long-term storage**:
- GitHub Releases page
- Tagged with `continuous`, `continuous-dev`, or version tag
- Direct download URLs for distribution

## Release qualification runbook

This repo now has two separate gates:

1. **Software-only qualification** — can be run in CI or on a developer workstation right now.
2. **Hardware qualification** — requires destructive installs, reboots, TPM2, and/or real disks. Do not treat these as passed without lab evidence.

### 1. Software-only qualification (verifiable now)

These checks are directly rooted in the current repo and should be completed before any hardware run:

```bash
./QUALIFY_SOFTWARE.sh
```

That script covers:

- manifest JSON validation for GNOME, Devel, XFCE, and KDE manifests
- Python unit tests
- GTK UI tests under Xvfb
- `fisherman` Go vet + tests
- production and devel Flatpak builds

Build the exact release candidate bundle from the commit being qualified after the software gate passes:

```bash
flatpak-builder --force-clean --user --repo=flatpak-repo \
  --install-deps-from=flathub \
  --disable-rofiles-fuse \
  build-dir \
  flatpak/org.bootcinstaller.Installer.json

flatpak build-bundle flatpak-repo \
  org.bootcinstaller.Installer.flatpak \
  org.bootcinstaller.Installer

git rev-parse HEAD
sha256sum org.bootcinstaller.Installer.flatpak
```

Optional non-hardware install/boot smoke coverage is available locally via `tests/integration/test_e2e_install.py`:

```bash
sudo FISHERMAN_BIN=/path/to/fisherman pytest tests/integration/test_e2e_install.py -v -s
sudo FISHERMAN_BIN=/path/to/fisherman BOOT_VERIFY=1 pytest tests/integration/test_e2e_install.py -v -s
```

That optional test can validate virtual installs for Yellowfin and Dakota, but it still does **not** prove:

- real TPM2 enrollment / auto-unlock
- physical passphrase prompts
- offline ISO behavior on actual media
- Windows slurp against a real NTFS disk
- destructive install/reboot on the target NVMe/USB device

### 2. Hardware qualification matrix (manual lab gate)

Run these on real hardware before calling a release candidate qualified:

| Scenario | Image / layout | What must be proven | Hardware-only? |
|---|---|---|---|
| Online happy path | Yellowfin or other GRUB image, XFS, no encryption | Real disk install, reboot, login, hostname, flatpaks, post-install assets | Yes |
| Passphrase encryption | GRUB image, `luks-passphrase` | Boot prompt appears, correct passphrase unlocks, wrong passphrase retries cleanly | Yes |
| Dakota TPM2 | Dakota or other systemd-boot + composefs image, `tpm2-luks-passphrase` | TPM2 auto-unlock on normal boot plus passphrase fallback when TPM policy is unavailable | Yes |
| Offline ISO | Image store baked into live media, networking disabled | Install completes without registry access and boots cleanly | Yes |
| Windows slurp | NTFS source disk present | Selected files/wallpapers land in the installed system | Yes |
| Failure path: bad image | Invalid OCI ref | Failure screen is actionable and leaves useful logs | Yes |
| Failure path: too-small disk | Small USB / undersized target | Install fails before damaging the wrong disk and explains why | Yes |

### Repo-grounded checkpoints to verify during each run

These checks come from the current implementation, not from aspirational behavior:

| Check | Why it matters | Current code anchor | How to verify on the lab machine |
|---|---|---|---|
| GRUB installs use 3 partitions (EFI + ext4 `/boot` + root) | Needed so GRUB never has to read modern XFS features | `fisherman/fisherman/internal/disk/partition.go`, `fisherman/fisherman/cmd/fisherman/main.go` | `lsblk -o NAME,SIZE,FSTYPE,LABEL,PARTTYPE /dev/<disk>` after install |
| systemd-boot installs use 2 partitions (2 GiB ESP + root) | Current Dakota/systemd-boot path puts kernels on the FAT32 ESP, not on a separate `/boot` | `fisherman/fisherman/internal/disk/partition.go`, `fisherman/fisherman/internal/install/systemdboot.go` | Confirm ESP size/layout and inspect `EFI/BOOT/BOOTX64.EFI` + `EFI/systemd/systemd-bootx64.efi` |
| Encrypted boots inject `rd.luks.name=<UUID>=root` into BLS entries | Required so the initrd maps LUKS as `/dev/mapper/root` | `fisherman/fisherman/internal/post/luks_args.go` | Inspect `boot/loader/entries/*.conf` or `boot/efi/loader/entries/*.conf` in the installed system |
| TPM2 enrollment is best-effort and non-fatal | VMs or unsupported hardware should still fall back cleanly | `fisherman/fisherman/cmd/fisherman/main.go`, `fisherman/fisherman/internal/luks/luks.go` | Save installer log and confirm warning vs success message |
| Only `tpm2-luks` emits a generated recovery key today | Do not expect a generated recovery key for passphrase-based modes | `fisherman/fisherman/cmd/fisherman/main.go`, `fisherman/fisherman/internal/progress/progress.go`, `bootc_installer/views/recovery_key.py` | For `tpm2-luks`, capture the recovery-key screen and test the key later; for `luks-passphrase` / `tpm2-luks-passphrase`, validate the user-supplied passphrase instead |
| GUI deletes the temporary recipe after install attempt | Recipe cleanup is part of handling plaintext passphrases safely | `bootc_installer/views/progress.py` | Before/after `find ~/.cache/bootc-installer -maxdepth 1 -name 'tuna-recipe-*.json'` |
| Cleanup closes the live LUKS mapper after install | Prevents stale `/dev/mapper/fisherman-root` from leaking into later runs | `fisherman/fisherman/internal/post/post.go` | After fisherman exits in the live environment, verify the mapper is gone |

### Executable manual procedure

#### Phase A — build and deploy the exact candidate

```bash
git checkout <candidate-sha>

flatpak-builder --force-clean --user --repo=flatpak-repo \
  --install-deps-from=flathub \
  --disable-rofiles-fuse \
  build-dir \
  flatpak/org.bootcinstaller.Installer.json

flatpak build-bundle flatpak-repo \
  org.bootcinstaller.Installer.flatpak \
  org.bootcinstaller.Installer

TARGET=<user>@<lab-ip>
scp org.bootcinstaller.Installer.flatpak ${TARGET}:~
ssh ${TARGET} "flatpak uninstall --user -y org.bootcinstaller.Installer 2>/dev/null || true; \
  flatpak install --user --bundle -y ~/org.bootcinstaller.Installer.flatpak"
```

#### Phase B — pre-install checks

```bash
ssh ${TARGET} "lsblk -o NAME,SIZE,MODEL,SERIAL,TRAN"
ssh ${TARGET} "test -e /dev/tpmrm0 && echo TPM2-present || echo TPM2-absent"
ssh ${TARGET} "curl -I https://ghcr.io | head -1"
```

For offline ISO qualification, disable networking before launch:

```bash
ssh ${TARGET} "sudo nmcli networking off"
```

#### Phase C — run install and capture evidence

Launch the installer on the live system, then monitor the host-visible log:

```bash
ssh ${TARGET} "flatpak run org.bootcinstaller.Installer"
ssh ${TARGET} "tail -f ~/.cache/tuna-installer/fisherman-output.log"
```

Capture at minimum:

- confirm screen screenshot
- done or failure screen screenshot
- `~/.cache/tuna-installer/fisherman-output.log`
- the recipe JSON used
- `lsblk` before and after install
- first boot `journalctl -b --no-pager`

#### Phase D — post-reboot verification

After the installed system boots:

```bash
TARGET_INSTALLED=<user>@<installed-host>

ssh ${TARGET_INSTALLED} "systemctl is-system-running || true"
ssh ${TARGET_INSTALLED} "hostname"
ssh ${TARGET_INSTALLED} "bootc status"
ssh ${TARGET_INSTALLED} "flatpak list --app --columns=application | head"
ssh ${TARGET_INSTALLED} "journalctl -b -p err --no-pager | head -100"
```

Additional scenario-specific checks:

```bash
# Encrypted systems: verify BLS args and mapper naming
ssh ${TARGET_INSTALLED} "grep -R 'rd.luks.name=' /boot /efi /boot/efi 2>/dev/null | head"

# Dakota / systemd-boot: verify fallback binary landed on the ESP
ssh ${TARGET_INSTALLED} "find /boot/efi/EFI -maxdepth 2 -type f | grep 'BOOTX64\\.EFI\\|systemd-bootx64\\.efi'"

# Windows slurp: verify migrated data landed in the installed home
ssh ${TARGET_INSTALLED} "find ~/Documents ~/Pictures ~/.local/share/backgrounds -maxdepth 1 -mindepth 1 2>/dev/null | head"
```

### Hardware-only blockers / still not provable from this environment

The following remain explicitly blocked until someone runs the manual lab flow above:

- TPM2 auto-unlock on real firmware with PCR7 state intact
- passphrase fallback after TPM policy changes (for example after firmware or Secure Boot changes)
- actual boot prompt behavior for wrong/correct passphrases
- Dakota/systemd-boot reboot behavior on real hardware rather than QEMU
- offline ISO installs using the real live image and baked image stores
- Windows slurp against a real NTFS source disk

Treat those as **open qualification work**, not as implied by CI success.

### Release URLs

Access built Flatpaks at:
```
https://github.com/projectbluefin/bootc-installer/releases/download/continuous/org.bootcinstaller.Installer.flatpak
https://github.com/projectbluefin/bootc-installer/releases/download/continuous/org.xfceinstaller.Installer.flatpak
https://github.com/projectbluefin/bootc-installer/releases/download/continuous/org.kdeinstaller.Installer.flatpak

# Dev versions
https://github.com/projectbluefin/bootc-installer/releases/download/continuous-dev/org.bootcinstaller.Installer.Devel.flatpak
https://github.com/projectbluefin/bootc-installer/releases/download/continuous-dev/org.xfceinstaller.Installer.flatpak
https://github.com/projectbluefin/bootc-installer/releases/download/continuous-dev/org.kdeinstaller.Installer.flatpak
```

## Integration with xfce-linux-iso and tromso-iso

The ISO builders automatically download these Flatpaks:

```bash
# xfce-linux-iso downloads XFCE variant
curl "https://github.com/projectbluefin/bootc-installer/releases/download/continuous/org.xfceinstaller.Installer.flatpak"

# tromso-iso downloads KDE variant  
curl "https://github.com/projectbluefin/bootc-installer/releases/download/continuous/org.kdeinstaller.Installer.flatpak"
```

## Monitoring Builds

1. **GitHub Actions Tab**: `Actions` > `Build Multi-Variant Flatpaks`
   - View all build runs
   - Check build logs
   - Download artifacts

2. **GitHub Releases**: `Releases`
   - View all published builds
   - Download Flatpak files
   - See build summaries

3. **Pull Requests**: Auto-validation comments
   - Validation results posted on PRs
   - Manifest consistency checks

## Troubleshooting

### Build Fails

Check the GitHub Actions logs:
1. Click the failed workflow run
2. View logs for the failed variant
3. Common issues:
   - Missing dependencies (install in workflow)
   - Invalid manifest JSON
   - Build cache issues (resolve by force-clean)

### Manifest Validation Fails

PR validation catches issues:
1. Check PR comments
2. Validate JSON: `python3 -m json.tool flatpak/*.json`
3. Verify app-ids match expected values

### Artifact Not Found

If artifact missing from release:
1. Check Actions tab for build logs
2. Verify manifest paths are correct
3. Re-run workflow if needed

## Security

- Workflows use `secrets.GITHUB_TOKEN` (auto-provided)
- No external credentials needed
- All builds are reproducible
- Artifacts signed via GitHub's Sigstore

## Future Enhancements

- [ ] Sign Flatpaks with GPG key
- [ ] Push to Flathub directly
- [ ] Automatic Flathub update PRs
- [ ] Test installations in containers
- [ ] Performance benchmarking
- [ ] Changelog generation

## References

- [GitHub Actions Documentation](https://docs.github.com/en/actions)
- [Flatpak Builder Docs](https://docs.flatpak.org/en/latest/building.html)
- [bootc-installer README](../README.md)
- [Multi-Variant Build Guide](../MULTI_VARIANT_BUILD.md)
