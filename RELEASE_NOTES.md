# GN Capture v1.1.1

Standalone naming and documentation update for the read-only Blender Geometry Nodes diagnostic exporter.

### Changed
- Add-on name: **GN Capture**
- F3 operator: **Export GN Capture**
- Removed old studio branding from report headings, help text, console output and public metadata.
- Renamed standalone script to `GN_Capture_Standalone.py`.

### Unchanged
- Node, link, modifier, object, material and source-mesh capture logic.
- Existing extension ID `mw_gn_capture`, operator ID `mw.export_gn_capture`, scene property keys and `MW_GN_CAPTURE_v1` diagnostic format key.

### Installation
Download **`gn_capture-1.1.1.zip`**, then use **Blender → Preferences → Get Extensions → Install from Disk**. Do not extract the ZIP. Blender 4.2+ is the declared minimum.

### Limitations
Captures may contain local paths, object names and other scene data. Review any exported ZIP before sharing. A live Blender install/export test is still required on the target system.
