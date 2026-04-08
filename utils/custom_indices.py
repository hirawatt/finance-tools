import os
from pathlib import Path
from typing import Optional

INDEX_PATH = (Path(os.getcwd()) / "indices").resolve()

def get_safe_path(index_file: str) -> Optional[Path]:
    """Get a safe path within INDEX_PATH, preventing traversal"""
    try:
        # Construct the requested path and resolve it
        safe_path = (INDEX_PATH / f"{index_file}.csv").resolve()

        # Check if the resolved path starts with INDEX_PATH
        if INDEX_PATH in safe_path.parents:
            return safe_path
        return None
    except (OSError, ValueError):
        return None

def custom_indices() -> list:
    """Get List of Custom Indices from folder"""
    # Import Custom Indices
    indices_list = os.listdir(INDEX_PATH)
    li = [x.split('.')[0] for x in indices_list]
    return li