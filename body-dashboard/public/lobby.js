/* lobby.js — rotatable 3D body in a "character lobby" scene. No camera, no tracking, no skinning: the body stays in its rest pose.
   Drag to rotate, wheel or pinch to zoom, click to select. Bones and muscles are selectable one by one (every bone, every muscle);
   organs are selected as a group. Selection units: ids below PART0 are group + side, ids from PART0 up are single parts.
   Anatomy: BodyParts3D, CC BY-SA 2.1 JP. */
import * as THREE from 'three';

const PAL = { skull: '#e9f1ff', spineC: '#e9f1ff', spineT: '#e9f1ff', spineL: '#e9f1ff', ribs: '#dfeaff', shoulder: '#e9f1ff', arm: '#e9f1ff', hand: '#e9f1ff', pelvis: '#e9f1ff', femur: '#e9f1ff', shin: '#e9f1ff', foot: '#e9f1ff',
  heart: '#ff3b4e', artery: '#ff5a4a', vein: '#3f7dff', lung: '#ff9fb5', airway: '#9fe8ff', liver: '#c9703f', stomach: '#f2b56b', intestine: '#f0c9a0', kidney: '#b56cff', spleen: '#7fd6a0', brain: '#ffd1e6', eye: '#ffffff',
  mHead: '#b8463f', mChest: '#ab3b36', mAbdomen: '#a83f35', mUpperArm: '#b5413a', mForearm: '#ae4338', mThigh: '#a83934', mShin: '#b24038', tendon: '#efe4cc' };
const BASE_GLOW = { brain: .28, lung: .5, heart: 1.7, artery: 1.3, vein: 1.3, intestine: .6, liver: .8, eye: .5 };
/** Status tints that replace a group's own colour. 'watch' = amber, 'warn' = orange, 'alert' = red. */
const TINT = { ok: null, watch: '#ffd23f', warn: '#ff8a1f', alert: '#ff2d3d' };
const PART0 = 100;                               // first id of a single-part selection unit
const clamp = (v, a, b) => Math.min(b, Math.max(a, v));

export async function createLobby(canvas, { paired = [], onPick = () => {}, onHover = () => {} } = {}) {
  const meta = await (await fetch('./data/anatomy.json')).json();
  const GROUPS = meta.groups, GI = Object.fromEntries(GROUPS.map((n, i) => [n, i]));
  const PAIRED = new Set(paired);
  const palette = GROUPS.map(g => new THREE.Color(PAL[g] || '#fff'));
  const basePalette = palette.map(c => c.clone());
  const glow = new Float32Array(32).fill(1); for (const g in BASE_GLOW) glow[GI[g]] = BASE_GLOW[g];
  const baseGlow = Float32Array.from(glow);
  const lvl = new Float32Array(32);

  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true, premultipliedAlpha: true });
  renderer.setClearColor(0x000000, 0);
  const scene = new THREE.Scene(), body = new THREE.Group(); scene.add(body);
  const camera = new THREE.PerspectiveCamera(28, 1, 50, 20000);

  const U = { palette: { value: palette }, glow: { value: glow }, lvl: { value: lvl },
    heartC: { value: new THREE.Vector3(...meta.heartC) }, lungC: { value: new THREE.Vector3(...meta.lungC) },
    beat: { value: 0 }, breath: { value: 0 }, time: { value: 0 }, sel: { value: -1 }, selG: { value: -1 }, sib: { value: -1 }, hov: { value: -1 }, dimOthers: { value: .3 }, fade: { value: 0 } };
  const VS = `
    uniform vec3 palette[32]; uniform float glow[32]; uniform float lvl[32];
    uniform vec3 heartC; uniform vec3 lungC; uniform float beat; uniform float breath; uniform float time;
    attribute float grp; attribute float pid; attribute float gid; attribute vec3 fib; attribute float ten;
    varying vec3 vN; varying vec3 vCol; varying float vP; varying float vG; varying float vL;
    varying vec3 vPo; varying vec3 vNo; varying vec3 vFib; varying vec3 vFibV; varying float vTen; varying vec3 vView;
    void main(){
      int g=int(grp+0.5); vec3 p=position;
      if(g==${GI.heart}) p=heartC+(p-heartC)*(1.0+0.06*beat);
      if(g==${GI.lung}) p=lungC+(p-lungC)*(1.0+0.03*breath);
      float pulse=lvl[g]>=2.0?0.25*sin(time*4.0):0.0;
      vCol=palette[g]*glow[g]*(1.0+pulse); vP=pid; vG=gid; vL=lvl[g]; vN=normalMatrix*normal;
      vPo=position; vNo=normal; vFib=fib; vFibV=normalMatrix*fib; vTen=ten;
      vec4 mv=modelViewMatrix*vec4(p,1.0); vView=-mv.xyz;
      gl_Position=projectionMatrix*mv;
    }`;
  /* Solid look. Muscles get fibres that run along each muscle's long axis, a pale tendon towards both ends of long muscles,
     wrap lighting and a soft sheen along the fibres. Bones get a matte ivory finish. Each part is shifted slightly in tone so
     neighbours can be told apart. Fibre lines fade out when they would be thinner than a pixel, so nothing shimmers. */
  const FS = `
    uniform float opacity; uniform float xray; uniform float gain; uniform float fade; uniform float sel; uniform float selG; uniform float sib; uniform float hov;
    uniform float time; uniform float dimOthers; uniform float kind;
    varying vec3 vN; varying vec3 vCol; varying float vP; varying float vG; varying float vL;
    varying vec3 vPo; varying vec3 vNo; varying vec3 vFib; varying vec3 vFibV; varying float vTen; varying vec3 vView;
    float hash(float n){ return fract(sin(n*12.9898)*43758.5453); }
    void main(){
      vec3 n=normalize(vN); float ndv=abs(n.z); vec3 col; float a;
      float tone=hash(vP+3.0)-0.5;
      if(xray>0.5){ float rim=pow(1.0-ndv,1.35); col=vCol*(0.30+1.25*rim)*gain; a=(0.16+0.84*rim)*opacity; }
      else{
        if(n.z<0.0) n=-n;
        vec3 V=normalize(vView), L=normalize(vec3(0.35,0.55,0.75)), H=normalize(L+V);
        float nl=dot(n,L), rim=pow(1.0-ndv,3.0), sky=0.5+0.5*normalize(vNo).y;
        if(kind>1.5){                                                          // muscle
          vec3 base=vCol*(1.0+0.16*tone); base.r*=1.0+0.05*tone; base.b*=1.0-0.25*tone;
          float status=step(0.5,vL);
          if(dot(vFib,vFib)>0.2){
            vec3 no=normalize(vNo), sd=cross(normalize(vFib),no); float sl=length(sd);
            float u=dot(vPo,sd/max(sl,1e-4)), w=dot(vPo,normalize(vFib));
            float f1=u*0.55+0.6*sin(w*0.035+vP), f2=u*1.9+0.9*sin(w*0.05+vP*2.0);
            float k1=1.0-smoothstep(0.5,1.6,fwidth(f1)), k2=1.0-smoothstep(0.5,1.6,fwidth(f2));
            float fibre=(0.6*sin(f1)*k1+0.4*sin(f2)*k2)*smoothstep(0.15,0.5,sl);
            base*=0.86+0.24*fibre;
            base=mix(base,vec3(0.93,0.88,0.78),vTen*(1.0-0.75*status));        // tendon ends
          }
          float d=clamp((nl+0.3)/1.3,0.0,1.0); d=d*d*(3.0-2.0*d);
          col=base*(0.17+0.19*sky+0.82*d);
          vec3 T=normalize(vFibV-n*dot(vFibV,n)+1e-4); float th=dot(T,H);
          col+=vec3(1.0,0.82,0.74)*pow(max(1.0-th*th,0.0),22.0)*0.22*max(nl,0.0)*(1.0-vTen);   // sheen along the fibres
          col+=vec3(0.50,0.13,0.12)*rim*0.45;
        } else if(kind>0.5){                                                   // bone
          vec3 base=vCol*(1.0+0.07*tone)*vec3(1.0,0.985,0.95);
          float d=clamp((nl+0.25)/1.25,0.0,1.0);
          col=base*(0.20+0.16*sky+0.66*d)+vec3(1.0)*pow(max(dot(n,H),0.0),36.0)*0.10+vec3(0.10,0.13,0.16)*rim;
        } else { float d=max(nl,0.0); col=vCol*(0.22+0.78*d)+vec3(0.12)*rim; }
        a=opacity;
      }
      float isSel=(abs(vP-sel)<0.5||abs(vG-selG)<0.5)?1.0:0.0; float isHov=abs(vP-hov)<0.5?1.0:0.0;
      if(isSel<0.5){
        if(sel>=0.0&&xray<0.5) col=mix(col,vec3(0.045,0.07,0.095),abs(vG-sib)<0.5?0.30:0.68);   // single part: darken the rest, keep it solid
        else if(sel>=0.0||selG>=0.0) a*=dimOthers;
      }
      col=mix(col,vec3(0.6,0.92,1.0),0.38*isHov);
      if(isSel>0.5){ col=col*1.25+vec3(0.08,0.2,0.28)*(0.65+0.35*sin(time*3.0)); a=max(a,0.92*opacity); }
      gl_FragColor=vec4(col,a*fade);
    }`;
  const makeMat = (gain, kind) => new THREE.ShaderMaterial({ vertexShader: VS, fragmentShader: FS, transparent: true, side: THREE.DoubleSide,
    uniforms: { ...U, opacity: { value: 1 }, xray: { value: 0 }, gain: { value: gain }, kind: { value: kind } } });
  const idMat = new THREE.ShaderMaterial({ side: THREE.DoubleSide, blending: THREE.NoBlending, transparent: false,
    vertexShader: VS, fragmentShader: 'varying float vP; void main(){ float v=floor(vP+1.5); gl_FragColor=vec4(mod(v,256.0)/255.0,floor(v/256.0)/255.0,0.0,1.0); }',
    uniforms: { ...U } });

  /* ---- load anatomy ---- */
  let buf = await (await fetch('./data/anatomy.bin.gz')).arrayBuffer();
  const u8 = new Uint8Array(buf);
  if (u8[0] === 0x1f && u8[1] === 0x8b) buf = await new Response(new Blob([buf]).stream().pipeThrough(new DecompressionStream('gzip'))).arrayBuffer();
  const layers = {}, layerOf = {}, info = {};      // info[id] = {pid, group, side, center, radius, layer, part?, name?}
  const acc = {}, PARTS = meta.parts || [];
  const add = (id, name, x, y, z) => {
    const A = acc[id] || (acc[id] = { n: 0, s: [0, 0, 0], mn: [1e9, 1e9, 1e9], mx: [-1e9, -1e9, -1e9], layer: name });
    A.n++; A.s[0] += x; A.s[1] += y; A.s[2] += z;
    if (x < A.mn[0]) A.mn[0] = x; if (y < A.mn[1]) A.mn[1] = y; if (z < A.mn[2]) A.mn[2] = z;
    if (x > A.mx[0]) A.mx[0] = x; if (y > A.mx[1]) A.mx[1] = y; if (z > A.mx[2]) A.mx[2] = z;
  };
  for (const name of ['muscle', 'organ', 'bone']) {
    const L = meta.layers[name]; let o = L.off;
    const q = new Uint16Array(buf, o, L.nv * 3); o += L.nv * 6;
    const gr = new Uint8Array(buf, o, L.nv); o += L.nv; o += o % 2;
    const pi = new Uint16Array(buf, o, L.nv); o += L.nv * 2; o += (4 - (o % 4)) % 4;
    const idx = new Uint32Array(buf, o, L.nf * 3);
    const pos = new Float32Array(L.nv * 3), pid = new Float32Array(L.nv), gid = new Float32Array(L.nv), single = name !== 'organ';
    for (let i = 0; i < L.nv * 3; i++) { const a = i % 3; pos[i] = meta.bmin[a] + q[i] / 65535 * (meta.bmax[a] - meta.bmin[a]); }
    for (let i = 0; i < L.nv; i++) {
      const g = gr[i], P = PARTS[pi[i]], x = pos[i * 3], y = pos[i * 3 + 1], z = pos[i * 3 + 2];
      const left = P && P.s ? P.s === 'L' : x > 0, G = g * 2 + (PAIRED.has(GROUPS[g]) && left ? 1 : 0);
      gid[i] = G; pid[i] = single ? PART0 + pi[i] : G;
      add(G, name, x, y, z); if (single) add(PART0 + pi[i], name, x, y, z);
      if (!layerOf[GROUPS[g]]) layerOf[GROUPS[g]] = name;
    }
    const geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.BufferAttribute(pos, 3));
    geo.setAttribute('grp', new THREE.BufferAttribute(new Float32Array(gr), 1));
    geo.setAttribute('pid', new THREE.BufferAttribute(pid, 1));
    geo.setAttribute('gid', new THREE.BufferAttribute(gid, 1));
    if (name === 'muscle') {                       // fibre axis per vertex, and how far along its muscle the vertex sits
      const fib = new Float32Array(L.nv * 3), ten = new Float32Array(L.nv), lo = {}, hi = {}, tendon = GI.tendon;
      const proj = i => { const a = PARTS[pi[i]].a; return pos[i * 3] * a[0] + pos[i * 3 + 1] * a[1] + pos[i * 3 + 2] * a[2]; };
      for (let i = 0; i < L.nv; i++) { const k = pi[i], t = proj(i); if (!(t >= lo[k])) lo[k] = t; if (!(t <= hi[k])) hi[k] = t; }
      for (let i = 0; i < L.nv; i++) {
        const k = pi[i], P = PARTS[k]; fib.set(P.a, i * 3);
        const t = Math.abs((proj(i) - lo[k]) / Math.max(1e-6, hi[k] - lo[k]) * 2 - 1), long = clamp((P.e - 3) / 3, 0, 1), big = clamp((hi[k] - lo[k] - 60) / 90, 0, 1);
        const sm = clamp((t - .7) / .28, 0, 1); ten[i] = gr[i] === tendon ? 0 : sm * sm * (3 - 2 * sm) * long * big * .85;
      }
      geo.setAttribute('fib', new THREE.BufferAttribute(fib, 3)); geo.setAttribute('ten', new THREE.BufferAttribute(ten, 1));
    }
    geo.setIndex(new THREE.BufferAttribute(idx, 1)); geo.computeVertexNormals();
    const mesh = new THREE.Mesh(geo, makeMat(name === 'muscle' ? .6 : name === 'organ' ? 1 : .95, name === 'muscle' ? 2 : name === 'bone' ? 1 : 0));
    mesh.frustumCulled = false; mesh.renderOrder = name === 'muscle' ? 1 : name === 'organ' ? 2 : 3;
    body.add(mesh); layers[name] = mesh;
  }
  // Neutral outer anatomy provides spatial context without intercepting picks.
  const shell = new THREE.Mesh(layers.muscle.geometry, new THREE.ShaderMaterial({
    transparent:true, depthWrite:false, side:THREE.DoubleSide, uniforms:{k:{value:1}},
    vertexShader:'varying vec3 n; varying vec3 v; void main(){vec4 p=modelViewMatrix*vec4(position,1.0);n=normalize(normalMatrix*normal);v=normalize(-p.xyz);gl_Position=projectionMatrix*p;}',
    fragmentShader:'uniform float k; varying vec3 n; varying vec3 v; void main(){float rim=pow(1.0-abs(dot(normalize(n),normalize(v))),2.2);gl_FragColor=vec4(0.38,0.77,0.74,(0.008+0.055*rim)*k);}'
  }));
  shell.renderOrder=4; body.add(shell);
  for (const id in acc) {
    const A = acc[id], c = A.s.map(v => v / A.n);
    const r = Math.hypot(A.mx[0] - A.mn[0], A.mx[1] - A.mn[1], A.mx[2] - A.mn[2]) / 2;
    if (+id >= PART0) { const P = PARTS[id - PART0], g = GROUPS[P.g];
      info[id] = { pid: +id, part: id - PART0, name: P.n, bp3d: P.id, named: P.s === 'L' ? 'left' : P.s === 'R' ? 'right' : null, group: g, side: P.s === 'L' ? 'left' : P.s === 'R' ? 'right' : PAIRED.has(g) ? (c[0] > 0 ? 'left' : 'right') : null,
        gid: P.g * 2 + (PAIRED.has(g) && (P.s ? P.s === 'L' : c[0] > 0) ? 1 : 0), center: new THREE.Vector3(...c), radius: r, layer: A.layer };
    } else info[id] = { pid: +id, gid: +id, group: GROUPS[Math.floor(id / 2)], side: id % 2 ? 'left' : 'right', center: new THREE.Vector3(...c), radius: r, layer: A.layer };
  }

  /* Scanner pad: dark dais with a clean light floor, a soft beam, a few drifting particles and distant stars.
     Lines are anti-aliased with fwidth() so they do not shimmer when the camera moves. Everything lives in `platform`,
     which is hidden while picking. */
  const platform = new THREE.Group(); scene.add(platform);
  scene.add(new THREE.HemisphereLight(0x9ab6cb, 0x03070c, 2));
  const keyLight = new THREE.DirectionalLight(0xd9eeff, 3); keyLight.position.set(-700, 1400, 700); scene.add(keyLight);
  const rimLight = new THREE.PointLight(0x5de1cb, 1800000, 2300); rimLight.position.set(450, 300, -450); scene.add(rimLight);
  const PU = { time: U.time };
  const TOP = -12;                                                  // top face of the dais; the light floor sits just above it
  function disc(rTop, rBottom, height, yTop, color, metal, rough) {
    const m = new THREE.Mesh(new THREE.CylinderGeometry(rTop, rBottom, height, 160), new THREE.MeshStandardMaterial({ color, metalness: metal, roughness: rough }));
    m.position.y = yTop - height / 2; platform.add(m); return m;
  }
  disc(470, 500, 40, TOP, 0x0e1a24, .75, .3);                       // main dais
  disc(530, 560, 14, TOP - 40, 0x0a131a, .7, .4);                   // base step
  function torus(radius, y, color, thickness, opacity = 1) {
    const m = new THREE.Mesh(new THREE.TorusGeometry(radius, thickness, 12, 200), new THREE.MeshBasicMaterial({ color, transparent: opacity < 1, opacity, depthWrite: opacity >= 1 }));
    m.rotation.x = -Math.PI / 2; m.position.y = y; platform.add(m); return m;
  }
  torus(470, TOP, 0x63dbcd, 2.4);                                   // lit rim of the dais
  torus(530, TOP - 40, 0x2b7f7a, 1.6, .7);

  const floor = new THREE.Mesh(new THREE.CircleGeometry(462, 160).rotateX(-Math.PI / 2), new THREE.ShaderMaterial({
    transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, premultipliedAlpha: true, uniforms: PU,
    polygonOffset: true, polygonOffsetFactor: -2, polygonOffsetUnits: -2,
    vertexShader: 'varying vec2 p; void main(){ p=position.xz/462.0; gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.0); }',
    fragmentShader: `
      uniform float time; varying vec2 p;
      float line(float d, float w){ float f=fwidth(d); return 1.0-smoothstep(w, w+f*1.5, abs(d)); }
      void main(){
        float r=length(p); if(r>1.0) discard; float a=atan(p.y,p.x)/6.2831853+0.5;
        vec3 teal=vec3(0.39,0.86,0.80), coral=vec3(1.0,0.57,0.62);
        vec3 col=teal*exp(-r*r*5.0)*0.32;                                     // soft glow under the feet
        col+=teal*line(r-0.94,0.004)*0.75;                                     // outer ring
        col+=teal*line(r-0.62,0.002)*0.35;                                     // inner ring
        float arc=step(0.0,sin((a+time*0.012)*6.2831853*3.0)-0.55);            // three slow arcs
        col+=teal*line(r-0.80,0.003)*arc*0.6;
        float carc=step(0.0,sin((a-time*0.008)*6.2831853)-0.85);               // one coral accent
        col+=coral*line(r-0.86,0.002)*carc*0.7;
        float pr=fract(time*0.16); col+=teal*line(r-pr*0.94,0.006)*(1.0-pr)*0.35;   // gentle outward pulse
        float a2=min(1.0,max(col.r,max(col.g,col.b)));
        gl_FragColor=vec4(col,a2);
      }`
  }));
  floor.position.y = TOP + 1.5; floor.renderOrder = 0; platform.add(floor);

  const beam = new THREE.Mesh(new THREE.CylinderGeometry(455, 455, 560, 160, 1, true), new THREE.ShaderMaterial({
    transparent: true, depthWrite: false, side: THREE.DoubleSide, blending: THREE.AdditiveBlending, premultipliedAlpha: true, uniforms: PU,
    vertexShader: 'varying vec2 u; void main(){ u=uv; gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.0); }',
    fragmentShader: `uniform float time; varying vec2 u;
      void main(){ float h=pow(1.0-u.y,3.0); float slow=0.85+0.15*sin(u.x*6.2831853*6.0+time*0.4);
        vec3 c=vec3(0.30,0.85,0.80)*h*slow*0.14; gl_FragColor=vec4(c,c.g); }`
  }));
  beam.position.y = TOP + 280; platform.add(beam);

  { // a few particles drifting up inside the beam
    const N = 70, pos = new Float32Array(N * 3), seed = new Float32Array(N); let s = 7;
    const rnd = () => (s = (s * 16807) % 2147483647) / 2147483647;
    for (let i = 0; i < N; i++) { const a = rnd() * Math.PI * 2, r = 140 + Math.sqrt(rnd()) * 290; pos[i * 3] = Math.cos(a) * r; pos[i * 3 + 1] = rnd() * 900; pos[i * 3 + 2] = Math.sin(a) * r; seed[i] = rnd(); }
    const g = new THREE.BufferGeometry(); g.setAttribute('position', new THREE.BufferAttribute(pos, 3)); g.setAttribute('seed', new THREE.BufferAttribute(seed, 1));
    const pts = new THREE.Points(g, new THREE.ShaderMaterial({ transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, premultipliedAlpha: true, uniforms: PU,
      vertexShader: `uniform float time; attribute float seed; varying float al;
        void main(){ vec3 q=position; q.y=mod(position.y+time*(14.0+seed*20.0),900.0); al=smoothstep(0.0,80.0,q.y)*(1.0-q.y/900.0);
          vec4 mv=modelViewMatrix*vec4(q,1.0); gl_PointSize=(2.0+seed*3.0)*(2400.0/-mv.z); gl_Position=projectionMatrix*mv; }`,
      fragmentShader: 'varying float al; void main(){ float d=length(gl_PointCoord-0.5); if(d>0.5) discard; vec3 c=vec3(0.45,0.95,0.88)*al*smoothstep(0.5,0.0,d)*0.6; gl_FragColor=vec4(c,c.g); }' }));
    pts.frustumCulled = false; platform.add(pts);
  }
  const halo = new THREE.Mesh(new THREE.CircleGeometry(1000, 96).rotateX(-Math.PI / 2), new THREE.ShaderMaterial({
    transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, premultipliedAlpha: true,
    vertexShader: 'varying vec2 p;void main(){p=position.xz/1000.0;gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.0);}',
    fragmentShader: 'varying vec2 p;void main(){float r=length(p);float a=exp(-r*r*5.0)*0.2;vec3 c=vec3(0.12,0.55,0.49)*a;gl_FragColor=vec4(c,a*0.5);}'
  })); halo.position.y = TOP - 60; platform.add(halo);
  { // distant stars, static
    const N = 380, pos = new Float32Array(N * 3), seed = new Float32Array(N); let s = 99;
    const rnd = () => (s = (s * 16807) % 2147483647) / 2147483647;
    for (let i = 0; i < N; i++) { const a = rnd() * Math.PI * 2, y = Math.min(1, -0.2 + rnd() * 1.2), rr = Math.sqrt(1 - y * y), R = 9000 + rnd() * 3000; pos[i * 3] = Math.cos(a) * rr * R; pos[i * 3 + 1] = y * R + 790; pos[i * 3 + 2] = Math.sin(a) * rr * R; seed[i] = rnd(); }
    const g = new THREE.BufferGeometry(); g.setAttribute('position', new THREE.BufferAttribute(pos, 3)); g.setAttribute('seed', new THREE.BufferAttribute(seed, 1));
    const stars = new THREE.Points(g, new THREE.ShaderMaterial({ transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, premultipliedAlpha: true, uniforms: { dpr: { value: Math.min(devicePixelRatio || 1, 1.5) } },
      vertexShader: 'uniform float dpr; attribute float seed; varying float al; void main(){ al=0.2+0.6*seed*seed; gl_PointSize=(1.2+seed*seed*1.8)*dpr; gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.0); }',
      fragmentShader: 'varying float al; void main(){ float d=length(gl_PointCoord-0.5); if(d>0.5) discard; vec3 c=vec3(0.75,0.9,1.0)*al*smoothstep(0.5,0.1,d); gl_FragColor=vec4(c,c.b); }' }));
    stars.frustumCulled = false; stars.renderOrder = -1; platform.add(stars);
  }

  /* ---- camera orbit ---- */
  const T0 = new THREE.Vector3(0, 790, 0), ZMIN = 260;
  const cam = { yaw: .45, pitch: .08, dist: 3800, target: T0.clone(), goalTarget: T0.clone(), goalDist: 3800, baseDist: 3800, vYaw: 0, idle: 0 };
  function fit() {
    const w = canvas.clientWidth || 600, h = canvas.clientHeight || 800, dpr = Math.min(devicePixelRatio || 1, 1.5);
    renderer.setPixelRatio(dpr); renderer.setSize(w, h, false); camera.aspect = w / h;
    const tv = Math.tan(camera.fov * Math.PI / 360), byH = 1180 / tv, byW = 540 / (tv * camera.aspect);
    const old = cam.baseDist; cam.baseDist = Math.max(byH, byW);
    if (!selected && Math.abs(cam.goalDist - old) < 1) cam.goalDist = cam.baseDist; else cam.goalDist = clamp(cam.goalDist, ZMIN, cam.baseDist * 1.15);
    camera.updateProjectionMatrix();
  }
  new ResizeObserver(fit).observe(canvas.parentElement || canvas);
  function placeCamera() {
    cam.pitch = Math.max(cam.pitch, Math.asin(clamp((10 - cam.target.y) / cam.dist, -1, 1)));
    const cp = Math.cos(cam.pitch);
    camera.position.set(cam.target.x + cam.dist * cp * Math.sin(cam.yaw), cam.target.y + cam.dist * Math.sin(cam.pitch), cam.target.z + cam.dist * cp * Math.cos(cam.yaw));
    camera.lookAt(cam.target);
  }

  /* ---- state ---- */
  let layer = 'bone', look = 'solid', selected = -1, hovered = -1, hr = 70, opacity = 1, auto = true;
  function applyLayer() {
    const all = layer === 'all', xr = look === 'xray', ghost = layer === 'organ' && xr;
    shell.visible = layer === 'organ'; shell.material.uniforms.k.value = xr ? .45 : 1;
    for (const n in layers) {
      const m = layers[n]; m.visible = all || layer === n || (ghost && n === 'bone');
      m.material.uniforms.opacity.value = opacity * (ghost && n === 'bone' ? .22 : all && xr ? (n === 'muscle' ? .4 : n === 'bone' ? .75 : 1) : all && n === 'muscle' ? .55 : 1);
      m.material.uniforms.xray.value = xr ? 1 : 0;
      m.material.blending = xr ? THREE.AdditiveBlending : THREE.NormalBlending;
      m.material.depthTest = !xr; m.material.depthWrite = !xr; m.material.needsUpdate = true;
    }
  }
  applyLayer();

  /* ---- picking: render only the pixel under the pointer into a 1x1 target (colour = id + 1) ---- */
  const rt = new THREE.WebGLRenderTarget(1, 1, { depthBuffer: true }), px = new Uint8Array(4);
  function pick(cx, cy) { try { stats.picks++; return pickRaw(cx, cy); } catch (e) { stats.pickErr++; stats.lastErr = String(e && e.message || e).slice(0, 160); for (const n in layers) { layers[n].visible = true; } applyLayer(); renderer.setRenderTarget(null); camera.clearViewOffset(); platform.visible = true; renderer.autoClear = true; return -1; } }
  function pickRaw(cx, cy) {
    const r = canvas.getBoundingClientRect(); if (!r.width) return -1;
    const bw = renderer.domElement.width, bh = renderer.domElement.height;
    const x = Math.floor((cx - r.left) / r.width * bw), y = Math.floor((cy - r.top) / r.height * bh);
    if (x < 0 || y < 0 || x >= bw || y >= bh) return -1;
    shell.visible = false;
    const vis = {}; for (const n in layers) { vis[n] = layers[n].visible; }
    const mats = {}; for (const n in layers) mats[n] = layers[n].material;
    const order = layer === 'all' ? ['muscle', 'bone', 'organ'] : [layer];      // later passes win: organ > bone > muscle
    camera.setViewOffset(bw, bh, x, y, 1, 1);
    const prevAuto = renderer.autoClear, prevT = renderer.getRenderTarget(), hp = platform.visible;
    renderer.autoClear = false; platform.visible = false; renderer.setRenderTarget(rt);
    renderer.setClearColor(0x000000, 0); renderer.clear(true, true, true);
    for (const n of order) {
      for (const k in layers) { layers[k].visible = k === n; layers[k].material = idMat; }
      renderer.clearDepth(); renderer.render(scene, camera);
    }
    renderer.readRenderTargetPixels(rt, 0, 0, 1, 1, px);
    renderer.setRenderTarget(prevT); renderer.autoClear = prevAuto; platform.visible = hp; camera.clearViewOffset();
    for (const n in layers) { layers[n].visible = vis[n]; layers[n].material = mats[n]; }
    shell.visible = layer === 'organ';
    const v = px[0] + px[1] * 256; return v > 0 && info[v - 1] ? v - 1 : -1;
  }

  /* ---- input ---- */
  const ptrs = new Map(); let down = null, lastHover = 0, pinch = 0;
  const stats = { down: 0, move: 0, up: 0, wheel: 0, picks: 0, pickErr: 0, lastErr: '' };
  canvas.style.touchAction = 'none';
  canvas.addEventListener('pointerdown', e => {
    stats.down++; clearTimeout(lastHover);
    canvas.setPointerCapture(e.pointerId); ptrs.set(e.pointerId, { x: e.clientX, y: e.clientY });
    if (ptrs.size === 1) down = { x: e.clientX, y: e.clientY, t: performance.now(), moved: 0 }; else { down = null; pinch = 0; }
    cam.vYaw = 0; cam.idle = 0;
  });
  canvas.addEventListener('pointermove', e => {
    stats.move++; const p = ptrs.get(e.pointerId);
    if (!p) {                                                              // hover (mouse only)
      if (e.pointerType !== 'mouse') return;
      const x = e.clientX, y = e.clientY;
      if (hovered >= 0) onHover(info[hovered], x, y);                       // keep the tooltip with the cursor
      clearTimeout(lastHover); lastHover = setTimeout(() => {               // read the GPU only once the pointer rests
        const id = pick(x, y); if (id !== hovered) { hovered = id; U.hov.value = id; canvas.style.cursor = id >= 0 ? 'pointer' : 'grab'; onHover(id >= 0 ? info[id] : null, x, y); }
      }, 70);
      return;
    }
    const dx = e.clientX - p.x, dy = e.clientY - p.y; p.x = e.clientX; p.y = e.clientY; cam.idle = 0;
    if (ptrs.size === 2) {
      const [a, b] = [...ptrs.values()], d = Math.hypot(a.x - b.x, a.y - b.y);
      if (pinch) cam.goalDist = clamp(cam.goalDist * pinch / d, ZMIN, cam.baseDist * 1.15); pinch = d; return;
    }
    if (down) down.moved += Math.abs(dx) + Math.abs(dy);
    cam.yaw -= dx * .0085; cam.vYaw = -dx * .0085 * 60; cam.pitch = clamp(cam.pitch + dy * .006, -.7, .9);
    canvas.style.cursor = 'grabbing';
  });
  const end = e => {
    stats.up++;
    ptrs.delete(e.pointerId); pinch = 0; canvas.style.cursor = 'grab';
    if (down && e.type === 'pointerup' && down.moved < 8 && performance.now() - down.t < 600) {
      const id = pick(e.clientX, e.clientY); select(id >= 0 ? id : -1, true);
    }
    if (!ptrs.size) down = null;
  };
  canvas.addEventListener('pointerup', end); canvas.addEventListener('pointercancel', end);
  canvas.addEventListener('pointerleave', e => { clearTimeout(lastHover); if (e.pointerType === 'mouse' && hovered >= 0) { hovered = -1; U.hov.value = -1; onHover(null); } });
  canvas.addEventListener('wheel', e => { stats.wheel++; e.preventDefault(); cam.goalDist = clamp(cam.goalDist * Math.exp(e.deltaY * .0012), ZMIN, cam.baseDist * 1.15); cam.idle = 0; }, { passive: false });
  canvas.style.cursor = 'grab';

  const scl = { x: 1, y: 1 };                                      // body scale from height and mass (see setBody)
  const worldC = i => new THREE.Vector3(i.center.x * scl.x, i.center.y * scl.y, i.center.z * scl.x);
  function select(id, fromUser) {
    if (!(id >= 0) || !info[id]) id = -1;
    selected = id; const part = id >= PART0;
    U.sel.value = part ? id : -1; U.selG.value = id >= 0 && !part ? id : -1; U.sib.value = part ? info[id].gid : -1;
    if (id >= 0) { const i = info[id], c = worldC(i); cam.goalTarget.copy(c); cam.goalTarget.y = clamp(c.y, 90, 1700); cam.goalDist = clamp(i.radius * (part ? 5.2 : 3.6), part ? 330 : 650, cam.baseDist); }
    else { cam.goalTarget.copy(T0); cam.goalDist = cam.baseDist; }
    onPick(id >= 0 ? info[id] : null, !!fromUser);
  }

  /* ---- loop ---- */
  let t0 = performance.now(), tPrev = t0, started = false;
  function frame(now) {
    requestAnimationFrame(frame);
    if (!started) { if (!canvas.clientWidth) return; started = true; fit(); cam.dist = cam.goalDist = cam.baseDist; }
    const dt = Math.min(.1, (now - tPrev) / 1000); tPrev = now; const t = (now - t0) / 1000;
    U.time.value = t; U.fade.value += (1 - U.fade.value) * Math.min(1, dt * 3);
    const ph = (t * hr / 60) % 1; U.beat.value = Math.exp(-ph * 9) * Math.sin(Math.min(1, ph * 6) * Math.PI) + .45 * Math.exp(-Math.abs(ph - .32) * 22);
    U.breath.value = Math.sin(t * 2 * Math.PI / 4.5);
    cam.idle += dt;
    if (!ptrs.size) { cam.yaw += cam.vYaw * dt; cam.vYaw *= Math.pow(.02, dt); if (auto && cam.idle > 5 && selected < 0 && Math.abs(cam.vYaw) < .05) cam.yaw += .16 * dt; }
    const k = 1 - Math.pow(.0015, dt);
    cam.target.lerp(cam.goalTarget, k); cam.dist += (cam.goalDist - cam.dist) * k;
    placeCamera(); renderer.render(scene, camera);
  }
  requestAnimationFrame(frame);

  return {
    groups: GROUPS, layerOf, info, THREE, PART0, parts: PARTS,
    ids: () => Object.keys(info).map(Number),
    pidOf: (group, side) => GI[group] * 2 + (PAIRED.has(group) && side === 'left' ? 1 : 0),
    setLayer(l) { layer = l; applyLayer(); },
    getLayer: () => layer,
    setLook(l) { look = l === 'xray' ? 'xray' : 'solid'; applyLayer(); },
    getLook: () => look,
    setOpacity(v) { opacity = v; applyLayer(); },
    /** status: {group: 'watch'|'warn'|'alert'} — everything else is reset to its own colour. */
    setStatus(map) {
      for (let i = 0; i < GROUPS.length; i++) { palette[i].copy(basePalette[i]); glow[i] = baseGlow[i]; lvl[i] = 0; }
      for (const g in map) { const i = GI[g], s = map[g]; if (i === undefined || !TINT[s]) continue;
        palette[i].copy(basePalette[i]).lerp(new THREE.Color(TINT[s]), s === 'watch' ? .7 : .85); glow[i] = s === 'watch' ? 1.35 : 1.8; lvl[i] = s === 'watch' ? 1 : s === 'warn' ? 2 : 3; }
    },
    select, selected: () => selected,
    /** Selection units of one group (and side): every single bone or muscle in it. */
    partsOf: (group, side) => Object.values(info).filter(i => i.pid >= PART0 && i.group === group && (!side || !i.side || i.side === side)),
    /** Rough body scaling: sy stretches the height, sx the breadth and depth. The model is scaled, not re-shaped. */
    setBody(sx, sy) { scl.x = clamp(+sx || 1, .8, 1.3); scl.y = clamp(+sy || 1, .8, 1.3); body.scale.set(scl.x, scl.y, scl.x); T0.y = 790 * scl.y;
      if (selected >= 0) { const c = worldC(info[selected]); cam.goalTarget.copy(c); cam.goalTarget.y = clamp(c.y, 90, 1700); } else cam.goalTarget.copy(T0); },
    getBody: () => ({ ...scl }),
    resetView() { select(-1); cam.yaw = .45; cam.pitch = .08; cam.vYaw = 0; },
    setAutoRotate(v) { auto = !!v; },
    setHeartRate(b) { hr = clamp(+b || 70, 30, 200); },
    nudge(d) { cam.vYaw = d * 2.2; cam.idle = 0; },
    stats,
    snapshot() { try { renderer.render(scene, camera); const c = document.createElement('canvas'); c.width = canvas.width; c.height = canvas.height; const x = c.getContext('2d'); x.fillStyle = '#0b1a30'; x.fillRect(0, 0, c.width, c.height); x.drawImage(canvas, 0, 0); return c.toDataURL('image/jpeg', .8); } catch (e) { return ''; } },
    pickAt: pick,
    camera: cam
  };
}
