"""Geometry/topology regression checks, requiring no external test runner."""
import json
from pathlib import Path
import tempfile
import unittest

from extrude import construct, load_shapefile, Polygon, shapefile


class ExtrusionTests(unittest.TestCase):
    def check_model(self, polygons, ids, expected_volume, height=10):
        model = construct(polygons, ids, height)
        self.assertAlmostEqual(sum(c['volume_m3'] for c in model.cells[1:]), expected_volume)
        model.validate()
        # Every primal/dual face cycle closes, and each NV star has one origin.
        seen = set()
        for i, e in enumerate(model.half_edges):
            if i not in seen:
                cycle = model.orbit(i, 'NF')
                seen.update(cycle)
            self.assertTrue(all(model.half_edges[j].V == e.V for j in model.orbit(i, 'NV')))
        return model

    def test_cube_and_exterior(self):
        m = self.check_model([Polygon([(0,0),(2,0),(2,2),(0,2)])], ['cube'], 40)
        self.assertEqual(len(m.vertices), 8)
        self.assertEqual(len(m.cells[1]['faces']), 6, 'cube must have six polygon faces')
        self.assertEqual(len(m.half_edges), 2*m.primal_count)
        self.assertEqual({m._cell_of[m.adjacent[i]] for i in range(m.primal_count)
                          if m._cell_of[i] == 1}, {0})

    def test_hole_and_concavity(self):
        hole = Polygon([(0,0),(6,0),(6,6),(0,6)], [[(2,2),(2,4),(4,4),(4,2)]])
        concave = Polygon([(10,0),(13,0),(13,1),(11,1),(11,4),(10,4)])
        self.check_model([hole, concave], ['hole', 'concave'], 380)

    def test_polygon_caps_and_hole_bridges(self):
        p = Polygon([(0,0),(8,0),(8,8),(0,8)], [[(2,2),(2,6),(6,6),(6,2)]])
        m = self.check_model([p], ['hole'], 480)
        roofs = [f for f in m.faces if f['cell']==1 and f['kind']=='roof']
        self.assertEqual(len(roofs),1)
        self.assertEqual(len(roofs[0]['rings']),2)
        self.assertEqual(len(roofs[0]['bridge_half_edges']),2)
        self.assertGreater(len(roofs[0]['render_triangles']),1)
        self.assertEqual(len(m.orbit(roofs[0]['half_edges'][0],'NF')),10)

    def test_partial_shared_wall_requires_noding(self):
        a = Polygon([(0,0),(3,0),(3,3),(0,3)])
        b = Polygon([(3,1),(5,1),(5,2),(3,2)])
        m = self.check_model([a, b], ['a', 'b'], 110)
        interfaces = [f for f in m.faces if f['cell'] == 1
                      and m._cell_of[m.adjacent[f['half_edges'][0]]] == 2]
        self.assertEqual(len(interfaces), 1)
        self.assertEqual(interfaces[0]['kind'], 'wall')

    def test_edge_and_vertex_contacts(self):
        a = Polygon([(0,0),(1,0),(1,1),(0,1)])
        b = Polygon([(1,1),(2,1),(2,2),(1,2)])
        self.check_model([a,b], ['a','b'], 20)

    def test_reject_bad_geometry_and_height(self):
        square = Polygon([(0,0),(2,0),(2,2),(0,2)])
        for h in [0,-1,float('nan'),float('inf')]:
            with self.assertRaises(ValueError):
                construct([square], ['a'], h)
        with self.assertRaisesRegex(ValueError, 'overlap'):
            construct([square, square], ['a','b'])
        with self.assertRaisesRegex(ValueError, 'Invalid polygon'):
            construct([Polygon([(0,0),(2,2),(2,0),(0,2)])], ['invalid'])

    def test_shapefile_id_and_crs_handling(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'test.shp'
            with shapefile.Writer(str(path)) as w:
                w.field('osm_id', 'C')
                w.poly([[(16,50),(16,50.001),(16.001,50.001),(16.001,50),(16,50)]])
                w.record('2001')
            with self.assertRaisesRegex(ValueError, 'No .prj'):
                load_shapefile(path, ['2001'])
            ps, ids, md = load_shapefile(path, ['2001'], source_crs='EPSG:4326')
            self.assertEqual(ids, ['2001'])
            self.assertEqual(md['id_field'], 'osm_id')
            self.assertGreater(ps[0].area, 7000)
            self.assertLess(ps[0].area, 9000)
            with self.assertRaisesRegex(ValueError, 'missing'):
                load_shapefile(path, ['missing'], id_field='osm_id', source_crs='EPSG:4326')
            m = construct(ps, ids)
            json.dumps(m.to_dict())


if __name__ == '__main__':
    unittest.main()
