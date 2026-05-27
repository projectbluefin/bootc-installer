# UX Research: ubuntu-desktop-provision Installer

**Source:** https://github.com/canonical/ubuntu-desktop-provision  
**Date:** 2026-05-27  
**Purpose:** Design reference for Project Bluefin Dakota installer UX improvements

---

## Key Takeaway

We want their **UX and workflow patterns**, not their visual styling. Dakota keeps libadwaita.

---

## Screen Flow (Happy Path, Single Image)

Minimum screens for a single-image install with defaults:

1. Loading/Splash
2. Disk Setup
3. Encryption choice
4. Passphrase (if encrypted)
5. Identity / account
6. **Review (Confirm)** ← the only place "Install" appears
7. Installing... (progress + slideshow)
8. Recovery Key (encrypted only)
9. Done / Restart

**Absolute minimum (autoinstall):** Loading → Confirm → Install → Done (4 screens).

---

## UX Patterns to Apply to Dakota

### 1. "Install" only appears on the Confirm screen
All prior screens use "Next". The confirm screen is the single destructive-action gate.
Button: `"Install"` with `destructive-action` style. ✅ Already correct in our confirm.blp.

### 2. Encryption copy — plain language

| Technical | Plain language (Ubuntu) |
|---|---|
| "Encrypt Device" | **"Encrypt this disk"** ✅ done |
| "Protect your data with a password" | **"You will need a passphrase each time you turn on your computer."** ✅ done |
| "TPM2 Auto-unlock" | **"Use hardware-backed encryption"** ✅ done |
| TPM subtitle | **"The disk unlocks automatically on this hardware. Your passphrase remains as a fallback."** ✅ done |

### 3. Inline data destruction warning (not a dialog)
Shown in the disk screen subtitle. Always visible once the step is loaded, not just after a disk is selected.
> "Select the disk where you want to install. All data on the selected disk will be permanently erased."
✅ Implemented in default-disk.blp subtitle.

### 4. Real-time passphrase strength (text only, no progress bar)
Below the passphrase field, per-keystroke:
- **Weak** (error CSS): < 8 chars or only 1 character class
- **Fair** (warning CSS): 8-11 chars, 2 classes
- **Strong** (success CSS): 12+ chars, 3+ classes
✅ Implemented in encryption.py + default-encryption.blp.

### 5. Done screen — specific, not generic
- Headline: `"{name} is installed"` (not "Installation Complete")
- Subtitle: `"Restart now to complete the installation."`
- Primary button: **"Restart Now"**
✅ Implemented in done.py.

### 6. Recovery Key screen (TODO)
Shown only after a successful **encrypted** install, before restart.
- Header: "Save Your Recovery Key"
- Body: "If your disk fails to unlock automatically, you will need this recovery key."
- Actions: Copy to clipboard / Save to file / Show QR code
- **Checkbox required** before Restart is enabled: "I have saved my recovery key"
- Requires fisherman to emit `{"type": "recovery_key", "key": "..."}` in its JSON stream

### 7. Install progress slideshow (TODO)
During installation, show Dakota-specific content (not just a log tail):
- Slide 1: "Built on GNOME OS" — composefs, atomic updates, bootc
- Slide 2: "Stays out of your way" — no package manager, bootc upgrade, rollback  
- Slide 3: "Ready when you are" — first boot, no account creation needed
- Toggle button (terminal icon) to switch to log view
Pattern: `Gtk.Stack` switching between slide carousel and log view.

### 8. Battery / not plugged in warning (TODO)
Non-blocking `Adw.Banner` on the disk screen when running on battery:
> "Computer is not plugged in"
Check: `cat /sys/class/power_supply/AC/online` → "0" = on battery.

### 9. Confirm screen — human-readable encryption label (TODO)
The confirm screen summary should show plain labels, not recipe keys:
```python
ENC_LABELS = {
    "none": "None",
    "luks-passphrase": "Encrypted with passphrase",
    "tpm2-luks": "Hardware-backed encryption",
    "tpm2-luks-passphrase": "Hardware-backed + passphrase fallback",
}
```

### 10. per-page `should_show()` pattern (TODO / refactor)
Each page self-reports visibility instead of central Builder logic.
```python
class VanillaDefaultEncryption(Adw.Bin):
    def should_show(self, context: dict) -> bool:
        return True  # default; can check context["has_tpm2"] etc.
```
Pattern from Ubuntu: `onLoad() → bool` in wizard_router.

---

## Ubuntu Technical Stack (for reference)

- **UI:** Flutter + Yaru (NOT GTK — do not copy widget implementations)
- **Backend:** Subiquity (Python) via Unix socket
- **Routing:** Declarative wizard_router with `onLoad()` predicates
- **Step indicator:** Dot-based (12px selected, 8px unselected) in Hero-tagged bottom bar
- **Illustrations:** Per-step SVGs with dynamic accent color recoloring

---

## What We Keep From Libadwaita

- `Adw.PreferencesPage` / `Adw.PreferencesGroup` / `Adw.ActionRow`
- `Adw.Banner` for warnings (disk, battery, errors)
- `Adw.PasswordEntryRow` for passphrase
- `Adw.AlertDialog` for confirmations
- CSS classes: `error`, `warning`, `success` for inline feedback
- `Adw.Carousel` for wizard flow (existing)
