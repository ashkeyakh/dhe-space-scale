"""Shapefile -> closed extruded cells -> linked primal/dual half-edges -> HTML.

Pointers follow Boguslawski & Gold (2016), doi:10.3390/ijgi5020019.
This is a batch constructor, not an implementation of their Euler operators.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
import math
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent / '.deps'))
import shapefile
from pyproj import CRS, Transformer
from shapely import constrained_delaunay_triangles, transform
from shapely.geometry import Polygon, MultiPolygon, LineString, shape
from shapely.geometry.polygon import orient
from shapely.ops import unary_union
from shapely.validation import explain_validity
from viewer import make_view


@dataclass
class HalfEdge:
    V: int
    S: int = -1
    NV: int = -1
    NF: int = -1
    D: int = -1


class DHE:
    """Primal and dual half-edges share one index space; D is an involution.

    V is the origin. The redundant faces/cells arrays are inspection/rendering
    indexes; all navigation uses V, S, NV, NF, D on the half-edges themselves.
    Cell 0 is the unbounded exterior; its dual node has no geometric position.
    """

    def __init__(self):
        self.vertices = []
        self._vertex_index = {}
        self.half_edges: list[HalfEdge] = []
        self.faces = []
        self.cells = [{'id': 0, 'feature_id': 'EXTERIOR', 'faces': [], 'position': None}]
        self._cell_of = []
        self._face_of = []
        self.adjacent = []
        self.primal_count = 0

    def vertex(self, xyz):
        # One-micrometre precision is explicit in output metadata.
        key = tuple(round(float(v), 6) for v in xyz)
        if key not in self._vertex_index:
            self._vertex_index[key] = len(self.vertices)
            self.vertices.append(key)
        return self._vertex_index[key]

    def add_cell(self, feature_id, part, position, area, height):
        c = len(self.cells)
        self.cells.append(dict(id=c, feature_id=feature_id, part=part,
                               position=position, area_m2=area, height_m=height,
                               volume_m3=area * height, faces=[]))
        return c

    def add_face(self, c, coords, kind, rings=None, bridge_pairs=None):
        vs = [self.vertex(p) for p in coords]
        if len(set(vs)) < 3 or any(a == b for a, b in zip(vs, vs[1:] + vs[:1])):
            raise ValueError('A face collapses at the 1 micrometre topology tolerance.')
        f = len(self.faces)
        start = len(self.half_edges)
        es = list(range(start, start + len(vs)))
        for i, v in enumerate(vs):
            self.half_edges.append(HalfEdge(V=v, NF=es[(i + 1) % len(vs)]))
            self._cell_of.append(c)
            self._face_of.append(f)
        ring_ids = [[self.vertex(p) for p in ring] for ring in rings] if rings else [vs.copy()]
        bridge_pairs = {tuple(sorted(pair)) for pair in (bridge_pairs or [])}
        bridges = [es[i] for i in range(len(vs)) if tuple(sorted((vs[i], vs[(i+1) % len(vs)]))) in bridge_pairs]
        self.faces.append(dict(id=f, cell=c, kind=kind, vertices=vs, rings=ring_ids,
                               half_edges=es, bridge_half_edges=bridges))
        self.cells[c]['faces'].append(f)
        return f

    def finish(self, explicit_sym=None):
        H = self.half_edges
        # Pair S inside each bounded cell, preserving separate cell shells.
        if explicit_sym is not None:
            if set(explicit_sym)!=set(range(len(H))):raise ValueError('Explicit Sym must cover every bounded half-edge.')
            for i,e in enumerate(H):e.S=explicit_sym[i]
        else:
            directed = {}
            for i, e in enumerate(H):
                key = (self._cell_of[i], e.V, H[e.NF].V)
                if key in directed:
                    raise ValueError('Duplicate directed edge in a cell: invalid shell.')
                directed[key] = i
            for i, e in enumerate(H):
                key = (self._cell_of[i], H[e.NF].V, e.V)
                if key not in directed:
                    raise ValueError(f'Open cell shell in cell {key[0]} at {self.vertices[e.V]} -> {self.vertices[H[e.NF].V]}.')
                e.S = directed[key]

        # Across-face links, including the exterior side of every boundary face.
        face_groups = {}
        for f in self.faces:
            face_groups.setdefault(tuple(sorted(f['vertices'])), []).append(f['id'])
        A = [-1] * len(H)
        for fs in face_groups.values():
            if len(fs) > 2:
                raise ValueError('More than two cells occupy the same face.')
            a = self.faces[fs[0]]
            if len(fs) == 1:
                bridges = [(H[e].V, H[H[e].NF].V) for e in a['bridge_half_edges']]
                b_id = self.add_face(0, [self.vertices[v] for v in reversed(a['vertices'])], a['kind'],
                    rings=[[self.vertices[v] for v in reversed(r)] for r in a['rings']], bridge_pairs=bridges)
                A.extend([-1] * len(a['vertices']))
                b = self.faces[b_id]
                if 'tessellation' in a:b['tessellation']=[tri[::-1] for tri in a['tessellation']]
                if 'render_xyz' in a:
                    b['render_xyz']=[tri[::-1] for tri in a['render_xyz']]
                    b['render_reference']=a['render_reference']
            else:
                b = self.faces[fs[1]]
            back = {(H[j].V, H[H[j].NF].V): j for j in b['half_edges']}
            for i in a['half_edges']:
                e = H[i]
                j = back.get((H[e.NF].V, e.V))
                if j is None:
                    raise ValueError('Coincident faces have inconsistent winding/overlapping cells.')
                A[i] = j
                A[j] = i

        # Sew exterior edges by walking the incident bounded-cell fan. This also
        # handles components meeting only at an edge without arbitrary pairing.
        for f in self.faces:
            if f['cell'] != 0:
                continue
            for i in f['half_edges']:
                q = H[A[i]].S
                seen = set()
                while self._cell_of[A[q]] != 0:
                    if q in seen:
                        raise ValueError('Unclosed exterior edge fan.')
                    seen.add(q)
                    q = H[A[q]].S
                H[i].S = A[q]

        self.primal_count = n = len(H)
        prev_f = [-1] * n
        for i, e in enumerate(H):
            prev_f[e.NF] = i
        for i, e in enumerate(H):
            e.NV = H[prev_f[i]].S
        prev_v = [-1] * n
        for i, e in enumerate(H):
            prev_v[e.NV] = i

        # Each primal half-edge has its own permanent dual half-edge. Thus a
        # k-sided primal face is penetrated by a bundle of k dual edge uses.
        for i in range(n):
            H[i].D = n + i
            H.append(HalfEdge(V=self._cell_of[i], D=i))
        for i in range(n):
            d = H[n + i]
            d.S = n + H[A[i]].NF
            d.NF = n + H[A[i]].S
            d.NV = n + prev_v[i]
        self.adjacent = A
        self.update_render_cache()
        self.validate()

    def update_render_cache(self):
        """Tessellate only a derived render/slicing cache; never create DHE edges."""
        for face in self.faces:
            if 'render_xyz' in face:
                face['render_triangles']=[]
                continue
            if 'tessellation' in face:
                face['render_triangles']=face['tessellation']
                continue
            rings = [[self.vertices[v] for v in r] for r in face['rings']]
            if face['kind'] in ('roof', 'base'):
                polygon = Polygon([p[:2] for p in rings[0]], [[p[:2] for p in r] for r in rings[1:]])
                reverse = face['kind'] == 'base'
                if face['cell'] == 0:
                    reverse = not reverse
                triangles = []
                z = rings[0][0][2]
                for tri in constrained_delaunay_triangles(polygon).geoms:
                    coords = list(orient(tri, sign=-1 if reverse else 1).exterior.coords)[:-1]
                    ids = [self._vertex_index[tuple(round(t, 6) for t in (x,y,z))] for x,y in coords]
                    triangles.append(ids)
                face['render_triangles'] = triangles
            else:
                vs = face['vertices']
                face['render_triangles'] = [[vs[0], vs[j], vs[j+1]] for j in range(1, len(vs)-1)]

    def orbit(self, start, pointer):
        result, e = [], start
        while e not in result:
            result.append(e)
            e = getattr(self.half_edges[e], pointer)
            if len(result) > len(self.half_edges):
                raise ValueError('Invalid pointer cycle.')
        if e != start:
            raise ValueError('Pointer orbit does not close at its origin.')
        return result

    def validate(self):
        H, n = self.half_edges, self.primal_count
        for pointer in ('S', 'NV', 'NF', 'D'):
            if sorted(getattr(e, pointer) for e in H) != list(range(len(H))):
                raise ValueError(f'{pointer} is not a permutation.')
        prev_f, prev_v = {}, {}
        for i, e in enumerate(H):
            prev_f[e.NF], prev_v[e.NV] = i, i
        for i, e in enumerate(H):
            if H[e.S].S != i or H[e.D].D != i:
                raise ValueError('S or D involution failed.')
            if H[e.NV].V != e.V or H[e.S].V != H[e.NF].V:
                raise ValueError('Origin/rotation/edge endpoint consistency failed.')
            if H[H[e.D].NV].D != prev_v[i]:
                raise ValueError('PrevV = D.NV.D failed.')
            if H[H[H[H[e.D].S].NF].D].S != prev_f[i]:
                raise ValueError('PrevF = D.S.NF.D.S failed.')
            if i < n:
                adjacent = H[H[H[e.D].NF].D].S
                if adjacent != self.adjacent[i]:
                    raise ValueError('Adjacent = D.NF.D.S failed.')
        # Signed shell volume independently checks orientation and cap coverage.
        for c in self.cells[1:]:
            v = 0.0
            for f in c['faces']:
                pts = [self.vertices[i] for i in self.faces[f]['vertices']]
                a = pts[0]
                for j in range(1, len(pts) - 1):
                    b, d = pts[j], pts[j + 1]
                    v += (a[0]*(b[1]*d[2]-b[2]*d[1])
                          + a[1]*(b[2]*d[0]-b[0]*d[2])
                          + a[2]*(b[0]*d[1]-b[1]*d[0])) / 6
            if not math.isclose(v, c['volume_m3'], rel_tol=2e-6, abs_tol=1e-5):
                raise ValueError(f'Cell {c["id"]}: signed shell volume {v} != expected {c["volume_m3"]}.')

    def to_dict(self):
        return dict(schema='DHE-extrusion-2', precision_m=1e-6,
                    face_representation='polygon rings; hole bridges in NF; render_triangles are a derived cache only',
                    pointer_convention='V=origin; S=Sym; NV=NextV; NF=NextF; D=Dual',
                    primal_half_edge_count=self.primal_count,
                    vertices=self.vertices, dual_vertices=self.cells,
                    half_edges=[asdict(e) for e in self.half_edges], faces=self.faces,
                    adjacent=self.adjacent)


def node_boundaries(polygons):
    """Insert common boundary vertices so a partial shared edge is sewn exactly."""
    lines = unary_union([p.boundary for p in polygons])
    pieces = list(lines.geoms) if hasattr(lines, 'geoms') else [lines]
    points = sorted({tuple(xy[:2]) for line in pieces for xy in line.coords})

    def ring(coords):
        out = []
        for a, b in zip(coords, coords[1:]):
            dx, dy = b[0]-a[0], b[1]-a[1]
            ll = dx*dx + dy*dy
            if ll < 1e-18:
                continue
            along = [(0.0, a)]
            for p in points:
                t = ((p[0]-a[0])*dx + (p[1]-a[1])*dy)/ll
                distance = abs((p[0]-a[0])*dy - (p[1]-a[1])*dx)/math.sqrt(ll)
                if 1e-10 < t < 1-1e-10 and distance < 1e-7:
                    along.append((t, p))
            out.extend(p for _, p in sorted(along))
        return out
    return [orient(Polygon(ring(list(p.exterior.coords)),
                           [ring(list(r.coords)) for r in p.interiors]), sign=1)
            for p in polygons]


def bridged_ring(polygon):
    """Connect hole rings with reversible bridge edges in a single face orbit."""
    walk = list(polygon.exterior.coords)[:-1]
    pending = [list(r.coords)[:-1] for r in polygon.interiors]
    bridges = []
    while pending:
        candidates = []
        for h, hole in enumerate(pending):
            for i, a in enumerate(walk):
                for j, b in enumerate(hole):
                    line = LineString([a,b])
                    if not polygon.covers(line):
                        continue
                    if any(not line.intersection(old).is_empty and
                           line.intersection(old).geom_type not in ('Point', 'MultiPoint') for old in bridges):
                        continue
                    candidates.append((line.length, h, i, j))
        if not candidates:
            raise ValueError('No visible bridge from an inner ring to the face boundary.')
        _, h, i, j = min(candidates)
        hole = pending.pop(h)
        a, b = walk[i], hole[j]
        cycle = hole[j:] + hole[:j]
        walk = walk[:i+1] + cycle + [b,a] + walk[i+1:]
        bridges.append(LineString([a,b]))
    return walk, bridges


def construct(polygons, feature_ids, height=10.0):
    if not math.isfinite(height) or height <= 0:
        raise ValueError('Height must be finite and greater than zero.')
    for p in polygons:
        if not p.is_valid or p.is_empty or p.area <= 0:
            raise ValueError(f'Invalid polygon: {explain_validity(p)}')
    for i, p in enumerate(polygons):
        for q in polygons[i+1:]:
            if p.intersection(q).area > 1e-8:
                raise ValueError('Selected footprints overlap in area; resolve overlaps before building a cell complex.')
    polygons = node_boundaries(polygons)
    model = DHE()
    part_counts = {}
    for p, fid in zip(polygons, feature_ids):
        part_counts[fid] = part_counts.get(fid, 0) + 1
        c = model.add_cell(fid, part_counts[fid],
                           [p.representative_point().x, p.representative_point().y, height/2], p.area, height)
        walk, bridges = bridged_ring(p)
        rings = [list(r.coords)[:-1] for r in [p.exterior, *p.interiors]]
        for z, kind in [(height, 'roof'), (0.0, 'base')]:
            path = walk if kind == 'roof' else list(reversed(walk))
            geometric_rings = rings if kind == 'roof' else [list(reversed(r)) for r in rings]
            pairs = [(model.vertex((a[0],a[1],z)), model.vertex((b[0],b[1],z)))
                     for line in bridges for a,b in [list(line.coords)]]
            model.add_face(c, [(x,y,z) for x,y in path], kind,
                rings=[[(x,y,z) for x,y in ring] for ring in geometric_rings], bridge_pairs=pairs)
        for ring in [p.exterior, *p.interiors]:
            xy = list(ring.coords)
            for a, b in zip(xy, xy[1:]):
                model.add_face(c, [(a[0], a[1], 0.0), (b[0], b[1], 0.0),
                                   (b[0], b[1], height), (a[0], a[1], height)], 'wall')
    model.finish()
    return model


def load_shapefile(path, ids, id_field=None, source_crs=None):
    path = Path(path)
    if not path.is_file():
        raise ValueError(f'Shapefile does not exist: {path}')
    cpg = path.with_suffix('.cpg')
    encoding = cpg.read_text().strip() if cpg.exists() else 'utf-8'
    if encoding == '65001':
        encoding = 'utf-8'
    with shapefile.Reader(str(path), encoding=encoding) as reader:
        fields = [f[0] for f in reader.fields[1:]]
        requested = {str(i) for i in ids}
        if id_field is None:
            candidates = [f for f in fields if f.lower() in ('osm_id', 'id', 'fid', 'objectid')]
            matches = [f for f in candidates if requested <= {str(r[f]) for r in reader.iterRecords()}]
            if len(matches) != 1:
                raise ValueError(f'Cannot unambiguously select ID field. Use --id-field. Fields: {fields}')
            id_field = matches[0]
        if id_field not in fields:
            raise ValueError(f'Unknown ID field {id_field}; available: {fields}')
        features, found = [], set()
        for sr in reader.iterShapeRecords():
            record = sr.record.as_dict()
            fid = str(record[id_field])
            if fid not in requested:
                continue
            if fid in found:
                raise ValueError(f'Duplicate selected ID {fid} in {id_field}. Use a unique field.')
            if sr.shape.shapeType not in (5, 15, 25):
                raise ValueError(f'ID {fid} is not a polygon geometry.')
            g = shape(sr.shape.__geo_interface__)
            if not g.is_valid:
                raise ValueError(f'ID {fid}: {explain_validity(g)}. Repair the input geometry first.')
            features.append((fid, g, record))
            found.add(fid)
        if requested - found:
            raise ValueError(f'IDs missing from {id_field}: {sorted(requested-found)}')
    prj = path.with_suffix('.prj')
    if not source_crs and not prj.exists():
        raise ValueError('No .prj file. Supply --source-crs EPSG:xxxx.')
    src = CRS.from_user_input(source_crs) if source_crs else CRS.from_wkt(prj.read_text())
    # Use a local azimuthal equidistant metric system for all source CRSs; avoid
    # degree/foot height errors and record the exact transform for reproducibility.
    centre = unary_union([g for _, g, _ in features]).centroid
    lon, lat = Transformer.from_crs(src, 'EPSG:4326', always_xy=True).transform(centre.x, centre.y)
    dst = CRS.from_proj4(f'+proj=aeqd +lat_0={lat} +lon_0={lon} +datum=WGS84 +units=m +no_defs')
    project = Transformer.from_crs(src, dst, always_xy=True).transform
    polygons, fids = [], []
    for fid, geom, _ in features:
        for p in (list(geom.geoms) if isinstance(geom, MultiPolygon) else [geom]):
            polygons.append(transform(p, project, interleaved=False))
            fids.append(fid)
    metadata = dict(source=str(path.resolve()), id_field=id_field, selected_ids=list(ids),
                    source_crs=src.to_wkt(), model_crs=dst.to_wkt(),
                    origin_lon_lat=[lon, lat], source_z='ignored; base z=0 m',
                    attributes={fid: attrs for fid, _, attrs in features})
    return polygons, fids, metadata


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', required=True, type=Path)
    parser.add_argument('--ids', required=True, nargs='+')
    parser.add_argument('--id-field')
    parser.add_argument('--height', type=float, default=10.0, help='Uniform extrusion height in metres (default: 10).')
    parser.add_argument('--source-crs', help='Override missing/incorrect .prj, e.g. EPSG:4326.')
    parser.add_argument('--output', type=Path, default=Path('output/extrusion.html'))
    args = parser.parse_args(argv)
    try:
        polygons, fids, metadata = load_shapefile(args.input, args.ids, args.id_field, args.source_crs)
        model = construct(polygons, fids, args.height)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        make_view(model, metadata, args.output)
        topology = model.to_dict()
        topology['metadata'] = metadata
        args.output.with_suffix('.dhe.json').write_text(json.dumps(topology, indent=2, ensure_ascii=True), encoding='utf-8')
        print(json.dumps(dict(html=str(args.output.resolve()), id_field=metadata['id_field'],
             cells=len(model.cells)-1, primal_vertices=len(model.vertices), primal_half_edges=model.primal_count,
             dual_half_edges=model.primal_count, height_m=args.height, validation='passed'), indent=2))
    except (ValueError, OSError, shapefile.ShapefileException) as e:
        parser.exit(2, f'Error: {e}\n')


if __name__ == '__main__':
    main()
