# Publishing notes

Repository: https://github.com/Chiesu/gn-capture

**Version 1.1.1:** This is a visibility/branding update. Do **not** change extension ID `mw_gn_capture` or operator ID `mw.export_gn_capture`: both are retained to support upgrades from v1.1.0. The JSON format identifier `MW_GN_CAPTURE_v1` also remains stable.

The downloadable Blender Extension ZIP contains exactly `__init__.py`, `blender_manifest.toml` and `LICENSE` at the archive root. The standalone script `GN_Capture_Standalone.py` is available from the GitHub source repository but is **not** included in the installable extension ZIP.

To publish: update repository source, then create a **new** GitHub Release tagged `v1.1.1` and attach `gn_capture-1.1.1.zip`. Keep previous v1.1.0 release intact. Once published, `releases/latest` will automatically point to the new release.
