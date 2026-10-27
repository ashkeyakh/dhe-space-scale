"""Transactional DHE boundary-column suppression for extruded polygon cells.

Geometry changes are continuous in a dimensionless parameter t. Incidence
changes occur at t=1. Assigning t to time or scale is a separate modelling choice.
This is an extruded-cell operator, not the general non-manifold Euler library.
"""
from __future__ import annotations
from copy import deepcopy
from dataclasses import dataclass
import itertools
import math

from extrude import DHE, Polygon
from shapely.geometry import LineString, Point
from shapely.ops import unary_union


def xy_key(point):
    return tuple(round(float(v), 6) for v in point[:2])


def cap_polygon(model, cell):
    roof = next(model.faces[f] for f in model.cells[cell]['faces'] if model.faces[f]['kind']=='roof')
    rings = [[model.vertices[v][:2] for v in ring] for ring in roof['rings']]
    return Polygon(rings[0], rings[1:])


def validate_geometry(model):
    polygons = []
    for cell in model.cells[1:]:
        polygon = cap_polygon(model, cell['id'])
        if not polygon.is_valid or polygon.area < 1e-8:
            raise ValueError(f'Cell {cell["id"]} becomes invalid or loses area.')
        polygons.append(polygon)
    for i,p in enumerate(polygons):
        if any(p.intersection(q).area > 2e-6 for q in polygons[i+1:]):
            raise ValueError('The deformation would overlap an adjacent cell.')
    return polygons


def refresh_geometry(model):
    model._vertex_index = {tuple(p):i for i,p in enumerate(model.vertices)}
    polygons = validate_geometry(model)
    for cell,p in zip(model.cells[1:],polygons):
        cell['area_m2'] = p.area
        cell['volume_m3'] = p.area*cell['height_m']
        point = p.representative_point()
        cell['position'] = [point.x,point.y,cell['height_m']/2]
    model.update_render_cache()
    model.validate()
    return model


def boundary_graph(model):
    """Unique XY edges/vertices, with ownership derived from polygon DHE rings."""
    graph,owners = {},{}
    for cell in model.cells[1:]:
        roof = next(model.faces[f] for f in cell['faces'] if model.faces[f]['kind']=='roof')
        for ring in roof['rings']:
            points = [xy_key(model.vertices[v]) for v in ring]
            for a,b in zip(points,points[1:]+points[:1]):
                graph.setdefault(a,set()).add(b)
                graph.setdefault(b,set()).add(a)
                owners.setdefault(a,set()).add(cell['id'])
                owners.setdefault(b,set()).add(cell['id'])
    return graph,owners


def geometry_at(model, source_xy, target_xy, t):
    if not 0 <= t <= 1:
        raise ValueError('Transition parameter must be in [0,1].')
    result = deepcopy(model)
    source_xy = xy_key(source_xy)
    target_xy = xy_key(target_xy)
    changed = [i for i,p in enumerate(model.vertices) if xy_key(p)==source_xy]
    if not changed:
        raise ValueError('Source column does not exist.')
    position = [round(source_xy[k]+t*(target_xy[k]-source_xy[k]),6) for k in range(2)]
    for v in changed:
        result.vertices[v] = (*position,model.vertices[v][2])
    return refresh_geometry(result)


def _moving_polygon(model, cell, source, target, t):
    roof = next(model.faces[f] for f in model.cells[cell]['faces'] if model.faces[f]['kind']=='roof')
    p = tuple(source[k]+t*(target[k]-source[k]) for k in range(2))
    rings = [[p if xy_key(model.vertices[v])==source else model.vertices[v][:2] for v in ring] for ring in roof['rings']]
    return Polygon(rings[0],rings[1:])


def check_motion(model,source,target):
    """Check all edge-orientation event intervals for this one moving column.

    Under one shared XY vertex moving linearly, segment orientation predicates
    are linear in t. Test their roots and interval interiors, rather than merely
    assuming a few animation frames imply a valid continuous deformation.
    Floating-point predicates still use the model's metric tolerance.
    """
    source,target=xy_key(source),xy_key(target)
    graph,_=boundary_graph(model)
    points=list(graph)
    def orient(a,b,c):
        return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
    times={0.0,1.0}
    for a,b in itertools.combinations([p for p in points if p!=source],2):
        start,end=orient(a,b,source),orient(a,b,target)
        if abs(start-end)>1e-12:
            t=start/(start-end)
            if 1e-10<t<1-1e-10:
                times.add(t)
    times=sorted(times)
    checks=sorted(set(times+[(a+b)/2 for a,b in zip(times,times[1:])]))
    for t in checks:
        polygons=[_moving_polygon(model,c['id'],source,target,t) for c in model.cells[1:]]
        if any(not p.is_valid or p.area<1e-8 for p in polygons):
            raise ValueError(f'Motion has an invalid polygon near t={t:.8f}.')
        for i,p in enumerate(polygons):
            if any(p.intersection(q).area>1e-7 for q in polygons[i+1:]):
                raise ValueError(f'Motion would overlap cells near t={t:.8f}.')
    return len(checks)


def suppress_collinear_column(model, source_xy):
    """Join incident wall faces and suppress this vertex in every cap ring.

    The affected primal face loops are edited together. Dense storage is then
    compacted and Sym/NV and the permanent primal/dual pairs are re-sewn by the
    canonical DHE constructor. This is transactional reconstruction of the
    incidence table, not in-place KEF/KVE on persistent object pointers.
    """
    source=xy_key(source_xy)
    graph,owners=boundary_graph(model)
    if source not in graph or len(graph[source])!=2:
        raise ValueError('Only a degree-two boundary column can be suppressed; junctions are protected.')
    a,c=sorted(graph[source])
    chord=LineString([a,c])
    if chord.distance(Point(source))>2e-6:
        raise ValueError('The column must reach its collinear event position before suppression.')
    for face in model.faces:
        if any(source in (xy_key(model.vertices[model.half_edges[e].V]),
                          xy_key(model.vertices[model.half_edges[model.half_edges[e].NF].V]))
               for e in face['bridge_half_edges']):
            raise ValueError('Hole-bridge endpoints must be re-routed before suppression.')
    result=DHE()
    result.cells=deepcopy(model.cells)
    for cell in result.cells:
        cell['faces']=[]
    removed={i for i,p in enumerate(model.vertices) if xy_key(p)==source}
    merged_wall_faces={}
    for cell in owners[source]:
        walls=[model.faces[f] for f in model.cells[cell]['faces']
               if model.faces[f]['kind']=='wall' and any(v in removed for v in model.faces[f]['vertices'])]
        if len(walls)!=2:
            raise ValueError('The column does not have exactly two incident wall faces per cell.')
        # A KEF-style face-loop splice: cancel the common vertical edge, follow
        # the resulting perimeter, and suppress the two collinear cap vertices.
        directed={}
        for face in walls:
            vs=face['vertices']
            for u,v in zip(vs,vs[1:]+vs[:1]):
                if (v,u) in directed: del directed[v,u]
                else: directed[u,v]=True
        following={u:v for u,v in directed}
        start=next(iter(following));walk=[start];at=following[start]
        while at!=start:
            if at in walk or at not in following:
                raise ValueError('The merged wall perimeter does not form one loop.')
            walk.append(at);at=following[at]
        walk=[v for v in walk if v not in removed]
        merged_wall_faces[min(f['id'] for f in walls)]=(walk,[f['id'] for f in walls])
        merged_wall_faces[max(f['id'] for f in walls)]=None
    for face in model.faces:
        if face['cell']==0:continue
        fid=face['id']
        if fid in merged_wall_faces:
            entry=merged_wall_faces[fid]
            if entry is None:continue
            vs,lineage=entry
            new_id=result.add_face(face['cell'],[model.vertices[v] for v in vs],'wall')
        else:
            vs=[v for v in face['vertices'] if v not in removed]
            rings=[[v for v in ring if v not in removed] for ring in face['rings']]
            if any(len(ring)<3 for ring in rings):
                raise ValueError('Suppression would collapse a cap ring.')
            bridge_pairs=[(result.vertex(model.vertices[model.half_edges[e].V]),
                           result.vertex(model.vertices[model.half_edges[model.half_edges[e].NF].V]))
                          for e in face['bridge_half_edges']]
            new_id=result.add_face(face['cell'],[model.vertices[v] for v in vs],face['kind'],
                rings=[[model.vertices[v] for v in ring] for ring in rings],bridge_pairs=bridge_pairs)
            lineage=[fid]
        result.faces[new_id]['source_faces']=lineage
    result.finish()
    validate_geometry(result)
    return result


@dataclass
class SimplificationEvent:
    before:DHE
    after:DHE
    source:tuple
    target:tuple
    affected_cells:list
    error_m:float
    motion_checks:int

    def at(self,t):
        if t==1:return deepcopy(self.after)
        return geometry_at(self.before,self.source,self.target,t)

    def to_dict(self):
        return dict(operator='SuppressBoundaryColumn',source_xy=self.source,target_xy=self.target,
                    affected_cells=self.affected_cells,error_m=self.error_m,
                    motion_predicate_checks=self.motion_checks,commit_parameter=1.0,
                    topology_event='join the two incident walls per cell; suppress the collinear cap vertices; re-sew primal/dual incidence',
                    before=self.before.to_dict(),after=self.after.to_dict())


class Generalizer:
    def __init__(self,model):
        self.model=deepcopy(model)
        self.events=[]

    def simplify(self,feature_id,tolerance_m=2.5,max_events=None,preserve_coverage=False):
        fid=str(feature_id)
        if tolerance_m<0 or not math.isfinite(tolerance_m):
            raise ValueError('Tolerance must be finite and nonnegative.')
        cells=[c['id'] for c in self.model.cells[1:] if str(c['feature_id'])==fid]
        if not cells:raise ValueError(f'Unknown feature ID {fid}.')
        original={c:cap_polygon(self.model,c) for c in range(1,len(self.model.cells))}
        while max_events is None or len(self.events)<max_events:
            graph,owners=boundary_graph(self.model)
            candidates=[]
            bridge_vertices={xy_key(self.model.vertices[self.model.half_edges[e].V])
                             for f in self.model.faces for e in f['bridge_half_edges']}
            for source,neighbors in graph.items():
                if len(neighbors)!=2 or not (owners[source]&set(cells)) or source in bridge_vertices:continue
                if preserve_coverage and len(owners[source])<2:continue
                a,c=sorted(neighbors)
                chord=LineString([a,c]);point=Point(source)
                parameter=chord.project(point,normalized=True)
                # A strict interior projection avoids a zero-length boundary edge
                # before the discrete suppression event.
                if not 1e-6<parameter<1-1e-6:continue
                target=xy_key(chord.interpolate(parameter,normalized=True).coords[0])
                error=point.distance(Point(target))
                if error<=tolerance_m:candidates.append((error,source,target))
            committed=False
            for error,source,target in sorted(candidates):
                try:
                    checks=check_motion(self.model,source,target)
                    endpoint=geometry_at(self.model,source,target,1)
                    after=suppress_collinear_column(endpoint,target)
                    if any(original[c].boundary.hausdorff_distance(cap_polygon(after,c).boundary)>tolerance_m+2e-6
                           for c in original):
                        continue
                    affected=sorted(owners[source])
                    # For internal boundaries, changes must exactly cancel in
                    # the union. Exterior boundary simplification may move it.
                    if len(affected)>1:
                        old_union=unary_union([cap_polygon(self.model,c) for c in affected])
                        new_union=unary_union([cap_polygon(after,c) for c in affected])
                        if old_union.symmetric_difference(new_union).area>1e-5:continue
                    event=SimplificationEvent(deepcopy(self.model),after,source,target,affected,error,checks)
                    self.events.append(event);self.model=after;committed=True
                    break
                except (ValueError,KeyError):
                    continue
            if not committed:break
        return self.model

    def transition_payload(self,samples_per_event=20):
        """Finite sample cache for the offline player; at(t) is the geometry API.

        Keep DHE incidence only at event boundaries. Samples contain coordinate,
        cell-metric and render-cache deltas, rather than duplicate pointer graphs.
        """
        if samples_per_event<2:raise ValueError('At least two samples per event are required.')
        if not self.events:return None
        states=[self.events[0].before,*[e.after for e in self.events]]
        # One internal anchor per cell keeps dual nodes continuous across the
        # entire simplification. A nonempty common interior is required here.
        anchors={}
        for cell in self.model.cells[1:]:
            c=cell['id'];common=cap_polygon(states[0],c)
            for m in states[1:]:common=common.intersection(cap_polygon(m,c))
            if common.is_empty or common.area<1e-8:
                raise ValueError('No common interior for a fixed dual anchor; a separate dual-node trajectory is required.')
            p=common.representative_point();anchors[c]=[p.x,p.y,cell['height_m']/2]
        serialized=[]
        for m in states:
            data=m.to_dict()
            for c,p in anchors.items():data['dual_vertices'][c]['position']=p
            serialized.append(deepcopy(data))
        operations=[]
        for event in self.events:
            changed=[v for v,p in enumerate(event.before.vertices) if xy_key(p)==event.source]
            affected_faces=[f['id'] for f in event.before.faces if any(v in changed for v in f['vertices'])]
            samples=[]
            for j in range(samples_per_event):
                model=event.at(j/samples_per_event)
                for c,p in anchors.items():
                    if not cap_polygon(model,c).covers(Point(p[:2])):
                        raise ValueError('A dual anchor leaves a cell during this transition.')
                samples.append(dict(vertices={v:model.vertices[v] for v in changed},
                    cells={c:{'area_m2':model.cells[c]['area_m2'],'volume_m3':model.cells[c]['volume_m3'],'position':anchors[c]}
                           for c in event.affected_cells},
                    render_cache={f:model.faces[f]['render_triangles'] for f in affected_faces}))
            operations.append(dict(source_xy=event.source,target_xy=event.target,
                affected_cells=event.affected_cells,error_m=event.error_m,
                motion_predicate_checks=event.motion_checks,samples=samples))
        return dict(operator='SimplifyFeature',parameter='dimensionless progress; time/scale interpretation is not assigned',
                    samples_per_event=samples_per_event,states=serialized,events=operations,
                    note='Geometry evolves between states; incidence changes only at event commits. Dense half-edge IDs are local to each committed state.')
