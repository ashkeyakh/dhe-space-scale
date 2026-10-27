import json
from pathlib import Path
import subprocess
import unittest

from extrude import construct,Polygon,load_shapefile
from space_scale import simplify_space_scale,merge_space_scale,collapse_space_scale,aggregate_space_scale
from shapely.ops import unary_union
from workbench_config import INPUT_SHP


def slices(model,levels):
    js="""
const G=require('./dhe_geometry.js'),fs=require('node:fs');const {model,levels}=JSON.parse(fs.readFileSync(0,'utf8'));
const out=levels.map(z=>{const s=G.sliceModel(model,model.vertices,G.makePlane(model.vertices,'horizontal',z));return {z,area:s.area,cells:s.cells.map(c=>({id:c.feature_id,area:c.area,open:c.open.length,points:c.points.length,loops:c.loops.length,segments:c.segments.length}))};});
process.stdout.write(JSON.stringify(out));
"""
    r=subprocess.run(['node','-e',js],input=json.dumps(dict(model=model.to_dict(),levels=levels)),capture_output=True,text=True,check=True)
    return json.loads(r.stdout)


class SpaceScaleTests(unittest.TestCase):
    def model(self):
        return construct([Polygon([(0,0),(4,0),(4,4),(0,4)]),Polygon([(4,0),(8,0),(8,4),(4,4)]),
                          Polygon([(0,4),(4,4),(4,8),(0,8)])],['source','recipient','north'])

    def check_coverage(self,model,area,levels):
        result=slices(model,levels)
        for s in result:
            with self.subTest(z=s['z']):self.assertAlmostEqual(s['area'],area,delta=5e-5)
        return result

    def test_merge_and_touching_aggregation(self):
        original=self.model()
        for build in (merge_space_scale,aggregate_space_scale):
            m,info=build(original,['source','recipient'])
            m.validate()
            self.assertEqual(len(m.cells)-1,4)
            result=self.check_coverage(m,48,[0,2.5,4.999,5,5.001,7.5,10])
            self.assertEqual(len([c for c in result[0]['cells'] if c['area']>1e-6]),3)
            self.assertEqual(len([c for c in result[-1]['cells'] if c['area']>1e-6]),2)

    def test_line_point_and_other_neighbour_resewing(self):
        original=self.model()
        for dimension in (0,1):
            m,info=collapse_space_scale(original,'source',dimension,'recipient')
            m.validate()
            result=self.check_coverage(m,48,[0,1,3,5,7,8.9,9,9.1,10])
            terminal=next(c for c in result[-3]['cells'] if c['id']=='source')
            self.assertAlmostEqual(terminal['area'],0,delta=1e-6)
            if dimension==0:self.assertEqual(terminal['points'],1)
            else:self.assertGreater(terminal['segments'],0)
            self.assertFalse(any(c['id']=='source' for c in result[-1]['cells']))
            self.assertTrue(any(c['id']=='north' and abs(c['area']-16)<1e-6 for c in result[-1]['cells']))
            self.assertAlmostEqual(sum(c['volume_m3'] for c in m.cells[1:]),480,delta=1e-4)

    def test_hole_preservation_in_collapse(self):
        p=Polygon([(0,0),(6,0),(6,6),(0,6)], [[(2,2),(2,4),(4,4),(4,2)]])
        q=Polygon([(6,0),(10,0),(10,6),(6,6)])
        original=construct([p,q],['source','recipient'])
        for dimension in (0,1):
            m,_=collapse_space_scale(original,'source',dimension,'recipient')
            self.check_coverage(m,56,[0,2,5,8,9,10])

    def test_disconnected_aggregation_is_rejected(self):
        m=construct([Polygon([(0,0),(1,0),(1,1),(0,1)]),Polygon([(5,0),(6,0),(6,1),(5,1)])],['a','b'])
        with self.assertRaisesRegex(ValueError,'touching'):aggregate_space_scale(m,['a','b'])

    def test_actual_all_five_operations(self):
        path=Path(INPUT_SHP)
        if not INPUT_SHP or not path.exists():self.skipTest('User data absent')
        ps,ids,_=load_shapefile(path,['2001','2002'],'osm_id');original=construct(ps,ids)
        area=sum(p.area for p in ps)
        operations=[simplify_space_scale(original),merge_space_scale(original,['2001','2002']),
            aggregate_space_scale(original,['2001','2002']),collapse_space_scale(original,dimension=0),collapse_space_scale(original,dimension=1)]
        for m,info in operations:
            m.validate()
            with self.subTest(operation=info['operation']):
                self.check_coverage(m,area,[0,0.7,2.2,4.9,5,5.1,7.5,8.99,9,9.1,10])
                self.assertAlmostEqual(sum(c['volume_m3'] for c in m.cells[1:]),area*10,delta=1e-3)


if __name__=='__main__':unittest.main()
