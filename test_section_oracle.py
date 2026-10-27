"""Compare JS sections against independent 2D Shapely footprint intersections."""
import json
import math
from pathlib import Path
import random
import subprocess
import unittest

from extrude import construct, Polygon
from shapely.geometry import LineString
from shapely.ops import unary_union


class SectionOracleTests(unittest.TestCase):
    def test_arbitrary_planes_against_footprint_geometry(self):
        fixture=Path('output/extrusion_2001_2002.dhe.json')
        actual = json.loads(fixture.read_text()) if fixture.exists() else construct([
            Polygon([(0,0),(4,0),(4,4),(0,4)]),
            Polygon([(4,0),(8,0),(8,4),(4,4)])],['2001','2002']).to_dict()
        courtyard = Polygon([(0,0),(8,0),(8,8),(0,8)], [[(2,2),(2,6),(6,6),(6,2)]])
        concave = Polygon([(12,0),(18,0),(18,2),(14,2),(14,8),(12,8)])
        models = [actual, construct([courtyard, concave], ['hole', 'concave']).to_dict()]
        rng = random.Random(419)
        for model in models:
            cases = [dict(kind='vertical', position=p, tilt=90, azimuth=a)
                     for a in (0,35,90,160,230) for p in (-2,0,2)]
            cases += [dict(kind='inclined', position=rng.uniform(-4,4),
                           tilt=rng.uniform(2,88), azimuth=rng.uniform(0,360)) for _ in range(30)]
            js = """
const fs=require('node:fs'),G=require('./dhe_geometry.js');
const {model,cases}=JSON.parse(fs.readFileSync(0,'utf8'));
const out=cases.map(c=>{const p=G.makePlane(model.vertices,c.kind,c.position,c.tilt,c.azimuth);
 const s=G.sliceModel(model,model.vertices,p);return {plane:p,area:s.area,open:s.cells.reduce((n,c)=>n+c.open.length,0)};});
process.stdout.write(JSON.stringify(out));
"""
            reply = subprocess.run(['node', '-e', js], input=json.dumps(dict(model=model, cases=cases)),
                                   text=True, capture_output=True, check=True)
            results = json.loads(reply.stdout)
            footprints=[]
            for cell in model['dual_vertices'][1:]:
                footprints.append(unary_union([Polygon([model['vertices'][v][:2] for v in f.get('rings', [f['vertices']])[0]],
                    [[model['vertices'][v][:2] for v in r] for r in f.get('rings', [f['vertices']])[1:]])
                    for f in model['faces'] if f['cell']==cell['id'] and f['kind']=='roof']))
            for case,result in zip(cases,results):
                plane=result['plane'];nx,ny,nz=plane['normal'];ox,oy,oz=plane['origin']
                horizontal_length=math.hypot(nx,ny)
                ux,uy=nx/horizontal_length,ny/horizontal_length
                vx,vy=-uy,ux
                def xy(t,s):
                    return (ox+ux*t+vx*s,oy+uy*t+vy*s)
                expected=0.0
                for cell,footprint in zip(model['dual_vertices'][1:],footprints):
                    if abs(nz)<1e-10:
                        expected += footprint.intersection(LineString([xy(0,-10000),xy(0,10000)])).length*cell['height_m']
                    else:
                        lo=nz*(oz-cell['height_m'])/horizontal_length
                        hi=nz*oz/horizontal_length
                        strip=Polygon([xy(lo,-10000),xy(hi,-10000),xy(hi,10000),xy(lo,10000)])
                        expected += footprint.intersection(strip).area/abs(nz)
                with self.subTest(case=case):
                    self.assertAlmostEqual(result['area'],expected,delta=2e-5)
                    self.assertEqual(result['open'],0)


if __name__ == '__main__':
    unittest.main()
