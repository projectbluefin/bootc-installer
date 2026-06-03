## libpastry Integration — Approach

Refs: #39|Draft

### Goal
Integrate libpastry for frosted glass effects, spring animations, and spinners across the installer UI.

### Proposed approach
1. Add libpastry as a Flatpak module in `org.bootcinstaller.Installer.json`
2. Create `bootc_installer/utils/pastry_compat.py` wrapper (may already exist as stub)
3. Apply frosted glass to: welcome screen background, progress screen overlay, credits window
4. Replace loading spinners with libpastry animated spinners
5. Add spring animations to carousel transitions and button press feedback

### Files to touch
- `org.bootcinstaller.Installer.json` (add libpastry module)
- `bootc_installer/utils/pastry_compat.py` (wrapper/facade)
- `bootc_installer/views/progress.py` (frosted glass overlay)
- `bootc_installer/windows/dialog_credits.py` (frosted glass)
- `bootc_installer/views/welcome.py` (frosted glass)
- `.blp` UI templates (glass CSS classes)

### Open questions
- libpastry API stability — which version to target?
- Performance impact on low-end hardware?
- Fallback when libpastry is unavailable?
