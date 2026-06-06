# CI/CD Guide — bootc-installer

Complete reference for all CI workflows, release process, and the release qualification runbook.

---

## Workflows

### `python-test.yml` — Python Tests

**Triggers:** push/PR to `dev`/`prod`, merge queue, manual dispatch

| Job | What it does |
|-----|-------------|
| `unit` | `pytest tests/unit/` with coverage (`--cov-fail-under=47`) — no display required |
| `ui` | `pytest tests/ui/` via Xvfb + compiled GResources (meson/ninja) |

Coverage gate is a **ratchet** — never lower `--cov-fail-under`. Measure with `pytest tests/unit/ -q --cov=bootc_installer 2>&1 | tail -5` before raising it.

---

### `go-test.yml` — Go Tests (fisherman)

**Triggers:** push/PR to `dev`/`prod`, merge queue, manual dispatch

Runs inside `fisherman/fisherman/`:
1. `go vet ./...`
2. `go test -v -count=1 -timeout=60s -coverprofile=coverage.out ./...`
3. Coverage gate: 20%
4. `go test -race -count=1 -timeout=60s ./...` (race detector)

---

### `flatpak.yml` — GNOME Flatpak Build

**Triggers:** push to `dev`/`prod`, `v*` tags, PRs to `dev`/`prod`

| Job | Condition | Output |
|-----|-----------|--------|
| `production` | PR, `prod` push, or `v*` tag | `org.bootcinstaller.Installer.flatpak` → `continuous` release |
| `devel` | PR or `dev` push | `org.bootcinstaller.Installer.Devel.flatpak` → `continuous-dev` release |

Uses `ghcr.io/flathub-infra/flatpak-github-actions:gnome-50` container with `--privileged`. Requires `permissions: contents: write` on the release job.

---

### `build-flatpaks.yml` — Multi-Variant Flatpak Build

**Triggers:** push to `dev`/`prod`, `v*` tags, manual dispatch

Builds all three variants in parallel via a matrix:

| Variant | App ID | Manifest |
|---------|--------|---------|
| GNOME | `org.bootcinstaller.Installer` | `flatpak/org.bootcinstaller.Installer.json` |
| XFCE | `org.xfceinstaller.Installer` | `flatpak/org.xfceinstaller.Installer.json` |
| KDE | `org.kdeinstaller.Installer` | `flatpak/org.kdeinstaller.Installer.json` |

Publishes Flatpaks as GitHub release assets under the same `continuous` / `continuous-dev` / `v*` tags.

---

### `validate-flatpak.yml` — Validate Flatpak Manifests

**Triggers:** PRs/pushes that touch `flatpak/*.json`, `meson.build`, `meson_options.txt`

- Validates all manifests are well-formed JSON
- Checks required fields: `app-id`, `runtime`, `command`
- Verifies app-id consistency per variant (GNOME / XFCE / KDE)
- Posts a ✅ comment on the PR when all pass

---

### `nightly.yml` — Nightly Tests

**Triggers:** 06:00 UTC daily, manual dispatch

Runs fisherman tests on both `dev` and `prod` branches:
1. `go vet ./...`
2. `go test -v -count=1 -timeout=60s ./...`
3. `go test -race -count=1 -timeout=60s ./...`

This catches race conditions and test drift that only appear under extended runs.

---

## Branch Strategy

```
feature/xyz  ──►  dev  ──►  prod
```

- All feature PRs target `dev`
- `prod` is promoted wholesale from `dev` when `dev` is shippable
- Never open PRs directly against `prod`
- Merge queue is enabled on `dev` — use `gh pr merge --squash <N>` to enqueue

---

## Release Process

### Continuous (pre-release)

Automatic on every push to `dev` or `prod`:
- `dev` → `continuous-dev` pre-release
- `prod` → `continuous` pre-release

### Tagged release

```bash
git tag v0.3.0
git push origin v0.3.0
```

Both `flatpak.yml` and `build-flatpaks.yml` attach their Flatpak artifacts to the tagged release.

---

## Release Qualification Runbook

### Software-only (automated — run locally)

```bash
./QUALIFY_SOFTWARE.sh
```

This validates Flatpak JSON, runs all unit + UI tests, runs fisherman Go tests, and builds the production and devel Flatpaks. All steps must pass green before promoting `dev → prod`.

### Hardware-only checks (manual — not automated in CI)

These require real hardware and cannot be gated in CI:

| Check | How to test |
|-------|-------------|
| TPM2 LUKS enrolment | Install with `tpm2-luks` on real hardware; verify no password prompt on reboot |
| Recovery key display | Install with `tpm2-luks-passphrase`; confirm key shown and copyable in GUI |
| Passphrase fallback | Install with `luks-passphrase`; verify passphrase prompt on reboot |
| GRUB boot (XFS root) | Install with `filesystem=xfs`; verify GRUB loads from ext4 `/boot` |
| systemd-boot (btrfs/composefs) | Install with `composeFsBackend=true`; verify `bootctl status` clean |
| Windows slurp | Run on machine with Windows NTFS partition; verify wallpapers + data migrated |
| Offline ISO | Boot from live ISO with embedded OCI; verify install completes without internet |
| Post-reboot WiFi | Install on machine with saved WiFi; verify auto-reconnect after reboot |
| OEM first-boot | Install on ASUS/Framework hardware; verify OEM packages queued |

For the full E2E integration tests (QEMU-backed, requires root):

```bash
go build -o /tmp/fisherman-test ./fisherman/fisherman/cmd/fisherman/
sudo FISHERMAN_BIN=/tmp/fisherman-test pytest tests/integration/test_e2e_install.py -v -s
# With QEMU boot verification (~5 min/image):
sudo FISHERMAN_BIN=/tmp/fisherman-test BOOT_VERIFY=1 pytest tests/integration/test_e2e_install.py -v -s
```

---

## Common CI Failures

| Symptom | Cause | Fix |
|---------|-------|-----|
| "No checks reported" on PR | Branch has merge conflicts — GitHub silently skips `pull_request` events | `gh pr view N --json mergeable` → rebase onto `dev` |
| Coverage gate fails | New code not covered | Add tests or measure actual floor before lowering gate |
| `ModuleNotFoundError` in Flatpak but not source | New `.py` not in `meson.build` `sources = [...]` | Add the file to its subpackage's `meson.build` |
| fisherman submodule not updated | Parent repo pointer not bumped after submodule push | `git add fisherman && git commit -m "chore: update fisherman submodule"` |
| `safe.bareRepository` Flatpak build failure | Used `"type": "git"` in manifest | Switch to `"type": "archive"` with SHA256 |


**Triggers:**
- Pushes to `dev` or `prod` branches
- Any tag matching `v*`
