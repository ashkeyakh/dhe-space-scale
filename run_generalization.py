"""PyCharm entry point for all five space-scale operation demonstrations."""
from pathlib import Path
import json
import webbrowser

from extrude import construct,load_shapefile
from viewer import make_view
from run_in_pycharm import INPUT_SHP,POLYGON_IDS,ID_FIELD
from space_scale import simplify_space_scale,merge_space_scale,collapse_space_scale,aggregate_space_scale

SCALE_END=10
OUTPUT=Path(__file__).resolve().parent/'output'/'space_scale_generalization.html'


def run(open_browser=True):
    ps,ids,source_metadata=load_shapefile(INPUT_SHP,[str(i) for i in POLYGON_IDS],ID_FIELD)
    source=construct(ps,ids)
    tasks=[('Simplification · 2001',lambda:simplify_space_scale(source,'2001',2.5,SCALE_END)),
        ('Merging · 2001 + 2002',lambda:merge_space_scale(source,['2001','2002'],5,SCALE_END)),
        ('Collapse to polyline · 2001',lambda:collapse_space_scale(source,'2001',1,'2002',9,SCALE_END)),
        ('Collapse to point · 2001',lambda:collapse_space_scale(source,'2001',0,'2002',9,SCALE_END)),
        ('Aggregation · touching features',lambda:aggregate_space_scale(source,['2001','2002'],5,SCALE_END))]
    operations=[]
    for label,build in tasks:
        model,description=build()
        metadata=dict(source_metadata,space_scale=description,
            z_dimension='scale parameter',volume_units='m2 * scale',source_z='ignored; Z now represents scale')
        data=model.to_dict();data['metadata']=metadata
        operations.append(dict(label=label,model=data))
        target=OUTPUT.with_name(description['operation']+'.ssc.dhe.json')
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_text(json.dumps(data,indent=2),encoding='utf-8')
        print(f'{description["operation"]}: {len(model.cells)-1} cells, {len(model.faces)} polygon/transition faces; validated')
    root=dict(operations[0]['model']);root['operation_models']=operations
    class AllOperations:
        def to_dict(self):return root
    make_view(AllOperations(),operations[0]['model']['metadata'],OUTPUT)
    print(OUTPUT)
    if open_browser:webbrowser.open(OUTPUT.as_uri(),new=2)
    return operations


if __name__=='__main__':run()
