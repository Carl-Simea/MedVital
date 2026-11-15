# Builds public/data/anatomy.{json,bin.gz} from BodyParts3D (CC BY-SA 2.1 JP). Usage: python3 tools/build_anatomy.py
import os,csv,re,json,gzip,struct,collections,numpy as np,trimesh,fast_simplification as fs
HERE=os.path.dirname(os.path.abspath(__file__))
D=os.environ.get('BP3D_DIR',HERE+'/_src/BodyParts3D/assets/BodyParts3D_data')
OUT=os.environ.get('OUT_DIR',HERE+'/../public/data'); os.makedirs(OUT,exist_ok=True); os.makedirs(HERE+'/_cache',exist_ok=True)
names={r[0]:r[1] for r in csv.reader(open(D+'/parts_list_e.txt'),delimiter='\t')}
comp=collections.defaultdict(set)
for r in csv.reader(open(D+'/composite_parts.txt'),delimiter='\t'): comp[r[0]].add(r[2])
SYS={'skel':'FMA23881','musc':'FMA72954','cardio':'FMA7161','resp':'FMA7158','alim':'FMA7152','urin':'FMA7159','nerv':'FMA7157'}
mem=collections.defaultdict(set)
for k,v in SYS.items():
    for p in comp[v]: mem[p].add(k)
ids=sorted(f[:-4] for f in os.listdir(D+'/stl'))
BUDGET={'bone':175000,'organ':75000,'muscle':300000}
MINF={'bone':140,'organ':48,'muscle':160}
SEG=['pelvis','chest','head','uaL','faL','haL','uaR','faR','haR','thL','shL','ftL','thR','shR','ftR']
SI={n:i for i,n in enumerate(SEG)}
GROUPS=['skull','spineC','spineT','spineL','ribs','shoulder','arm','hand','pelvis','femur','shin','foot',
 'heart','artery','vein','lung','airway','liver','stomach','intestine','kidney','spleen','brain','eye',
 'mHead','mChest','mAbdomen','mUpperArm','mForearm','mThigh','mShin','tendon']
GI={n:i for i,n in enumerate(GROUPS)}
EXCL=re.compile(r'penis|testis|epididymis|deferent|seminal|prostate|urethra|hair|eyebrow|^ear$|^skin$|labial part|gingiva|anal sphincter|puborectalis|pubococcygeus|iliococcygeus|coccygeus|levator ani|pubic')
SKULL=re.compile(r'frontal bone|parietal bone|occipital bone|temporal bone|sphenoid|ethmoid|maxilla|mandible|zygomatic bone|nasal bone|lacrimal|palatine|vomer|concha|tooth')
def side_strip(n):
    m=re.match(r'^(left|right) (.*)$',n)
    if m: return m.group(1)[0].upper(),m.group(2)
    m=re.search(r' (left|right) ',n)
    if m: return m.group(1)[0].upper(),n
    return None,n
def classify(pid):
    n=names.get(pid,'?'); sy=mem.get(pid,set()); sd,b=side_strip(n)
    if EXCL.search(n): return None
    VERT=re.search(r'vertebra|^atlas$|^axis$',b)
    if 'skel' in sy or VERT or 'costal cartilage' in b or 'tooth' in b:
        if SKULL.search(b): g='skull'
        elif re.search(r'cervical|atlas|axis|hyoid',b): g='spineC'
        elif 'thoracic' in b: g='spineT'
        elif 'lumbar' in b: g='spineL'
        elif re.search(r'rib|costal|sternum|manubrium|xiphoid',b): g='ribs'
        elif re.search(r'clavicle|scapula',b): g='shoulder'
        elif re.search(r'humerus|radius|ulna|forearm',b): g='arm'
        elif re.search(r'scaphoid|lunate|triquetral|pisiform|trapezium|trapezoid|capitate|hamate|metacarpal|finger|thumb',b): g='hand'
        elif re.search(r'hip bone|sacrum',b): g='pelvis'
        elif 'femur' in b: g='femur'
        elif re.search(r'patella|tibia|fibula|membrane of (left|right) leg',b): g='shin'
        elif re.search(r'calcaneus|talus|cuboid|navicular|cuneiform|metatarsal|toe|foot|plantar',b): g='foot'
        elif 'nasal cartilages' in b: return None
        else: g='ribs'
        return 'bone',g,sd,b
    if 'musc' in sy or re.search(r'extensor carpi|rectus abdominis|linea alba|^diaphragm$',b):
        g='tendon' if re.search(r'tendon|tract|aponeurosis|linea alba|retinaculum|ligament|tendinous',b) else 'm?'
        return 'muscle',g,sd,b
    if 'nerv' in sy or re.search(r'pituitary|orbital gyri',b): return 'organ','brain',sd,b
    if 'eyeball' in b: return 'organ','eye',sd,b
    if re.search(r'coronary|cardiac|papillary|valve|wall of heart|interventricular',b): g='heart'
    elif re.search(r'pulmonary artery',b): g='vein'
    elif re.search(r'pulmonary vein',b): g='artery'
    elif re.search(r'aorta|artery',b): g='artery'
    elif re.search(r'vein|vena cava',b): g='vein'
    elif 'lobe of' in b and 'lung' in b: g='lung'
    elif re.search(r'trachea|bronchus|thyroid cartilage',b): g='airway'
    elif re.search(r'liver|gallbladder',b): g='liver'
    elif re.search(r'stomach|esophagus|duodenum',b): g='stomach'
    elif re.search(r'jejunum|ileum|colon|taenia|rectum|appendix',b): g='intestine'
    elif re.search(r'kidney|ureter|bladder|adrenal',b): g='kidney'
    elif re.search(r'spleen|pancrea|thymus',b): g='spleen'
    else: return None
    return 'organ',g,sd,b
def load(pid):
    m=trimesh.load(D+'/stl/'+pid+'.stl',process=True)
    v=np.asarray(m.vertices,dtype=np.float64); f=np.asarray(m.faces)
    v=np.stack([v[:,0],v[:,2],-v[:,1]],1)   # X=subject left, Y=up, Z=anterior
    return v,f
import pickle
parts=pickle.load(open(HERE+'/_cache/parts.pkl','rb')) if os.path.exists(HERE+'/_cache/parts.pkl') else []
for pid in ([] if parts else ids):
    c=classify(pid)
    if not c: continue
    v,f=load(pid)
    area=trimesh.Trimesh(v,f,process=False).area
    parts.append(dict(id=pid,layer=c[0],g=c[1],side=c[2],name=c[3],v=v,f=f,area=area))
pickle.dump(parts,open(HERE+'/_cache/parts.pkl','wb')) if not os.path.exists(HERE+'/_cache/parts.pkl') else None
print('parts',len(parts),collections.Counter(p['layer'] for p in parts))
def P(name,side=None,layer=None):
    for p in parts:
        if p['name']==name and (side is None or p['side']==side or (p['side'] is None and ((p['v'][:,0].mean()>0)==(side=='L')))): return p
    raise KeyError(name+str(side))
def end(v,axis,frac,top):
    a=v[:,axis]; lo,hi=a.min(),a.max(); th=hi-(hi-lo)*frac if top else lo+(hi-lo)*frac
    return v[a>=th].mean(0) if top else v[a<=th].mean(0)
J={}
for s,sg in (('L',1),('R',-1)):
    hu=P('humerus',s)['v']; ra=np.vstack([P('radius',s)['v'],P('ulna',s)['v']]); fe=P('femur',s)['v']; ti=P('tibia',s)['v']
    top=hu[hu[:,1]>=hu[:,1].max()-0.12*np.ptp(hu[:,1])]; J['sh'+s]=top.mean(0)
    J['el'+s]=end(hu,1,0.04,False); J['wr'+s]=end(ra,1,0.04,False)
    for k,nm in (('ix','second metacarpal bone'),('pk','fifth metacarpal bone')):
        J[k+s]=end(P(nm,s)['v'],1,0.15,False)
    J['th'+s]=end(P('distal phalanx of %s thumb'%('left' if s=='L' else 'right'))['v'],1,0.2,False)
    J['tip'+s]=end(P('distal phalanx of %s middle finger'%('left' if s=='L' else 'right'))['v'],1,0.2,False)
    ft=fe[fe[:,1]>=fe[:,1].max()-0.10*np.ptp(fe[:,1])]; med=ft[(ft[:,0]*sg)<=np.median(ft[:,0]*sg)]; J['hp'+s]=med.mean(0)
    J['kn'+s]=end(fe,1,0.03,False); J['an'+s]=end(ti,1,0.04,False)
    ca=P('calcaneus',s)['v']; J['he'+s]=ca[ca[:,2]<=ca[:,2].min()+6].mean(0)
    bt=P('distal phalanx of %s big toe'%('left' if s=='L' else 'right'))['v']; J['to'+s]=bt[bt[:,2]>=bt[:,2].max()-5].mean(0)
    te=[p for p in parts if p['name']=='temporal bone' and ((p['v'][:,0].mean()>0)==(s=='L'))][0]['v']
    lat=te[(te[:,0]*sg)>=(te[:,0]*sg).max()-4]; e=lat.mean(0); e[0]*=1.08; J['ear'+s]=e
    ey=np.vstack([p['v'] for p in parts if p['name']=='eyeball']); ey=ey[(ey[:,0]*sg)>0]; c=ey.mean(0); c[2]=ey[:,2].max(); J['eye'+s]=c; J['ear'+s][1]=c[1]-5
inc=np.vstack([p['v'] for p in parts if p['name']=='upper central secondary incisor tooth'])
mo=inc.mean(0); mo[1]=inc[:,1].min()-4; mo[2]=inc[:,2].max()+8
J['moL']=mo+np.array([24,0,-6]); J['moR']=mo+np.array([-24,0,-6])
nb=np.vstack([p['v'] for p in parts if p['name']=='nasal bone']); nose=nb.mean(0); nose[1]=nb[:,1].min()-18; nose[2]=nb[:,2].max()+22; J['nose']=nose
Y=lambda nm:np.vstack([p['v'] for p in parts if p['name']==nm]).mean(0)[1]
zA=np.vstack([p['v'] for p in parts if p['name']=='sacrum'])[:,1].max(); zB=Y('twelfth thoracic vertebra'); zC=Y('first thoracic vertebra'); zD=Y('atlas')+12
hipMid=(J['hpL']+J['hpR'])/2; shMid=(J['shL']+J['shR'])/2
print('zones',zA,zB,zC,zD,'hipY',hipMid[1],'shY',shMid[1]); print({k:v.round(0).tolist() for k,v in J.items()})
def sstep(a,b,x): t=np.clip((x-a)/(b-a),0,1); return t*t*(3-2*t)
def trunkW(v):
    W=np.zeros((len(v),15)); y=v[:,1]
    wc=sstep(zA-20,zB+10,y); wh=sstep(zC+10,zD,y)
    W[:,0]=1-wc; W[:,1]=wc*(1-wh); W[:,2]=wc*wh; return W
def unit(a): return a/np.linalg.norm(a)
def capsule(v,A,B,R,t0=0.,t1=1.):
    ax=B-A; L=np.linalg.norm(ax); ax=ax/L; t=(v-A)@ax; tc=np.clip(t,t0*L,t1*L); d=np.linalg.norm(v-(A+np.outer(tc,ax)),axis=1); return d<R
def limb(s,arm):
    if arm: return J['sh'+s],J['el'+s],J['wr'+s],J['tip'+s],(SI['ua'+s],SI['fa'+s],SI['ha'+s]),SI['chest']
    return J['hp'+s],J['kn'+s],J['an'+s],J['to'+s],(SI['th'+s],SI['sh'+s],SI['ft'+s]),SI['pelvis']
def inLimb(v,s,arm,k=1.0):
    J0,J1,J2,J3,_,_=limb(s,arm); sg=1 if s=='L' else -1
    if arm: m=capsule(v,J0,J1,70*k,-0.05,1)|capsule(v,J1,J2,65*k)|capsule(v,J2,J3,75*k,0,1.2)
    else:
        m=capsule(v,J0,J1,115*k,0.0,1)|capsule(v,J1,J2,85*k)|(capsule(v,J['he'+s],J['to'+s],70*k,-0.2,1.2)&(v[:,1]<J2[1]+25))
        m&=(v[:,0]*sg>0)
    return m
def chainW(v,s,arm,rootA,rootB):
    J0,J1,J2,J3,(a,b,c),root=limb(s,arm); W=np.zeros((len(v),15))
    u=unit(J1-J0); l=unit(J2-J1); n1=unit(u+l)
    sE=(v-J1)@n1; sW=(v-J2)@l; s0=(v-J0)@u
    wl=sstep(-(35 if arm else 45),(35 if arm else 45),sE); we=sstep(-22,22,sW)*(wl>0.5); wr=1-sstep(rootA,rootB,s0)
    wr=wr*(1-wl)
    W[:,c]=we; W[:,b]=wl*(1-we); W[:,a]=(1-wl)*(1-we)*(1-wr); 
    tw=trunkW(v); W+=tw*(((1-wl)*(1-we)*wr))[:,None] if False else 0
    rw=((1-wl)*(1-we)*wr)
    W[:,root]+=rw
    return W
BONE_SEG=[(r'humerus','ua'),(r'radius|ulna|forearm','fa'),(r'scaphoid|lunate|triquetral|pisiform|trapezium|trapezoid|capitate|hamate|metacarpal|finger|thumb','ha'),
 (r'femur','th'),(r'patella|tibia|fibula|membrane of (left|right) leg','sh'),(r'calcaneus|talus|cuboid|navicular|cuneiform|metatarsal|toe|foot|plantar','ft')]
stats=collections.Counter()
for p in parts:
    v=p['v']; n=p['name']; s=p['side'] or ('L' if v[:,0].mean()>0 else 'R'); W=None
    if p['layer']=='bone':
        for rx,sg in BONE_SEG:
            if re.search(rx,n) and p['g'] in('arm','hand','femur','shin','foot'):
                W=np.zeros((len(v),15)); W[:,SI[sg+s]]=1; break
        if W is None:
            if p['g']=='skull': W=np.zeros((len(v),15)); W[:,2]=1
            elif p['g'] in('pelvis',): W=np.zeros((len(v),15)); W[:,0]=1
            elif p['g'] in('ribs','shoulder','spineT'): W=np.zeros((len(v),15)); W[:,1]=1
            else: W=np.repeat(trunkW(v.mean(0)[None]),len(v),0)
    else:
        if v.mean(0)[1]>zD-10 or p['g'] in('brain','eye'):
            W=np.zeros((len(v),15)); W[:,2]=1; stats['head']+=1
        else:
            W=trunkW(v); best=None
            if p['layer']=='muscle':
                for sd in ('L','R'):
                    for arm in (True,False):
                        f=inLimb(v,sd,arm).mean()
                        if best is None or f>best[0]: best=(f,sd,arm)
                f,sd,arm=best
                if f>0.55:
                    W=chainW(v,sd,arm,-30,50) if arm else chainW(v,sd,arm,-20,70); stats['limb']+=1
                elif f>0.12:
                    m=inLimb(v,sd,arm,0.62 if arm else 0.8); Wc=chainW(v,sd,arm,(10 if arm else -20),(130 if arm else 90)); root=SI['chest'] if arm else SI['pelvis']
                    Wt=trunkW(v); wl=1-Wc[:,root]; Wb=Wc.copy(); Wb[:,root]=0; Wb=Wb+Wt*(1-wl)[:,None]
                    W=np.where(m[:,None],Wb,Wt); stats['bridge']+=1; p['bridge']=True
                else: stats['trunk']+=1
        if p['g']=='m?':
            dom=W.sum(0).argmax(); sn=SEG[dom]
            p['g']={'pelvis':'mAbdomen','chest':'mChest','head':'mHead'}.get(sn) or {'ua':'mUpperArm','fa':'mForearm','ha':'mForearm','th':'mThigh','sh':'mShin','ft':'mShin'}[sn[:2]]
    W=W/W.sum(1,keepdims=True); p['W']=W
print(stats); print(collections.Counter(p['g'] for p in parts))
print('bridge:',sorted({p['name'] for p in parts if p.get('bridge')}))
# decimate (no smoothing afterwards: Taubin smoothing threw single vertices far out and left needle triangles)
out={}; plist=[]
allv=np.vstack([p['v'] for p in parts]); bmin=allv.min(0)-1; bmax=allv.max(0)+1
for layer in ('bone','organ','muscle'):
    ps=[p for p in parts if p['layer']==layer]
    wts=np.array([p['area']*(0.35 if p['g']=='brain' else 1.6 if p['g'] in('hand','foot','heart','skull') else 1) for p in ps]); wts/=wts.sum()
    V=[];F=[];G=[];PI=[];off=0
    for p,w in zip(ps,wts):
        tgt=int(max(MINF[layer],min(len(p['f']),BUDGET[layer]*w)))
        v,f=p['v'],p['f']
        if len(f)>tgt*1.1:
            try:
                v2,f2=v.astype(np.float32),f.astype(np.int32)
                for agg in (2,3,4,5,6,7):          # gentle passes first: they pick better collapses and keep thin sheets intact
                    if len(f2)>tgt*1.05: v2,f2=fs.simplify(v2,f2,target_count=tgt,agg=agg)
            except Exception as e:
                print('simplify fail',p['name'],e); v2,f2=v,f
        else: v2,f2=v,f
        V.append(v2); F.append(f2+off); off+=len(v2)
        G.append(np.full(len(v2),GI[p['g']],np.uint8)); PI.append(np.full(len(v2),len(plist),np.uint16))
        c=v-v.mean(0); ev,evec=np.linalg.eigh(c.T@c/len(c)); ax=evec[:,2]
        if abs(ax[1])>0.3 and ax[1]<0: ax=-ax
        plist.append({'n':p['name'],'g':GI[p['g']],'s':p['side'] or '','l':layer[0],'id':p['id'],'a':[round(float(x),2) for x in ax],'e':round(float(np.sqrt(ev[2]/max(ev[1],1e-9))),1)})
    V=np.vstack(V);F=np.vstack(F);G=np.concatenate(G);PI=np.concatenate(PI)
    q=np.round((V-bmin)/(bmax-bmin)*65535).astype('<u2')
    out[layer]=(q,G,PI.astype('<u2'),F.astype('<u4')); print(layer,'verts',len(V),'faces',len(F))
blob=b''; meta={'v':2,'parts':plist,'bmin':bmin.tolist(),'bmax':bmax.tolist(),'seg':SEG,'groups':GROUPS,'layers':{},'J':{k:v.round(2).tolist() for k,v in J.items()},
 'heartC':np.vstack([p['v'] for p in parts if p['name']=='wall of heart']).mean(0).round(1).tolist(),
 'lungC':np.vstack([p['v'] for p in parts if p['g']=='lung']).mean(0).round(1).tolist(),
 'credit':'BodyParts3D, (c) The Database Center for Life Science licensed under CC Attribution-Share Alike 2.1 Japan'}
# per layer: positions u16*3, group u8 (+pad to 2), part index u16 (+pad to 4), faces u32*3
for layer,(q,G,PI,F) in out.items():
    meta['layers'][layer]={'nv':len(q),'nf':len(F),'off':len(blob)}
    b=q.tobytes()+G.tobytes(); b+=b'\0'*(len(b)%2); b+=PI.tobytes(); b+=b'\0'*((-len(b))%4); blob+=b+F.tobytes()
open(OUT+'/anatomy.bin','wb').write(blob); json.dump(meta,open(OUT+'/anatomy.json','w'),separators=(',',':'))
gz=gzip.compress(blob,9); open(OUT+'/anatomy.bin.gz','wb').write(gz); print('bin',len(blob)/1e6,'gz',len(gz)/1e6)
