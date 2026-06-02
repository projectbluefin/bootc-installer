# Encryption Test Matrix

Full validation of all encryption types across both GRUB and systemd-boot bootloaders.

Refs: #45|Closes

## Test Matrix

| # | Encryption Type | Bootloader | Partition Layout | Expected Behavior |
|---|----------------|------------|-----------------|-------------------|
| 1 | `none` | GRUB | EFI + /boot ext4 + root XFS | Normal boot, no passphrase |
| 2 | `none` | systemd-boot | EFI FAT32 + root | Normal boot, no passphrase |
| 3 | `luks-passphrase` | GRUB | EFI + /boot ext4 + LUKS(root) | Passphrase prompt at boot |
| 4 | `luks-passphrase` | systemd-boot | EFI FAT32 + LUKS(root) | Passphrase prompt at boot |
| 5 | `tpm2-luks` | GRUB | EFI + /boot ext4 + LUKS(root) | Auto-unlock via TPM2, no prompt |
| 6 | `tpm2-luks` | systemd-boot | EFI FAT32 + LUKS(root) | Auto-unlock via TPM2, no prompt |
| 7 | `tpm2-luks-passphrase` | GRUB | EFI + /boot ext4 + LUKS(root) | Auto-unlock OR passphrase fallback |
| 8 | `tpm2-luks-passphrase` | systemd-boot | EFI FAT32 + LUKS(root) | Auto-unlock OR passphrase fallback |

## Per-Scenario Verification

### All encrypted installs
- [ ] Recovery key displayed on recovery-key screen
- [ ] Recovery key is correct (can unlock the LUKS device)
- [ ] `rd.luks.name=<UUID>=root` in boot entries (GRUB: grub.cfg, systemd-boot: BLS entries)
- [ ] Recipe JSON passphrase is securely deleted after install
- [ ] LUKS device is properly closed after install (no stale /dev/mapper)

### TPM2 installs
- [ ] `systemd-cryptenroll --tpm2-device=auto` completes (or fails non-fatally)
- [ ] System auto-unlocks on normal boot (TPM2 PCR policy satisfied)
- [ ] After firmware update (PCR7 changes): passphrase fallback works
- [ ] After kernel update: TPM2 still unlocks (PCR values stable)

### Passphrase-only installs
- [ ] Boot prompts for passphrase
- [ ] Correct passphrase unlocks
- [ ] Wrong passphrase shows retry prompt (not crash)

## Files Involved

- `fisherman/fisherman/internal/luks/luks.go` — LUKS format, open, close, TPM2 enroll
- `fisherman/fisherman/internal/disk/partition.go` — `PartitionEncrypted()`
- `fisherman/fisherman/cmd/fisherman/main.go` — steps 3-4 (LUKS + format)
- `bootc_installer/views/recovery_key.py` — recovery key display
- `bootc_installer/defaults/encryption.py` — encryption type selection UI

## Known Issues

- `systemd-cryptenroll --unlock-key-file=-` fails with "Reading keyfile /var/roothome/- failed" — may be systemd version issue on live ISO
- Recovery key screen (`recovery_key.py`) shows placeholder text until fisherman reports the key

## Acceptance

- [ ] At least `none`, `luks-passphrase`, and `tpm2-luks-passphrase` tested on real hardware
- [ ] At least one GRUB and one systemd-boot scenario tested
- [ ] Recovery key verified as functional
- [ ] No stale LUKS devices or mounts after install
- [ ] Passphrase fallback works when TPM2 policy fails
