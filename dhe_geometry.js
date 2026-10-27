/* Pure DHE navigation and plane/shell intersection; also usable in Node tests. */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.DHEGeometry = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';
  const add = (a,b) => a.map((v,i)=>v+b[i]);
  const sub = (a,b) => a.map((v,i)=>v-b[i]);
  const mul = (a,s) => a.map(v=>v*s);
  const dot = (a,b) => a.reduce((s,v,i)=>s+v*b[i],0);
  const cross = (a,b) => [a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]];
  const norm = a => Math.hypot(...a);
  const unit = a => mul(a,1/norm(a));
  function orbit(H,start,pointer) {
    const out=[], seen=new Set(); let e=start;
    while (!seen.has(e)) {
      if (!H[e] || out.length>H.length) throw Error('Broken DHE orbit');
      seen.add(e);out.push(e);e=H[e][pointer];
    }
    if (e!==start) throw Error('DHE orbit does not close');
    return out;
  }
  function navigate(H,e,op) {
    const adjacent = i => H[H[H[H[i].D].NF].D].S;
    if (op==='a') return adjacent(e);
    if (op==='e') return H[adjacent(e)].S;
    if (op==='o') return adjacent(H[adjacent(e)].NF);
    const p={f:'NF',s:'S',d:'D',v:'NV'}[op];
    if (!p) throw Error('Unknown navigation operator');
    return H[e][p];
  }
  function connectedDuals(model) {
    const H=model.half_edges,n=model.primal_half_edge_count;
    const groups=new Map();
    // Inspect real DHE edge endpoints. Never infer adjacency from distance.
    for (let i=n;i<H.length;i++) {
      const a=H[i].V,b=H[H[i].S].V;
      if (!a || !b || a===b) continue;
      const key=[a,b].sort((x,y)=>x-y).join(':');
      if (!groups.has(key)) groups.set(key,{cells:[Math.min(a,b),Math.max(a,b)],half_edges:[]});
      groups.get(key).half_edges.push(i);
    }
    return [...groups.values()];
  }
  function bounds(points) {
    return [0,1,2].map(k=>[Math.min(...points.map(p=>p[k])),Math.max(...points.map(p=>p[k]))]);
  }
  function makePlane(points,kind,position,tilt=45,azimuth=0) {
    const box=bounds(points),center=box.map(([a,b])=>(a+b)/2);
    const t=(kind==='horizontal'?0:kind==='vertical'?90:tilt)*Math.PI/180;
    const a=azimuth*Math.PI/180;
    const normal=[Math.sin(t)*Math.cos(a),Math.sin(t)*Math.sin(a),Math.cos(t)].map(x=>Math.abs(x)<1e-12?0:x);
    const u=unit(cross(Math.abs(normal[1])>0.95?[1,0,0]:[0,1,0],normal));
    const v=cross(normal,u);
    const projected=points.map(p=>dot(sub(p,center),normal));
    const range=[Math.min(...projected),Math.max(...projected)];
    const offset=kind==='horizontal'?position-center[2]:position;
    const origin=add(center,mul(normal,offset));
    return {kind,normal,u,v,origin,center,offset,
      range:kind==='horizontal'?[box[2][0],box[2][1]]:range,
      position,tilt:kind==='horizontal'?0:kind==='vertical'?90:tilt,azimuth};
  }
  function triangleSegments(triangle,plane,eps) {
    const d=triangle.map(p=>dot(sub(p,plane.origin),plane.normal));
    if (d.every(v=>Math.abs(v)<eps)) return {coplanar:true,segments:triangle.map((p,i)=>[p,triangle[(i+1)%3]]),isolated:[]};
    const points=[];
    const push=p=>{if (!points.some(q=>norm(sub(p,q))<eps)) points.push(p);};
    triangle.forEach((p,i)=>{
      const j=(i+1)%3;
      if (Math.abs(d[i])<eps) push(p);
      if (d[i]*d[j]<0 && Math.abs(d[i])>=eps && Math.abs(d[j])>=eps)
        push(add(p,mul(sub(triangle[j],p),d[i]/(d[i]-d[j]))));
    });
    return {coplanar:false,segments:points.length===2 && norm(sub(points[0],points[1]))>eps?[[points[0],points[1]]]:[],isolated:points.length===1?points:[],edgeOnPlane:d.filter(x=>Math.abs(x)<eps).length>=2};
  }
  const area2 = ring => ring.reduce((s,p,i)=>{const q=ring[(i+1)%ring.length];return s+p[0]*q[1]-q[0]*p[1];},0)/2;
  function inside(p,ring) {
    let yes=false;
    for(let i=0,j=ring.length-1;i<ring.length;j=i++) {
      const a=ring[i],b=ring[j];
      if ((a[1]>p[1])!==(b[1]>p[1]) && p[0]<(b[0]-a[0])*(p[1]-a[1])/(b[1]-a[1])+a[0]) yes=!yes;
    }
    return yes;
  }
  function inClosedShell(p,triangles,eps) {
    // Boundary-inclusive solid containment. Used only when the slicing plane
    // coincides with shell facets, to remove seams inside the planar section.
    const ray=unit([0.823,0.457,0.337]),hits=[];
    for(const [a,b,c] of triangles){
      const u=sub(b,a),v=sub(c,a),w=sub(p,a),normal=cross(u,v),nn=norm(normal);
      if(nn<1e-15)continue;
      const den=dot(normal,normal);
      if(Math.abs(dot(w,normal))<=eps*nn){
        const s=dot(cross(w,v),normal)/den,t=dot(cross(u,w),normal)/den;
        const tol=eps/Math.max(1,norm(u),norm(v));
        if(s>=-tol&&t>=-tol&&s+t<=1+tol)return true;
      }
      const h=cross(ray,v),det=dot(u,h);
      if(Math.abs(det)<1e-12)continue;
      const inv=1/det,s=dot(w,h)*inv;
      if(s<0||s>1)continue;
      const q=cross(w,u),t=dot(ray,q)*inv;
      if(t<0||s+t>1)continue;
      const distance=dot(v,q)*inv;
      if(distance>eps&&!hits.some(x=>Math.abs(x-distance)<eps))hits.push(distance);
    }
    return hits.length%2===1;
  }
  function faceTriangles(face,points) {
    if(face.render_xyz){const ref=face.render_reference,factor=ref?points[ref[0]][2]/ref[1]:1;return face.render_xyz.map(t=>t.map(p=>[p[0],p[1],p[2]*factor]));}
    const ids=face.render_triangles||face.vertices.slice(1,-1).map((v,j)=>[face.vertices[0],v,face.vertices[j+2]]);
    return ids.map(t=>t.map(v=>points[v]));
  }
  function sliceModel(model,points,plane) {
    const box=bounds(points),eps=Math.max(1,...box.map(([a,b])=>b-a))*1e-11;
    const buckets=new Map();let nextPoint=0;
    const pointKey=p=>{
      const bin=p.map(x=>Math.floor(x/eps));
      // Quantization alone can put numerically identical intersections on
      // opposite bin boundaries. Search neighbouring buckets before interning.
      for(let x=-1;x<=1;x++)for(let y=-1;y<=1;y++)for(let z=-1;z<=1;z++){
        const nearby=buckets.get([bin[0]+x,bin[1]+y,bin[2]+z].join(','));
        if(nearby)for(const q of nearby)if(norm(sub(p,q.p))<eps)return q.key;
      }
      const bucket=bin.join(','),key=String(nextPoint++);
      if(!buckets.has(bucket))buckets.set(bucket,[]);buckets.get(bucket).push({p,key});return key;
    };
    const segmentKey=(a,b)=>[pointKey(a),pointKey(b)].sort().join('|');
    const result=[];
    for (const cell of model.dual_vertices.slice(1)) {
      if(cell.end_inclusive===false&&Math.abs(plane.normal[0])+Math.abs(plane.normal[1])<1e-10){
        const end=Math.max(...cell.faces.flatMap(f=>model.faces[f].vertices.map(v=>points[v][2])));
        if(plane.origin[2]>=end-eps)continue;
      }
      const horizontalEndpoint=Math.abs(plane.normal[0])+Math.abs(plane.normal[1])<1e-10&&
        (Math.abs(plane.origin[2]-box[2][0])<eps||Math.abs(plane.origin[2]-box[2][1])<eps);
      if(horizontalEndpoint){
        // A section on a closed endpoint is its actual B-rep cap. Use the
        // geometric face rings, avoiding internal render-mesh seams and skinny
        // facets. Point/line terminals have no cap and follow the path below.
        const caps=cell.faces.map(f=>model.faces[f]).filter(f=>
          f.rings&&f.vertices.every(v=>Math.abs(points[v][2]-plane.origin[2])<eps));
        const loops=caps.flatMap(f=>(f.rings||[f.vertices]).map(r=>{
          const ps=r.map(v=>points[v]);return {points:[...ps,ps[0]],
            uv:ps.map(p=>[dot(sub(p,plane.origin),plane.u),dot(sub(p,plane.origin),plane.v)])};
        })).filter(l=>l.points.length>3&&Math.abs(area2(l.uv))>eps*eps);
        if(loops.length){
          loops.forEach(l=>l.area=Math.abs(area2(l.uv)));loops.sort((a,b)=>b.area-a.area);
          loops.forEach((l,i)=>l.depth=loops.slice(0,i).filter(o=>inside(l.uv[0],o.uv)).length);
          const segments=loops.flatMap(l=>l.points.slice(1).map((p,i)=>[l.points[i],p]));
          result.push({cell:cell.id,feature_id:cell.feature_id,segments,points:[],loops,open:[],
            area:loops.reduce((s,l)=>s+(l.depth%2?-1:1)*l.area,0)});
          continue;
        }
      }
      const segments=new Map(),coplanar=[],triangles=[],isolated=new Map(),tangents=new Map();
      let edgeOnPlane=false;
      for(const fId of cell.faces) {
        for(const triangle of faceTriangles(model.faces[fId],points)) {
          triangles.push(triangle);
          const hit=triangleSegments(triangle,plane,eps);
          edgeOnPlane=edgeOnPlane||hit.edgeOnPlane;
          hit.isolated.forEach(p=>isolated.set(pointKey(p),p));
          for (const [a,b] of hit.segments) {
            const key=segmentKey(a,b);
            if (hit.coplanar) coplanar.push([a,b]);
            else segments.set(key,[a,b]);
          }
        }
      }
      // Node collinear overlaps (e.g. plane coincides with a triangulated cap).
      const endpoints=[...new Map([...segments.values(),...coplanar].flat().map(p=>[pointKey(p),p])).values()];
      function splitSegments(input,parity) {
        const output=new Map();
        for(const [a,b] of input) {
        const ab=sub(b,a),ll=dot(ab,ab),cuts=[[0,a],[1,b]];
        for(const p of endpoints) {
          const ap=sub(p,a),t=dot(ap,ab)/ll;
          if(t>eps && t<1-eps && norm(sub(ap,mul(ab,t)))<eps*2) cuts.push([t,p]);
        }
        cuts.sort((a,b)=>a[0]-b[0]);
        for(let i=1;i<cuts.length;i++) {
          const a=cuts[i-1][1],b=cuts[i][1];
          if(norm(sub(a,b))>eps) {
            const key=segmentKey(a,b);
            if(parity&&output.has(key))output.delete(key);else output.set(key,[a,b]);
          }
        }
        }
        return output;
      }
      const noded=splitSegments(segments.values(),false);
      for(const [key,seg] of splitSegments(coplanar,true))noded.set(key,seg);
      if(coplanar.length||edgeOnPlane){
        const horizontal=Math.abs(plane.normal[0])+Math.abs(plane.normal[1])<1e-10;
        const zs=cell.faces.flatMap(f=>model.faces[f].vertices.map(v=>points[v][2]));
        const minZ=Math.min(...zs),maxZ=Math.max(...zs),globalMax=box[2][1];
        const sourceHigh=model.metadata?.space_scale?.source_at_highest;
        const sign=Math.abs(plane.origin[2]-box[2][0])<eps?1:sourceHigh?-1:Math.abs(plane.origin[2]-globalMax)<eps?-1:1;
        const endpoint=Math.abs(plane.origin[2]-box[2][0])<eps||Math.abs(plane.origin[2]-globalMax)<eps;
        const bias=horizontal&&!endpoint?[0,0,sign*eps*.01]:[0,0,0];
        const retainTangent=!horizontal||Math.abs(plane.origin[2]-minZ)<eps||Math.abs(plane.origin[2]-maxZ)<eps;
        for(const [key,[a,b]] of noded){
          const midpoint=add(mul(add(a,b),0.5),bias),side=mul(unit(cross(plane.normal,sub(b,a))),eps*.1);
          const left=inClosedShell(add(midpoint,side),triangles,eps*.001),right=inClosedShell(sub(midpoint,side),triangles,eps*.001);
          if(left&&right)noded.delete(key);
          else if(right&&!left)noded.set(key,[b,a]);
          else if(horizontal&&!left&&!right){noded.delete(key);if(retainTangent)tangents.set(key,[a,b]);}
        }
      }
      const isHorizontal=Math.abs(plane.normal[0])+Math.abs(plane.normal[1])<1e-10;
      const cellZ=cell.faces.flatMap(f=>model.faces[f].vertices.map(v=>points[v][2]));
      const pointEndpoint=!isHorizontal||Math.abs(plane.origin[2]-Math.min(...cellZ))<eps||Math.abs(plane.origin[2]-Math.max(...cellZ))<eps;
      const onlyPoints=[...isolated.values()].filter(p=>pointEndpoint&&![...noded.values(),...tangents.values()].some(([a,b])=>{
        const ab=sub(b,a),t=Math.max(0,Math.min(1,dot(sub(p,a),ab)/dot(ab,ab)));
        return norm(sub(p,add(a,mul(ab,t))))<eps*2;
      })&&![plane.u,mul(plane.u,-1),plane.v,mul(plane.v,-1)].every(direction=>inClosedShell(add(p,mul(direction,eps*8)),triangles,eps)));
      if (!noded.size) {
        if(onlyPoints.length||tangents.size)result.push({cell:cell.id,feature_id:cell.feature_id,segments:[...tangents.values()],points:onlyPoints,loops:[],open:[...tangents.values()],area:0});
        continue;
      }
      const edges=[...noded.values()],nodes=new Map(),adj=new Map();
      edges.forEach(([a,b],i)=>{for(const p of [a,b]) {
        const k=pointKey(p);nodes.set(k,p);if(!adj.has(k))adj.set(k,[]);adj.get(k).push(i);
      }});
      const used=new Set(),rings=[],open=[];
      for(let i=0;i<edges.length;i++) {
        if(used.has(i))continue;
        let start=pointKey(edges[i][0]),at=start,edge=i;const path=[];
        while(true) {
          path.push(nodes.get(at));used.add(edge);
          const [a,b]=edges[edge].map(pointKey);at=at===a?b:a;
          if(at===start){path.push(nodes.get(at));rings.push(path);break;}
          const candidates=adj.get(at).filter(j=>!used.has(j));
          // At a contact vertex several contours can meet. Follow the boundary
          // with the filled section on its left, rather than arbitrary edge order.
          const incoming=sub(nodes.get(at),path[path.length-1]);
          const turn=j=>{const ends=edges[j],q=pointKey(ends[0])===at?ends[1]:ends[0],out=sub(q,nodes.get(at));
            return Math.atan2(dot(cross(incoming,out),plane.normal),dot(incoming,out));};
          const directed=candidates.filter(j=>pointKey(edges[j][0])===at);
          const choices=directed.length?directed:candidates;
          choices.sort((a,b)=>turn(b)-turn(a));
          const next=choices[0];
          if(next===undefined){path.push(nodes.get(at));open.push(path);break;}
          edge=next;
        }
      }
      const to2=p=>[dot(sub(p,plane.origin),plane.u),dot(sub(p,plane.origin),plane.v)];
      const loops=rings.map(r=>({points:r,uv:r.map(to2)}));
      loops.forEach(loop=>{loop.area=Math.abs(area2(loop.uv));});
      loops.sort((a,b)=>b.area-a.area);
      loops.forEach((loop,i)=>{loop.depth=loops.slice(0,i).filter(outer=>inside(loop.uv[0],outer.uv)).length;});
      result.push({cell:cell.id,feature_id:cell.feature_id,segments:[...edges,...tangents.values()],points:onlyPoints,loops,open:[...open,...tangents.values()],
        area:loops.reduce((sum,loop)=>sum+(loop.depth%2?-1:1)*loop.area,0)});
    }
    return {plane,cells:result,area:result.reduce((s,c)=>s+c.area,0),tolerance:eps};
  }
  return {add,sub,mul,dot,cross,norm,unit,orbit,navigate,connectedDuals,bounds,makePlane,sliceModel,faceTriangles,inClosedShell};
});
