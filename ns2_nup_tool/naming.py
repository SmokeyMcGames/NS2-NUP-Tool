"""Windows-safe default names for newly created containers."""

import re


def nup_filename(title, title_id=""):
    title_id = title_id.strip().upper()
    known_id = bool(re.fullmatch(r"[0-9A-F]{16}", title_id) and int(title_id, 16))
    name = title.strip()
    if known_id:
        name = re.sub(r"\s*\[[0-9A-Fa-f]{16}\]\s*$", "", name)
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).rstrip(" .")
    name = name[:180].rstrip(" .") or "Game"
    if known_id:
        name += f" [{title_id}]"
    if re.fullmatch(r"CON|PRN|AUX|NUL|COM[1-9¹²³]|LPT[1-9¹²³]", name.split(".")[0], re.IGNORECASE):
        name = "_" + name
    return name + ".nup"
