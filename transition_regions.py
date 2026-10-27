"""A single symmetric-difference -> DHE -> triangulate -> lift -> close path."""
from collections import defaultdict
from dataclasses import dataclass
import math

from extrude import Polygon, LineString, DHE, bridged_ring, orient
import numpy as np
import triangle
from shapely.geometry import Point,MultiLineString,box,mapping
from shapely import set_precision
from shapely.ops import unary_union,polygonize
from target_geometry import polygonal
from transition_brep import WedgeBoundary


def parts(g):
    if g.is_empty:return []
    return list(g.geoms) if g.geom_type=='MultiPolygon' else [g]


def _lines(g):
    if g.is_empty:return []
    if g.geom_type in ('Polygon','MultiPolygon'):return _lines(g.boundary)
    if g.geom_type in ('LineString','LinearRing'):return [g]
    if g.geom_type in ('MultiLineString','GeometryCollection'):return [line for p in g.geoms for line in _lines(p)]
    return []


def transition_faces(source,target,symbols,z_high):
    """Step 2/3 diagnostic DHE faces: lower-dimensional targets are constraints."""
    model=DHE();regions=[]
    for fid,s in source.items():
        t=target.get(fid,Polygon());difference=polygonal(s.symmetric_difference(t))
        for index,p in enumerate(parts(difference)):
            if p.area<1e-10:continue
            p=orient(p,sign=1);walk,bridges=bridged_ring(p)
            rings=[list(r.coords)[:-1] for r in [p.exterior,*p.interiors]]
            pairs=[(model.vertex((*a,z_high)),model.vertex((*b,z_high))) for line in bridges for a,b in [list(line.coords)]]
            f=model.add_face(0,[(*q,z_high) for q in walk],'transition_region',rings=[[(*q,z_high) for q in r] for r in rings],bridge_pairs=pairs)
            from extrude import constrained_delaunay_triangles
            regions.append(dict(id=f,feature_id=fid,geometry=mapping(p),render_triangles=[list(t.exterior.coords)[:-1] for t in constrained_delaunay_triangles(p).geoms],source_vertices=[list(q) for pp in parts(s) for r in [pp.exterior] for q in list(r.coords)[:-1]],
                target_constraint=mapping(symbols[fid]) if fid in symbols else None))
    # These are deliberately unsewn planar construction faces, not closed cells.
    return dict(vertices=model.vertices,faces=model.faces,
                half_edges=[vars(e).copy() for e in model.half_edges],regions=regions,z=z_high,
                state='planar DHE construction faces; closed primal/dual shells follow lifting')


def _mesh(source,target,symbols,extra=None):
    geometries=[g for g in [*source.values(),*target.values(),*(extra or {}).values()] if not g.is_empty]
    domain=unary_union(geometries).convex_hull
    minx,miny,maxx,maxy=domain.bounds;pad=max(maxx-minx,maxy-miny)*0.03+1
    frame=box(minx-pad,miny-pad,maxx+pad,maxy+pad)
    constraints=[*_lines(frame),*[line for g in geometries for line in _lines(g)],*[line for g in symbols.values() for line in _lines(g)]]
    network=unary_union([set_precision(line,1e-6) for line in constraints])
    points=[];lookup={};segments=set()
    def vertex(p):
        key=(round(p[0],6),round(p[1],6))
        if key not in lookup:lookup[key]=len(points);points.append(key)
        return lookup[key]
    # Explicitly node source/target intersection vertices BEFORE Triangle.
    isolated=[g.coords[0] for g in symbols.values() if g.geom_type=='Point']
    for line in _lines(network):
        coords=list(line.coords)
        for a,b in zip(coords,coords[1:]):
            cuts=[(0,a),(1,b)];ab=(b[0]-a[0],b[1]-a[1]);ll=ab[0]**2+ab[1]**2
            for p in isolated:
                t=((p[0]-a[0])*ab[0]+(p[1]-a[1])*ab[1])/ll
                if 1e-9<t<1-1e-9 and LineString([a,b]).distance(Point(p))<1e-8:cuts.append((t,p))
            cuts.sort()
            for (_,p),(_,q) in zip(cuts,cuts[1:]):
                i,j=vertex(p),vertex(q)
                if i!=j:segments.add(tuple(sorted((i,j))))
    for p in isolated:vertex(p)
    for attempt in range(6):
        out=triangle.triangulate(dict(vertices=np.asarray(points),segments=np.asarray(sorted(segments),dtype=np.int32)),'pQ')
        canonical=[(round(float(p[0]),6),round(float(p[1]),6)) for p in out['vertices']]
        if len(set(canonical))==len(canonical) and all(math.dist(p,q)<1e-9 for p,q in zip(out['vertices'],canonical)):
            out['vertices']=np.asarray(canonical);break
        # Triangle can introduce a sub-grid intersection beside an existing
        # endpoint. Snap/merge its noded PSLG and retriangulate before lifting;
        # never lift an artificial near-zero-width wedge.
        remap={};points=[];lookup={}
        for i,p in enumerate(canonical):
            if p not in lookup:lookup[p]=len(points);points.append(p)
            remap[i]=lookup[p]
        segments={tuple(sorted((remap[int(a)],remap[int(b)]))) for a,b in out['segments'] if remap[int(a)]!=remap[int(b)]}
    else:raise ValueError('PSLG intersections do not stabilize at one-micrometre precision.')
    if 'triangles' not in out:raise ValueError('Constrained triangulation produced no transition mesh.')
    vertices=[tuple(p) for p in out['vertices']];coarse=[tuple(map(int,t)) for t in out['triangles']]
    # Interior centroids prevent endpoint plateaus without subdividing shared
    # constraint edges. Do not refine sub-grid slivers: rounding their new
    # centroids would collapse distinct wedge corners to the same coordinate.
    refined=[]
    for a,b,c in coarse:
        xy=[vertices[a],vertices[b],vertices[c]];p=Polygon(xy)
        altitude=2*p.area/max(math.dist(xy[0],xy[1]),math.dist(xy[1],xy[2]),math.dist(xy[2],xy[0]))
        if altitude<2e-5:refined.append((a,b,c));continue
        q=tuple(round((vertices[a][k]+vertices[b][k]+vertices[c][k])/3,6) for k in range(2))
        if not p.contains(Point(q)):refined.append((a,b,c));continue
        center=len(vertices);vertices.append(q)
        refined.extend([(a,b,center),(b,c,center),(c,a,center)])
    return vertices,refined,frame


def _owner(point,geometries):
    for fid,g in geometries.items():
        if not g.is_empty and g.covers(point):return fid
    return None


def build_transition(plan,z_low=0,z_high=10,classic_target=None,interface_z=None):
    if not math.isfinite(z_high+z_low) or z_high<=z_low:raise ValueError('Source Z must be higher than target Z.')
    source={i:set_precision(g,1e-6) for i,g in plan.source.items()}
    target={i:set_precision(g,1e-6) for i,g in plan.target.items()}
    symbols={i:set_precision(g,1e-6) for i,g in plan.symbols.items()}
    if classic_target is not None:classic_target={i:set_precision(g,1e-6) for i,g in classic_target.items()}
    changed=[fid for fid in source if not source[fid].equals(target.get(fid,Polygon())) or fid in symbols]
    source_edges=unary_union([g.boundary for fid,g in source.items() if fid in changed])
    symbol_constraints=unary_union(list(symbols.values()))
    target_constraints=unary_union([g.boundary for fid,g in target.items() if fid in changed and not g.is_empty]+list(symbols.values()))
    if source_edges.is_empty or target_constraints.is_empty:
        # For complete absorption without a symbol, use a representative point
        # of the assigned target as a finite target constraint.
        target_constraints=unary_union([g.boundary for g in target.values() if not g.is_empty])
    if classic_target is not None:
        if interface_z is None or not z_low<interface_z<z_high:raise ValueError('Aggregation interface must be between source and target Z.')
    lift_low=interface_z if classic_target is not None else z_low
    vertices,triangles,frame=_mesh(source,target,symbols,classic_target)
    heights=[]
    for p in vertices:
        point=Point(p);ds=source_edges.distance(point) if not source_edges.is_empty else 1
        dt=target_constraints.distance(point) if not target_constraints.is_empty else 1
        if not symbol_constraints.is_empty and symbol_constraints.distance(point)<1e-7:fraction=0
        elif ds<1e-7 and dt<1e-7:fraction=0.5
        elif ds<1e-7:fraction=1
        elif dt<1e-7:fraction=0
        else:fraction=dt/(ds+dt)
        heights.append(round(lift_low+(z_high-lift_low)*fraction,6))
    boundary=WedgeBoundary();tri_report=[]
    for tri in triangles:
        xy=[vertices[i] for i in tri]
        if Polygon(xy).area<1e-12:continue
        if not Polygon(xy).exterior.is_ccw:tri=tuple(reversed(tri));xy=xy[::-1]
        point=Polygon(xy).representative_point();above=_owner(point,source);below=_owner(point,target)
        final=_owner(point,classic_target) if classic_target is not None else None
        if above is None and below is None and final is None:continue
        field=[heights[i] for i in tri]
        boundary.fragment(above,xy,field,[z_high]*3)
        boundary.fragment(below,xy,[lift_low]*3,field)
        if classic_target is not None:boundary.fragment(final,xy,[z_low]*3,[interface_z]*3)
        if above!=below:tri_report.append(dict(vertices=list(tri),source_owner=above,target_owner=below,z=field))
    for fid,g in source.items():
        for p in parts(g):
            for ring in [p.exterior,*p.interiors]:
                for q in list(ring.coords)[:-1]:boundary.protected.add(boundary.vertex((*q,z_high)))
    final_map=classic_target if classic_target is not None else target
    for fid,g in final_map.items():
        for p in parts(g):
            for ring in [p.exterior,*p.interiors]:
                for q in list(ring.coords)[:-1]:boundary.protected.add(boundary.vertex((*q,z_low)))
    for g in symbols.values():
        for q in (list(g.coords) if hasattr(g,'coords') and g.geom_type!='MultiLineString' else [p for line in g.geoms for p in line.coords]):boundary.protected.add(boundary.vertex((*q,z_low)))
    result=boundary.finish(list(source),source,z_high)
    diagnostic=transition_faces(source,target,symbols,z_high)
    info=dict(operation=plan.operation,source_z=z_high,target_z=z_low,source_at_highest=True,scale_end=z_high,winner=plan.winner,
        selected_ids=plan.selected,affected_feature_ids=changed,targets={i:mapping(g) for i,g in plan.requested.items()},
        source_map={i:mapping(g) for i,g in source.items()},target_map={i:mapping(g) for i,g in final_map.items()},
        target_symbols={i:mapping(g) for i,g in symbols.items()},
        coverage_policy='shared owner-labelled transition complex; background is the exterior cell',
        transition_faces=diagnostic,transition_mesh=dict(vertices=vertices,triangles=tri_report),
        source_target_intersections='shared vertices use intermediate Z; vertical closure curtains retain both endpoint maps',
        surgery=result.surgery_stats,**plan.details)
    if classic_target is not None:info.update(interface_z=interface_z,partition_map={i:mapping(g) for i,g in target.items()},stages=['outward straight-skeleton transition','classic SSC merge'])
    return result,info
