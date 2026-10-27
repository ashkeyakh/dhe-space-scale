"""Right-click this file in PyCharm and choose Run. No parameters required."""
from pathlib import Path
import webbrowser

from extrude import main
from workbench_config import INPUT_SHP


# Edit these values to choose a different input, selection, or height.
POLYGON_IDS = [2001, 2002]
ID_FIELD = 'osm_id'
HEIGHT = 10
OUTPUT = Path(__file__).resolve().parent / 'output' / 'extrusion_2001_2002.html'


def run(open_browser=True):
    if not INPUT_SHP:raise ValueError('Configure DHE_INPUT_SHP or workbench.local.json, or run run_demo.py without external data.')
    main([
        '--input', INPUT_SHP,
        '--ids', *map(str, POLYGON_IDS),
        '--id-field', ID_FIELD,
        '--height', str(HEIGHT),
        '--output', str(OUTPUT),
    ])
    if open_browser:
        webbrowser.open(OUTPUT.as_uri(), new=2)


if __name__ == '__main__':
    run()
