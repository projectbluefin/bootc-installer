# Demo Mode E2E Validation

Automated E2E test for demo mode and screen-isolated preview support for rapid UI iteration.

Refs: #38|Closes

## 1. Automated Demo Mode Test (`tests/ui/test_demo_e2e.py`)

A single integration test that:
- Launches the app with `BOOTC_DEMO=1` + `TUNA_TEST=1`
- Auto-advances through all wizard steps
- Verifies confirm screen renders with "( Become Legend )" button
- Clicks confirm
- Waits for demo install to complete (~5 seconds)
- Verifies done screen shows success state

## 2. Screen-Isolated Preview Mode

Add `BOOTC_PREVIEW_SCREEN=<name>` env var support:
- Skips wizard, jumps directly to the named screen
- `progress`: immediately starts demo mode
- `done`: shows success state with dummy data
- `confirm`: shows with sample finals data
- `credits`: opens credits window directly

Enables rapid UI iteration on individual screens.

## 3. Dev Setup Documentation

Document in `README.md` or `docs/DEV_SETUP.md`:
- How to create the `dakota-lab` toolbox
- Required packages (meson, blueprint-compiler, libadwaita-devel, etc.)
- How to run demo mode
- How to run tests

## Files to Change

- [ ] `tests/ui/test_demo_e2e.py` (new)
- [ ] `bootc_installer/windows/main_window.py` (`BOOTC_PREVIEW_SCREEN` support)
- [ ] `run-dev.sh` (document better, add `--screen` flag)
- [ ] `README.md` or `docs/DEV_SETUP.md` (dev setup guide)

## Acceptance

- [ ] `xvfb-run -a pytest tests/ui/test_demo_e2e.py -v` passes
- [ ] `BOOTC_PREVIEW_SCREEN=progress` opens directly to progress in demo
- [ ] Dev setup documented enough that a new contributor can run the app in < 10 min
