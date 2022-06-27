import pandas as pd
import os

index_path = os.getcwd() + "/indices/"

def custom_indices() -> list:
    """Get List of Custom Indices from folder"""
    # Import Custom Indices
    indices_list = os.listdir(index_path)
    li = [x.split('.')[0] for x in indices_list]
    return li