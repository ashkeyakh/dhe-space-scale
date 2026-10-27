"""Package the interactive viewer and complete topology into offline HTML."""
import json
from html import escape
from pathlib import Path


def make_view(model, metadata, output):
    from plotly.offline import get_plotlyjs
    root = Path(__file__).parent
    data = model.to_dict()
    data['metadata'] = metadata
    # Inline JSON cannot terminate its containing script, even with arbitrary IDs.
    payload = json.dumps(data, ensure_ascii=True).replace('<', '\\u003c')
    replacements = {
        '__MODEL__': payload,
        '__PLOTLY__': get_plotlyjs(),
        '__GEOMETRY__': (root / 'dhe_geometry.js').read_text(encoding='utf-8'),
        '__VIEWER__': (root / 'viewer.js').read_text(encoding='utf-8'),
        '__WORKBENCH__': (root / 'workbench.js').read_text(encoding='utf-8'),
        '__IDS__': escape(', '.join(map(str, metadata['selected_ids']))),
        '__SOURCE__': escape(Path(metadata['source']).name),
    }
    html = (root / 'viewer.html').read_text(encoding='utf-8')
    # Replace placeholders in a single pass; do not reprocess injected content.
    import re
    html = re.sub('|'.join(re.escape(k) for k in replacements), lambda m: replacements[m[0]], html)
    output.write_text(html, encoding='utf-8')
