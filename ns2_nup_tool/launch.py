"""Optional replacement of base content with an update's NUP v1 trees."""

from pathlib import Path

from nup_core import format as F, meta as M
from nup_core.discover import DirObj, FileObj

# The format reserves 0x8000..0xFFFF for tool-private metadata. Loaders skip
# this marker; it lets our update workflow maintain an already-promoted view.
LAUNCH_POLICY_TAG = 0x8000
LEGACY_LAUNCH_POLICY_VALUE = b"NS2NUPTool:prefer-update-exefs:v1"
LAUNCH_POLICY_VALUE = b"NS2NUPTool:replace-base-content:v2"


def launch_plan(packages):
    bases = [p for p in packages if p.kind == F.KIND_BASE]
    candidates = [p for p in packages if p.kind == F.KIND_UPDATE
                  and (Path(p.src) / "exefs/main").is_file()
                  and (Path(p.src) / "exefs/main").stat().st_size > 0]
    result = {"available": False, "detected": len(candidates), "reason": "No update main executable was found."}
    if not candidates:
        return result
    newest = max(p.version for p in candidates)
    selected = [p for p in candidates if p.version == newest]
    if len(bases) != 1 or not bases[0].title_id:
        result["reason"] = "A base package with a known title ID is required to replace its content with an update."
    elif len(selected) != 1:
        result["reason"] = "Multiple updates with main have the same version; select an unambiguous update layout."
    elif selected[0].title_id != bases[0].title_id:
        result["reason"] = "The update main belongs to a different or unknown title ID."
    else:
        update = selected[0]
        result.update(available=True, reason="", version=update.version,
                      source=update.src, main=str(Path(update.src) / "exefs/main"),
                      build_id=update.build_id.hex().upper() if update.build_id else "",
                      has_romfs=(Path(update.src) / "romfs").is_dir(),
                      base_index=packages.index(bases[0]), update_index=packages.index(update))
    return result


def child_directory(root, name):
    return next((child for child in root.children if isinstance(child, DirObj) and child.name == name), None)


def overlay_directory(base, incoming, clone):
    """Apply update path shadowing without sharing mutable TOC nodes."""
    children = {child.name: child for child in base.children}
    for child in incoming.children:
        previous = children.get(child.name)
        if isinstance(child, DirObj) and isinstance(previous, DirObj):
            overlay_directory(previous, child, clone)
        else:
            children[child.name] = clone(child)
    base.children = sorted(children.values(), key=lambda child: child.name)


def clone_source_node(node):
    if isinstance(node, FileObj):
        return FileObj(node.name, node.src_path)
    result = DirObj(node.name)
    result.children = [clone_source_node(child) for child in node.children]
    return result


def replace_base_content(base, incoming, clone):
    """Use only the update's content folders; no original base paths survive."""
    base.children = [clone(child) for child in incoming.children
                     if isinstance(child, DirObj) and child.name in (b"exefs", b"romfs")]


def replace_base_from_update(packages):
    plan = launch_plan(packages)
    if not plan["available"]:
        raise ValueError(plan["reason"])
    base, update = packages[plan["base_index"]], packages[plan["update_index"]]
    base.launch_content = update.src
    base.build_id = update.build_id
    base.npdm = update.npdm
    return plan


def has_launch_policy(metadata):
    return metadata.get(LAUNCH_POLICY_TAG) in (LAUNCH_POLICY_VALUE, LEGACY_LAUNCH_POLICY_VALUE)


def replaces_base_content(metadata):
    return metadata.get(LAUNCH_POLICY_TAG) == LAUNCH_POLICY_VALUE


def mark_launch_policy(block):
    metadata = M.parse_block(block)
    existing = metadata.get(LAUNCH_POLICY_TAG)
    if existing is not None and existing not in (LAUNCH_POLICY_VALUE, LEGACY_LAUNCH_POLICY_VALUE):
        raise ValueError("The NUP already uses this private metadata tag for another tool.")
    metadata[LAUNCH_POLICY_TAG] = LAUNCH_POLICY_VALUE
    return M.serialize_block(metadata)
