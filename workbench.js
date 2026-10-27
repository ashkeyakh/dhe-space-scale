(function(){
 'use strict';
 const initial=JSON.parse(document.getElementById('dhe-model').textContent),cfg=initial.metadata?.workbench;
 if(!cfg)return;
 const $=id=>document.getElementById(id),NS='http://www.w3.org/2000/svg';
 const panel=$('workbenchPanel');document.querySelector('aside').prepend(panel);panel.classList.remove('off');
 const sources=cfg.source_map,ids=cfg.feature_ids,svg=$('selectionMap');
 let selected=[],mode=null,draft=[],info=null;
 const polygons=g=>g.type==='Polygon'?[g.coordinates]:g.type==='MultiPolygon'?g.coordinates:[];
 const all=Object.values(sources).flatMap(g=>polygons(g).flat(2));
 const xmin=Math.min(...all.map(p=>p[0])),xmax=Math.max(...all.map(p=>p[0])),ymin=Math.min(...all.map(p=>p[1])),ymax=Math.max(...all.map(p=>p[1]));
 const span=Math.max(xmax-xmin,ymax-ymin),pad=span*.05;
 svg.setAttribute('viewBox',`${xmin-pad} ${-ymax-pad} ${xmax-xmin+2*pad} ${ymax-ymin+2*pad}`);
 function message(text,error=false){$('workbenchMessage').textContent=text;$('workbenchMessage').style.color=error?'#ad2443':'#52677d';}
 function pathData(g){return polygons(g).map(poly=>poly.map(r=>r.map((p,i)=>`${i?'L':'M'}${p[0]},${-p[1]}`).join(' ')+'Z').join(' ')).join(' ');}
 function updateWinner(){const previous=$('winnerId').value;$('winnerId').replaceChildren();
  selected.forEach(fid=>{const op=document.createElement('option');op.value=fid;op.textContent=fid;$('winnerId').appendChild(op);});
  if(selected.includes(previous))$('winnerId').value=previous;
 }
 function selection(values){selected=[...new Set(values.map(String))];$('selectedIds').value=selected.join(', ');updateWinner();drawMap();window.dheViewer?.refresh();}
 function toggle(fid){selection(selected.includes(fid)?selected.filter(i=>i!==fid):[...selected,fid]);}
 function drawMap(){
  svg.replaceChildren();
  ids.forEach(fid=>{const p=document.createElementNS(NS,'path');p.setAttribute('d',pathData(sources[fid]));p.dataset.featureId=fid;
   p.setAttribute('fill',selected.includes(fid)?'#dce9f6':'transparent');p.setAttribute('fill-rule','evenodd');p.setAttribute('stroke',selected.includes(fid)?'#2f6fa9':'#6c7e90');p.setAttribute('stroke-width',selected.includes(fid)?'2':'1');p.setAttribute('vector-effect','non-scaling-stroke');
   const title=document.createElementNS(NS,'title');title.textContent=`ID ${fid}`;p.appendChild(title);p.onclick=event=>{if(mode)return;event.stopPropagation();toggle(fid);};svg.appendChild(p);
   if(selected.includes(fid)){const ps=polygons(sources[fid])[0][0],x=ps.reduce((s,p)=>s+p[0],0)/ps.length,y=ps.reduce((s,p)=>s+p[1],0)/ps.length;
    const text=document.createElementNS(NS,'text');text.setAttribute('x',x);text.setAttribute('y',-y);text.setAttribute('font-size',span*.052);text.setAttribute('text-anchor','middle');text.setAttribute('fill','#214e7a');text.textContent=fid;svg.appendChild(text);}
  });
  if(draft.length){const path=document.createElementNS(NS,'path');path.setAttribute('d',draft.map((p,i)=>`${i?'L':'M'}${p[0]},${-p[1]}`).join(' '));path.setAttribute('fill','none');path.setAttribute('stroke','#13814b');path.setAttribute('stroke-width','2');path.setAttribute('vector-effect','non-scaling-stroke');svg.appendChild(path);
   draft.forEach(p=>{const c=document.createElementNS(NS,'circle');c.setAttribute('cx',p[0]);c.setAttribute('cy',-p[1]);c.setAttribute('r',span*.008);c.setAttribute('fill','#13814b');svg.appendChild(c);});}
 }
 svg.addEventListener('click',event=>{if(!mode)return;const p=svg.createSVGPoint();p.x=event.clientX;p.y=event.clientY;const q=p.matrixTransform(svg.getScreenCTM().inverse());draft.push([Number(q.x.toFixed(6)),Number((-q.y).toFixed(6))]);
  if(mode==='point'){finishTarget();}else{drawMap();message(`${draft.length} target vertices. Click Finish target when done.`);}
 });
 function draw(kind){mode=kind;draft=[];$('targetGeometry').value='';svg.style.cursor='crosshair';drawMap();message(`Click the map to draw a ${kind} target in local XY coordinates.`);}
 function finishTarget(){
  const text=draft.map(p=>p.join(' '));
  if(mode==='point'&&text.length===1)$('targetGeometry').value=`POINT (${text[0]})`;
  else if(mode==='polyline'&&text.length>=2)$('targetGeometry').value=`LINESTRING (${text.join(', ')})`;
  else if(mode==='polygon'&&text.length>=3)$('targetGeometry').value=`POLYGON ((${[...text,text[0]].join(', ')}))`;
  else{message('Add enough target vertices before finishing.',true);return;}
  mode=null;svg.style.cursor='default';drawMap();message('Target geometry is ready. Build the transition when the source selection is ready.');
 }
 $('drawPoint').onclick=()=>draw('point');$('drawLine').onclick=()=>draw('polyline');$('drawPolygon').onclick=()=>draw('polygon');$('finishTarget').onclick=finishTarget;
 $('cancelTarget').onclick=()=>{mode=null;draft=[];$('targetGeometry').value='';svg.style.cursor='default';drawMap();message('Automatic target will be used.');};
 $('selectedIds').onchange=function(){selection(this.value.split(/[\s,;]+/).filter(Boolean));};
 ids.forEach(fid=>{const op=document.createElement('option');op.value=fid;op.textContent=fid;$('recipientId').appendChild(op);});
 function operationFields(){const op=$('operationType').value;
  $('winnerRow').classList.toggle('off',!['merge','aggregation'].includes(op));
  ['loserKind'].forEach(id=>{$(id).classList.toggle('off',op!=='merge');document.querySelector(`label[for="${id}"]`).classList.toggle('off',op!=='merge');});
  $('simplifyTolerance').parentElement.classList.toggle('off',op!=='simplification');$('interfaceZ').parentElement.classList.toggle('off',op!=='aggregation');
  $('recipientId').classList.toggle('off',['merge','aggregation'].includes(op));document.querySelector('label[for="recipientId"]').classList.toggle('off',['merge','aggregation'].includes(op));
 }
 $('operationType').onchange=operationFields;operationFields();
 $('sourceZ').value=cfg.source_z;$('targetZ').value=cfg.target_z;
 function linesOf(g){
  if(!g)return [];
  if(g.type==='Polygon')return g.coordinates;
  if(g.type==='MultiPolygon')return g.coordinates.flat();
  if(g.type==='LineString')return [g.coordinates];
  if(g.type==='MultiLineString')return g.coordinates;
  if(g.type==='GeometryCollection')return g.geometries.flatMap(linesOf);
  return [];
 }
 function lineTrace(name,lines,z,color,width=3){const x=[],y=[],zz=[];
  lines.forEach(line=>{line.forEach(p=>{x.push(p[0]);y.push(p[1]);zz.push(typeof z==='function'?z(p):z);});x.push(null);y.push(null);zz.push(null);});
  return {type:'scatter3d',name,mode:'lines',x,y,z:zz,line:{color,width},hoverinfo:'skip',showlegend:false};
 }
 function meshTrace(name,triangles,color,opacity){const x=[],y=[],z=[],i=[],j=[],k=[];
  triangles.forEach(t=>{const a=x.length;t.forEach(p=>{x.push(p[0]);y.push(p[1]);z.push(p[2]);});i.push(a);j.push(a+1);k.push(a+2);});
  return {type:'mesh3d',name,x,y,z,i,j,k,color,opacity,hoverinfo:'skip',showlegend:false};
 }
 function overlays(){const viewer=window.dheViewer,M=viewer.model,ratio=viewer.zRatio,traces=[];
  if(selected.length){const triangles=M.faces.filter(f=>f.cell&&selected.includes(String(M.dual_vertices[f.cell].feature_id))).flatMap(f=>DHEGeometry.faceTriangles(f,M.vertices).map(t=>t.map(p=>[p[0],p[1],p[2]*ratio])));
   traces.push(meshTrace('Selected source cells',triangles,'#4d85b8',0.035));}
  if(!info)return traces;
  if($('targetOutlines').checked)Object.entries(info.targets||{}).forEach(([fid,g])=>{
   traces.push(lineTrace(`Target ${fid}`,linesOf(g),info.target_z*ratio,'#14834b',5));
   if(g.type==='Point')traces.push({type:'scatter3d',name:`Target ${fid}`,mode:'markers',x:[g.coordinates[0]],y:[g.coordinates[1]],z:[info.target_z*ratio],marker:{size:7,color:'#14834b'},showlegend:false,hovertemplate:`Target ID ${fid}<extra></extra>`});
  });
  const layer=$('constructionLayer').value;
  if(layer==='regions'){
   const triangles=(info.transition_faces?.regions||[]).flatMap(r=>(r.render_triangles||[]).map(t=>t.map(p=>[p[0],p[1],info.source_z*ratio])));
   traces.push(meshTrace('Transition-region faces at source Z',triangles,'#bd4968',0.10));
   traces.push(lineTrace('Transition-region boundaries',(info.transition_faces?.regions||[]).flatMap(r=>linesOf(r.geometry)),info.source_z*ratio,'#a34666',3));
  }else if(layer==='triangles'||layer==='lifted'){
   const mesh=info.transition_mesh,lines=[];
   for(const t of mesh?.triangles||[]){const ps=t.vertices.map((v,k)=>[...mesh.vertices[v],(layer==='triangles'?info.source_z:t.z[k])*ratio]);lines.push([...ps,ps[0]]);}
   traces.push(lineTrace('Transition triangulation',lines,p=>p[2],layer==='triangles'?'#a34666':'#7a62ad',2));
  }else if(layer==='skeleton'&&info.skeleton){
   traces.push(lineTrace('Straight-skeleton interface',info.skeleton.arcs.flatMap(linesOf),info.interface_z*ratio,'#8060ad',4));
  }
  return traces;
 }
 $('constructionLayer').onchange=() => window.dheViewer.refresh();$('targetOutlines').onchange=()=>window.dheViewer.refresh();
 $('buildOperation').onclick=async()=>{
  if(location.protocol==='file:'){message('Run run_workbench.py in PyCharm and use its local URL; operation construction needs the Python backend.',true);return;}
  const values=$('selectedIds').value.split(/[\s,;]+/).filter(Boolean),unknown=values.filter(i=>!ids.includes(i));
  if(!values.length||unknown.length){message(unknown.length?`IDs not loaded: ${unknown.join(', ')}`:'Select at least one source feature.',true);return;}
  const request={operation:$('operationType').value,selected:values,winner:$('winnerId').value||values[0],loser_kind:$('loserKind').value,
   recipient:$('recipientId').value,tolerance:Number($('simplifyTolerance').value),source_z:Number($('sourceZ').value),target_z:Number($('targetZ').value),interface_z:$('interfaceZ').value};
  const text=$('targetGeometry').value.trim();
  if(text){try{if(text.startsWith('{')){const value=JSON.parse(text);if(value.type)request.target=value;else request.targets=value;}else request.target=text;}catch(e){message(`Invalid target JSON: ${e.message}`,true);return;}}
  $('buildOperation').disabled=true;message('Computing transition regions, lifting the mesh, and closing the DHE shell…');
  try{
   const response=await fetch('/api/apply',{method:'POST',headers:{'Content-Type':'application/json','X-DHE-Token':cfg.token},body:JSON.stringify(request)}),data=await response.json();
   if(!response.ok)throw Error(data.error||'Construction failed');
   info=data.metadata.space_scale;await window.dheViewer.loadModel(data);
   const others=info.affected_feature_ids.filter(i=>!selected.includes(i));
   const recipient=info.released_area_recipient;
   message(`Closed DHE validated. ${info.transition_faces.regions.length} transition regions. `+
    (others.length?`Also adjusted: ${others.join(', ')}. `:'')+
    (recipient?`Released area → ${recipient==='EXTERIOR'?'exterior (no adjacent recipient)':recipient}. `:'')+
    (info.stages?'Aggregation: straight-skeleton partition, then SSC merge.':'Source at top; target at bottom.'));
  }catch(error){message(error.message,true);}finally{$('buildOperation').disabled=false;}
 };
 $('resetSources').onclick=async()=>{const response=await fetch('/api/initial');info=null;await window.dheViewer.loadModel(await response.json());message('All source extrusions restored.');};
 $('exportModel').onclick=()=>{const data=JSON.parse(JSON.stringify(window.dheViewer.model));if(data.metadata.workbench)delete data.metadata.workbench.token;
  const url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'})),link=document.createElement('a');link.href=url;link.download='transition-model.dhe.json';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};
 window.dheWorkbench={select:selection,get selected(){return selected;},get info(){return info;}};
 drawMap();
 window.dheReady.then(()=>{
  window.dheViewer.extraTraces=overlays;
  $('plot').on('plotly_click',event=>{
   if(!$('pickFeatures').checked)return;
   const data=event.points?.[0]?.customdata,M=window.dheViewer.model;let cell;
   if(data?.cell)cell=data.cell;
   else if(Number.isInteger(data)){let e=data;if(e>=M.primal_half_edge_count)e=M.half_edges[e].D;cell=window.dheViewer.cellOf[e];}
   const fid=cell?String(M.dual_vertices[cell].feature_id):null;if(fid&&ids.includes(fid))toggle(fid);
  });
  window.dheViewer.refresh();
 });
})();
