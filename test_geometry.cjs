const assert=require('node:assert/strict');
const fs=require('node:fs');
const G=require('./dhe_geometry.js');
const model=JSON.parse(fs.readFileSync('output/extrusion_2001_2002.dhe.json','utf8'));
const H=model.half_edges,n=model.primal_half_edge_count;
for(let e=0;e<H.length;e++) {
  assert.equal(G.navigate(H,G.navigate(H,e,'f'),'o'),e,'PrevF reverses NF in both spaces');
  assert.equal(G.navigate(H,G.navigate(H,e,'d'),'d'),e);
  assert.equal(G.navigate(H,e,'e'),H[G.navigate(H,e,'a')].S);
  if(e<n)assert.equal(G.navigate(H,e,'a'),model.adjacent[e]);
}
const pairs=G.connectedDuals(model);
assert.equal(pairs.length,1);assert.deepEqual(pairs[0].cells,[1,2]);
assert.ok(pairs[0].half_edges.every(e=>H[e].V!==0&&H[H[e].S].V!==0));

function prism(rings,height=10,offset=0) {
  const vertices=[],faces=[],cell={id:1,feature_id:'test',faces:[]};
  const v=p=>{const i=vertices.length;vertices.push(p);return i;};
  const face=ps=>{cell.faces.push(faces.length);faces.push({cell:1,vertices:ps.map(v)});};
  // Cap triangulation is supplied separately for hole tests below.
  const outer=rings[0];
  for(let i=1;i<outer.length-1;i++){
    face([outer[0],outer[i],outer[i+1]].map(([x,y])=>[x+offset,y,0]));
    face([outer[0],outer[i],outer[i+1]].map(([x,y])=>[x+offset,y,height]));
  }
  for(const ring of rings)for(let i=0;i<ring.length;i++){
    const a=ring[i],b=ring[(i+1)%ring.length];
    face([[a[0]+offset,a[1],0],[b[0]+offset,b[1],0],[b[0]+offset,b[1],height],[a[0]+offset,a[1],height]]);
  }
  return {vertices,faces,dual_vertices:[{id:0},cell]};
}
const square=[[0,0],[2,0],[2,2],[0,2]],cube=prism([square]);
function section(m,kind,value,tilt=45,az=0) {
  return G.sliceModel(m,m.vertices,G.makePlane(m.vertices,kind,value,tilt,az));
}
const near=(a,b,msg)=>assert.ok(Math.abs(a-b)<1e-5,`${msg}: ${a} vs ${b}`);
for(const z of [0,0.5,5,9.9,10]){
  const s=section(cube,'horizontal',z);near(s.area,4,`horizontal/coplanar Z=${z}`);
  assert.equal(s.cells[0].loops.length,1);assert.equal(s.cells[0].open.length,0);
}
near(section(cube,'vertical',0).area,20,'vertical');
near(section(cube,'vertical',1).area,20,'vertical coincident wall');
near(section(cube,'inclined',0,45).area,4*Math.sqrt(2),'inclined area');
assert.equal(section(cube,'horizontal',11).cells.length,0,'outside model');

// Hollow square, caps formed from four rectangular strips.
const outer=[[0,0],[6,0],[6,6],[0,6]],hole=[[2,2],[4,2],[4,4],[2,4]];
const hollow=prism([outer,hole]);
const wallFaces=hollow.faces.slice(4);hollow.faces=wallFaces;hollow.dual_vertices[1].faces=wallFaces.map((_,i)=>i);
const rects=[[[0,0],[6,0],[6,2],[0,2]],[[0,4],[6,4],[6,6],[0,6]],[[0,2],[2,2],[2,4],[0,4]],[[4,2],[6,2],[6,4],[4,4]]];
for(const ring of rects)for(const z of [0,10])for(let j=1;j<ring.length-1;j++){
  const ids=[ring[0],ring[j],ring[j+1]].map(([x,y])=>{const i=hollow.vertices.length;hollow.vertices.push([x,y,z]);return i;});
  hollow.dual_vertices[1].faces.push(hollow.faces.length);hollow.faces.push({cell:1,vertices:ids});
}
for(const z of [0,5,10]){
  const s=section(hollow,'horizontal',z);near(s.area,32,'hole area');assert.equal(s.cells[0].loops.length,2);assert.equal(s.cells[0].open.length,0);
}
const cut=section(hollow,'vertical',0);near(cut.area,40,'disconnected vertical components through courtyard');assert.equal(cut.cells[0].loops.length,2);
const actual=G.sliceModel(model,model.vertices,G.makePlane(model.vertices,'horizontal',5));
near(actual.area,model.dual_vertices.slice(1).reduce((s,c)=>s+c.area_m2,0),'actual shapefile section');
console.log('PASS: all DHE operators in both spaces; topology-only dual connections; horizontal, vertical, inclined, coplanar, outside, courtyard and disconnected sections.');
