"""Inputs for the interactive transition-region workbench."""
from pathlib import Path
import json
import os

_local_path=Path(__file__).resolve().parent/'workbench.local.json'
_local=json.loads(_local_path.read_text(encoding='utf-8')) if _local_path.exists() else {}
INPUT_SHP=os.environ.get('DHE_INPUT_SHP',_local.get('input_shp',''))
ID_FIELD='osm_id'
FEATURE_IDS=[20,2001,2002,8,9,17,18,21,1123,3000,3001,3002,3003,3004]
SOURCE_Z=10.0
TARGET_Z=0.0
OUTPUT_DIR=Path(__file__).resolve().parent/'output'/'workbench'
