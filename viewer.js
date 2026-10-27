(function () {
  'use strict';
  let M=JSON.parse(document.getElementById('dhe-model').textContent);
  const plan=M.generalization;
  const operationModels=M.operation_models;
  const G=window.DHEGeometry;
  let H=M.half_edges,n=M.primal_half_edge_count;
  const $=id=>document.getElementById(id),plot=$('plot');
  let cellOf=Array(n),faceOf=Array(n);
  M.faces.forEach(f=>f.half_edges.forEach(e=>{cellOf[e]=f.cell;faceOf[e]=f.id;}));
  const colors=['#3c82c4','#d39831','#6c9f71','#9b79ba'];
  const color=c=>c?colors[(c-1)%colors.length]:'#8190a0';
  const firstWall=M.faces.find(f=>f.cell>0&&f.kind==='wall')||M.faces.find(f=>f.cell>0);
  const state={edge:firstWall.half_edges[0],active:false,edgeVisible:false,faceVisible:false,
    highlights:new Set(),labels:false,connections:false,graphView:'both',
    height:M.dual_vertices[1].height_m,sliceEnabled:false,kind:'horizontal',tilt:45,azimuth:0,
    position:M.metadata.space_scale?(M.metadata.space_scale.source_z??0):M.dual_vertices[1].height_m/2,notice:'',lastAction:'',coordinates:false};
  if(M.metadata.space_scale&&M.metadata.space_scale.operation!=='source_extrusions')state.sliceEnabled=true;
  let baseHeight=state.height;
  let connections=G.connectedDuals(M);
  let section=null,plane=null,ready=false,renderPromise=Promise.resolve();
  const defaultCamera={eye:M.metadata.workbench?{x:1.9,y:-2.15,z:1.5}:{x:1.45,y:-1.65,z:1.15}};
  const coordinates=p=>p&&[p[0],p[1],p[2]*state.height/baseHeight];
  const origin=e=>e<n?coordinates(M.vertices[H[e].V]):coordinates(M.dual_vertices[H[e].V].position);
  const fmt=x=>Number(x).toFixed(2);
  const modelPoints=()=>M.vertices.map(coordinates);
  const associatedCell=e=>cellOf[e<n?e:H[e].D];
  function replaceModel(model){
    model.metadata=model.metadata||M.metadata;
    M=model;H=M.half_edges;n=M.primal_half_edge_count;
    cellOf=Array(n);faceOf=Array(n);
    M.faces.forEach(f=>f.half_edges.forEach(e=>{cellOf[e]=f.cell;faceOf[e]=f.id;}));
    connections=G.connectedDuals(M);
    const wall=M.faces.find(f=>f.cell>0&&f.kind==='wall')||M.faces.find(f=>f.cell>0);
    state.edge=wall.half_edges[0];state.active=false;state.edgeVisible=false;state.faceVisible=false;state.highlights.clear();
    $('edgeId').max=H.length-1;
    $('object').replaceChildren();
    for(const c of M.dual_vertices.slice(1)){const option=document.createElement('option');option.value=c.id;option.textContent=`ID ${c.feature_id} · cell ${c.id}`;$('object').appendChild(option);}
    window.dheViewer.model=M;window.dheViewer.connections=connections;
    return render();
  }

  function lineTrace(name,segments,line,extra={}) {
    const x=[],y=[],z=[],customdata=[];
    for(const seg of segments) {
      for(const p of seg.points){x.push(p[0]);y.push(p[1]);z.push(p[2]);customdata.push(seg.edge??null);}
      x.push(null);y.push(null);z.push(null);customdata.push(null);
    }
    return {type:'scatter3d',mode:'lines',x,y,z,line,name,customdata,
      showlegend:false,hoverinfo:'skip',...extra};
  }
  function arrow(a,b,edge) {
    const ab=G.sub(b,a),len=G.norm(ab);
    if(len<1e-9)return [];
    const dir=G.mul(ab,1/len),ref=Math.abs(dir[2])>0.9?[0,1,0]:[0,0,1];
    const side=G.unit(G.cross(dir,ref)),size=Math.min(len*0.18,0.65);
    const tip=G.add(a,G.mul(ab,0.78)),back=G.sub(tip,G.mul(dir,size));
    return [{points:[a,b],edge},{points:[G.add(back,G.mul(side,size*0.42)),tip,G.sub(back,G.mul(side,size*0.42))],edge}];
  }
  function mesh(name,polygons,c,opacity) {
    const x=[],y=[],z=[],i=[],j=[],k=[];
    for(const ps of polygons){const start=x.length;
      ps.forEach(p=>{x.push(p[0]);y.push(p[1]);z.push(p[2]);});
      for(let t=1;t<ps.length-1;t++){i.push(start);j.push(start+t);k.push(start+t+1);}
    }
    return {type:'mesh3d',name,x,y,z,i,j,k,color:c,opacity,flatshading:true,
      showlegend:false,hoverinfo:'skip',lighting:{ambient:0.85,diffuse:0.3,specular:0}};
  }
  function facePolygon(e) {
    const loop=G.orbit(H,e,'NF'),ps=[];
    for(const i of loop){const p=origin(i);if(!p)return [];if(!ps.some(q=>G.norm(G.sub(p,q))<1e-8))ps.push(p);}
    if(ps.length<3)return [];
    const normal=G.cross(G.sub(ps[1],ps[0]),G.sub(ps[2],ps[0]));
    return G.norm(normal)>1e-8?ps:[];
  }
  function cellPolygons(key) {
    const [space,number]=key.split(':'),id=Number(number);
    if(space==='P')return M.dual_vertices[id].faces.flatMap(f=>G.faceTriangles(M.faces[f],modelPoints()));
    const visited=new Set(),polygons=[];
    for(let i=n;i<H.length;i++) {
      if(H[H[i].D].V!==id || visited.has(i))continue;
      G.orbit(H,i,'NF').forEach(e=>visited.add(e));
      const ps=facePolygon(i);if(ps.length)polygons.push(ps);
    }
    return polygons;
  }
  function updatePlane(reset=false) {
    const points=modelPoints();
    let candidate=G.makePlane(points,state.kind,state.position,state.tilt,state.azimuth);
    const [lo,hi]=candidate.range;
    if(reset)state.position=(lo+hi)/2;
    state.position=Math.max(lo,Math.min(hi,state.position));
    plane=G.makePlane(points,state.kind,state.position,state.tilt,state.azimuth);
    $('slicePosition').min=lo;$('slicePosition').max=hi;$('slicePosition').step=Math.max((hi-lo)/200,0.001);
    $('slicePosition').value=state.position;$('positionText').textContent=fmt(state.position);
    $('positionLabel').textContent=state.kind==='horizontal'?(M.metadata.space_scale?'Scale Z':'Z level'):'Offset from model centre';
    $('positionUnits').textContent=M.metadata.space_scale?(state.kind==='horizontal'?'':'plot units'):'m';
    $('tiltRow').classList.toggle('off',state.kind!=='inclined');
    $('azimuthRow').classList.toggle('off',state.kind==='horizontal');
    $('tiltText').textContent=state.tilt;$('azimuthText').textContent=state.azimuth;
    section=state.sliceEnabled?G.sliceModel(M,points,plane):null;
  }
  function sectionTraces() {
    if(!state.sliceEnabled)return [];
    const points=modelPoints(),uv=points.map(p=>[G.dot(G.sub(p,plane.origin),plane.u),G.dot(G.sub(p,plane.origin),plane.v)]);
    const ranges=[0,1].map(k=>[Math.min(...uv.map(p=>p[k])),Math.max(...uv.map(p=>p[k]))]);
    const padding=0.06*Math.max(...ranges.map(([a,b])=>b-a));
    const [umin,umax]=[ranges[0][0]-padding,ranges[0][1]+padding];
    const [vmin,vmax]=[ranges[1][0]-padding,ranges[1][1]+padding];
    const corners=[[umin,vmin],[umax,vmin],[umax,vmax],[umin,vmax]].map(([u,v])=>G.add(plane.origin,G.add(G.mul(plane.u,u),G.mul(plane.v,v))));
    const traces=[mesh('Slicing plane',[corners],'#698baf',0.055)];
    for(const c of section.cells){
      traces.push(lineTrace(`Section · ID ${c.feature_id}`,c.segments.map(points=>({points})),{color:color(c.cell),width:6}));
      if(c.points?.length)traces.push({type:'scatter3d',name:'Terminal point',mode:'markers',x:c.points.map(p=>p[0]),y:c.points.map(p=>p[1]),z:c.points.map(p=>p[2]),marker:{size:8,color:color(c.cell)},showlegend:false});
    }
    return traces;
  }
  function drawSectionPanel() {
    const svg=$('sectionPlot');svg.replaceChildren();
    if(!section){$('sectionSummary').textContent='Enable slicing to inspect the section.';return;}
    const ns='http://www.w3.org/2000/svg',all=section.cells.flatMap(c=>[...c.segments.flat(),...(c.points||[])]).map(p=>[G.dot(G.sub(p,plane.origin),plane.u),G.dot(G.sub(p,plane.origin),plane.v)]);
    if(!all.length){$('sectionSummary').textContent='No intersection at this plane position.';return;}
    const xmin=Math.min(...all.map(p=>p[0])),xmax=Math.max(...all.map(p=>p[0]));
    const ymin=Math.min(...all.map(p=>p[1])),ymax=Math.max(...all.map(p=>p[1]));
    const span=Math.max(xmax-xmin,ymax-ymin,1),pad=span*0.08;
    svg.setAttribute('viewBox',`${xmin-pad} ${-ymax-pad} ${xmax-xmin+2*pad} ${ymax-ymin+2*pad}`);
    for(const c of section.cells){
      const path=document.createElementNS(ns,'path');
      const ringPath=c.loops.map(l=>l.uv.map((p,i)=>`${i?'L':'M'}${p[0]},${-p[1]}`).join(' ')+'Z').join(' ');
      const openPath=c.open.map(l=>l.map((p,i)=>{const u=G.dot(G.sub(p,plane.origin),plane.u),v=G.dot(G.sub(p,plane.origin),plane.v);return `${i?'L':'M'}${u},${-v}`;}).join(' ')).join(' ');
      path.setAttribute('d',ringPath+' '+openPath);path.setAttribute('fill',color(c.cell));path.setAttribute('fill-opacity','0.12');path.setAttribute('fill-rule','evenodd');
      path.setAttribute('stroke',color(c.cell));path.setAttribute('stroke-width','2');path.setAttribute('vector-effect','non-scaling-stroke');
      svg.appendChild(path);
      for(const p of c.points||[]){const circle=document.createElementNS(ns,'circle');circle.setAttribute('cx',G.dot(G.sub(p,plane.origin),plane.u));circle.setAttribute('cy',-G.dot(G.sub(p,plane.origin),plane.v));circle.setAttribute('r',span*0.015);circle.setAttribute('fill',color(c.cell));svg.appendChild(circle);}
    }
    const summary=$('sectionSummary');summary.replaceChildren();
    const areaUnit=M.metadata.space_scale&&state.kind!=='horizontal'?'plot units²':'m²';
    const title=document.createElement('div');title.textContent=`Section area ${fmt(section.area)} ${areaUnit} · ${section.cells.length} intersected cells`;summary.appendChild(title);
    for(const c of section.cells){const row=document.createElement('div');row.className='section-row';
      const label=document.createElement('span'),swatch=document.createElement('span');swatch.className='swatch';swatch.style.background=color(c.cell);
      label.append(swatch,document.createTextNode(`ID ${c.feature_id}`));
      const area=document.createElement('span');area.textContent=`${fmt(c.area)} ${areaUnit} · ${c.loops.length} contours${c.open.length?' · line stratum':''}${c.points?.length?' · point stratum':''}`;
      row.append(label,area);summary.appendChild(row);
    }
  }
  function describe() {
    const e=state.edge,p=e<n?e:H[e].D,c=associatedCell(e),isPrimal=e<n;
    $('edgeId').value=e;$('spaceValue').textContent=isPrimal?'Primal':'Dual';
    $('cellValue').textContent=isPrimal?(c?`${c} · ID ${M.dual_vertices[c].feature_id}`:'0 · exterior'):`around primal vertex ${H[H[e].D].V}`;
    $('faceValue').textContent=isPrimal?`${faceOf[e]} · ${M.faces[faceOf[e]].kind}`:`dual loop · primal edge ${p}`;
    $('pointerValue').textContent=`NF ${H[e].NF} · S ${H[e].S} · NV ${H[e].NV} · D ${H[e].D}`;
    if(c)$('object').value=c;
    const xyz=origin(e);
    $('coordinates').textContent=state.coordinates?(xyz?`V = (${xyz.map(fmt).join(', ')}) ${M.metadata.space_scale?'[m, m, scale]':'m'}`:'V = exterior dual vertex; no finite coordinates'):'';
    let status=state.active?`e${e} · ${isPrimal?'primal':'dual'} · ${state.lastAction}`:'Wireframe ready. Select an edge or use a navigation key.';
    if(state.active&&!xyz)status+=' · origin is the unbounded exterior';
    else if(state.active&&!origin(H[e].S))status+=' · exterior connection omitted';
    $('status').textContent=status;$('notice').textContent=state.notice;
    $('heightText').textContent=fmt(state.height);
    const ssc=M.metadata.space_scale;
    $('extrusionHeading').textContent=ssc?'Scale coordinate':'Extrusion';$('heightLabel').textContent=ssc?'Scale extent':'Height';$('heightUnits').textContent=ssc?'':'m';
    $('dimensionHint').textContent=ssc?'Z is a dimensionless scale parameter. The 3D cells encode feature evolution; volume is measured in m² × scale.':'Uniform assumed height; source data has no height field. Base Z = 0 m.';
    $('connectDual').setAttribute('aria-pressed',String(state.connections));
    $('connectDual').textContent=state.connections?'Detach displayed dual links':'Attach internal dual vertices';
    const count=M.dual_vertices.length-1,uses=connections.reduce((sum,c)=>sum+c.half_edges.length,0);
    $('dualSummary').textContent=`${count} dual vertices · ${connections.length} connected cell pairs · ${uses} dual half-edge uses`;
    $('volumes').replaceChildren();
    for(const c of M.dual_vertices.slice(1)){const row=document.createElement('div');row.className='section-row';row.textContent=ssc?`ID ${c.feature_id} · scale volume ${fmt(c.volume_m3*state.height/baseHeight)}`:`ID ${c.feature_id} · ${fmt(c.area_m2)} m² · ${fmt(c.area_m2*state.height)} m³`;$('volumes').appendChild(row);}
    drawSectionPanel();
  }
  function buildTraces() {
    const traces=[],seen=new Set(),wire=[];
    if(state.graphView==='both'){
      for(const f of M.faces){
        if(!f.cell || (M.metadata.space_scale?['base','roof'].includes(f.kind):f.kind!=='wall'))continue;
        for(const e of f.half_edges){const a=H[e].V,b=H[H[e].S].V,key=[a,b].sort((x,y)=>x-y).join(':');
          if(seen.has(key))continue;seen.add(key);wire.push({points:[coordinates(M.vertices[a]),coordinates(M.vertices[b])],edge:e});
        }
      }
    }
    traces.push(lineTrace('Primal edges',wire,{color:'#7d8b9a',width:2},{hovertemplate:'Half-edge %{customdata}<extra></extra>'}));
    const nodes=M.dual_vertices.slice(1),positions=nodes.map(c=>coordinates(c.position));
    traces.push({type:'scatter3d',name:'Dual vertices',mode:state.labels?'markers+text':'markers',
      x:positions.map(p=>p[0]),y:positions.map(p=>p[1]),z:positions.map(p=>p[2]),
      text:nodes.map(c=>`dual ${c.id} · ID ${c.feature_id}`),textposition:'top center',
      marker:{size:6,color:'#b26d24',line:{color:'#fff',width:1}},showlegend:false,
      customdata:nodes.map(c=>({cell:c.id})),hovertemplate:'%{text}<extra></extra>'});
    const links=[];
    if(state.connections)for(const pair of connections){
      const [a,b]=pair.cells.map(c=>coordinates(M.dual_vertices[c].position));
      const forward=pair.half_edges.find(e=>H[e].V===pair.cells[0]);
      const backward=pair.half_edges.find(e=>H[e].V===pair.cells[1]);
      links.push(...arrow(a,b,forward),...arrow(b,a,backward));
    }
    traces.push(lineTrace('Connected dual half-edges',links,{color:'#16854d',width:5},{hovertemplate:'Dual half-edge %{customdata}<extra></extra>'}));
    for(const key of state.highlights){
      if(key.startsWith('P:')&&state.graphView!=='both')continue;
      traces.push(mesh(`Cell highlight ${key}`,cellPolygons(key),color(Number(key.split(':')[1])),0.075));
    }
    if(state.faceVisible&&(state.edge>=n||state.graphView==='both')){
      const polygons=state.edge<n?G.faceTriangles(M.faces[faceOf[state.edge]],modelPoints()):[facePolygon(state.edge)].filter(p=>p.length);
      if(polygons.length)traces.push(mesh('Current face',polygons,color(associatedCell(state.edge)),0.13));
    }
    if(state.edgeVisible&&(state.edge>=n||state.graphView==='both')){
      const a=origin(state.edge),b=origin(H[state.edge].S);
      const dual=state.edge>=n;
      if(a&&b)traces.push(lineTrace('Current half-edge',arrow(a,b,state.edge),{color:dual?'#08783c':'#cb3150',width:8}));
      if(a)traces.push({type:'scatter3d',name:'Current origin',mode:'markers',x:[a[0]],y:[a[1]],z:[a[2]],
        marker:{size:7,color:'#f3a63c',line:{color:'#9b5624',width:1}},showlegend:false,
        hovertemplate:`e${state.edge} origin<br>(%{x:.2f}, %{y:.2f}, %{z:.2f}) m<extra></extra>`});
    }
    if(state.labels&&state.graphView==='both'){
      const ps=modelPoints();traces.push({type:'scatter3d',name:'Primal vertex labels',mode:'text',
        x:ps.map(p=>p[0]),y:ps.map(p=>p[1]),z:ps.map(p=>p[2]),text:ps.map((_,i)=>`v${i}`),
        textposition:'top center',textfont:{size:10,color:'#52677d'},hoverinfo:'skip',showlegend:false});
    }
    return traces.concat(sectionTraces(),window.dheViewer?.extraTraces?.()||[]);
  }
  async function draw() {
    updatePlane();describe();
    const box=G.bounds(modelPoints()),ranges=box.map(([a,b])=>{const pad=Math.max((b-a)*0.16,1);return [a-pad,b+pad];});
    const axis=(title,range)=>({title:{text:title},range,showbackground:false,gridcolor:'#e1e7ee',zeroline:false,tickfont:{size:10}});
    const layout={margin:{l:0,r:0,b:0,t:0},paper_bgcolor:'#f5f7fa',uirevision:'keep-camera',
      scene:{xaxis:axis('East (m)',ranges[0]),yaxis:axis('North (m)',ranges[1]),zaxis:axis(M.metadata.space_scale?'Scale Z':'Z (m)',ranges[2]),
        aspectmode:'data',uirevision:'keep-camera',camera:defaultCamera}};
    const data=buildTraces(),config={responsive:true,displaylogo:false,scrollZoom:true};
    if(!ready){await Plotly.newPlot(plot,data,layout,config);ready=true;}
    else await Plotly.react(plot,data,layout,config);
  }
  function render() {renderPromise=renderPromise.then(draw);return renderPromise;}
  function activate(e,action) {
    if(!Number.isInteger(e)||e<0||e>=H.length){state.notice=`Choose an edge ID from 0 to ${H.length-1}.`;return render();}
    state.edge=e;state.active=true;state.edgeVisible=true;state.faceVisible=true;state.lastAction=action;state.notice='';
    if(e>=n&&!facePolygon(e).length)state.notice='This dual face touches the exterior or has fewer than three finite nodes; no face fill is drawn.';
    return render();
  }
  function moveSlice(sign) {
    state.sliceEnabled=true;$('sliceEnabled').checked=true;updatePlane();
    state.position+=sign*(plane.range[1]-plane.range[0])/20;
    return render();
  }
  function action(key) {
    state.notice='';
    if('fsadvoe'.includes(key)&&key.length===1)return activate(G.navigate(H,state.edge,key),key.toUpperCase());
    if(key==='c'){
      const id=state.edge<n?cellOf[state.edge]:H[H[state.edge].D].V;
      const space=state.edge<n?'P':'D',key=`${space}:${id}`;
      if(cellPolygons(key).length)state.highlights.add(key);
      else state.notice='The current dual cell has no finite polygonal boundary to fill; its vertices and connected half-edges remain visible.';
    } else if(key==='x')state.highlights.clear();
    else if(key==='k')state.edgeVisible=false;
    else if(key==='l'){state.edgeVisible=false;state.faceVisible=false;}
    else if(key==='z'){state.coordinates=true;const p=origin(state.edge);console.log('Current origin:',p??'unbounded exterior');}
    else if(key==='h'){state.labels=!state.labels;$('labels').checked=state.labels;}
    else if(key==='up')return moveSlice(1);
    else if(key==='down')return moveSlice(-1);
    else return render();
    return render();
  }
  for(const c of M.dual_vertices.slice(1)){
    const option=document.createElement('option');option.value=c.id;option.textContent=`ID ${c.feature_id} · cell ${c.id}${c.part>1?' · part '+c.part:''}`;$('object').appendChild(option);
  }
  document.querySelectorAll('[data-action]').forEach(button=>button.onclick=()=>action(button.dataset.action));
  $('goEdge').onclick=()=>activate(Number($('edgeId').value),'selected by ID');
  $('edgeId').max=H.length-1;$('edgeId').onkeydown=event=>{if(event.key==='Enter'){event.preventDefault();$('goEdge').click();}};
  $('object').onchange=function(){const face=M.faces.find(f=>f.cell===Number(this.value)&&f.kind==='wall');activate(face.half_edges[0],'selected cell');};
  $('labels').onchange=function(){state.labels=this.checked;render();};
  $('connectDual').onclick=()=>{state.connections=!state.connections;render();};
  $('graphView').onchange=function(){state.graphView=this.value;render();};
  $('sliceEnabled').onchange=function(){state.sliceEnabled=this.checked;render();};
  $('sliceEnabled').checked=state.sliceEnabled;
  $('planeKind').onchange=function(){state.kind=this.value;updatePlane(true);render();};
  for(const id of ['tilt','azimuth'])$(id).oninput=function(){state[id]=Number(this.value);updatePlane();render();};
  $('slicePosition').oninput=function(){state.position=Number(this.value);state.sliceEnabled=true;$('sliceEnabled').checked=true;render();};
  $('slicePosition').addEventListener('wheel',event=>{event.preventDefault();moveSlice(event.deltaY<0?1:-1);},{passive:false});
  $('height').max=Math.max(60,baseHeight*2);$('height').value=state.height;
  $('height').oninput=function(){const factor=Number(this.value)/state.height;state.height=Number(this.value);if(state.kind==='horizontal')state.position*=factor;render();};
  $('resetCamera').onclick=()=>Plotly.relayout(plot,{'scene.camera':defaultCamera});
  document.addEventListener('keydown',event=>{
    if(event.ctrlKey||event.metaKey||event.altKey||/^(INPUT|SELECT|TEXTAREA)$/.test(event.target.tagName)||event.target.isContentEditable)return;
    const key=event.key==='ArrowUp'?'up':event.key==='ArrowDown'?'down':event.key.toLowerCase();
    if(['f','s','a','d','v','o','e','z','c','x','k','l','h','up','down'].includes(key)){
      event.preventDefault();action(key);
    }
  });
  window.dheViewer={model:M,state,connections,action,select:activate,idle:()=>renderPromise,
    refresh:render,loadModel:async model=>{
      baseHeight=model.dual_vertices[1].height_m;state.height=baseHeight;
      state.position=model.metadata.space_scale?.source_z??0;state.kind='horizontal';state.sliceEnabled=model.metadata.space_scale?.operation!=='source_extrusions';
      $('height').value=baseHeight;$('height').max=Math.max(60,baseHeight*2);$('planeKind').value='horizontal';$('sliceEnabled').checked=state.sliceEnabled;
      return replaceModel(model);
    },get cellOf(){return cellOf;},get zRatio(){return state.height/baseHeight;},
    get section(){return section;},get plane(){return plane;}};
  if(operationModels){
    $('operationPanel').classList.remove('off');
    operationModels.forEach((op,i)=>{const option=document.createElement('option');option.value=i;option.textContent=op.label;$('operation').appendChild(option);});
    const explain=()=>{const info=M.metadata.space_scale;$('operationDescription').textContent=info.coverage_policy+(info.recipient_feature_id?` · recipient ID ${info.recipient_feature_id}`:'')+(info.critical_scale?` · terminal scale ${info.critical_scale}`:info.event_scale?` · merge scale ${info.event_scale}`:'');};
    $('operation').onchange=async function(){state.position=0;state.sliceEnabled=true;state.kind='horizontal';$('sliceEnabled').checked=true;$('planeKind').value='horizontal';await replaceModel(JSON.parse(JSON.stringify(operationModels[Number(this.value)].model)));explain();};
    explain();
    $('operationPanel').after($('planeKind').closest('section'));
  }
  if(plan){
    $('generalizationPanel').classList.remove('off');
    const per=plan.samples_per_event,maximum=plan.events.length*per;
    const slider=$('generalizationProgress');slider.max=maximum;
    let playing=false;
    async function setProgress(value){
      const tick=Math.max(0,Math.min(maximum,Math.round(value)));slider.value=tick;
      const index=Math.min(plan.events.length,Math.floor(tick/per)),sample=tick%per;
      const model=JSON.parse(JSON.stringify(plan.states[index]));
      if(index<plan.events.length){
        const delta=plan.events[index].samples[sample];
        Object.entries(delta.vertices).forEach(([v,p])=>model.vertices[v]=p);
        Object.entries(delta.cells).forEach(([c,metrics])=>Object.assign(model.dual_vertices[c],metrics));
        Object.entries(delta.render_cache).forEach(([f,triangles])=>model.faces[f].render_triangles=triangles);
      }
      $('generalizationText').textContent=`${(tick/maximum*100).toFixed(1)}%`;
      const source=plan.events[Math.min(index,plan.events.length-1)];
      $('generalizationSummary').textContent=`${index} / ${plan.events.length} committed boundary events · `+
        (index===plan.events.length?'complete':`current event affects ${source.affected_cells.map(c=>'ID '+model.dual_vertices[c].feature_id).join(', ')}`);
      await replaceModel(model);
    }
    slider.oninput=()=>{playing=false;$('playGeneralization').textContent='Play transition';setProgress(Number(slider.value));};
    $('nextGeneralization').onclick=()=>{playing=false;$('playGeneralization').textContent='Play transition';setProgress(Math.min(maximum,(Math.floor(Number(slider.value)/per)+1)*per));};
    $('playGeneralization').onclick=async()=>{
      playing=!playing;$('playGeneralization').textContent=playing?'Pause':'Play transition';
      if(playing&&Number(slider.value)>=maximum)await setProgress(0);
      while(playing&&Number(slider.value)<maximum){await setProgress(Number(slider.value)+1);await new Promise(resolve=>setTimeout(resolve,40));}
      playing=false;$('playGeneralization').textContent='Play transition';
    };
    window.dheViewer.setProgress=setProgress;
    $('generalizationText').textContent='0.0%';
    $('generalizationSummary').textContent=`0 / ${plan.events.length} committed boundary events`;
  }
  window.dheReady=render().then(()=>{
    plot.on('plotly_click',event=>{
      const point=event.points?.[0],data=point?.customdata;
      if(Number.isInteger(data))activate(data,'clicked edge');
      else if(data?.cell){const f=M.faces.find(f=>f.cell===data.cell&&f.kind==='wall');activate(f.half_edges[0],'clicked dual vertex');}
    });
  });
})();
