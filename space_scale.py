"""Polygonal DHE space-scale constructions for five generalization operations.

Original map caps stay polygons. Transition surfaces are exact planar patches;
noncoplanar swept quads and PL collapse terrain have real triangular event faces.
These are not arbitrary diagonals added to original cap topology.
"""
from __future__ import annotations
from copy import deepcopy
import heapq
import math

from extrude import DHE, Polygon, LineString, bridged_ring, orient
from shapely.geometry import Point
from dhe_ops import Generalizer, cap_polygon, xy_key
from shapely.ops import unary_union


def _cross(a,b):return (a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])
def _sub(a,b):return tuple(x-y for x,y in zip(a,b))
def _norm(a):return math.sqrt(sum(x*x for x in a))
def _dot(a,b):return sum(x*y for x,y in zip(a,b))
def _at(p,z):return (round(p[0],6),round(p[1],6),round(z,6))


class _Builder:
    def __init__(self,scale_end):
        if not math.isfinite(scale_end) or scale_end<=0:raise ValueError('Scale extent must be positive and finite.')
        self.model=DHE();self.raw=[];self.scale_end=scale_end

    def cell(self,fid,polygon,position,lineage=None,expected_volume=None):
        c=self.model.add_cell(str(fid),1,list(position),polygon.area,self.scale_end)
        self.model.cells[c].update(scale_range=[0,self.scale_end],source_feature_ids=lineage or [str(fid)])
        self.model.cells[c]['expected_volume']=expected_volume
        return c

    def face(self,c,coords,kind='transition',rings=None,bridges=None):
        clean=[]
        for p in coords:
            p=tuple(round(x,6) for x in p)
            if not clean or p!=clean[-1]:clean.append(p)
        if len(clean)>1 and clean[-1]==clean[0]:clean.pop()
        if len(set(clean))<3:return
        normal=next((_cross(_sub(clean[j],clean[0]),_sub(clean[j+1],clean[0]))
                     for j in range(1,len(clean)-1)
                     if _norm(_cross(_sub(clean[j],clean[0]),_sub(clean[j+1],clean[0])))>1e-10),None)
        if normal is None:return
        if any(abs(_dot(normal,_sub(p,clean[0])))>1e-7*_norm(normal) for p in clean):
            if len(clean)!=4:raise ValueError('A nonplanar transition patch needs an explicit surface definition.')
            # Both cell sides choose the same diagonal, independent of winding.
            a,b=tuple(sorted((clean[0],clean[2]))),tuple(sorted((clean[1],clean[3])))
            triangles=([clean[0],clean[1],clean[2]],[clean[0],clean[2],clean[3]]) if a<b else (
                [clean[1],clean[2],clean[3]],[clean[1],clean[3],clean[0]])
            for triangle in triangles:self.face(c,triangle,'transition')
            return
        self.raw.append(dict(cell=c,coords=clean,kind=kind,rings=rings,bridges=bridges or []))

    def cap(self,c,polygon,z,kind):
        polygon=orient(polygon,sign=1)
        walk,bridges=bridged_ring(polygon)
        rings=[list(r.coords)[:-1] for r in [polygon.exterior,*polygon.interiors]]
        if kind=='base':walk=walk[::-1];rings=[r[::-1] for r in rings]
        self.face(c,[_at(p,z) for p in walk],kind,rings=[[_at(p,z) for p in r] for r in rings],
                  bridges=[(_at(line.coords[0],z),_at(line.coords[1],z)) for line in bridges])

    def wall(self,c,a,b,z0,z1):
        self.face(c,[_at(a,z0),_at(b,z0),_at(b,z1),_at(a,z1)],'wall')

    def finish(self):
        points=sorted({p for face in self.raw for p in face['coords']})
        def node(ring):
            result=[]
            for a,b in zip(ring,ring[1:]+ring[:1]):
                ab=_sub(b,a);ll=_dot(ab,ab);cuts=[(0,a)]
                for p in points:
                    ap=_sub(p,a);t=_dot(ap,ab)/ll
                    if 1e-9<t<1-1e-9 and _norm(_cross(ap,ab))<2e-6*math.sqrt(ll):cuts.append((t,p))
                result.extend(p for _,p in sorted(cuts))
            return result
        for face in self.raw:
            ring=node(face['coords'])
            rings=[node(r) for r in face['rings']] if face['rings'] else None
            bridges=[]
            for a,b in face['bridges']:
                for u,v in zip(ring,ring[1:]+ring[:1]):
                    if LineString([a,b]).distance(Point(u))<2e-6 and LineString([a,b]).distance(Point(v))<2e-6:
                        bridges.append((self.model.vertex(u),self.model.vertex(v)))
            self.model.add_face(face['cell'],ring,face['kind'],rings=rings,bridge_pairs=bridges)
        for cell in self.model.cells[1:]:
            volume=0.0
            for f in cell['faces']:
                ps=[self.model.vertices[v] for v in self.model.faces[f]['vertices']]
                for j in range(1,len(ps)-1):volume+=_dot(ps[0],_cross(ps[j],ps[j+1]))/6
            expected=cell.pop('expected_volume')
            if volume<=1e-8:raise ValueError('Space-scale cell does not enclose positive scale volume.')
            if expected is not None and not math.isclose(volume,expected,rel_tol=2e-6,abs_tol=2e-5):
                raise ValueError(f'Space-scale volume {volume} differs from independent integral {expected}.')
            cell['volume_m3']=volume
        self.model.finish()
        return self.model


def _rings(p):
    p=orient(p,sign=1)
    return [list(r.coords)[:-1] for r in [p.exterior,*p.interiors]]
def _edges(p):
    for ring in _rings(p):yield from zip(ring,ring[1:]+ring[:1])


def simplify_space_scale(model,feature_id='2001',tolerance_m=2.5,scale_end=10):
    g=Generalizer(model);g.simplify(feature_id,tolerance_m,preserve_coverage=True)
    states=[g.events[0].before if g.events else model,*[e.after for e in g.events]]
    b=_Builder(scale_end);count=len(g.events)+1
    cells={}
    for c in model.cells[1:]:
        p=cap_polygon(model,c['id']);common=p
        for state in states[1:]:common=common.intersection(cap_polygon(state,c['id']))
        q=common.representative_point()
        cells[c['id']]=b.cell(c['feature_id'],p,(q.x,q.y,scale_end/2))
        b.cap(cells[c['id']],p,0,'base')
    for index,event in enumerate(g.events):
        z0,z1=scale_end*index/count,scale_end*(index+1)/count
        for face in event.before.faces:
            if not face['cell'] or face['kind']!='wall':continue
            lower=[event.before.vertices[v] for v in face['vertices']]
            # A wall's first two vertices follow its footprint boundary.
            a,bb=lower[:2]
            def target(p):return event.target if xy_key(p)==event.source else p[:2]
            b.face(cells[face['cell']],[_at(a,z0),_at(bb,z0),_at(target(bb),z1),_at(target(a),z1)],'wall')
    final=g.model;z0=scale_end*(count-1)/count
    for c in final.cells[1:]:
        p=cap_polygon(final,c['id'])
        for a,bb in _edges(p):b.wall(cells[c['id']],a,bb,z0,scale_end)
        b.cap(cells[c['id']],p,scale_end,'roof')
    result=b.finish()
    return result,dict(operation='simplification',feature_id=str(feature_id),tolerance_m=tolerance_m,
        events=[dict(scale=scale_end*(i+1)/count,source_xy=e.source,target_xy=e.target,
                     affected_feature_ids=[str(model.cells[c]['feature_id']) for c in e.affected_cells]) for i,e in enumerate(g.events)],
        coverage_policy='fixed outer boundary; suppress shared degree-two vertices only',
        scale_end=scale_end,endpoint_boundary_counts={c['feature_id']:len(cap_polygon(final,c['id']).exterior.coords)-1 for c in final.cells[1:]})


def merge_space_scale(model,feature_ids,scale_event=5,scale_end=10,new_id=None,operation='merging'):
    ids={str(i) for i in feature_ids}
    selected=[c for c in model.cells[1:] if str(c['feature_id']) in ids]
    if {str(c['feature_id']) for c in selected}!=ids or len(selected)<2:raise ValueError('Select at least two existing features.')
    if not 0<scale_event<scale_end:raise ValueError('Merge scale must lie inside the scale range.')
    # The selected faces must form one component through shared boundaries.
    reached={selected[0]['id']};pending={c['id'] for c in selected}
    while True:
        previous=len(reached)
        for c in selected:
            if any(cap_polygon(model,c['id']).boundary.intersection(cap_polygon(model,j).boundary).length>1e-7 for j in reached):reached.add(c['id'])
        if len(reached)==previous:break
    if reached!=pending:raise ValueError('Aggregation/merge requires a touching, face-connected set; no gap is filled.')
    union=unary_union([cap_polygon(model,c['id']) for c in selected])
    if union.geom_type!='Polygon':raise ValueError('This operator requires one touching polygonal result.')
    new_id=new_id or '+'.join(sorted(ids));b=_Builder(scale_end);cellmap={}
    for c in model.cells[1:]:
        p=cap_polygon(model,c['id']);end=scale_event if c in selected else scale_end;q=p.representative_point()
        target=b.cell(c['feature_id'],p,(q.x,q.y,end/2),expected_volume=p.area*end);cellmap[c['id']]=target
        b.model.cells[target]['scale_range']=[0,end]
        if c in selected:b.model.cells[target]['end_inclusive']=False
        b.cap(target,p,0,'base');b.cap(target,p,end,'roof')
        intervals=[(0,end)] if c in selected else [(0,scale_event),(scale_event,scale_end)]
        for z0,z1 in intervals:
            for a,bb in _edges(p):b.wall(target,a,bb,z0,z1)
    q=union.representative_point()
    merged=b.cell(new_id,union,(q.x,q.y,(scale_event+scale_end)/2),sorted(ids),union.area*(scale_end-scale_event))
    b.model.cells[merged]['scale_range']=[scale_event,scale_end]
    for c in selected:b.cap(merged,cap_polygon(model,c['id']),scale_event,'base')
    b.cap(merged,union,scale_end,'roof')
    for a,bb in _edges(union):b.wall(merged,a,bb,scale_event,scale_end)
    result=b.finish()
    return result,dict(operation=operation,source_feature_ids=sorted(ids),result_feature_id=new_id,
                       event_scale=scale_event,scale_end=scale_end,coverage_policy='exact union; touching features only')


def _collapse_mesh(model,source,dimension,critical):
    roof=next(model.faces[f] for f in model.cells[source]['faces'] if model.faces[f]['kind']=='roof')
    points={v:tuple(model.vertices[v][:2]) for tri in roof['render_triangles'] for v in tri}
    triangles=[list(tri) for tri in roof['render_triangles']]
    if dimension==0:
        chosen=max(range(len(triangles)),key=lambda i:Polygon([points[v] for v in triangles[i]]).area)
        tri=triangles.pop(chosen);root=max(points)+1
        points[root]=tuple(sum(points[v][k] for v in tri)/3 for k in range(2))
        triangles.extend([[tri[0],tri[1],root],[tri[1],tri[2],root],[tri[2],tri[0],root]])
        roots=[root]
    else:
        uses={}
        for tri in triangles:
            for a,bb in zip(tri,tri[1:]+tri[:1]):uses[tuple(sorted((a,bb)))]=uses.get(tuple(sorted((a,bb))),0)+1
        internal=[edge for edge,count in uses.items() if count==2]
        if not internal:raise ValueError('No internal mesh edge is available as a line-collapse target.')
        roots=list(max(internal,key=lambda e:math.dist(points[e[0]],points[e[1]])))
    graph={v:{} for v in points}
    for tri in triangles:
        for a,bb in zip(tri,tri[1:]+tri[:1]):graph[a][bb]=graph[bb][a]=math.dist(points[a],points[bb])
    distance={v:float('inf') for v in points};queue=[]
    for root in roots:distance[root]=0;heapq.heappush(queue,(0,root))
    while queue:
        d,v=heapq.heappop(queue)
        if d!=distance[v]:continue
        for other,length in graph[v].items():
            candidate=d+length
            if candidate<distance[other]:distance[other]=candidate;heapq.heappush(queue,(candidate,other))
    maximum=max(distance.values())
    heights={v:round(critical*(1-0.9*distance[v]/maximum),6) for v in points}
    return points,triangles,heights,roots


def collapse_space_scale(model,feature_id='2001',dimension=0,recipient_id=None,critical_scale=9,scale_end=10):
    if dimension not in (0,1):raise ValueError('Collapse dimension must be 0 (point) or 1 (polyline).')
    if not 0<critical_scale<scale_end:raise ValueError('A positive plateau above the terminal scale is required.')
    selected=[c for c in model.cells[1:] if str(c['feature_id'])==str(feature_id)]
    if len(selected)!=1:raise ValueError('Collapse one polygon component at a time; multipart targets need separate terminal strata.')
    source=selected[0]['id'];p=cap_polygon(model,source)
    neighbours=[(p.boundary.intersection(cap_polygon(model,c['id']).boundary).length,c['id'])
                for c in model.cells[1:] if c['id']!=source]
    neighbours=[pair for pair in neighbours if pair[0]>1e-7]
    if recipient_id is None:
        if not neighbours:raise ValueError('Coverage-preserving collapse needs an adjacent recipient feature.')
        recipient=max(neighbours)[1]
    else:
        recipient=next((c['id'] for c in model.cells[1:] if str(c['feature_id'])==str(recipient_id)),None)
        if recipient not in [c for _,c in neighbours]:raise ValueError('Recipient must share a boundary with the source.')
    q=cap_polygon(model,recipient);union=p.union(q)
    if union.geom_type!='Polygon':raise ValueError('Source and recipient must have a polygonal touching union.')
    points,triangles,heights,roots=_collapse_mesh(model,source,dimension,critical_scale)
    field={xy_key(points[v]):heights[v] for v in points}
    volume=sum(Polygon([points[v] for v in tri]).area*sum(heights[v] for v in tri)/3 for tri in triangles)
    b=_Builder(scale_end);cellmap={}
    for c in model.cells[1:]:
        polygon=cap_polygon(model,c['id']);r=polygon.representative_point()
        if c['id']==source:
            tri=max(triangles,key=lambda t:sum(heights[v] for v in t))
            center=[sum(points[v][k] for v in tri)/3 for k in range(2)];center.append(sum(heights[v] for v in tri)/6)
            expected=volume
        else:center=[r.x,r.y,scale_end/2];expected=(union.area*scale_end-volume) if c['id']==recipient else polygon.area*scale_end
        cellmap[c['id']]=b.cell(c['feature_id'],polygon,center,expected_volume=expected)
        b.cap(cellmap[c['id']],polygon,0,'base')
        if c['id']!=source:b.cap(cellmap[c['id']],union if c['id']==recipient else polygon,scale_end,'roof')
    for tri in triangles:
        coords=[_at(points[v],heights[v]) for v in tri]
        # Render-cache triangles were oriented as a positive roof.
        b.face(cellmap[source],coords,'transition');b.face(cellmap[recipient],coords[::-1],'transition')
    source_edges={tuple(sorted((xy_key(a),xy_key(bb)))) for a,bb in _edges(p)}
    for c in model.cells[1:]:
        polygon=cap_polygon(model,c['id']);owner=c['id'];target=cellmap[owner]
        for a,bb in _edges(polygon):
            shared=tuple(sorted((xy_key(a),xy_key(bb)))) in source_edges
            if owner==source:
                ha,hb=field[xy_key(a)],field[xy_key(bb)]
                lower=[_at(a,0),_at(bb,0),_at(bb,hb),_at(a,ha)]
                b.face(target,lower,'wall')
                # The upper part of every former source boundary is inherited
                # by the recipient unless both sides already belong to it.
                old_neighbour=next((other['id'] for other in model.cells[1:] if other['id']!=source and
                    cap_polygon(model,other['id']).boundary.covers(LineString([a,bb]))),0)
                if old_neighbour!=recipient:
                    b.face(cellmap[recipient],[_at(a,ha),_at(bb,hb),_at(bb,scale_end),_at(a,scale_end)],'wall')
            elif shared:
                ha,hb=field[xy_key(a)],field[xy_key(bb)]
                b.face(target,[_at(a,0),_at(bb,0),_at(bb,hb),_at(a,ha)],'wall')
                if owner!=recipient:b.face(target,[_at(a,ha),_at(bb,hb),_at(bb,scale_end),_at(a,scale_end)],'wall')
            else:b.wall(target,a,bb,0,scale_end)
    result=b.finish()
    result.cells[cellmap[source]]['scale_range']=[0,critical_scale]
    terminal=[_at(points[v],critical_scale) for v in roots]
    return result,dict(operation='collapse_to_point' if dimension==0 else 'collapse_to_polyline',
        feature_id=str(feature_id),recipient_feature_id=str(model.cells[recipient]['feature_id']),
        critical_scale=critical_scale,scale_end=scale_end,terminal_dimension=dimension,terminal_geometry=terminal,
        coverage_policy='fixed union; all released area assigned to the adjacent recipient',
        transition_geometry='piecewise-linear distance terrain; unique maximum point or connected maximum edge',
        post_terminal='source absorbed above the critical scale; terminal geometry is recorded at the event',
        source_caps='original polygon base retained; no terminal polygon cap is fabricated')


def aggregate_space_scale(model,feature_ids,scale_event=5,scale_end=10,new_id=None):
    return merge_space_scale(model,feature_ids,scale_event,scale_end,new_id or 'aggregate:'+','.join(map(str,feature_ids)),operation='aggregation')
