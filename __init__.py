# SPDX-License-Identifier: GPL-3.0-or-later
bl_info = {
    "name": "MW | Geometry Nodes Capture",
    "author": "Magnetic Works contributors",
    "version": (1, 1, 0),
    "blender": (4, 2, 0),
    "location": "3D Viewport > Sidebar (N) > GN Capture; F3 > MW Export GN Capture",
    "description": "Read-only Geometry Nodes diagnostic export to ~/Downloads",
    "category": "Node",
}

"""
MW | Geometry Nodes Capture v1.1
=================================
One reusable exporter for Blender 4.2+ / 5.2.x.

QUICK RUN (no addon installation):
    Select an object with Geometry Nodes, open this file in Blender's
    Scripting > Text Editor, click Run Script. A ZIP is written to Downloads.

INSTALL AS ADDON (optional):
    Edit > Preferences > Add-ons > Install from Disk, select this .py.
    Select the object, press F3 and search "MW Export GN Capture", or
    open Viewport N-panel > GN Capture > Export to Downloads.

Produces one .zip: full graph.json, human-readable overview.txt, and README.txt.
This does not modify meshes, node groups, materials, modifiers, or the scene.
The graph is a diagnostic description, not an independently executable .blend.
"""

import bpy
from bpy.props import BoolProperty, StringProperty
from pathlib import Path
from datetime import datetime
from collections import Counter
import json
import math
import re
import zipfile
import traceback
from itertools import islice

FORMAT = "MW_GN_CAPTURE_v1"
MAX_ARRAY_ITEMS = 96
MAX_RNA_DEPTH = 5
MAX_FULL_MESH_VERTICES = 12000
MAX_FULL_MESH_FACES = 18000
MAX_TOTAL_FACE_CORNERS = 85000
MAX_ATTRIBUTE_VALUES = 12000
MAX_ATTRIBUTE_SAMPLE = 32
MAX_SHADER_MATERIALS = 75


def safe_filename(value):
    return (re.sub(r"[^A-Za-z0-9._-]+", "_", str(value)).strip("._")[:72]
            or "Selected_Object")


def attr(obj, key, fallback=None):
    try:
        return getattr(obj, key)
    except Exception:
        return fallback


def identifier(obj):
    return attr(obj, "name_full", attr(obj, "name", ""))


def jsonify(value, depth=0):
    """Convert Blender IDs, mathutils types and RNA values into real JSON.

    Avoids the previous reader's '<Vector>' / '<Euler>' information loss.
    """
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else repr(value)
    if depth > MAX_RNA_DEPTH:
        return {"truncated_type": type(value).__name__}
    try:
        if isinstance(value, bpy.types.ID):
            out = {"datablock_type": type(value).__name__, "name": value.name}
            library = attr(value, "library")
            if library:
                out["library_path"] = attr(library, "filepath", "")
            if isinstance(value, bpy.types.Object):
                out["object_type"] = value.type
                out["location"] = jsonify(value.location, depth + 1)
                out["rotation_euler"] = jsonify(value.rotation_euler, depth + 1)
                out["scale"] = jsonify(value.scale, depth + 1)
                out["matrix_world"] = jsonify(value.matrix_world, depth + 1)
            elif isinstance(value, bpy.types.Image):
                out["filepath"] = attr(value, "filepath", "")
            return out
    except Exception:
        pass
    if isinstance(value, (dict,)):
        return {str(k): jsonify(v, depth + 1) for k, v in
                list(value.items())[:MAX_ARRAY_ITEMS]}
    # ColorRamp or CurveMapping, CollectionProperty etc are handled separately.
    if hasattr(value, "bl_rna"):
        return {"rna_type": type(value).__name__,
                "name": attr(value, "name", None)}
    try:
        if hasattr(value, "to_list"):
            return jsonify(value.to_list(), depth + 1)
        if hasattr(value, "__iter__"):
            # Matrix -> rows, Vector/Color/Euler/Quaternion -> floats.
            result = []
            for i, element in enumerate(value):
                if i == MAX_ARRAY_ITEMS:
                    result.append({"remaining_elements_truncated": True})
                    break
                result.append(jsonify(element, depth + 1))
            return result
    except Exception:
        pass
    if hasattr(value, "name"):
        return {"name": str(attr(value, "name", "")),
                "type": type(value).__name__}
    return {"unhandled_type": type(value).__name__}


IGNORE_RNA = {
    "rna_type", "bl_rna", "id_data", "inputs", "outputs", "internal_links",
    "nodes", "links", "interface", "node_tree", "parent", "location",
    "location_absolute", "dimensions", "width", "width_hidden", "height",
    "select", "label", "name", "color", "type", "bl_idname", "mute",
    "hide", "warning_propagation", "is_registered_node_type", "bl_static_type",
    "poll", "poll_instance", "use_custom_color", "show_options", "show_preview",
    "show_texture", "draw_buttons", "draw_buttons_ext", "is_active_output",
    "scatter5", "panel_states", "texture_mapping", "color_mapping",
    "color_ramp", "mapping", "curve_mapping", "index_switch_items",
    "enum_items", "repeat_items", "simulation_items", "capture_items",
    "bake_items", "items", "paired_input", "paired_output", "state_items",
    "node_warnings", "node_warning_texts", "image_user",
}


def rna_scalars(obj):
    result = {}
    try:
        properties = obj.bl_rna.properties
    except Exception:
        return result
    for prop in properties:
        key = attr(prop, "identifier", "")
        if not key or key in IGNORE_RNA or key.startswith(("bl_", "rna_")):
            continue
        try:
            ptype = attr(prop, "type", "")
            if ptype == "COLLECTION":
                continue
            value = getattr(obj, key)
            if ptype == "POINTER":
                if value is not None and isinstance(value, bpy.types.ID):
                    result[key] = jsonify(value)
                continue
            if ptype in {"INT", "FLOAT", "BOOLEAN", "STRING", "ENUM"}:
                result[key] = jsonify(value)
        except Exception:
            continue
    return result


def capture_special_node_settings(node):
    special = {}
    cr = attr(node, "color_ramp")
    if cr is not None:
        try:
            special["color_ramp"] = {
                "color_mode": cr.color_mode,
                "interpolation": cr.interpolation,
                "hue_interpolation": cr.hue_interpolation,
                "elements": [
                    {"position": element.position, "color": jsonify(element.color)}
                    for element in cr.elements
                ],
            }
        except Exception as exc:
            special["color_ramp_read_error"] = str(exc)
    mp = attr(node, "mapping") or attr(node, "curve_mapping")
    if mp is not None:
        try:
            special["curve_mapping"] = {
                "use_clip": attr(mp, "use_clip"),
                "clip_min_x": attr(mp, "clip_min_x"),
                "clip_min_y": attr(mp, "clip_min_y"),
                "clip_max_x": attr(mp, "clip_max_x"),
                "clip_max_y": attr(mp, "clip_max_y"),
                "curves": [
                    [{"location": jsonify(p.location),
                      "handle_type": attr(p, "handle_type")}
                     for p in c.points]
                    for c in mp.curves
                ],
            }
        except Exception as exc:
            special["curve_mapping_read_error"] = str(exc)
    for name in ("index_switch_items", "enum_items", "repeat_items",
                 "simulation_items", "capture_items", "bake_items", "state_items"):
        item_collection = attr(node, name)
        if item_collection is not None:
            try:
                special[name] = [
                    {"name": attr(it, "name"), "identifier": attr(it, "identifier"),
                     "socket_type": attr(it, "socket_type"),
                     "data_type": attr(it, "data_type")}
                    for it in list(item_collection)[:MAX_ARRAY_ITEMS]
                ]
            except Exception:
                pass
    for name in ("paired_input", "paired_output"):
        target = attr(node, name)
        if target is not None:
            special[name] = attr(target, "name")
    return special


def socket_info(socket, index):
    out = {
        "index": index,
        "name": attr(socket, "name", ""),
        "identifier": attr(socket, "identifier", ""),
        "bl_idname": attr(socket, "bl_idname", ""),
        "type": attr(socket, "type", ""),
        "enabled": bool(attr(socket, "enabled", True)),
        "is_linked": bool(attr(socket, "is_linked", False)),
        "is_multi_input": bool(attr(socket, "is_multi_input", False)),
        "hide_value": bool(attr(socket, "hide_value", False)),
    }
    try:
        if hasattr(socket, "default_value"):
            out["default_value"] = jsonify(socket.default_value)
    except Exception as exc:
        out["default_value_error"] = str(exc)
    for key in ("default_attribute_name", "attribute_domain", "subtype",
                "min_value", "max_value"):
        if hasattr(socket, key):
            out[key] = jsonify(attr(socket, key))
    return out


def socket_index(node, socket, direction):
    collection = node.inputs if direction == "INPUT" else node.outputs
    try:
        address = socket.as_pointer()
        for i, candidate in enumerate(collection):
            if candidate.as_pointer() == address:
                return i
    except Exception:
        pass
    try:
        for i, candidate in enumerate(collection):
            if candidate == socket:
                return i
    except Exception:
        pass
    return -1


def interface_info(group):
    output = []
    interface = attr(group, "interface")
    if interface is None:
        return output
    try:
        items = list(interface.items_tree)
    except Exception:
        return output
    for item in items:
        parent = attr(item, "parent")
        record = {
            "item_type": attr(item, "item_type"),
            "name": attr(item, "name"),
            "identifier": attr(item, "identifier"),
            "parent_panel": attr(parent, "name"),
            "parent_identifier": attr(parent, "identifier"),
            "description": attr(item, "description", ""),
        }
        for key in ("in_out", "socket_type", "default_value", "subtype",
                    "min_value", "max_value", "hide_value", "hide_in_modifier",
                    "default_attribute_name", "attribute_domain", "is_panel_toggle",
                    "closed", "default_closed", "menu_expanded"):
            try:
                if hasattr(item, key):
                    record[key] = jsonify(getattr(item, key))
            except Exception:
                pass
        output.append(record)
    return output


def node_info(node):
    group = attr(node, "node_tree")
    data = {
        "name": node.name,
        "label": attr(node, "label", ""),
        "bl_idname": attr(node, "bl_idname", ""),
        "node_type": attr(node, "type", ""),
        "location": jsonify(attr(node, "location")),
        "width": attr(node, "width"),
        "parent_frame": attr(attr(node, "parent"), "name"),
        "mute": bool(attr(node, "mute", False)),
        "hide": bool(attr(node, "hide", False)),
        "settings": rna_scalars(node),
        "special_settings": capture_special_node_settings(node),
        "inputs": [socket_info(s, i) for i, s in enumerate(node.inputs)],
        "outputs": [socket_info(s, i) for i, s in enumerate(node.outputs)],
    }
    if group is not None:
        data["nested_node_tree"] = identifier(group)
        data["nested_node_tree_type"] = attr(group, "bl_idname")
    for key in ("object", "collection", "material", "image", "texture",
                "text", "scene", "font", "node_group"):
        reference = attr(node, key)
        if reference is not None:
            data.setdefault("datablock_references", {})[key] = jsonify(reference)
    return data


def link_info(link):
    return {
        "from_node": link.from_node.name,
        "from_socket": link.from_socket.name,
        "from_socket_index": socket_index(link.from_node, link.from_socket, "OUTPUT"),
        "from_identifier": attr(link.from_socket, "identifier", ""),
        "to_node": link.to_node.name,
        "to_socket": link.to_socket.name,
        "to_socket_index": socket_index(link.to_node, link.to_socket, "INPUT"),
        "to_identifier": attr(link.to_socket, "identifier", ""),
        "is_valid": bool(attr(link, "is_valid", True)),
        "is_muted": bool(attr(link, "is_muted", False)),
        "multi_input_sort_id": attr(link, "multi_input_sort_id"),
    }


def walk_node_tree(tree, destination, key_prefix="", visited=None):
    if visited is None:
        visited = set()
    # Pointer prevents collisions for duplicated group names.
    try:
        token = tree.as_pointer()
    except Exception:
        token = id(tree)
    if token in visited:
        return
    visited.add(token)
    key = key_prefix + identifier(tree)
    nodes = list(tree.nodes)
    links = list(tree.links)
    destination[key] = {
        "name": tree.name,
        "type": attr(tree, "bl_idname"),
        "description": attr(tree, "description", ""),
        "interface": interface_info(tree),
        "nodes": [node_info(node) for node in nodes],
        "links": [link_info(link) for link in links],
        "node_count": len(nodes),
        "link_count": len(links),
        "node_types": dict(Counter(n.bl_idname for n in nodes)),
    }
    for node in nodes:
        nested = attr(node, "node_tree")
        if nested is not None:
            walk_node_tree(nested, destination, key_prefix, visited)


def modifier_inputs(mod):
    tree = attr(mod, "node_group")
    if tree is None:
        return []
    records = []
    for socket in interface_info(tree):
        if socket["item_type"] != "SOCKET" or socket.get("in_out") != "INPUT":
            continue
        name = socket.get("name", "")
        identifier_ = socket.get("identifier", "")
        value = {"name": name, "identifier": identifier_,
                 "socket_type": socket.get("socket_type"),
                 "interface_default": socket.get("default_value")}
        # Blender 5.2+ stores actual GN overrides in modifier.properties.inputs.
        modprops = attr(mod, "properties")
        inputprops = attr(modprops, "inputs")
        current = attr(inputprops, identifier_) if inputprops is not None else None
        if current is None and inputprops is not None:
            try:
                current = inputprops[identifier_]
            except Exception:
                pass
        if current is not None:
            value["storage"] = "Blender_5_2_RNA"
            for prop in ("value", "use_attribute", "attribute_name", "use_field",
                         "is_attribute"):
                try:
                    if hasattr(current, prop):
                        value[prop] = jsonify(getattr(current, prop))
                except Exception:
                    pass
        # Earlier Blender versions, and transitional versions.
        try:
            if identifier_ in mod:
                value["legacy_value"] = jsonify(mod[identifier_])
                if "value" not in value:
                    value["value"] = value["legacy_value"]
                    value["storage"] = "legacy_ID_property"
            for suffix in ("_use_attribute", "_attribute_name"):
                k = identifier_ + suffix
                if k in mod:
                    value[suffix[1:]] = jsonify(mod[k])
        except Exception:
            pass
        records.append(value)
    return records


def all_modifier_info(mod):
    data = {
        "name": mod.name,
        "type": mod.type,
        "show_viewport": bool(attr(mod, "show_viewport", True)),
        "show_render": bool(attr(mod, "show_render", True)),
        "show_in_editmode": bool(attr(mod, "show_in_editmode", False)),
        "settings": rna_scalars(mod),
    }
    if mod.type == "NODES":
        tree = attr(mod, "node_group")
        data["node_group"] = identifier(tree) if tree else None
        data["node_group_inputs"] = modifier_inputs(mod)
    return data


def mesh_capture(obj):
    """Source mesh topology only: no GN evaluation or forced realization."""
    if obj.type != "MESH" or obj.data is None:
        return None
    mesh = obj.data
    result = {
        "name": mesh.name,
        "statistics": {
            "vertices": len(mesh.vertices),
            "edges": len(mesh.edges),
            "faces": len(mesh.polygons),
            "corners": len(mesh.loops),
            "material_index_face_counts": dict(Counter(str(p.material_index) for p in mesh.polygons)),
        },
        "object_bbox_local": [jsonify(p) for p in obj.bound_box],
        "attributes": [],
        "vertex_group_names": [g.name for g in obj.vertex_groups],
    }
    for attribute in getattr(mesh, "attributes", []):
        record = {
            "name": attr(attribute, "name"),
            "domain": attr(attribute, "domain"),
            "data_type": attr(attribute, "data_type"),
            "length": len(attribute.data),
        }
        if record["name"] in ("position", "material_index", ".edge_verts", ".corner_vert", ".corner_edge"):
            result["attributes"].append(record)
            continue
        total = len(attribute.data)
        sample_size = total if total <= MAX_ATTRIBUTE_VALUES else min(MAX_ATTRIBUTE_SAMPLE, total)
        values = []
        for element in islice(attribute.data, sample_size):
            captured = None
            for prop in ("value", "vector", "color", "uv", "string", "byte_color"):
                if hasattr(element, prop):
                    captured = jsonify(attr(element, prop))
                    break
            values.append(captured)
        record["values"] = values
        record["is_complete"] = sample_size == total
        result["attributes"].append(record)
    n_verts = len(mesh.vertices)
    n_faces = len(mesh.polygons)
    total_corners = len(mesh.loops)
    complete = (n_verts <= MAX_FULL_MESH_VERTICES
                and n_faces <= MAX_FULL_MESH_FACES
                and total_corners <= MAX_TOTAL_FACE_CORNERS)
    result["complete_source_mesh_included"] = complete
    if complete:
        result["vertices_local"] = [jsonify(v.co) for v in mesh.vertices]
        result["faces"] = [
            {"vertex_indices": list(poly.vertices),
             "material_index": poly.material_index,
             "use_smooth": bool(poly.use_smooth)}
            for poly in mesh.polygons
        ]
        if obj.vertex_groups:
            result["vertex_group_assignments"] = [
                {"vertex": vertex.index,
                 "weights": [{"group_index": g.group, "weight": g.weight}
                             for g in vertex.groups]}
                for vertex in mesh.vertices if vertex.groups
            ]
    else:
        result["mesh_omission_reason"] = (
            "Source mesh too large; statistics and attributes retained, "
            "but complete vertex/face lists omitted. Supply .blend if exact "
            "large-mesh topology is needed."
        )
    return result


def object_info(obj):
    return {
        "name": obj.name,
        "type": obj.type,
        "data_name": attr(attr(obj, "data"), "name"),
        "parent": attr(attr(obj, "parent"), "name"),
        "location": jsonify(obj.location),
        "rotation_mode": obj.rotation_mode,
        "rotation_euler": jsonify(obj.rotation_euler),
        "rotation_quaternion": jsonify(obj.rotation_quaternion),
        "scale": jsonify(obj.scale),
        "dimensions": jsonify(obj.dimensions),
        "matrix_world": jsonify(obj.matrix_world),
        "matrix_local": jsonify(obj.matrix_local),
        "materials": [
            {"slot": i, "slot_name": slot.name,
             "material": attr(slot.material, "name")}
            for i, slot in enumerate(obj.material_slots)
        ],
        "custom_properties": read_safe_custom_props(obj),
        "modifiers_in_stack_order": [all_modifier_info(mod) for mod in obj.modifiers],
        "source_mesh": mesh_capture(obj),
    }


def read_safe_custom_props(obj):
    props = {}
    try:
        for key, value in obj.items():
            if key == "_RNA_UI":
                continue
            props[str(key)] = jsonify(value)
    except Exception:
        pass
    return props


def node_socket_id_defaults(node, cls):
    """Find referenced IDs stored in node sockets (Object Info, Set Material,
    Collection Info, Image Texture, etc.) as well as node properties.
    """
    for socket in node.inputs:
        try:
            value = socket.default_value
            if isinstance(value, cls):
                yield value
        except Exception:
            continue


def material_tree_references(selected):
    materials = {}
    for obj in selected:
        for slot in obj.material_slots:
            if slot.material:
                materials[slot.material.name] = slot.material
        for modifier in obj.modifiers:
            if modifier.type == "NODES" and modifier.node_group:
                todo = [modifier.node_group]
                visited = set()
                while todo:
                    tree = todo.pop()
                    try:
                        token = tree.as_pointer()
                    except Exception:
                        token = id(tree)
                    if token in visited:
                        continue
                    visited.add(token)
                    for node in tree.nodes:
                        material = attr(node, "material")
                        if material is not None:
                            materials[material.name] = material
                        for socket_mat in node_socket_id_defaults(node, bpy.types.Material):
                            materials[socket_mat.name] = socket_mat
                        if attr(node, "node_tree") is not None:
                            todo.append(node.node_tree)
                for setting in modifier_inputs(modifier):
                    val = setting.get("value")
                    if isinstance(val, dict) and val.get("datablock_type") == "Material":
                        material = bpy.data.materials.get(val.get("name", ""))
                        if material:
                            materials[material.name] = material
    return materials


def gather_referenced_objects(selected):
    references = {}
    for obj in selected:
        for mod in obj.modifiers:
            if mod.type != "NODES" or mod.node_group is None:
                continue
            todo, visited = [mod.node_group], set()
            while todo:
                tree = todo.pop()
                try:
                    token = tree.as_pointer()
                except Exception:
                    token = id(tree)
                if token in visited:
                    continue
                visited.add(token)
                for node in tree.nodes:
                    referenced = attr(node, "object")
                    if referenced and referenced.name not in references:
                        references[referenced.name] = referenced
                    for socket_object in node_socket_id_defaults(node, bpy.types.Object):
                        references[socket_object.name] = socket_object
                    sub = attr(node, "node_tree")
                    if sub:
                        todo.append(sub)
            for setting in modifier_inputs(mod):
                value = setting.get("value")
                if isinstance(value, dict) and value.get("datablock_type") == "Object":
                    referent = bpy.data.objects.get(value.get("name", ""))
                    if referent:
                        references[referent.name] = referent
    return {
        name: {
            "type": obj.type,
            "location": jsonify(obj.location),
            "rotation_euler": jsonify(obj.rotation_euler),
            "scale": jsonify(obj.scale),
            "dimensions": jsonify(obj.dimensions),
            "matrix_world": jsonify(obj.matrix_world),
        }
        for name, obj in references.items()
    }


def chosen_objects(context):
    """If the active selected object has GN, capture it alone. Otherwise capture
    selected GN objects. Makes accidental mass-exports less likely.
    """
    active = attr(attr(context, "view_layer"), "objects")
    active = attr(active, "active")
    if active is not None and any(
        m.type == "NODES" and m.node_group for m in active.modifiers
    ):
        return [active]
    return [obj for obj in context.selected_objects
            if any(m.type == "NODES" and m.node_group for m in obj.modifiers)]


def report_data(context, selected, include_materials=True):
    groups = {}
    shared_visited = set()
    for obj in selected:
        for mod in obj.modifiers:
            if mod.type == "NODES" and mod.node_group:
                walk_node_tree(mod.node_group, groups, visited=shared_visited)
    materials = material_tree_references(selected)
    mat_result = {}
    for idx, (name, mat) in enumerate(materials.items()):
        if idx >= MAX_SHADER_MATERIALS:
            break
        mat_result[name] = {
            "name": name,
            "use_nodes": bool(attr(mat, "use_nodes", False)),
            "diffuse_color": jsonify(attr(mat, "diffuse_color")),
            "node_tree": identifier(mat.node_tree) if attr(mat, "node_tree") else None,
        }
        if include_materials and attr(mat, "node_tree"):
            walk_node_tree(mat.node_tree, groups, "MATERIAL::", shared_visited)
    object_records = [object_info(obj) for obj in selected]
    data = {
        "format": FORMAT,
        "exported_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "blender_version": bpy.app.version_string,
        "blend_file": bpy.data.filepath or "<unsaved>",
        "scene": attr(context.scene, "name", ""),
        "active_object": attr(attr(context.view_layer.objects, "active"), "name"),
        "selected_object_names": [o.name for o in context.selected_objects],
        "captured_objects": object_records,
        "referenced_objects": gather_referenced_objects(selected),
        "materials": mat_result,
        "node_trees": groups,
        "summary": {
            "objects": len(selected),
            "gn_modifiers": sum(
                bool(mod.node_group) for obj in selected
                for mod in obj.modifiers if mod.type == "NODES"
            ),
            "node_trees": len(groups),
            "nodes": sum(group["node_count"] for group in groups.values()),
            "links": sum(group["link_count"] for group in groups.values()),
            "full_meshes": sum(
                bool(obj["source_mesh"] and obj["source_mesh"].get("complete_source_mesh_included"))
                for obj in object_records
            ),
        },
        "limitations": [
            "This captures configured procedural definitions and original source mesh, not the .blend file.",
            "Evaluated GN output/visual viewport appearance is not baked. Include a screenshot for visual issues.",
            "Complex simulation cache, packed textures, external addons, and linked libraries are not embedded.",
            "A JSON alone cannot safely recreate every Blender node type; the original .blend may be needed for difficult edits.",
        ],
    }
    return data


def format_plain(value, max_length=220):
    try:
        s = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    except Exception:
        s = str(value)
    return s if len(s) < max_length else s[:max_length] + " ..."


def text_report(data):
    summary = data["summary"]
    lines = [
        "MW | GEOMETRY NODES CAPTURE",
        "=" * 72,
        "Blender: " + data["blender_version"],
        "Blend: " + data["blend_file"],
        "Objects: " + ", ".join(o["name"] for o in data["captured_objects"]),
        "Summary: {objects} object(s), {gn_modifiers} GN modifier(s), {node_trees} tree(s), "
        "{nodes} nodes, {links} links".format(**summary),
        "",
        "CAPTURED OBJECTS & MODIFIERS",
        "-" * 72,
    ]
    for obj in data["captured_objects"]:
        lines += ["", "OBJECT " + obj["name"],
                  "  transform: " + format_plain({
                      "location": obj["location"], "rotation_euler": obj["rotation_euler"],
                      "scale": obj["scale"], "dimensions": obj["dimensions"]}),
                  "  mesh: " + format_plain(
                      obj["source_mesh"]["statistics"] if obj["source_mesh"] else None),
                  "  materials: " + format_plain(obj["materials"], 420)]
        for mod in obj["modifiers_in_stack_order"]:
            lines.append("  MODIFIER {name} [{type}] -> {node_group}".format(
                name=mod["name"], type=mod["type"], node_group=mod.get("node_group", "")))
            for setting in mod.get("node_group_inputs", []):
                lines.append("    {name} [{identifier}] = {value}".format(
                    name=setting["name"], identifier=setting["identifier"],
                    value=format_plain(setting.get("value", setting.get("interface_default")))))
    for name, group in data["node_trees"].items():
        lines += ["", "", "NODE TREE " + name, "-" * 72,
                  "nodes: %s | links: %s" % (group["node_count"], group["link_count"]),
                  "INTERFACE:"]
        for entry in group["interface"]:
            lines.append("  " + format_plain(entry, 600))
        incoming = {}
        for link in group["links"]:
            incoming.setdefault((link["to_node"], link["to_socket_index"]), []).append(link)
        lines.append("NODES:")
        for node in group["nodes"]:
            lines.append("  [%s] %s (%s)" % (node["name"], node["bl_idname"], node["label"]))
            if node.get("nested_node_tree"):
                lines.append("    nested group: " + node["nested_node_tree"])
            if node["settings"]:
                lines.append("    settings: " + format_plain(node["settings"], 800))
            if node["special_settings"]:
                lines.append("    special: " + format_plain(node["special_settings"], 800))
            for sock in node["inputs"]:
                sources = incoming.get((node["name"], sock["index"]), [])
                incoming_description = (
                    " | ".join("%s.%s#%s" %
                             (link["from_node"], link["from_socket"], link["from_socket_index"])
                             for link in sources)
                    if sources else "default=" + format_plain(sock.get("default_value"))
                )
                lines.append("    IN  #%d %s -> %s" %
                             (sock["index"], sock["name"], incoming_description))
        lines.append("LINKS:")
        for link in group["links"]:
            lines.append("  {from_node}.{from_socket}#{from_socket_index} -> "
                         "{to_node}.{to_socket}#{to_socket_index}".format(**link))
    return "\n".join(lines) + "\n"


def downloads_directory():
    path = Path.home() / "Downloads"
    if not path.is_dir():
        raise RuntimeError("Could not locate ~/Downloads. Create that folder or edit downloads_directory().")
    return path


def export_capture(context, include_materials=True):
    objects = chosen_objects(context)
    if not objects:
        raise RuntimeError("Select an object with a Geometry Nodes modifier. "
                           "If it is instanced, select the source object that owns the modifier.")
    data = report_data(context, objects, include_materials)
    name = safe_filename(objects[0].name)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output = downloads_directory() / ("GN_CAPTURE_" + name + "_" + stamp + ".zip")
    readme = (
        "MW | GEOMETRY NODES CAPTURE\n"
        "===========================\n\n"
        "Upload this ZIP to ChatGPT when asking for a Geometry Nodes fix.\n"
        "It contains graph.json (machine-readable, full node graph) and\n"
        "overview.txt (readable connection map).\n\n"
        "READ-ONLY: no scene changes, no geometry evaluation, no render.\n"
        "Captured: selected object's geometry nodes, nested groups, modifier\n"
        "settings, original mesh if under size limit, referenced objects,\n"
        "assigned materials, material node graph when enabled.\n\n"
        "Does NOT contain textures, full blend file, plugin code, simulations,\n"
        "or a rendered preview. Include a screenshot if geometry looks wrong.\n"
        "Local file paths, object names and node labels may be in the JSON.\n"
        "Review before sharing if privacy is important.\n"
    )
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED,
                         compresslevel=6) as archive:
        archive.writestr("graph.json", json.dumps(data, indent=2, ensure_ascii=False,
                                                  allow_nan=False) + "\n")
        archive.writestr("overview.txt", text_report(data))
        archive.writestr("README.txt", readme)
    try:
        context.window_manager.clipboard = str(output)
    except Exception:
        pass
    print("\n[MW GN Capture] Exported:", output)
    print("[MW GN Capture] Summary:", data["summary"])
    print("[MW GN Capture] Upload this ZIP to ChatGPT with your screenshot and fix request.")
    return output, data


class MW_OT_export_gn_capture(bpy.types.Operator):
    bl_idname = "mw.export_gn_capture"
    bl_label = "MW Export GN Capture"
    bl_description = "Export selected object's Geometry Nodes diagnostic ZIP to Downloads"
    bl_options = {"REGISTER"}

    include_materials: BoolProperty(
        name="Include Material Nodes",
        description="Also export material/shader node trees",
        default=True,
    )

    def execute(self, context):
        try:
            path, data = export_capture(context, self.include_materials)
            # Store last export for display in sidebar. No scene data changes.
            try:
                context.window_manager.mw_gn_capture_last_export = str(path)
            except Exception:
                pass
            self.report({"INFO"}, "GN Capture saved in Downloads: " + path.name)
            return {"FINISHED"}
        except Exception as exc:
            self.report({"ERROR"}, "GN Capture failed: " + str(exc))
            traceback.print_exc()
            return {"CANCELLED"}


class MW_PT_gn_capture(bpy.types.Panel):
    bl_label = "GN Capture"
    bl_idname = "MW_PT_gn_capture"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "GN Capture"

    def draw(self, context):
        layout = self.layout
        # Intentionally avoid custom/icon identifiers: an invalid Blender icon
        # breaks the panel draw and leaves a blank N-panel without explanation.
        layout.label(text="Export Geometry Nodes")

        objects = chosen_objects(context)
        if objects:
            object_name = objects[0].name
            count = sum(1 for obj in objects for mod in obj.modifiers
                        if mod.type == "NODES" and mod.node_group is not None)
            info = layout.box()
            info.label(text="Object: " + object_name[:45])
            info.label(text="GN modifiers: " + str(count))
        else:
            warning = layout.box()
            warning.label(text="Select an object with GN")
            warning.label(text="Then click Export below")

        wm = context.window_manager
        layout.separator()
        layout.prop(wm, "mw_gn_capture_include_materials", text="Include material nodes")
        row = layout.row()
        row.enabled = bool(objects)
        op = row.operator("mw.export_gn_capture", text="Export ZIP to Downloads")
        op.include_materials = wm.mw_gn_capture_include_materials

        open_row = layout.row()
        open_op = open_row.operator("wm.path_open", text="Open Downloads folder")
        open_op.filepath = str(Path.home() / "Downloads")

        last_export = wm.mw_gn_capture_last_export
        if last_export:
            layout.separator()
            layout.label(text="Last export:")
            layout.label(text=Path(last_export).name[:42])
            layout.label(text="Full path copied to clipboard")
        else:
            layout.label(text="Exports graph.json + overview.txt")


CLASSES = (MW_OT_export_gn_capture, MW_PT_gn_capture)


def register():
    # Support repeated Text Editor runs without duplicate registered panels.
    for cls in reversed(CLASSES):
        existing = getattr(bpy.types, cls.__name__, None)
        if existing is not None:
            try:
                bpy.utils.unregister_class(existing)
            except Exception:
                pass

    # Clean up properties from earlier runs, then register the new controls.
    for key in ("mw_gn_capture_include_materials", "mw_gn_capture_last_export"):
        if hasattr(bpy.types.WindowManager, key):
            try:
                delattr(bpy.types.WindowManager, key)
            except Exception:
                pass

    bpy.types.WindowManager.mw_gn_capture_include_materials = BoolProperty(
        name="Include material nodes", default=True,
        description="Capture materials and shaders referenced by the Geometry Nodes setup",
    )
    bpy.types.WindowManager.mw_gn_capture_last_export = StringProperty(
        name="Last GN Capture", default="", options={"SKIP_SAVE"},
    )
    try:
        for cls in CLASSES:
            bpy.utils.register_class(cls)
    except Exception:
        unregister()
        raise


def unregister():
    for cls in reversed(CLASSES):
        existing = getattr(bpy.types, cls.__name__, None)
        if existing is not None:
            try:
                bpy.utils.unregister_class(existing)
            except Exception:
                pass
    for key in ("mw_gn_capture_include_materials", "mw_gn_capture_last_export"):
        if hasattr(bpy.types.WindowManager, key):
            try:
                delattr(bpy.types.WindowManager, key)
            except Exception:
                pass


if __name__ == "__main__":
    register()
    try:
        path, _report = export_capture(bpy.context)
        def _popup(self, context):
            self.layout.label(text="Saved in Downloads: " + path.name[:75])
            self.layout.label(text="ZIP path copied to clipboard. Upload the ZIP to ChatGPT.")
        try:
            bpy.context.window_manager.popup_menu(_popup, title="GN Capture Complete", icon="CHECKMARK")
        except Exception:
            pass
    except Exception as error:
        traceback.print_exc()
        try:
            def _error_popup(self, context):
                self.layout.label(text=str(error)[:120])
            bpy.context.window_manager.popup_menu(_error_popup, title="GN Capture Error", icon="ERROR")
        except Exception:
            pass
        raise
