"""Boundary surgery on lifted transition wedges, retaining the DHE edge fans.

Internal faces are removed by following Sym/Across fans. Coplanar face pairs
are joined by NF splices (KEF); dispensable dangling branches and collinear
vertices are suppressed. Explicit Sym permits non-manifold terminal line fans.
"""
from collections import defaultdict
import math

from extrude import DHE, Polygon, orient, constrained_delaunay_triangles
from shapely.ops import unary_union


def sub(a,b):return tuple(x-y for x,y in zip(a,b))
def cross(a,b):return (a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])
def dot(a,b):return sum(x*y for x,y in zip(a,b))
def norm(a):return math.sqrt(dot(a,a))
def plane(coords):
    n=next(cross(sub(coords[j],coords[0]),sub(coords[j+1],coords[0])) for j in range(1,len(coords)-1)
           if norm(cross(sub(coords[j],coords[0]),sub(coords[j+1],coords[0])))>1e-12)
    n=tuple(v/norm(n) for v in n);d=dot(n,coords[0])
    sign=next((1 if x>0 else -1 for x in n if abs(x)>1e-8),1)
    canonical=tuple(round(sign*x,8) for x in n)+(round(sign*d,6),)
    return n,d,canonical


class WedgeBoundary:
    def __init__(self):
        self.vertices=[];self.index={};self.edges=[];self.faces=[];self.fragments=[]
        self.protected=set()

    def vertex(self,p):
        p=tuple(round(float(x),6) for x in p)
        if p not in self.index:self.index[p]=len(self.vertices);self.vertices.append(p)
        return self.index[p]

    def fragment(self,owner,xy,lower,upper):
        if owner is None:return
        bottom=[self.vertex((*p,z)) for p,z in zip(xy,lower)]
        top=[self.vertex((*p,z)) for p,z in zip(xy,upper)]
        volume=Polygon(xy).area*sum(b-a for a,b in zip(lower,upper))/3
        if volume<1e-10:return
        frag=len(self.fragments);fs=[]
        candidates=[bottom[::-1],top,*[[bottom[i],bottom[(i+1)%3],top[(i+1)%3],top[i]] for i in range(3)]]
        local={}
        for walk in candidates:
            vs=[]
            for v in walk:
                if not vs or v!=vs[-1]:vs.append(v)
            if len(vs)>1 and vs[0]==vs[-1]:vs.pop()
            if len(set(vs))<3:continue
            coords=[self.vertices[v] for v in vs]
            try:normal,d,key=plane(coords)
            except StopIteration:continue
            f=len(self.faces);start=len(self.edges);es=list(range(start,start+len(vs)))
            self.faces.append(dict(edges=es,owner=owner,fragment=frag,plane=key,normal=normal,d=d,vertices=vs))
            fs.append(f)
            for j,v in enumerate(vs):
                e=es[j];dst=vs[(j+1)%len(vs)]
                self.edges.append(dict(V=v,NF=es[(j+1)%len(vs)],prev=es[j-1],S=-1,face=f))
                if (v,dst) in local:raise ValueError('Degenerate lifted wedge has duplicate directed edges.')
                local[v,dst]=e
        for (a,b),e in local.items():
            if (b,a) not in local:raise ValueError('A lifted wedge has an open edge at coordinate precision.')
            self.edges[e]['S']=local[b,a]
        allvs=set(bottom+top);center=[sum(self.vertices[v][k] for v in allvs)/len(allvs) for k in range(3)]
        self.fragments.append(dict(owner=owner,faces=fs,volume=volume,position=center,xy=xy))

    def finish(self,feature_order,source_shapes,scale_extent):
        E=self.edges;F=self.faces
        groups=defaultdict(list)
        for f,face in enumerate(F):groups[tuple(sorted(face['vertices']))].append(f)
        across={};internal=set();other={}
        for fs in groups.values():
            if len(fs)>2:raise ValueError(f'More than two wedge faces coincide: {[(F[f]["owner"], F[f]["fragment"], self.fragments[F[f]["fragment"]]["xy"]) for f in fs]}.')
            if len(fs)==2:
                a,b=fs
                back={(E[e]['V'],E[E[e]['NF']]['V']):e for e in F[b]['edges']}
                for e in F[a]['edges']:
                    key=(E[E[e]['NF']]['V'],E[e]['V'])
                    if key not in back:raise ValueError('Wedge face winding mismatch.')
                    q=back[key];across[e]=q;across[q]=e
                if F[a]['owner']==F[b]['owner']:internal.update(fs)
                other[a]=F[b]['owner'];other[b]=F[a]['owner']
            else:other[fs[0]]=None
        active={e for f,face in enumerate(F) if f not in internal for e in face['edges']}
        old_s=[e['S'] for e in E]
        for e in active:
            q=old_s[e];seen=set()
            while E[q]['face'] in internal:
                if q in seen:raise ValueError('Internal face fan does not reach the boundary.')
                seen.add(q);q=old_s[across[q]]
            E[e]['S']=q
        parent=list(range(len(F)))
        def root(f):
            while parent[f]!=f:parent[f]=parent[parent[f]];f=parent[f]
            return f
        geometry_key=lambda e:tuple(sorted((self.vertices[E[e]['V']],self.vertices[E[E[e]['NF']]['V']])))
        pairs=sorted((e for e in active if e<E[e]['S']),key=geometry_key)
        surgeries=0
        for e in pairs:
            if e not in active:continue
            s=E[e]['S'];a,b=root(E[e]['face']),root(E[s]['face'])
            if a==b or F[a]['plane']!=F[b]['plane'] or other[a]!=other[b]:continue
            if dot(F[a]['normal'],F[b]['normal'])<0.999999:continue
            if any(abs(dot(F[a]['normal'],self.vertices[v])-F[a]['d'])>2e-6 for v in F[b]['vertices']):continue
            pa,pb=E[e]['prev'],E[s]['prev'];na,nb=E[e]['NF'],E[s]['NF']
            E[pa]['NF']=nb;E[nb]['prev']=pa;E[pb]['NF']=na;E[na]['prev']=pb
            parent[b]=a;active.remove(e);active.remove(s);surgeries+=1
        # KVE of a dangling unprotected leaf inside one coalesced planar face.
        while True:
            outgoing=defaultdict(list)
            for e in active:outgoing[E[e]['V']].append(e)
            removed=False
            for e in sorted(active,key=geometry_key):
                s=E[e]['S'];v=E[s]['V']
                if E[e]['NF']!=s or v in self.protected:continue
                current=root(E[e]['face'])
                if any(F[root(E[q]['face'])]['plane']!=F[current]['plane'] for q in outgoing[v]):continue
                if any(root(E[q]['face'])==current and q!=s for q in outgoing[v]):continue
                p,nxt=E[e]['prev'],E[s]['NF']
                E[p]['NF']=nxt;E[nxt]['prev']=p;active.remove(e);active.remove(s);removed=True;break
            if not removed:break
        # Remove degree-two collinear vertices left by mesh subdivision. Their
        # two face loops and Sym pairing are spliced in one transaction.
        while True:
            outgoing=defaultdict(list)
            for e in active:outgoing[E[e]['V']].append(e)
            removed=False
            for v,outs in outgoing.items():
                if v in self.protected or len(outs)!=2:continue
                k,sh=outs;h=E[sh]['S'];sk=E[k]['S']
                if len({h,k,sh,sk})!=4 or E[h]['NF']!=k or E[sk]['NF']!=sh:continue
                a,b=self.vertices[E[h]['V']],self.vertices[E[sk]['V']];p=self.vertices[v]
                if norm(cross(sub(p,a),sub(b,a)))>2e-6*max(norm(sub(b,a)),1):continue
                E[h]['NF']=E[k]['NF'];E[E[k]['NF']]['prev']=h
                E[sk]['NF']=E[sh]['NF'];E[E[sh]['NF']]['prev']=sk
                E[h]['S']=sk;E[sk]['S']=h;active.remove(k);active.remove(sh);removed=True;break
            if not removed:break
        # Every resulting face is an NF orbit; preserve bridges/spines in that
        # orbit while deriving its geometric rings from the union of old facets.
        face_walks=[];visited=set()
        for e in sorted(active):
            if e in visited:continue
            walk=[];at=e
            while at not in visited:
                if at not in active:raise ValueError('A face splice points to a retired half-edge.')
                visited.add(at);walk.append(at);at=E[at]['NF']
            if at!=e:raise ValueError('A face orbit does not close.')
            face_walks.append(walk)
        face_of={e:i for i,walk in enumerate(face_walks) for e in walk}
        components=[];seen=set()
        for i,walk in enumerate(face_walks):
            if i in seen:continue
            stack=[i];seen.add(i);part=[]
            while stack:
                f=stack.pop();part.append(f)
                for e in face_walks[f]:
                    q=face_of[E[e]['S']]
                    if q not in seen:seen.add(q);stack.append(q)
            components.append(part)
        owner_rank={fid:i for i,fid in enumerate(feature_order)}
        components.sort(key=lambda part:(owner_rank.get(F[E[face_walks[part[0]][0]]['face']]['owner'],9999),min(part)))
        result=DHE();exported_edges={};part_counts=defaultdict(int)
        by_root=defaultdict(list)
        for f,face in enumerate(F):
            if f not in internal:by_root[root(f)].append(face)
        for part in components:
            first=face_walks[part[0]][0];owner=F[E[first]['face']]['owner'];part_counts[owner]+=1
            fragment=self.fragments[F[E[first]['face']]['fragment']]
            source=source_shapes.get(owner,Polygon())
            c=result.add_cell(owner,part_counts[owner],fragment['position'],source.area,scale_extent)
            for f in part:
                walk=face_walks[f];r=root(E[walk[0]]['face']);normal=F[r]['normal']
                ref=(0,1,0) if abs(normal[1])<0.95 else (1,0,0)
                u=cross(ref,normal);u=tuple(x/norm(u) for x in u);v=cross(normal,u);origin=self.vertices[E[walk[0]]['V']]
                project=lambda p:(dot(sub(p,origin),u),dot(sub(p,origin),v))
                geometry=unary_union([Polygon([project(self.vertices[x]) for x in old['vertices']]) for old in by_root[r]])
                if geometry.geom_type!='Polygon':raise ValueError('Coalesced face has disconnected geometry.')
                geometry=orient(geometry.simplify(1e-7,preserve_topology=True),sign=1)
                def lift(p):return tuple(origin[k]+p[0]*u[k]+p[1]*v[k] for k in range(3))
                def snap(p):
                    key=tuple(round(x,6) for x in p)
                    if key in self.index:return self.vertices[self.index[key]]
                    # Plane projection may accumulate sub-micrometre roundoff.
                    for old in self.vertices:
                        if norm(sub(old,p))<2e-6:return old
                    raise ValueError('A render-cache coordinate is not a DHE vertex.')
                coords=[self.vertices[E[e]['V']] for e in walk]
                kind=('roof' if normal[2]>0 else 'base') if abs(abs(normal[2])-1)<1e-7 else 'wall' if abs(normal[2])<1e-7 else 'transition'
                rings=[[snap(lift(p)) for p in list(ring.coords)[:-1]] for ring in [geometry.exterior,*geometry.interiors]]
                bridges=[(result.vertex(self.vertices[E[e]['V']]),result.vertex(self.vertices[E[E[e]['NF']]['V']])) for e in walk if face_of[E[e]['S']]==f]
                new=result.add_face(c,coords,kind,rings=rings,bridge_pairs=bridges)
                # Keep the EXACT constituent surface mesh in a separate XYZ
                # cache. Re-triangulating a projected polygon can perturb a
                # microscopic intersection and open cracks for plane slicing.
                # Cache vertices are not restored as topological DHE vertices.
                triangles=[]
                for old in by_root[r]:
                    ps=[self.vertices[x] for x in old['vertices']]
                    triangles.extend([[ps[0],ps[j],ps[j+1]] for j in range(1,len(ps)-1)])
                result.faces[new]['render_xyz']=triangles
                reference=next((v for v in result.faces[new]['vertices'] if abs(result.vertices[v][2])>1e-12),None)
                result.faces[new]['render_reference']=[reference,result.vertices[reference][2]] if reference is not None else None
                for old,new_e in zip(walk,result.faces[new]['half_edges']):exported_edges[old]=new_e
            volume=0
            for f in result.cells[c]['faces']:
                ps=[result.vertices[x] for x in result.faces[f]['vertices']]
                volume+=sum(dot(ps[0],cross(ps[j],ps[j+1]))/6 for j in range(1,len(ps)-1))
            if volume<=1e-9:raise ValueError('A boundary component is a cavity or degenerates; a cavity bridge is required.')
            result.cells[c]['volume_m3']=volume
        sym={new:exported_edges[E[old]['S']] for old,new in exported_edges.items()}
        result.finish(explicit_sym=sym)
        expected=defaultdict(float);actual=defaultdict(float)
        for frag in self.fragments:expected[frag['owner']]+=frag['volume']
        for c in result.cells[1:]:actual[c['feature_id']]+=c['volume_m3']
        for owner,volume in expected.items():
            if not math.isclose(volume,actual[owner],rel_tol=1e-5,abs_tol=1e-4):raise ValueError(f'Wedge integral/closed-shell volume mismatch for {owner}.')
        result.surgery_stats=dict(internal_faces_removed=len(internal),coplanar_KEF=surgeries,fragments=len(self.fragments))
        return result
