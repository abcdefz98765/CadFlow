"""FreeCAD path discovery — find FreeCAD installation and its Python path."""

import os
import shutil
import sys
from pathlib import Path


def find_freecad_paths() -> dict | None:
    """Locate FreeCAD installation and return its Python/lib paths.

    Returns a dict with keys: 'python_exe', 'freecad_lib', 'freecad_exe'
    Returns None if FreeCAD is not found.
    """
    search_roots = []

    env_home = os.environ.get("FREECAD_HOME")
    if env_home:
        search_roots.append(Path(env_home))

    for command in ("FreeCADCmd.exe", "freecadcmd.exe", "freecadcmd", "FreeCAD.exe", "freecad"):
        exe_path = shutil.which(command)
        if exe_path:
            exe = Path(exe_path)
            root = exe.parent.parent if exe.parent.name.lower() == "bin" else exe.parent
            return {
                "python_exe": None,
                "freecad_lib": str(root),
                "freecad_exe": str(exe),
                "importable": False,
            }

    search_roots.extend([
        "C:/Program Files/FreeCAD",
        "C:/Program Files/FreeCAD 1.0",
        "C:/Program Files (x86)/FreeCAD",
        Path.home() / "AppData/Local/Programs/FreeCAD",
        "/usr/lib/freecad",
        "/usr/share/freecad",
        "/Applications/FreeCAD.app",
    ])

    # Check if already importable (running inside FreeCAD's Python)
    try:
        import FreeCAD
        return {
            "python_exe": sys.executable,
            "freecad_lib": str(Path(FreeCAD.__file__).parent),
            "freecad_exe": None,
            "importable": True,
        }
    except ImportError:
        pass

    # Check known install paths
    for root in search_roots:
        root = Path(root)
        if not root.exists():
            continue

        # Find FreeCAD lib directory
        for pattern in ["Ext", "lib", "Mod"]:
            lib_dir = root / pattern
            if lib_dir.exists():
                # Find FreeCAD executable
                exe_candidates = [
                    root / "bin" / "FreeCADCmd.exe",
                    root / "bin" / "freecadcmd.exe",
                    root / "bin" / "freecad.exe",
                    root / "bin" / "freecad",
                    root / "bin" / "FreeCAD.exe",
                    root / "FreeCAD.exe",
                ]
                for exe in exe_candidates:
                    if exe.exists():
                        return {
                            "python_exe": None,  # Use freecad's bundled python
                            "freecad_lib": str(root),
                            "freecad_exe": str(exe),
                            "importable": False,
                        }

    return None


def add_freecad_to_path(freecad_paths: dict):
    """Add FreeCAD lib paths to sys.path so FreeCAD modules can be imported."""
    if freecad_paths is None:
        raise RuntimeError("FreeCAD not found. Install FreeCAD 1.0+ from https://www.freecad.org")

    if freecad_paths.get("importable"):
        return  # Already importable

    lib_root = Path(freecad_paths["freecad_lib"])
    paths_to_add = [
        str(lib_root / "bin"),
        str(lib_root / "lib"),
        str(lib_root / "Ext"),
        str(lib_root / "Mod"),
        str(lib_root),
    ]

    for p in paths_to_add:
        if Path(p).exists() and p not in sys.path:
            sys.path.insert(0, p)
