# Release Qualification

Hardware lab procedure for gating releases: build → deploy → install → reboot → verify.

Refs: #42|Closes

## Release Qualification Matrix

| # | Scenario | Encryption | Bootloader | Network | Disk |
|---|----------|-----------|------------|---------|------|
| 1 | Online install (happy path) | none | GRUB | online | real NVMe |
| 2 | Encrypted install (passphrase) | luks-passphrase | GRUB | online | real NVMe |
| 3 | Encrypted install (TPM2) | tpm2-luks-passphrase | systemd-boot | online | real NVMe |
| 4 | Offline ISO install | none | GRUB | **disabled** | real NVMe |
| 5 | Windows slurp | none | GRUB | online | NVMe with NTFS |
| 6 | Failure path (bad image) | — | — | online | real NVMe |
| 7 | Failure path (too-small disk) | — | — | — | USB stick |

## Lab Machine Requirements

- **Primary:** NUC or Framework with NVMe + TPM2
- **Access:** SSH or IPMI/remote KVM for headless observation
- **Target disk:** Identified by model/serial, NOT by `/dev/nvmeXnY` alone
- **Live ISO:** Boot from USB with installer Flatpak pre-installed
- **Secondary:** Machine with dual-boot Windows (NTFS) for slurp testing

## Procedure

### Phase 1: Build Artifact
```bash
git checkout <SHA>
flatpak run org.flatpak.Builder --force-clean --user --install _build flatpak/org.bootcinstaller.Installer.json
flatpak build-bundle ~/.local/share/flatpak/repo org.bootcinstaller.Installer.flatpak org.bootcinstaller.Installer
echo "SHA: $(git rev-parse HEAD)"
sha256sum org.bootcinstaller.Installer.flatpak
```

### Phase 2: Deploy
```bash
scp org.bootcinstaller.Installer.flatpak <target>:~
ssh <target> "flatpak install --user --bundle -y ~/org.bootcinstaller.Installer.flatpak"
```

### Phase 3: Pre-Install Validation
```bash
ssh <target> "lsblk -o NAME,SIZE,MODEL,SERIAL,TRAN /dev/nvme0n1"
ssh <target> "sudo wipefs -a /dev/nvme0n1"  # DESTRUCTIVE
```

### Phase 4: Run Install
```bash
ssh <target> "flatpak run org.bootcinstaller.Installer"
ssh <target> "tail -f ~/.cache/tuna-installer/fisherman-output.log"
```

### Phase 5: Post-Install Verification (after reboot)
```bash
ssh <target> "systemctl is-system-running"
ssh <target> "bootc status --json | jq '.status.booted.image'"
ssh <target> "hostname"
ssh <target> "flatpak list --app --columns=application | head -10"
ssh <target> "journalctl -b -p err --no-pager | head -10"
```

## Evidence Collection

For each test run:
- [ ] Screenshot of confirm screen (summary of choices)
- [ ] Screenshot of done screen (success or failure)
- [ ] `fisherman-output.log` (full log)
- [ ] Recipe JSON used
- [ ] `lsblk` output before and after install
- [ ] `journalctl -b` first 100 lines after reboot
- [ ] Pass/fail per checklist item

## Related Issues

- #20 — Dakota TPM2 E2E (subset of scenario 3)
- #41 — UI/demo test plan (complementary)
- #38 — Demo mode E2E (software-only)
