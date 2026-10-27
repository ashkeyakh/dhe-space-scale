import json
from pathlib import Path
import subprocess
import unittest

from extrude import Polygon,load_shapefile
from shapely.geometry import Point,LineString,shape
from shapely import union_all,set_precision,make_valid
from shapely.ops import unary_union
from unified_operations import generalize
from workbench_config import FEATURE_IDS,INPUT_SHP,ID_FIELD


def sections(model,info,levels):
    data=model.to_dict();data['metadata']={'space_scale':info}
    script="""
const fs=require('node:fs'),G=require('./dhe_geometry.js');const {model,levels}=JSON.parse(fs.readFileSync(0,'utf8'));
const out=levels.map(z=>{const s=G.sliceModel(model,model.vertices,G.makePlane(model.vertices,'horizontal',z));return {z,area:s.area,cells:s.cells.map(c=>({fid:c.feature_id,area:c.area,loops:c.loops.map(l=>({coordinates:l.points,depth:l.depth})),points:c.points,lines:c.open}))};});
process.stdout.write(JSON.stringify(out));
"""
    result=subprocess.run(['node','-e',script],input=json.dumps(dict(model=data,levels=levels)),text=True,capture_output=True,check=True)
    return json.loads(result.stdout)


def section_polygon(section,fid):
    polygons=[]
    for cell in section['cells']:
        if cell['fid']!=fid:continue
        loops=cell['loops']
        for ring in loops:
            if ring['depth']%2:continue
            outer=Polygon([p[:2] for p in ring['coordinates']])
            holes=[r for r in loops if r['depth']==ring['depth']+1 and outer.covers(Point(r['coordinates'][0][:2]))]
            polygons.append(make_valid(Polygon([p[:2] for p in ring['coordinates']],[[p[:2] for p in h['coordinates']] for h in holes])))
    return unary_union(polygons) if polygons else Polygon()


def field_section(info,z):
    """Independent 2D clipping oracle for the owner-labelled lifted field."""
    if info.get('interface_z',float('-inf'))>=z:
        return {i:shape(g) for i,g in info['target_map'].items()}
    maps={i:shape(g) for i,g in info['source_map'].items()}
    additions={i:[] for i in maps};removed=[]
    for tri in info['transition_mesh']['triangles']:
        xy=[info['transition_mesh']['vertices'][v] for v in tri['vertices']]
        removed.append(Polygon(xy))
        for key,above in [('source_owner',True),('target_owner',False)]:
            fid=tri[key]
            if fid is None:continue
            vertices=[(*p,h) for p,h in zip(xy,tri['z'])];out=[]
            for a,b in zip(vertices,vertices[1:]+vertices[:1]):
                ina=a[2]<z if above else a[2]>=z
                inb=b[2]<z if above else b[2]>=z
                if ina:out.append(a[:2])
                if ina!=inb:
                    t=(z-a[2])/(b[2]-a[2]);out.append(tuple(a[k]+t*(b[k]-a[k]) for k in range(2)))
            if len(out)>=3 and Polygon(out).area>1e-12:additions[fid].append(set_precision(make_valid(Polygon(out)),1e-8))
    cut=unary_union(removed)
    return {i:union_all([g.difference(cut),*additions[i]],grid_size=1e-8) for i,g in maps.items()}


class UnifiedTransitionTests(unittest.TestCase):
    def sources(self):
        return {'left':Polygon([(0,0),(4,0),(4,4),(0,4)]),
                'right':Polygon([(4,0),(8,0),(8,4),(4,4)]),
                'north':Polygon([(0,4),(4,4),(4,8),(0,8)])}

    def endpoints(self,m,info):
        cuts=sections(m,info,[info['target_z'],info['source_z']])
        for at,label in [(cuts[0],'target_map'),(cuts[1],'source_map')]:
            for fid,geometry in info[label].items():
                expected=shape(geometry);got=section_polygon(at,fid)
                self.assertLess(expected.symmetric_difference(got).area,2e-4,(fid,label,expected.area,got.area))
        return cuts

    def test_arbitrary_point_and_bent_polyline_with_neighbours(self):
        for op,target in [('point','POINT (1 2)'),('polyline','LINESTRING (1 1,3 1,2 3)')]:
            m,info=generalize(self.sources(),op,['left'],target=target,recipient='right')
            m.validate();cuts=self.endpoints(m,info)
            for cut in sections(m,info,[0,0.1,1,2.5,5,5.5,9.5,10]):self.assertAlmostEqual(cut['area'],48,delta=2e-4)
            terminal=next(c for c in cuts[0]['cells'] if c['fid']=='left')
            if op=='point':self.assertEqual(len(terminal['points']),1)
            else:
                lines=unary_union([LineString([p[:2] for p in line]) for line in terminal['lines']])
                self.assertLess(lines.hausdorff_distance(shape(info['target_symbols']['left'])),1e-5)
            self.assertEqual(len([f for f in m.faces if f['cell'] and m.cells[f['cell']]['feature_id']=='left' and f['kind']=='roof' and all(m.vertices[v][2]==10 for v in f['vertices'])]),1)

    def test_merge_winner_and_boundary_loser(self):
        for winner in ('left','right'):
            m,info=generalize(self.sources(),'merge',['left','right'],winner=winner,loser_kind='boundary')
            self.endpoints(m,info);m.validate()
            self.assertEqual(info['winner'],winner)
            self.assertGreater(info['surgery']['coplanar_KEF'],0)
            for cut in sections(m,info,[0,1,5,9,10]):self.assertAlmostEqual(cut['area'],48,delta=2e-4)

    def test_crossing_polygon_boundaries_and_symmetric_difference(self):
        target=Polygon([(0,0),(3,0),(5,2),(3,4),(0,4)])
        m,info=generalize(self.sources(),'custom',['left'],target=target)
        self.endpoints(m,info);m.validate()
        regions=[shape(r['geometry']) for r in info['transition_faces']['regions'] if r['feature_id']=='left']
        self.assertLess(unary_union(regions).symmetric_difference(self.sources()['left'].symmetric_difference(target)).area,1e-5)

    def test_point_target_on_source_boundary(self):
        m,info=generalize(self.sources(),'point',['left'],target='POINT (0 2)',recipient='right')
        cuts=self.endpoints(m,info)
        self.assertTrue(any(c['fid']=='left' and len(c['points'])==1 for c in cuts[0]['cells']))

    def test_two_stage_true_skeleton_aggregation(self):
        source={'a':Polygon([(0,0),(2,0),(2,2),(0,2)]),'b':Polygon([(4,0),(6,0),(6,2),(4,2)])}
        m,info=generalize(source,'aggregation',['a','b'],winner='b',z_high=20)
        cuts=self.endpoints(m,info)
        self.assertEqual(info['skeleton']['engine'],'py_straight_skeleton 0.1.0')
        self.assertLess(info['skeleton']['coverage_error_m2'],1e-5)
        at_mid=sections(m,info,[10.0001,9.9999])
        self.assertEqual(len([c for c in at_mid[0]['cells'] if c['area']>1e-5]),2)
        self.assertEqual(len([c for c in at_mid[1]['cells'] if c['area']>1e-5]),1)
        self.assertAlmostEqual(cuts[0]['area'],12,delta=1e-5);self.assertAlmostEqual(cuts[1]['area'],8,delta=1e-5)

    def test_holes_remain_valid(self):
        source={'hole':Polygon([(0,0),(8,0),(8,8),(0,8)], [[(2,2),(2,5),(5,5),(5,2)]]),
                'neighbour':Polygon([(8,0),(12,0),(12,8),(8,8)])}
        m,info=generalize(source,'point',['hole'],target='POINT (6 6)',recipient='neighbour')
        self.endpoints(m,info);m.validate()

    def test_rejects_targets_outside_source_and_disconnected_merges(self):
        with self.assertRaisesRegex(ValueError,'inside'):
            generalize(self.sources(),'point',['left'],target='POINT (20 20)')
        with self.assertRaisesRegex(ValueError,'higher'):
            generalize(self.sources(),'point',['left'],z_low=10,z_high=0)
        separate={'a':self.sources()['left'],'b':Polygon([(10,0),(12,0),(12,2),(10,2)])}
        with self.assertRaisesRegex(ValueError,'adjacent'):
            generalize(separate,'merge',['a','b'])

    def test_user_context_is_not_hardcoded_to_two_features(self):
        if not INPUT_SHP or not Path(INPUT_SHP).exists():self.skipTest('User shapefile unavailable')
        ps,ids,_=load_shapefile(INPUT_SHP,list(map(str,FEATURE_IDS)),ID_FIELD)
        source={str(i):unary_union([p for p,f in zip(ps,ids) if f==str(i)]) for i in FEATURE_IDS}
        for op,selected in [('point',['20']),('simplification',['2001']),('aggregation',['8','9']),('simplification',['3000']),('polyline',['1123']),('merge',['3000','3001']),('aggregation',['17','18','21'])]:
            m,info=generalize(source,op,selected,winner=selected[0],z_high=20)
            with self.subTest(operation=op):self.endpoints(m,info);m.validate()
            self.assertTrue(set(i for i in map(str,FEATURE_IDS))<=set(info['source_map']))
            if op in ('simplification','merge','aggregation'):
                for cut in sections(m,info,[1,5,10,15,19]):
                    for fid,expected in field_section(info,cut['z']).items():
                        with self.subTest(operation=op,selected=selected,z=cut['z'],fid=fid):
                            self.assertLess(expected.symmetric_difference(section_polygon(cut,fid)).area,2e-4)


if __name__=='__main__':unittest.main()
