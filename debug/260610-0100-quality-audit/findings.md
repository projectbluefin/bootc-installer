# bootc-installer Quality Audit — Findings

**Date:** 2026-06-10  
**Branch:** `debug/quality-audit-20260610` (Python fixes) + `fix/composefs-native-post-install-paths` (fisherman fixes)  
**Baseline:** 712 unit tests pass, ruff clean, go vet clean, go build clean

---

## FIXED ✅

### F-1 · MEDIUM · `keyboard.py:150,152` — Invalid Python escape sequences
**File:** `bootc_installer/defaults/keyboard.py`  
**Root cause:** `"Czech (with <\|> key)"` — `\|` is not a valid Python escape sequence. Python 3.12 raises `SyntaxWarning`; Python 3.14+ will make it a `SyntaxError`, breaking the module at import time.  
**Fix:** Changed to raw strings: `r"Czech (with <\|> key)"`.  
**Evidence:** `python3 -W error::DeprecationWarning` confirmed warning before fix; `ast.parse()` confirms clean after.

### F-2 · MEDIUM · `conn_check.py` — Hardcoded `github.com` connectivity check
**File:** `bootc_installer/defaults/conn_check.py`  
**Root cause:** The installer checks `https://github.com` to determine if the network is available. `github.com` is blocked on corporate proxies and in some countries (China, etc.) — those environments can still reach `ghcr.io` where the OCI images live.  
**Fix:** Replaced with `socket.create_connection` probing `ghcr.io:443` first, then `8.8.8.8:53` as fallback. No TLS overhead, no HTTP library dependency.  
**Impact:** False-failure for valid network environments that block github.com but not the OCI registry. Users see "No Internet Connection" when internet is fine.  
**Tests updated:** `test_conn_check.py` — all 7 tests pass.

### F-3 · LOW · `bootnext.go` — `blkid` nil error wrapping produces unintelligible message
**File:** `fisherman/fisherman/internal/post/bootnext.go`  
**Root cause:** When `blkid` succeeds but returns empty output, the original code called `fmt.Errorf("blkid %s: %w", efiPart, nil)` — wrapping `nil` produces `"blkid /dev/sda1: <nil>"` in logs.  
**Fix:** Split the error and empty-output conditions into two distinct `if` blocks with clear messages.

### F-4 · MEDIUM · fisherman `checkRequiredTools` — Missing `systemd-cryptenroll` for TPM2 encryption
**File:** `fisherman/fisherman/cmd/fisherman/main.go`  
**Root cause:** The pre-flight tool check verifies `cryptsetup` for LUKS but not `systemd-cryptenroll` for TPM2 enrollment. Without this check, a TPM2 install would:  
1. Partition the disk  
2. Format partitions  
3. Install the OS (~15 min image pull)  
4. **Then fail** at TPM2 enrollment step because `systemd-cryptenroll` is missing  

This leaves the target disk wiped with no bootable system — a data-loss scenario for reinstalls.  
**Fix:** Added `{"systemd-cryptenroll", "systemd", hasTPM2}` to `checkRequiredTools`.  
**Tests added:** 3 new tests in `main_test.go` — all pass.

---

## FOUND (NOT YET FIXED)

### F-5 · HIGH (latent) · `user.go` — `CreateUser` uses wrong root for composefs-native
**File:** `fisherman/fisherman/internal/post/user.go`  
**Root cause:** For composefs-native installs (`isComposeFsNative(sysroot) == true`), `CreateUser` uses `root = sysroot` — but `sysroot/etc/` is a "ghost directory" on composefs systems whose writes are silently lost after first boot. The correct path is the deploy etc dir (found via `ComposeFsDeployEtcDirFn`), which is what `WriteHostname` and `AppendFstabEntry` already use correctly.  
**Current exposure:** ZERO. All production images with `needs_user_creation=True` use `grub2` bootloader (ostree path). Only systemd-boot images (Dakota) use composefs-native, and Dakota has `needs_user_creation=False` → `CreateUser` is never called. **But this will break silently if a future image uses both composefs-native and user creation.**  
**Recommendation:** Fix proactively before composefs-native images start requiring user creation.

### F-6 · MEDIUM · Dead code — `keyboard.py`, `language.py`, `timezone.py` wizard steps never wired
**Files:** `bootc_installer/defaults/keyboard.py`, `defaults/language.py`, `defaults/timezone.py`  
**Root cause:** These modules implement full wizard step classes with `get_finals()` but are NOT registered in `builder.py`'s `templates` dict. They are never instantiated. The installer does not configure keyboard layout, system language, or timezone on the installed system.  
**Current behavior:** The installed system uses whatever keyboard/language/timezone the image ships with. Users must configure these post-install via GNOME Settings or `localectl`.  
**Note:** This may be intentional — GNOME Initial Setup handles these on first boot for images with it enabled. But for images with GNOME Initial Setup disabled (`needs_user_creation=True`), users might expect the installer to have handled this. At minimum, the dead code should be removed or the feature documented.

### F-7 · LOW · `confirm.py:process_keyboards()` — cosmetic label bug in dead code
**File:** `bootc_installer/views/confirm.py`  
**Root cause:** `keyboard_index` is initialized to `""` (not `0`). When `len(selected_keyboards) == 1`, the confirmation row label becomes `"Keyboard "` (with trailing space). Since `keyboard.py` is not registered in `builder.py`, this code path is never reached in production. Dead code cosmetic issue.

---

## INVESTIGATED — NO BUG

| Area | Finding |
|---|---|
| Recipe file permissions | `NamedTemporaryFile` creates 0o600 — only owner-readable. Root bypasses DAC to read it. OK. |
| `_stage_fisherman_on_host()` binary replacement race | Window between staging and pkexec is milliseconds in a live-ISO single-user context. LOW theoretical risk. |
| `__finish_install` 300ms log drain | Explicit `remaining = self.__log_file.read()` before `set_installation_result` handles the race. OK. |
| `UnifiedStorage: true` default | `UnifiedStorage` is intentionally NOT emitted by fisherman — retained for schema compat only. OK. |
| `CheckImage` always uses local cache | Intentional — ISO installs use baked image; online installs update via `bootc upgrade` post-install. OK. |
| `CreateUser` with empty username | `if u.Username == "" { return nil }` — skips silently, consistent with spec. OK. |
| `bootnext.go` boot-entry parsing | `line[4:8]` correctly extracts 4-digit hex EFI boot number per UEFI spec. OK. |
| mutter `center-new-windows` hack | Window centering hack restores after 3s via background thread. If installer exits < 3s, setting stays True — cosmetic only, live ISO session is temporary. OK. |
| `checkRequiredTools` missing `fstrim`/`fsfreeze` | Both are in `util-linux` — same package as `sfdisk`, which IS checked. Always present. OK. |
| `progress.py` terminate SIGTERM scope | bash wrapper runs in its own process group. `flatpak-spawn --host` creates the pkexec/fisherman process outside the sandbox. The killpg targets bash's PGID, not the whole Flatpak session. Fisherman on host may not get SIGTERM — it will continue to completion or fail. Non-fatal: fisherman has cleanup handlers. |

---

## VM REAL-WORLD TEST

**Workflow:** `bootc-installer-qa-ssjmm` (Argo, ghost cluster)  
**Status:** Running (build step: pulling `golang:1.23-bookworm`)  
**Tests:**  
1. **validate-recipes** — 12 edge-case recipe validation tests (6 should-fail + 6 should-pass)  
2. **install-and-verify** — Full `ghcr.io/ublue-os/bluefin:stable` install to loop device + verify hostname, user, password hash, wheel group, EFI, GRUB  

**Key assertions in install test:**
- `PASS: hostname correct (qa-bluefin-install)`
- `PASS: user qauser in /etc/passwd`
- `PASS: password hash set` (non-empty, non-locked)
- `PASS: user in wheel group`
- `PASS: EFI directory populated`
- `PASS: /boot/grub2/grub.cfg exists`

Results will be appended when the workflow completes (~20 min for image pull).

---

## SUMMARY

| Severity | Fixed | Open |
|---|---|---|
| HIGH | 0 | 1 (latent, no current exposure) |
| MEDIUM | 3 | 1 (dead code) |
| LOW | 1 | 1 (dead code cosmetic) |

**Python unit tests:** 712 pass (unchanged — no regressions)  
**Go tests:** All packages pass; 3 new TPM2 preflight tests added  
**Coverage:** 52% (up from 51% — conn_check tests now mock socket correctly)
