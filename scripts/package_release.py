"""Create the installable GN Capture Blender extension ZIP from repository files."""
from pathlib import Path
import tomllib
import zipfile

repo = Path(__file__).resolve().parents[1]
with (repo / 'blender_manifest.toml').open('rb') as file:
    manifest = tomllib.load(file)
assert manifest['id'] == 'mw_gn_capture'
assert manifest['version'] == '1.1.1'
out = repo / 'dist' / 'gn_capture-1.1.1.zip'
out.parent.mkdir(parents=True, exist_ok=True)
with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
    for name in ('__init__.py', 'blender_manifest.toml', 'LICENSE'):
        archive.write(repo / name, arcname=name)
print(out)
