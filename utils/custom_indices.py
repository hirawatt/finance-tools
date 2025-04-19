import os
from pathlib import Path

INDEX_PATH = Path(os.getcwd()) / "indices"

def custom_indices() -> list:
    """Get List of Custom Indices from folder"""
    # Import Custom Indices
    indices_list = os.listdir(INDEX_PATH)
    li = [x.split('.')[0] for x in indices_list]
    return li