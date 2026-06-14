# docs/skills — Index

Agent skill docs for `projectbluefin/bootc-installer`. Any agent (Copilot,
Claude, etc.) working in this repo should load the relevant files.

## What belongs here

Workflow knowledge, architectural context, operational runbooks, and engineering
gotchas that any agent needs to work effectively in this repo.

## What does NOT belong here

Agent-specific instruction files (`AGENTS.md`, `.github/copilot-instructions.md`)
are loaded separately and must not be listed here.

## Skill docs

| File | What it covers |
|---|---|
| [PITFALLS.md](PITFALLS.md) | Engineering gotchas — GTK unit testing, composefs-native path layout, GStreamer quirks, recipe override chain, QR companion, stub contamination, flatpak-builder `--run` PATH |
| [SKILL.md](SKILL.md) | Main skill — quick commands, architecture, dev loop, fisherman submodule workflow, CI/release, ISO integration |

## Key architectural facts (current state)

- **Two-component**: Python GUI (GTK4/Adwaita) + fisherman Go backend (submodule at `fisherman/`)
- **Three image variants**: GNOME (default), XFCE, KDE — shared Python core
- **Branch model**: `feature/xyz → dev → prod`. All PRs target `dev`. Never `prod` directly.
- **Fisherman is a separate git repo** (`projectbluefin/fisherman`). Commit there first, then update the submodule pointer in this repo.
- **Dev loop**: `./dev.sh` — builds via `flatpak run org.flatpak.Builder --ccache` into `_build/`, runs with `flatpak-builder --run` (no user/system install). `/app/bin` not in PATH by default; use `/app/bin/bootc-installer`.
- **Debug log (in `--run` mode)**: `~/.var/app/org.bootcinstaller.Installer.Devel/cache/bootc-installer/installer-debug.log`
- **Branch protection**: no classic branch protection on `dev` — uses repository rulesets. Remove via `gh api --method DELETE repos/org/repo/rulesets/<id>`.
- **composefs-native layout**: writable `/etc` = `state/deploy/<HASH>/etc/`, writable `/var` = `state/os/default/var/`. Never write to `$TARGET/etc/` or `$TARGET/var/` for post-install state — those are orphaned ghost dirs. See PITFALLS.md for full details.
