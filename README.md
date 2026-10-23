# GN Capture

A read-only Blender extension for exporting Geometry Nodes diagnostics as a single ZIP. Useful for documenting complex procedural setups, inspecting node graphs, and sharing data for troubleshooting.

**Current release:** v1.1.1 · **Blender:** 4.2+ · **License:** GPL-3.0-or-later.

<img width="1920" height="1080" alt="hero" src="https://github.com/user-attachments/assets/d483fc62-2025-426e-8db6-91a70e98f1c6" />

## Download and install

1. Download **`gn_capture-1.1.1.zip`** from [GitHub Releases](https://github.com/Chiesu/gn-capture/releases/latest). Download the attached asset, **not** GitHub's automatically generated source archive.
2. In Blender, open **Edit → Preferences → Get Extensions → Install from Disk** and choose the ZIP **without extracting it**.
3. Enable **GN Capture** if Blender asks.
4. In the 3D Viewport, open the **N** sidebar → **GN Capture**, or press **F3** and search **Export GN Capture**.

This update keeps the existing extension ID (`mw_gn_capture`) to avoid creating a second installation for people upgrading from v1.1.0.

## How to use it

<img width="1920" height="1080" alt="export-panel" src="https://github.com/user-attachments/assets/51ac907b-8c87-432b-b7b4-2108218c0ece" />

1. Select the object with a **Geometry Nodes** modifier.
2. Optionally disable **Include material nodes**.
3. Click **Export ZIP to Downloads**.
4. Find `GN_CAPTURE_<object>_<timestamp>.zip` in your Downloads folder. The export path is also copied to the clipboard.

If your active object contains Geometry Nodes, the exporter captures that object only. Otherwise, it captures the other selected objects that have Geometry Nodes.

## What the export includes

- **`graph.json`**: nested node trees, node properties, sockets, links, group interfaces, modifier values and referenced datablocks.
- **`overview.txt`**: a readable map of nodes, connections, objects and modifier inputs.
- **`README.txt`**: included export guidance and limitations.

The export can include source-mesh topology and vertex-group assignments for smaller objects. Large meshes are summarized for manageable file sizes. Material graph capture is optional.

## Single-script alternative

If you don't want to install an extension, open **`GN_Capture_Standalone.py`** from this repository in Blender's **Scripting → Text Editor** and select **Run Script** with a Geometry Nodes object selected. The script registers the panel and immediately exports the selected object's diagnostic ZIP.

## Privacy and limitations

- Exports are written locally. There is no account, network request or automatic upload.
- Diagnostic ZIPs can contain **local file paths, custom properties, object names, node labels, referenced materials and source-mesh details**. Inspect `graph.json` before sharing a capture publicly.
- This is a **diagnostic snapshot**, not a `.blend` replacement or full scene importer.
- Evaluated Geometry Nodes geometry, simulation caches, packed textures, linked libraries and render previews are not bundled.
- The legacy JSON format key **`MW_GN_CAPTURE_v1`** remains unchanged in v1.1.1 for compatibility with existing readers. It is an internal format identifier, not an add-on name.
- Blender installation and export require a runtime check on the user's target Blender version; the release was verified for Python syntax, manifest structure and ZIP integrity in the packaging environment.

## Updating from v1.1.0

Install v1.1.1 over the previous extension. The extension ID, operator `mw.export_gn_capture`, registered property keys, and diagnostic JSON format remain unchanged; only visible naming, attribution, export messaging and packaging documentation have been updated.

## Source and support

Source and issues: https://github.com/Chiesu/gn-capture

License: GPL-3.0-or-later. See [LICENSE](LICENSE).
