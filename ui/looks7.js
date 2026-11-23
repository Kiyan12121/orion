/* ORION 7.0 — the Orion Core and Halo looks: the living core, callouts, the orbiting places, ghost mode.
   Shares globals with index.html (api, cfg, state, speaking, audioLevel, micLevel, lite, go, globeOpen, UIP, applyUi). */
(function(){
const core=document.querySelector(".stage .core");
if(!core) return;
core.insertAdjacentHTML("afterbegin",`<canvas id="look0"></canvas><canvas id="look"></canvas>`);
core.insertAdjacentHTML("beforeend",`
  <div class="co7" id="co0"></div><div class="co7" id="co1"></div><div class="co7 r" id="co2"></div><div class="co7 r" id="co3"></div>
  <div class="greet7"><small id="g7s">ORION CORE · STANDING BY</small><h2 id="g7h">Good evening, <em>sir</em>.</h2><p id="g7p"></p></div>
  <div class="orbit7" id="orbit7"></div><div class="hgreet7" id="hg7"><b id="hg7b">Evening, sir.</b><span>Tap a place, or just start talking</span></div>
  <div class="glance7" id="gl7"></div>`);
const ORB=[["Home","comms"],["Revision","study"],["Money","ventures"],["Streams","streams"],["Automate","automate"],["Globe","globe"],["PC","dash"],["Settings","settings"]];
const orbit=document.getElementById("orbit7");
orbit.innerHTML=ORB.map(([n,p])=>`<button data-o="${p}">${n}</button>`).join("");
orbit.addEventListener("click",e=>{ const b=e.target.closest("[data-o]"); if(!b) return; const p=b.dataset.o;
  if(p==="globe"){ try{ globeOpen(); }catch(err){} } else if(p==="settings") document.getElementById("nSet").click(); else go(p); });

const cv=document.getElementById("look"), x=cv.getContext("2d");
let W=0,H=0,GL=[],last=0,GHOST=false,EMA=4,LEAD=[],stars=[];
const STATIC=document.getElementById("look0"), sx=STATIC.getContext("2d"); let staticKey="";
const SPR={};
const STARS=[[.32,.04,1],[.12,.2,0,1],[.74,.24,0],[.36,.52,2],[.5,.48,2],[.63,.44,2],[.18,.94,0],[.82,.86,1]];
const LINES=[[0,1],[0,2],[1,3],[2,5],[3,4],[4,5],[3,6],[5,7]];
function skin(){ return UIP&&UIP.skin; }
function active(){ const s=skin(); return (s==="core"||s==="halo")&&!GHOST&&!document.hidden&&!document.querySelector(".stage.wide"); }
function size(){ const r=core.getBoundingClientRect(); W=Math.round(r.width); H=Math.round(r.height); if(!W||!H) return;
  cv.width=W; cv.height=H; STATIC.width=W; STATIC.height=H; staticKey="";
  stars=[]; for(let i=0;i<Math.round(W*H/7000);i++) stars.push([Math.random()*W,Math.random()*H,Math.random()*1.1+.3,.2+Math.random()*.45]); place(); }
function geo(){ const halo=skin()==="halo"; const cx=W*(halo&&W>900?.6:.5), cy=H*(halo?.42:.43), R=Math.min(W*.24,H*(halo?.25:.27)); return {cx,cy,R}; }
function acc(){ const cs=getComputedStyle(document.body); return {a:cs.getPropertyValue("--ar").trim()||"139,233,255", think:cs.getPropertyValue("--thinkr").trim()||"255,179,71", listen:cs.getPropertyValue("--listenr").trim()||"255,79,123"}; }
let ACC=null; setInterval(()=>{ ACC=null; },3000);           // colours change rarely; don't read styles every frame
function col3(){ if(!ACC) ACC=acc(); return ACC; }
function place(){ const {cx,cy,R}=geo(); const narrow=W<760;
  const spots=[[cx-R*1.42-230,cy-R*.95],[cx-R*1.48-230,cy+R*.55],[cx+R*1.42,cy-R*.95],[cx+R*1.48,cy+R*.55]];
  spots.forEach(([l,t],i)=>{ const el=document.getElementById("co"+i); el.style.left=Math.max(4,Math.min(W-234,l))+"px"; el.style.top=t+"px"; el.style.display=narrow?"none":""; });
  const n=ORB.length, rr=R*1.45; orbit.querySelectorAll("button").forEach((b,i)=>{ const a=-Math.PI/2+i*2*Math.PI/n; b.style.left=(cx+Math.cos(a)*rr*(W>900?1.18:1))+"px"; b.style.top=(cy+Math.sin(a)*rr)+"px"; });
  const hg=document.getElementById("hg7"); hg.style.left=cx+"px"; hg.style.top=cy+"px"; requestAnimationFrame(lead); }
function lead(){ const {cx,cy,R}=geo(), cr=core.getBoundingClientRect(); LEAD=[];   // leader-line ends, measured once (not every frame)
  if(W<760) return; [[-.86,-.62,0],[-.9,.5,1],[.86,-.66,2],[.9,.6,3]].forEach(([dx,dy,i])=>{ const el=document.getElementById("co"+i); if(!el.textContent) return; const r=el.getBoundingClientRect();
    LEAD.push([cx+R*dx,cy+R*dy,i<2?r.right-cr.left+6:r.left-cr.left-6,r.top-cr.top+26]); }); staticKey=""; }
addEventListener("resize",size); new ResizeObserver(()=>size()).observe(core);
function sprite(rgb,r,warm){ const k=rgb+r+(warm?"w":""); if(SPR[k]) return SPR[k]; const c=document.createElement("canvas"); c.width=c.height=r*2; const g=c.getContext("2d");
  const gr=g.createRadialGradient(r,r,0,r,r,r); gr.addColorStop(0,warm?"rgba(255,190,140,.95)":"rgba(228,246,255,.95)"); gr.addColorStop(.25,`rgba(${rgb},.45)`); gr.addColorStop(1,`rgba(${rgb},0)`); g.fillStyle=gr; g.fillRect(0,0,r*2,r*2);
  g.fillStyle="#fff"; g.beginPath(); g.arc(r,r,Math.max(1.4,r*.1),0,7); g.fill(); return SPR[k]=c; }
function glowSprite(rgb,r){ const k="g"+rgb+r; if(SPR[k]) return SPR[k]; const c=document.createElement("canvas"); c.width=c.height=r*2; const g=c.getContext("2d");
  const gr=g.createRadialGradient(r,r,0,r,r,r); gr.addColorStop(0,`rgba(${rgb},.16)`); gr.addColorStop(1,`rgba(${rgb},0)`); g.fillStyle=gr; g.fillRect(0,0,r*2,r*2); return SPR[k]=c; }
function haloRing(rgb,R){ const k="h"+rgb+R; if(SPR[k]) return SPR[k]; const pad=60, c=document.createElement("canvas"); c.width=c.height=(R+pad)*2; const g=c.getContext("2d"), m=R+pad;
  for(let i=0;i<3;i++){ const rr=R+i*10; const gr=g.createRadialGradient(m,m,rr-30,m,m,rr+46); gr.addColorStop(0,"rgba(127,255,208,0)"); gr.addColorStop(.45,`rgba(127,255,208,${.11-i*.03})`); gr.addColorStop(.55,`rgba(165,139,255,${.15-i*.04})`); gr.addColorStop(1,"rgba(165,139,255,0)"); g.fillStyle=gr; g.beginPath(); g.arc(m,m,rr+46,0,7); g.fill(); }
  const cg=g.createConicGradient?g.createConicGradient(0,m,m):null; if(cg){ cg.addColorStop(0,`rgb(${rgb})`); cg.addColorStop(.33,"#69d7ff"); cg.addColorStop(.66,"#a58bff"); cg.addColorStop(1,`rgb(${rgb})`); g.strokeStyle=cg; } else g.strokeStyle=`rgb(${rgb})`;
  g.lineWidth=3; g.beginPath(); g.arc(m,m,R,0,7); g.stroke(); return SPR[k]=c; }

/* ---- the parts that never move: drawn once, reused every frame ---- */
function drawStatic(col,halo){ const {cx,cy,R}=geo(), g=sx; g.clearRect(0,0,W,H);
  for(const s of stars){ g.globalAlpha=s[3]; g.fillStyle=halo?"#e8e6ff":"#d6ecff"; g.fillRect(s[0],s[1],s[2],s[2]); } g.globalAlpha=1;
  if(!halo){ const gs=glowSprite(col,Math.round(R*1.6)); g.drawImage(gs,cx-R*1.6,cy-R*1.6); }
  if(halo){ g.lineWidth=1; g.strokeStyle="rgba(255,255,255,.1)"; g.beginPath(); g.arc(cx,cy,R*1.45,0,7); g.stroke();
    g.setLineDash([2,8]); g.strokeStyle="rgba(255,255,255,.16)"; g.beginPath(); g.arc(cx,cy,R*1.17,0,7); g.stroke(); g.setLineDash([]); return; }
  const ring=(r,a,dots)=>{ g.strokeStyle=`rgba(${col},${a})`; g.lineWidth=1; g.beginPath(); g.arc(cx,cy,r,0,7); g.stroke();
    if(dots) for(let k=0;k<60;k++){ const an=k/60*Math.PI*2, s2=k%5?1.3:2.4; g.fillStyle=`rgba(${col},${k%5?a*.45:a*1.3})`; g.fillRect(cx+Math.cos(an)*r-s2/2,cy+Math.sin(an)*r-s2/2,s2,s2); } };
  ring(R,.32,true); ring(R*.78,.16); ring(R*1.18,.09);
  for(let k=0;k<180;k++){ const an=k/180*Math.PI*2, l=k%15?5:11; g.strokeStyle=`rgba(${col},${k%15?.22:.55})`; g.beginPath(); g.moveTo(cx+Math.cos(an)*R*1.26,cy+Math.sin(an)*R*1.26); g.lineTo(cx+Math.cos(an)*(R*1.26+l),cy+Math.sin(an)*(R*1.26+l)); g.stroke(); }
  g.strokeStyle=`rgba(${col},.3)`; g.fillStyle=`rgba(${col},.9)`; for(const [ax,ay,ex,ey] of LEAD){ g.beginPath(); g.moveTo(ax,ay); g.lineTo(ex,ey); g.stroke(); g.beginPath(); g.arc(ax,ay,2.4,0,7); g.fill(); } }

function drawCore(t,lv){ const {cx,cy,R}=geo(), C=col3(); const think=state==="thinking", listen=state==="listening"; const col=think?C.think:listen?C.listen:C.a;
  const key="c"+col+W+H+LEAD.length; if(staticKey!==key){ drawStatic(col,false); staticKey=key; }
  const B=R*1.62; x.clearRect(cx-B,cy-B,B*2,B*2);
  if(lv>.03){ const gs=glowSprite(col,Math.round(R*1.6)), gr=R*1.6*lv*.25; x.globalAlpha=Math.min(1,lv*1.5); x.drawImage(gs,cx-R*1.6-gr,cy-R*1.6-gr,(R*1.6+gr)*2,(R*1.6+gr)*2); x.globalAlpha=1; }
  const spin=t*(think?.9:.18);
  const ell=(rx,ry,rot,a)=>{ x.save(); x.translate(cx,cy); x.rotate(rot); x.strokeStyle=`rgba(${col},${a})`; x.lineWidth=1.2; x.beginPath(); x.ellipse(0,0,rx,ry,0,0,7); x.stroke();
    x.fillStyle=`rgba(${col},${a*1.2})`; for(let k=0;k<24;k++){ const an=k/24*Math.PI*2; x.fillRect(Math.cos(an)*rx-1,Math.sin(an)*ry-1,2,2); } x.restore(); };
  ell(R,R*(.28+.06*Math.sin(t*.3)),-.35+spin*.6,.5); ell(R*(.28+.06*Math.cos(t*.27)),R,.5-spin*.4,.3);
  const cpu=(parseFloat((document.getElementById("cpu")||{}).textContent)||0)/100, ram=(parseFloat((document.getElementById("ram")||{}).textContent)||0)/100;
  x.lineWidth=3; x.lineCap="round"; x.strokeStyle=`rgba(${col},.9)`; x.beginPath(); x.arc(cx,cy,R*1.38,-2.6,-2.6+Math.max(.02,cpu)*1.25); x.stroke();
  x.strokeStyle="rgba(255,178,62,.85)"; x.beginPath(); x.arc(cx,cy,R*1.38,.3,.3+Math.max(.02,ram)*1.25); x.stroke(); x.lineCap="butt";
  const fh=R*1.2, fw=fh*.62, ox=cx-fw/2, oy=cy-fh/2, P=s=>[ox+s[0]*fw,oy+s[1]*fh];
  x.lineWidth=1; x.strokeStyle=`rgba(${col},.42)`; x.beginPath(); LINES.forEach(([a,b])=>{ const p=P(STARS[a]),q=P(STARS[b]); x.moveTo(p[0],p[1]); x.lineTo(q[0],q[1]); }); x.stroke();
  if(think){ x.fillStyle=`rgba(${col},.95)`; LINES.forEach(([a,b],i)=>{ const p=P(STARS[a]),q=P(STARS[b]),f=(t*.9+i*.17)%1; x.fillRect(p[0]+(q[0]-p[0])*f-1.5,p[1]+(q[1]-p[1])*f-1.5,3,3); }); }
  STARS.forEach((s,i)=>{ const p=P(s), belt=s[2]===2, r=Math.round(belt?20:11); const sz=r*(1+(belt?lv*.8:0))*(.92+.08*Math.sin(t*1.3+i)); x.drawImage(sprite(col,r,!!s[3]),p[0]-sz,p[1]-sz,sz*2,sz*2); }); }
function drawHalo(t,lv){ const {cx,cy,R}=geo(); const think=state==="thinking", listen=state==="listening";
  const key="h"+W+H; if(staticKey!==key){ drawStatic("",true); staticKey=key; }
  const B=R*1.5; x.clearRect(cx-B-60,cy-B-60,(B+60)*2,(B+60)*2);
  const c1=think?"255,207,107":listen?"255,143,176":"127,255,208", ring=haloRing(c1,Math.round(R)), m=ring.width/2, sc=1+.02*Math.sin(t*1.1)+lv*.06, rot=t*(think?1.6:.22);
  x.save(); x.translate(cx,cy); x.rotate(rot); x.scale(sc,sc); x.drawImage(ring,-m,-m); x.restore();
  [["127,255,208",.4],["165,139,255",2.2],["105,215,255",4.1]].forEach(([c,a])=>{ const an=a+rot, r=R*sc; x.drawImage(sprite(c,9),cx+Math.cos(an)*r-9,cy+Math.sin(an)*r-9); }); }
function frame(now){ requestAnimationFrame(frame); if(!active()) return;
  if(document.querySelector("#liveview.show")) return;           // a window is covering the core — nothing to animate
  const busy=state!=="idle"||speaking, focus=document.hasFocus();
  let gap=busy?33:110; if(!focus) gap=200; if(EMA>12) gap*=2; if(lite) gap=busy?120:1000;     // 30 fps busy, 12 idle, 5 in the background
  if(now-last<gap) return; last=now; if(!W) size(); if(!W) return;
  const t0=performance.now(), t=now/1000, lv=Math.min(1,(speaking?audioLevel*1.6:0)+(state==="listening"?micLevel*2:0));
  if(skin()==="halo") drawHalo(t,lv); else drawCore(t,lv);
  EMA=EMA*.9+(performance.now()-t0)*.1; }
requestAnimationFrame(frame);

/* ---------------- words around the core ---------------- */
function hello(){ const h=new Date().getHours(); return h<5?"Late night":h<12?"Good morning":h<18?"Good afternoon":"Good evening"; }
function setH(el,h){ if(el&&el._h!==h){ el._h=h; el.innerHTML=h; } }
function setT(el,t){ if(el&&el.textContent!==t) el.textContent=t; }
function paintWords(){ const title=(cfg&&cfg.title)||"sir";
  setH(document.getElementById("g7h"),`${hello()}, <em>${esc(title)}</em>.`);
  setT(document.getElementById("hg7b"),`${hello().replace("Good ","").replace(/^./,c=>c.toUpperCase())}, ${title}.`);
  const st={idle:"STANDING BY",thinking:"THINKING",listening:"LISTENING"}[state]||"ONLINE";
  setT(document.getElementById("g7s"),`${(cfg&&cfg.name)||"ORION"} CORE · ${speaking?"SPEAKING":st}`);
  const det=(document.getElementById("statusdetail")||{}).textContent||"";
  const nx=GL.find(g=>g.k==="next"), wx=GL.find(g=>g.k==="weather");
  setT(document.getElementById("g7p"),state!=="idle"&&det?det:[nx&&nx.title!=="Nothing booked"?`${nx.title}, ${nx.sub.toLowerCase()}.`:"",wx?`${wx.title}.`:""].join(" ").trim()||"All systems nominal.");
  GL.slice(0,4).forEach((g,i)=>{ const el=document.getElementById("co"+i); const cn="co7"+(i>=2?" r":"")+(g.warn?" warn":""); if(el.className!==cn) el.className=cn; setH(el,`<small>${esc(g.label)}</small><b>${esc(g.title)}</b><span>${esc(g.sub)}</span>`); });
  setH(document.getElementById("gl7"),GL.slice(0,3).map(g=>`<div class="${g.warn?"warn":""}"><small>${esc(g.label.charAt(0)+g.label.slice(1).toLowerCase())}</small><b>${esc(g.title)} · ${esc(g.sub)}</b></div>`).join(""));
  orbit.querySelectorAll("button").forEach(b=>{ const on=document.querySelector(`.nav.on[data-page="${b.dataset.o}"]`)!=null; if(b.classList.contains("on")!==on) b.classList.toggle("on",on); });
  const sig=GL.map(g=>g.title).join("|"); if(sig!==paintWords.sig){ paintWords.sig=sig; requestAnimationFrame(lead); } }
async function loadGlance(){ try{ GL=await api.look_data()||[]; }catch(e){ GL=[]; } paintWords(); }
setInterval(()=>{ if(active()) paintWords(); },2000);
setInterval(()=>{ if(api&&active()) loadGlance(); },10*60*1000);
const wait=setInterval(()=>{ if(api&&api.look_data){ clearInterval(wait); loadGlance(); } },500);

/* ---------------- applying the look ---------------- */
const _apply=applyUi;
applyUi=function(u){ _apply(u); const s=UIP.skin, b=document.body; b.classList.toggle("skin-core",s==="core"); b.classList.toggle("skin-halo",s==="halo"); b.classList.toggle("look7",s==="core"||s==="halo");
  const no=document.getElementById("cNo"), yes=document.getElementById("cYes"), on=s==="core"||s==="halo";
  if(no&&yes){ no.textContent=on?"Not now":"DENY"; yes.textContent=on?"Go ahead":"AUTHORISE"; }
  if(on){ setTimeout(()=>{ size(); paintWords(); },60); } };
// the header style button cycles all four looks
const sb=document.getElementById("skinBtn");
if(sb){ sb.title="Switch look: Orion Core / Halo / HUD / Aurora"; sb.onclick=()=>{ const order=["core","halo","hud","aurora"]; const n=order[(order.indexOf(UIP.skin)+1)%order.length];
  saveUi({skin:n}); toast({core:"Orion Core",halo:"Halo",hud:"Jarvis HUD",aurora:"Aurora"}[n]+" look"); try{ sfx("card"); }catch(e){} }; }
const sel=document.getElementById("sSkin");
if(sel) sel.innerHTML='<option value="core">Orion Core</option><option value="halo">Halo</option><option value="hud">Jarvis HUD (classic)</option><option value="aurora">Aurora</option>';
if(UIP&&UIP.skin) applyUi({});

/* ---------------- ghost: nothing animates while you're gaming ---------------- */
window.ghost=function(on){ GHOST=!!on; document.body.classList.toggle("ghost",GHOST); if(GHOST){ x.clearRect(0,0,W,H); sx.clearRect(0,0,W,H); staticKey=""; for(const k in SPR) delete SPR[k]; } };
})();
