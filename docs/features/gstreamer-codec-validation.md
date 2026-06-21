## GStreamer VP9/AV1 Codec Validation — Approach

Refs: #36|Draft

### Goal
Validate that GStreamer VP9 and AV1 codecs are present in the Flatpak runtime before attempting video playback, with graceful fallback.

### Proposed approach
1. Add codec detection at startup using GStreamer `GstRegistry` or `gst-inspect-1.0`
2. If VP9/AV1 missing: show warning, video playback unavailable
3. If codecs present: proceed with video playback as normal
4. Log detected codecs for debugging

### Files to touch
- `bootc_installer/utils/codec_check.py` (new — GStreamer codec detection)
- `bootc_installer/views/progress.py` (codec check before video init)
- `org.bootcinstaller.Installer.json` (ensure GStreamer codec plugins)

### Open questions
- Which GStreamer plugins provide VP9/AV1? (gst-plugins-good, gst-plugins-bad?)
- Detection via Python gi.repository.Gst or subprocess gst-inspect?
- Fallback UX — silent or user-visible warning?
