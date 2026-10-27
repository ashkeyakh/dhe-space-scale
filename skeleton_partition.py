"""True straight-skeleton outward-wavefront partitions, clipped to a target.

An enclosing frame places selected polygon components as holes. The holes'
wavefronts expand outwards. Frame-owned faces must not reach the target; this
is checked, and a larger frame is retried. No Voronoi/nearest-site fallback.
"""
from collections import defaultdict

from extrude import Polygon,LineString,orient
from shapely.geometry import box,mapping
from shapely.ops import unary_union
from py_straight_skeleton import compute_skeleton


def _polygons(g):return list(g.geoms) if g.geom_type=='MultiPolygon' else [g]


def outward_partition(sources,target):
    union=unary_union(list(sources.values()))
    if target.geom_type!='Polygon' or not target.covers(union):raise ValueError('Skeleton target must contain all selected source polygons.')
    xmin,ymin,xmax,ymax=target.bounds;span=max(xmax-xmin,ymax-ymin,1);cx=(xmin+xmax)/2;cy=(ymin+ymax)/2
    norm=lambda p:((p[0]-cx)/span*100,(p[1]-cy)/span*100)
    world=lambda p:(p.x*span/100+cx,p.y*span/100+cy)
    components=[orient(p,sign=1) for p in _polygons(union)]
    def engine(exterior,holes,clip):
        skeleton=compute_skeleton([norm(p) for p in exterior],[[norm(p) for p in ring] for ring in holes])
        owned=defaultdict(list);foreign=[]
        for face in skeleton.get_faces():
            xy=[world(skeleton.nodes[i].position) for i in face]
            polygon=Polygon(xy)
            if not polygon.is_valid:polygon=polygon.buffer(0)
            polygon=polygon.intersection(clip)
            if polygon.is_empty or polygon.area<1e-10:continue
            edge=LineString(xy[:2]);matches=[(g.boundary.intersection(edge).length,fid) for fid,g in sources.items()]
            length,fid=max(matches)
            if length<1e-6:
                # A source edge may differ by roundoff after normalization.
                length,fid=max((g.boundary.buffer(1e-6).intersection(edge).length,i) for i,g in sources.items())
            if length<min(edge.length*0.5,1e-5):foreign.append(polygon)
            else:owned[fid].append(polygon)
        arcs=[]
        for a,b in skeleton.arc_iterator():
            line=LineString([world(a.position),world(b.position)]).intersection(clip)
            if not line.is_empty:arcs.append(mapping(line))
        return owned,foreign,arcs
    gap=target.difference(union);last_error=None
    for factor in (10,40,160):
        frame=box(xmin-span*factor,ymin-span*factor,xmax+span*factor,ymax+span*factor)
        exterior=list(orient(frame,sign=1).exterior.coords)[:-1]
        holes=[list(p.exterior.coords)[:-1][::-1] for p in components]
        try:
            owned,foreign,arcs=engine(exterior,holes,gap)
            # Courtyards are independent void wavefront domains.
            for component in components:
                for ring in component.interiors:
                    courtyard=Polygon(ring).intersection(target)
                    if courtyard.area<1e-10:continue
                    o,f,a=engine(list(orient(Polygon(ring),sign=1).exterior.coords)[:-1],[],courtyard)
                    for fid,polygons in o.items():owned[fid].extend(polygons)
                    foreign.extend(f);arcs.extend(a)
            if sum(p.area for p in foreign)>max(1e-5,target.area*1e-8):
                raise ValueError('Enclosing-frame wavefront reaches the aggregation target.')
            partitions={fid:unary_union([source,*owned.get(fid,[])]).intersection(target) for fid,source in sources.items()}
            joined=unary_union(list(partitions.values()));error=joined.symmetric_difference(target).area
            overlap=sum(p.area for p in partitions.values())-joined.area
            if error>max(1e-4,target.area*1e-7) or overlap>max(1e-4,target.area*1e-7):
                raise ValueError(f'Straight-skeleton faces do not partition the target (gap {error}, overlap {overlap}).')
            return partitions,dict(engine='py_straight_skeleton 0.1.0',method='outward hole wavefronts; frame faces excluded',
                frame_factor=factor,coverage_error_m2=error,overlap_m2=overlap,arcs=arcs,
                partitions={fid:mapping(p) for fid,p in partitions.items()})
        except (RuntimeError,ValueError,AssertionError,KeyError) as error:last_error=error
    raise ValueError(f'True straight-skeleton partition failed: {last_error}')
