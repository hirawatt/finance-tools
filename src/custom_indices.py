import pandas as pd
import os

index_path = os.getcwd() + "/indices/"

def custom_indices() -> list:
    """Get List of Custom Indices from folder"""
    # Import Custom Indices
    indices_list = os.listdir(index_path)
    return indices_list