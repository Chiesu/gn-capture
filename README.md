# MW Geometry Nodes Capture

Read-only diagnostic exporter for Blender Geometry Nodes setups.

It exports the selected object's node graphs (including nested groups), node links and socket data, modifier inputs, object transforms, material references and source-mesh information (with safety limits).

## Installation (Blender extension)

1. Download `mw_gn_capture-1.1.0.zip` from [GitHub Releases](https://github.com/Chiesu/gn-capture/releases/latest).
2. Blender 4.2+: **Edit > Preferences > Get Extensions > Install from Disk**.
3. Select the ZIP and enable **MW Geometry Nodes Capture**.
4. Select an object containing a Geometry Nodes modifier.
5. In the 3D Viewport sidebar (`N`) choose **GN Capture > Export ZIP to Downloads**.

You can also press `F3` and search **MW Export GN Capture**.

## Alternative without installation

Open `MW_GN_Capture_v1_1.py` from this repository in Blender's **Scripting** workspace and choose **Run Script**. It automatically exports a capture for the active GN object.

## What's in the diagnostic ZIP?

- `graph.json`: structured nodes, links, interface and selected source data.
- `overview.txt`: readable overview and connection list.
- `README.txt`: summary and limitations.

Captures are written into `~/Downloads`. The exporter does not alter the scene, evaluate the final Geometry Nodes output or include a full `.blend` file. Complex meshes may be summarized rather than fully exported.

## Privacy: read before sharing

**A capture is not automatically anonymous.** It may contain your local `.blend` path, linked library paths, object/material names, custom properties and mesh samples. Inspect `graph.json` before posting the ZIP in a public issue, sharing on a forum or uploading it to another service.

## Limitations

- Not an importer or full scene reconstruction tool.
- Does not bake GN evaluation or capture rendered appearance.
- Textures, simulation caches and external add-ons are not embedded.
- Use a screenshot and/or the `.blend` file if the visual output is essential to debugging.

## License

GPL-3.0-or-later; see [LICENSE](LICENSE).
