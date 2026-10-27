"""Operation-specific targets; transition construction is operation independent."""
from dataclasses import dataclass

from extrude import Polygon, LineString, constrained_delaunay_triangles, orient
from shapely.geometry import Point,shape,GeometryCollection
from shapely import wkt,set_precision
from shapely.ops import unary_union


def polygonal(g):
    if g.is_empty:return Polygon()
    if g.geom_type in ('Polygon','MultiPolygon'):return g
    return unary_union([p for p in getattr(g,'geoms',[]) if p.geom_type in ('Polygon','MultiPolygon')])


def parse_target(value):
    if value is None or value=='':return None
    if isinstance(value,str):return wkt.loads(value)
    if hasattr(value,'geom_type'):return value
    return shape(value)


def automatic_target(source,kind):
    if kind=='point':return source.representative_point()
    if kind=='boundary':return source.boundary
    triangles=list(constrained_delaunay_triangles(source).geoms)
    edges={}
    for tri in triangles:
        ps=list(tri.exterior.coords)[:-1]
        for a,b in zip(ps,ps[1:]+ps[:1]):
            key=tuple(sorted((tuple(a),tuple(b))));edges[key]=edges.get(key,0)+1
    internal=[LineString(edge) for edge,count in edges.items() if count==2]
    if internal:return max(internal,key=lambda line:line.length)
    p=source.representative_point();a=list(source.exterior.coords)[0]
    return LineString([p.coords[0],((p.x+a[0])/2,(p.y+a[1])/2)])


@dataclass
class TargetPlan:
    operation:str
    selected:list
    winner:str|None
    source:dict
    target:dict
    symbols:dict
    requested:dict
    details:dict


def plan_targets(source,operation,selected,winner=None,target=None,targets=None,tolerance=2.5,loser_kind='point',recipient=None):
    selected=list(dict.fromkeys(str(i) for i in selected));winner=str(winner) if winner is not None else (selected[0] if selected else None)
    if not selected:raise ValueError('Select at least one source feature.')
    if any(i not in source for i in selected):raise ValueError('Selected ID is not loaded.')
    if winner not in selected:raise ValueError('Winner must be one of the selected IDs.')
    target_map=dict(source);symbols={};requested={};details={}
    explicit={str(i):parse_target(g) for i,g in (targets or {}).items()}
    one=parse_target(target)
    def symbol(fid,g,kind):
        g=g if g is not None else automatic_target(source[fid],kind)
        allowed=('Point',) if kind=='point' else ('LineString','MultiLineString')
        if g.geom_type not in allowed or g.is_empty or not g.is_valid:raise ValueError(f'{fid}: expected a valid {kind} target.')
        if not source[fid].covers(g):raise ValueError(f'{fid}: target must be inside its source, including its boundary.')
        symbols[fid]=g;requested[fid]=g;target_map[fid]=Polygon()
    if operation=='simplification' or operation=='custom':
        if len(selected)!=1:raise ValueError('Select one source for simplification/custom target.')
        fid=selected[0]
        if tolerance<0:raise ValueError('Simplification tolerance must be nonnegative.')
        g=one or explicit.get(fid)
        if g is None:g=source[fid].simplify(tolerance,preserve_topology=True)
        if g.geom_type not in ('Polygon','MultiPolygon') or not g.is_valid or g.is_empty:raise ValueError('A polygon target is required.')
        target_map[fid]=g;requested[fid]=g
        lost=source[fid].difference(g)
        neighbours=[(source[fid].boundary.intersection(p.boundary).length,i) for i,p in source.items() if i!=fid]
        neighbours=[(length,i) for length,i in neighbours if length>1e-7]
        receiver=str(recipient) if recipient is not None else max(neighbours,default=(0,None))[1]
        if receiver is not None and receiver not in [i for _,i in neighbours]:raise ValueError('Recipient must be adjacent to the source.')
        for i in source:
            if i!=fid:target_map[i]=polygonal(source[i].difference(g))
        if receiver is not None:target_map[receiver]=polygonal(target_map[receiver].union(lost))
        details['released_area_recipient']=receiver or 'EXTERIOR'
    elif operation=='merge':
        if len(selected)<2:raise ValueError('Merging needs at least two selected features.')
        reached={selected[0]}
        while True:
            before=len(reached)
            reached.update(i for i in selected if any(source[i].boundary.intersection(source[j].boundary).length>1e-7 for j in reached.copy()))
            if len(reached)==before:break
        if set(selected)!=reached:raise ValueError('Merging sources must be adjacent; use aggregation for separated polygons.')
        union=unary_union([source[i] for i in selected]);target_map[winner]=union;requested[winner]=union
        for fid in selected:
            if fid!=winner:symbol(fid,explicit.get(fid) or (one if len(selected)==2 else None),loser_kind)
    elif operation in ('point','polyline'):
        if len(selected)!=1:raise ValueError('Select one source to collapse.')
        fid=selected[0];symbol(fid,one or explicit.get(fid),'point' if operation=='point' else 'polyline')
        neighbours=[(source[fid].boundary.intersection(p.boundary).length,i) for i,p in source.items() if i!=fid]
        neighbours=[(length,i) for length,i in neighbours if length>1e-7]
        receiver=str(recipient) if recipient is not None else max(neighbours,default=(0,None))[1]
        if receiver is not None:
            if receiver not in [i for _,i in neighbours]:raise ValueError('Recipient must be adjacent to the source.')
            target_map[receiver]=polygonal(target_map[receiver].union(source[fid]))
        details['released_area_recipient']=receiver or 'EXTERIOR'
    elif operation=='aggregation':
        if len(selected)<2:raise ValueError('Aggregation needs at least two selected polygons.')
        union=unary_union([source[i] for i in selected]);g=one or union.convex_hull
        if g.geom_type!='Polygon' or not g.is_valid or not g.covers(union):raise ValueError('Outward aggregation target must be a polygon covering all selected sources.')
        target_map[winner]=g;requested[winner]=g
        for fid in selected:
            if fid!=winner:target_map[fid]=Polygon()
        for fid in source:
            if fid not in selected:target_map[fid]=polygonal(source[fid].difference(g))
    else:raise ValueError('Unknown operation.')
    for fid,g in target_map.items():
        if not g.is_valid:raise ValueError(f'Target map contains invalid geometry for {fid}.')
    items=[(i,g) for i,g in target_map.items() if not g.is_empty]
    for k,(i,a) in enumerate(items):
        if any(a.intersection(b).area>1e-7 for _,b in items[k+1:]):raise ValueError(f'Target ownership overlaps at feature {i}.')
    return TargetPlan(operation,selected,winner,source,target_map,symbols,requested,details)
