import json
from pathlib import Path
import unittest

from extrude import construct, Polygon, load_shapefile
from dhe_ops import Generalizer, boundary_graph, cap_polygon, check_motion, geometry_at
from shapely.ops import unary_union
from workbench_config import INPUT_SHP


def shared_bend():
    left=Polygon([(0,0),(3,0),(2.5,2),(3.5,4),(3,6),(0,6)])
    right=Polygon([(3,0),(6,0),(6,6),(3,6),(3.5,4),(2.5,2)])
    return construct([left,right],['left','right'])


class DHEOperatorTests(unittest.TestCase):
    def test_shared_boundary_motion_and_atomic_commit(self):
        original=shared_bend()
        untouched=json.dumps(original.to_dict())
        generalizer=Generalizer(original)
        result=generalizer.simplify('left',0.9,max_events=1)
        self.assertEqual(len(generalizer.events),1)
        event=generalizer.events[0]
        self.assertEqual(event.affected_cells,[1,2])
        original_union=unary_union([cap_polygon(original,c) for c in (1,2)])
        for t in (0,0.1,0.5,0.9,0.999,1):
            model=event.at(t);model.validate()
            self.assertLess(original_union.symmetric_difference(unary_union([cap_polygon(model,c) for c in (1,2)])).area,1e-5)
            if t<1:self.assertEqual(model.primal_count,original.primal_count)
        self.assertLess(result.primal_count,original.primal_count)
        self.assertFalse(cap_polygon(original,2).equals(cap_polygon(result,2)))
        self.assertEqual(json.dumps(original.to_dict()),untouched,'source snapshot must not be modified')
        self.assertEqual(len(result.cells[1]['faces']),len(original.cells[1]['faces'])-1)
        self.assertEqual(len(result.cells[2]['faces']),len(original.cells[2]['faces'])-1)

    def test_junctions_are_protected(self):
        original=shared_bend();graph,_=boundary_graph(original)
        protected={v for v,neighbors in graph.items() if len(neighbors)!=2}
        g=Generalizer(original);g.simplify('left',2.0)
        self.assertTrue(protected <= set(boundary_graph(g.model)[0]))

    def test_invalid_motion_is_rejected(self):
        m=construct([Polygon([(0,0),(3,0),(3,3),(0,3)])],['one'])
        with self.assertRaises(ValueError):check_motion(m,(3,0),(-1,4))
        with self.assertRaises(ValueError):geometry_at(m,(3,0),(2,1),1.1)

    def test_holes_and_bridge_endpoints_remain_valid(self):
        p=Polygon([(0,0),(10,0),(10,10),(0,10)], [[(2,2),(2,7),(3,8),(7,7),(7,2)]])
        m=construct([p],['hole']);g=Generalizer(m)
        g.simplify('hole',1.0)
        g.model.validate()
        self.assertEqual(len(cap_polygon(g.model,1).interiors),1)

    def test_actual_2001_and_automatic_2002_update(self):
        source=Path(INPUT_SHP)
        if not INPUT_SHP or not source.exists():self.skipTest('User shapefile not present on this machine')
        ps,ids,_=load_shapefile(source,['2001','2002'],'osm_id')
        original=construct(ps,ids);g=Generalizer(original);g.simplify('2001',2.5)
        self.assertEqual(len(g.events),12)
        self.assertTrue(any(e.affected_cells==[1,2] for e in g.events))
        self.assertEqual(len(g.model.faces[g.model.cells[1]['faces'][0]]['rings'][0]),11)
        self.assertEqual(len(g.model.faces[g.model.cells[2]['faces'][0]]['rings'][0]),7)
        for c in (1,2):
            self.assertLessEqual(cap_polygon(original,c).boundary.hausdorff_distance(cap_polygon(g.model,c).boundary),2.500002)
        payload=g.transition_payload(3)
        self.assertEqual(len(payload['states']),13)
        self.assertEqual(len(payload['events'][-1]['samples']),3)


if __name__=='__main__':unittest.main()
