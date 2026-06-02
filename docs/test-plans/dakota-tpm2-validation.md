# Dakota TPM2 Encryption Validation

Validate Dakota (composefs + systemd-boot) with TPM2 encryption end-to-end.

Refs: #20|Closes

## Context

Dakota uses composefs + systemd-boot (not GRUB). The fisherman pipeline already handles this combination:

1. `isSystemdBoot = true` when `r.Bootloader == "systemd"`
2. `PartitionSystemdBoot()` creates 2-partition layout (2 GiB FAT32 ESP + root)
3. LUKS (if requested) wraps the root partition; ESP stays unencrypted
4. `EnsureLuksArgs()` injects `rd.luks.name=<UUID>=root` into BLS loader entries
5. `EnrollTPM2()` runs after install — non-fatal if TPM2 hardware is absent
6. GPT auto-discovery retag correctly skips when `hasEncryption` is true

## Testing Checklist

- [ ] Install Dakota with `tpm2-luks-passphrase` encryption on real hardware with TPM2
- [ ] Verify system boots and auto-unlocks via TPM2
- [ ] Verify passphrase fallback works when TPM2 is unavailable (e.g. after firmware update changes PCR 7)
- [ ] Install Dakota with `tpm2-luks-passphrase` in a VM (no TPM2) — confirm non-fatal warning and passphrase-only unlock works
- [ ] Verify `rd.luks.name` is correctly injected into systemd-boot BLS entries (not GRUB configs)

## Dakota-Specific Recipe

```json
{
  "disk": "/dev/nvme0n1",
  "filesystem": "btrfs",
  "encryption": {
    "type": "tpm2-luks-passphrase",
    "passphrase": "user-passphrase"
  },
  "image": "ghcr.io/projectbluefin/dakota-nvidia:latest",
  "targetImgref": "ghcr.io/projectbluefin/dakota:latest",
  "bootloader": "systemd",
  "composeFsBackend": true,
  "flatpakVarPath": "state/os/default/var",
  "hostname": "framework-a7c3"
}
```

## Known Issue

`systemd-cryptenroll --unlock-key-file=-` fails with "Reading keyfile /var/roothome/- failed". May be a systemd version issue on the live ISO vs installed system. Non-fatal since passphrase still works.
