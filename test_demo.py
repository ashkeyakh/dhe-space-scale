"""Public-demo regression checks independent of private input files."""
import tempfile
from pathlib import Path
import unittest
from demo_data import demo_sources
from unified_operations import generalize
from workbench_server import Workbench


class DemoTests(unittest.TestCase):
    def test_fourteen_valid_nonoverlapping_sources(self):
        source=demo_sources();self.assertEqual(len(source),14)
        for i,a in source.items():
            self.assertTrue(a.is_valid)
            for j,b in source.items():
                if i!=j:self.assertLess(a.intersection(b).area,1e-8)

    def test_all_common_operations_close_on_demo(self):
        for op,ids in [('simplification',['2001']),('point',['2001']),('polyline',['2001']),
                       ('merge',['2001','2002']),('aggregation',['8','9'])]:
            with self.subTest(operation=op):
                model,info=generalize(demo_sources(),op,ids,winner=ids[0],tolerance=1)
                model.validate();self.assertTrue(info['source_at_highest'])

    def test_demo_workbench_exports_no_local_source_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            workbench=Workbench(Path(tmp),demo=True)
            self.assertEqual(len(workbench.source),14)
            self.assertEqual(workbench.metadata['data_origin'],'Original synthetic demo')
            self.assertTrue((Path(tmp)/'index.html').exists())


if __name__=='__main__':unittest.main()
