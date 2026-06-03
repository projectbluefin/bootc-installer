## Pre-Generate Soundtrack QR Codes — Approach

Refs: #35|Draft

### Goal
Pre-generate QR code images for soundtrack links at build time instead of generating them at runtime.

### Proposed approach
1. Add build step: read `data/tracks.json`, generate QR PNGs for each track URL
2. Bundle QR PNGs as GResources alongside existing soundtrack data
3. At runtime: load pre-generated QR images from GResource instead of generating on-the-fly
4. Removes runtime dependency on QR generation library

### Files to touch
- `scripts/generate_soundtrack_qrs.py` (new — build-time QR generator)
- `org.bootcinstaller.Installer.json` (add build step, add `qrcode` pip dep for build)
- `bootc_installer/views/progress.py` (load QR from GResource instead of generating)
- `data/tracks.json` (ensure song.link URLs are present)

### Open questions
- Use `qrcode` (pure Python) or `qrencode` (C, faster)?
- QR size/resolution for phone scannability?
- Regenerate QRs when tracks.json changes (CI check)?
