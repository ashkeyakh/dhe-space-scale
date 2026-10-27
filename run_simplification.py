"""PyCharm launcher: simplify 2001 with automatically coupled neighbours."""
from pathlib import Path
import json
import webbrowser

from extrude import construct,load_shapefile
from viewer import make_view
from dhe_ops import Generalizer
from run_in_pycharm import INPUT_SHP,POLYGON_IDS,ID_FIELD,HEIGHT

FEATURE_TO_SIMPLIFY='2001'
TOLERANCE_M=2.5
OUTPUT=Path(__file__).resolve().parent/'output'/'simplification_2001.html'


def run(open_browser=True):
    polygons,ids,metadata=load_shapefile(INPUT_SHP,[str(i) for i in POLYGON_IDS],ID_FIELD)
    original=construct(polygons,ids,HEIGHT)
    generalizer=Generalizer(original)
    result=generalizer.simplify(FEATURE_TO_SIMPLIFY,TOLERANCE_M)
    payload=generalizer.transition_payload()
    data=original.to_dict()
    data['generalization']=payload
    class ModelWithTransition:
        def to_dict(self):return data
    make_view(ModelWithTransition(),metadata,OUTPUT)
    result_data=result.to_dict();result_data['metadata']=metadata
    OUTPUT.with_suffix('.dhe.json').write_text(json.dumps(result_data,indent=2),encoding='utf-8')
    OUTPUT.with_suffix('.events.json').write_text(json.dumps(payload),encoding='utf-8')
    print(json.dumps(dict(output=str(OUTPUT),events=len(generalizer.events),tolerance_m=TOLERANCE_M,
        before_boundary_vertices=len(next(f for f in original.faces if f['cell']==1 and f['kind']=='roof')['rings'][0]),
        after_boundary_vertices=len(next(f for f in result.faces if f['cell']==1 and f['kind']=='roof')['rings'][0]),
        neighbours_changed=sorted({result.cells[c]['feature_id'] for e in generalizer.events for c in e.affected_cells
                                   if str(result.cells[c]['feature_id'])!=FEATURE_TO_SIMPLIFY})),indent=2))
    if open_browser:webbrowser.open(OUTPUT.as_uri(),new=2)
    return generalizer


if __name__=='__main__':run()
