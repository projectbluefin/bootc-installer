# End-to-End Feature Verification Test Plan

Software-level test plan (demo mode + automated). Complements hardware lab testing (#42), encryption testing (#45), and failure path testing (#44).

Refs: #41|Closes

## Test Layers

| Layer | Command | Description |
|-------|---------|-------------|
| 1 | `pytest tests/unit/ -q` | Pure-logic, no display (210+ tests) |
| 2 | `xvfb-run pytest tests/ui/ -v` | Headless GTK, real widgets (14+ tests) |
| 3 | `BOOTC_DEMO=1 ./run-dev.sh` | Full UI flow, fake install |
| 4 | `flatpak run org.bootcinstaller.Installer` | Real sandbox, real GResource |
| 5 | Hardware lab deploy + real install | Real fisherman, real disk (#42) |
| 6 | Post-reboot verification | Installed system validates (#42) |

## Layer 3: Demo Mode Walkthrough

### Welcome Screen
- [ ] App launches without crashes or tracebacks
- [ ] Welcome text displays correctly
- [ ] Credits button opens credits window with hero cards
- [ ] Credits window shows all sections from credits.json
- [ ] Bluetooth pairing row visible (if BT adapter present)
- [ ] Power off row opens confirmation dialog
- [ ] "Install" row advances to next step

### Wizard Steps
- [ ] Image selection shows images from images.json with logos
- [ ] Custom image entry works (paste URL)
- [ ] Disk selection lists available disks with size/model
- [ ] Battery warning banner shows when on battery power
- [ ] Encryption type selector shows all 4 options
- [ ] Passphrase field accepts input, shows/hides password
- [ ] Timezone map/list works
- [ ] Dinosaur fact shows when country is selected
- [ ] Language/keyboard selection works with search
- [ ] User creation fields validate (username format, password match)

### Confirm Screen
- [ ] Summary shows all selected options as rows
- [ ] Disk info formatted correctly (device + size)
- [ ] Encryption type shown if selected
- [ ] Image name/ref shown
- [ ] "( Become Legend )" button text is correct

### Progress Screen
- [ ] Video plays (not black rectangle, not frozen frame)
- [ ] Video is muted and loops continuously
- [ ] Soundtrack toggle button is clickable
- [ ] QR codes render as actual QR images
- [ ] QR codes are scannable with phone
- [ ] Carousel has indicator dots, auto-advances every 50s
- [ ] Console/media toggle buttons work
- [ ] Progress bar advances through 9 steps (demo: 0% → 100% in ~5s)
- [ ] Step name updates as progress advances

### Done Screen
- [ ] Success: shows "[Image] is installed" with distro name
- [ ] Success: elapsed time in subtitle
- [ ] Success: reboot button visible and functional
- [ ] Failure: shows "Installation failed" with error icon
- [ ] Failure: error hint extracted from log
- [ ] Failure: retry button visible

## Sign-off Criteria
- [ ] All Layer 1 tests pass (210+ unit tests)
- [ ] All Layer 2 tests pass (14+ UI tests)
- [ ] Layer 3 demo walkthrough: all checkboxes checked
- [ ] Layer 4 Flatpak builds without error
- [ ] No Python tracebacks or GStreamer CRITICALs in stderr
