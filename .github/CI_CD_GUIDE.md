# GitHub Actions CI/CD Guide

Automated building and releasing of all three bootc-installer variants (GNOME, XFCE, KDE).

## Workflows

### 1. `build-flatpaks.yml` - Multi-Variant Flatpak Builder

**Triggers:**
- Pushes to `dev` or `main` branches
- Any tag matching `v*`
- Manual dispatch via GitHub Actions UI

**What it does:**
- Builds all three variants in parallel:
  - **GNOME**: `org.bootcinstaller.Installer`
  - **XFCE**: `org.xfceinstaller.Installer`
  - **KDE**: `org.kdeinstaller.Installer`
- Exports Flatpaks to `.flatpak` files
- Creates/updates GitHub releases with tags:
  - `continuous` (releases on main branch)
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

# Automatic on push to main
git push origin main

# Automatic on tag
git tag v0.2.0
git push origin v0.2.0

# Manual trigger via GitHub UI
# Actions > Build Multi-Variant Flatpaks > Run workflow
```

### 2. `validate-flatpak.yml` - Manifest Validation

**Triggers:**
- Pull requests modifying Flatpak configs
- Pushes to `dev` or `main` branches
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

### Release URLs

Access built Flatpaks at:
```
https://github.com/tuna-os/tuna-installer/releases/download/continuous/org.bootcinstaller.Installer.flatpak
https://github.com/tuna-os/tuna-installer/releases/download/continuous/org.xfceinstaller.Installer.flatpak
https://github.com/tuna-os/tuna-installer/releases/download/continuous/org.kdeinstaller.Installer.flatpak

# Dev versions
https://github.com/tuna-os/tuna-installer/releases/download/continuous-dev/org.bootcinstaller.Installer.Devel.flatpak
https://github.com/tuna-os/tuna-installer/releases/download/continuous-dev/org.xfceinstaller.Installer.Devel.flatpak
https://github.com/tuna-os/tuna-installer/releases/download/continuous-dev/org.kdeinstaller.Installer.Devel.flatpak
```

## Integration with xfce-linux-iso and tromso-iso

The ISO builders automatically download these Flatpaks:

```bash
# xfce-linux-iso downloads XFCE variant
curl "https://github.com/tuna-os/tuna-installer/releases/download/continuous/org.xfceinstaller.Installer.flatpak"

# tromso-iso downloads KDE variant  
curl "https://github.com/tuna-os/tuna-installer/releases/download/continuous/org.kdeinstaller.Installer.flatpak"
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
