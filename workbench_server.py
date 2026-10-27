"""Local, click-driven source/target transition construction service."""
from copy import deepcopy
from functools import partial
from http.server import SimpleHTTPRequestHandler,ThreadingHTTPServer
import json
import secrets
import threading
import traceback
import webbrowser

from extrude import construct,load_shapefile
from shapely.ops import unary_union
from shapely.geometry import mapping
from shapely import set_precision
from viewer import make_view
from unified_operations import generalize
from workbench_config import INPUT_SHP,ID_FIELD,FEATURE_IDS,SOURCE_Z,TARGET_Z,OUTPUT_DIR


class Workbench:
    def __init__(self,output_dir=OUTPUT_DIR,demo=False):
        self.output_dir=output_dir;self.output_dir.mkdir(parents=True,exist_ok=True)
        if demo or not INPUT_SHP:
            from demo_data import demo_sources
            self.source={i:set_precision(g,1e-6) for i,g in demo_sources().items()}
            self.metadata=dict(source='Synthetic building footprints',selected_ids=list(self.source),
                               coordinate_system='Local Cartesian XY in metres',data_origin='Original synthetic demo')
        else:
            polygons,ids,self.metadata=load_shapefile(INPUT_SHP,list(map(str,FEATURE_IDS)),ID_FIELD)
            self.source={str(fid):set_precision(unary_union([p for p,i in zip(polygons,ids) if i==str(fid)]),1e-6) for fid in FEATURE_IDS}
        self.token=secrets.token_urlsafe(24);self.lock=threading.Lock()
        context=[];context_ids=[]
        for fid,g in self.source.items():
            for p in (list(g.geoms) if g.geom_type=='MultiPolygon' else [g]):context.append(p);context_ids.append(fid)
        model=construct(context,context_ids,SOURCE_Z)
        self.initial=model.to_dict()
        self.initial['metadata']=dict(self.metadata,space_scale=dict(operation='source_extrusions',source_z=SOURCE_Z,target_z=TARGET_Z,scale_end=SOURCE_Z,source_at_highest=True),
            workbench=dict(token=self.token,feature_ids=list(self.source),source_map={i:mapping(g) for i,g in self.source.items()},
                           source_z=SOURCE_Z,target_z=TARGET_Z,backend='local Python transition-region constructor'))
        class Initial:
            def to_dict(_):return self.initial
        make_view(Initial(),self.initial['metadata'],self.output_dir/'index.html')

    def apply(self,request):
        z_low=float(request.get('target_z',TARGET_Z));z_high=float(request.get('source_z',SOURCE_Z))
        model,info=generalize(self.source,request['operation'],request.get('selected',[]),winner=request.get('winner'),
            target=request.get('target'),targets=request.get('targets'),tolerance=float(request.get('tolerance',2.5)),
            loser_kind=request.get('loser_kind','point'),recipient=request.get('recipient') or None,z_low=z_low,z_high=z_high,
            interface_z=float(request['interface_z']) if request.get('interface_z') not in (None,'') else None)
        data=model.to_dict();data['metadata']=dict(self.metadata,space_scale=info,workbench=self.initial['metadata']['workbench'])
        (self.output_dir/'latest.dhe.json').write_text(json.dumps(data,ensure_ascii=True,allow_nan=False),encoding='utf-8')
        return data


def make_server(workbench,port=0):
    class Handler(SimpleHTTPRequestHandler):
        def __init__(self,*args,**kwargs):super().__init__(*args,directory=str(workbench.output_dir),**kwargs)
        def do_GET(self):
            if self.path=='/api/initial':self.reply(200,workbench.initial)
            else:super().do_GET()
        def reply(self,status,data):
            payload=json.dumps(data,ensure_ascii=True,allow_nan=False).encode()
            self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(payload)))
            self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(payload)
        def do_POST(self):
            if self.path!='/api/apply':self.reply(404,dict(error='Unknown endpoint'));return
            if self.headers.get('X-DHE-Token')!=workbench.token:self.reply(403,dict(error='Open this workbench from its local launch URL.'));return
            size=int(self.headers.get('Content-Length',0))
            if size<1 or size>500000:self.reply(400,dict(error='Invalid request size'));return
            try:
                request=json.loads(self.rfile.read(size))
                with workbench.lock:result=workbench.apply(request)
                self.reply(200,result)
            except (ValueError,TypeError,KeyError,AssertionError,RuntimeError) as error:
                traceback.print_exc();self.reply(400,dict(error=str(error)))
            except Exception as error:
                traceback.print_exc();self.reply(500,dict(error=f'Construction failed: {error}'))
    return ThreadingHTTPServer(('127.0.0.1',port),Handler)


def run(port=0,open_browser=True,demo=False):
    workbench=Workbench(demo=demo);server=make_server(workbench,port)
    url=f'http://127.0.0.1:{server.server_address[1]}/'
    print(f'Loaded {len(workbench.source)} source features: {", ".join(workbench.source)}',flush=True)
    print(f'DHE_WORKBENCH_URL={url}',flush=True)
    print('Source is at highest Z. Stop this run in PyCharm to stop the local workbench.',flush=True)
    if open_browser:webbrowser.open(url,new=2)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()
