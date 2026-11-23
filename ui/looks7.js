/* ORION 7.0 — the Orion Core and Halo looks: the living core, callouts, the orbiting places, ghost mode.
   Shares globals with index.html (api, cfg, state, speaking, audioLevel, micLevel, lite, go, globeOpen, UIP, applyUi). */
(function(){
const core=document.querySelector(".stage .core");
if(!core) return;
core.insertAdjacentHTML("afterbegin",`<canvas id="look"></canvas>`);
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
let W=0,H=0,DPR=1,GL=[],last=0,raf=0,GHOST=false, stars=[];
const STARS=[[.32,.04,1],[.12,.2,0,1],[.74,.24,0],[.36,.52,2],[.5,.48,2],[.63,.44,2],[.18,.94,0],[.82,.86,1]];
const LINES=[[0,1],[0,2],[1,3],[2,5],[3,4],[4,5],[3,6],[5,7]];
function skin(){ return UIP&&UIP.skin; }
function active(){ const s=skin(); return (s==="core"||s==="halo")&&!GHOST&&!document.hidden&&!document.querySelector(".stage.wide"); }
function size(){ const r=core.getBoundingClientRect(); DPR=Math.min(1.5,devicePixelRatio||1); W=r.width; H=r.height; cv.width=W*DPR; cv.height=H*DPR;
  stars=[]; for(let i=0;i<Math.round(W*H/5200);i++) stars.push([Math.random()*W,Math.random()*H,Math.random()*1.1+.2,Math.random()*6]); place(); }
function geo(){ const halo=skin()==="halo"; const cx=W*(halo&&W>900?.6:.5), cy=H*(halo?.42:.43), R=Math.min(W*.24,H*(halo?.25:.27)); return {cx,cy,R}; }
function acc(){ const cs=getComputedStyle(document.body); return {a:cs.getPropertyValue("--ar").trim()||"139,233,255", think:cs.getPropertyValue("--thinkr").trim()||"255,179,71", listen:cs.getPropertyValue("--listenr").trim()||"255,79,123"}; }
function place(){ const {cx,cy,R}=geo(); const narrow=W<760;
  // callouts (Orion Core)
  const spots=[[cx-R*1.42-230,cy-R*.95],[cx-R*1.48-230,cy+R*.55],[cx+R*1.42,cy-R*.95],[cx+R*1.48,cy+R*.55]];
  spots.forEach(([l,t],i)=>{ const el=document.getElementById("co"+i); el.style.left=Math.max(4,Math.min(W-234,l))+"px"; el.style.top=t+"px"; el.style.display=narrow?"none":""; });
  // halo places
  const n=ORB.length, rr=R*1.45; orbit.querySelectorAll("button").forEach((b,i)=>{ const a=-Math.PI/2+i*2*Math.PI/n; b.style.left=(cx+Math.cos(a)*rr*(W>900?1.18:1))+"px"; b.style.top=(cy+Math.sin(a)*rr)+"px"; });
  const hg=document.getElementById("hg7"); hg.style.left=cx+"px"; hg.style.top=cy+"px"; }
addEventListener("resize",()=>{ size(); });
new ResizeObserver(()=>size()).observe(core);

/* ---------------- drawing ---------------- */
function bg(t){ x.clearRect(0,0,W,H); const halo=skin()==="halo";
  for(const s of stars){ x.globalAlpha=(.25+.25*Math.sin(t*.7+s[3]))*(halo?.8:1); x.fillStyle=halo?"#e8e6ff":"#d6ecff"; x.fillRect(s[0],s[1],s[2],s[2]); } x.globalAlpha=1; }
function drawCore(t){ const {cx,cy,R}=geo(), C=acc(); const think=state==="thinking", listen=state==="listening";
  const col=think?C.think:listen?C.listen:C.a; const lv=Math.min(1,(speaking?audioLevel*1.6:0)+(listen?micLevel*2:0));
  bg(t);
  let g=x.createRadialGradient(cx,cy,0,cx,cy,R*1.6); g.addColorStop(0,`rgba(${col},${.13+lv*.12})`); g.addColorStop(1,`rgba(${col},0)`); x.fillStyle=g; x.fillRect(cx-R*1.6,cy-R*1.6,R*3.2,R*3.2);
  const spin=t*(think?.9:.18);
  const ring=(rx,ry,rot,a,w,dots)=>{ x.save(); x.translate(cx,cy); x.rotate(rot); x.strokeStyle=`rgba(${col},${a})`; x.lineWidth=w; x.beginPath(); x.ellipse(0,0,rx,ry,0,0,7); x.stroke();
    if(dots){ for(let k=0;k<60;k++){ const an=k/60*Math.PI*2; x.fillStyle=`rgba(${col},${k%5?a*.45:a*1.3})`; const s=k%5?1.3:2.4; x.fillRect(Math.cos(an)*rx-s/2,Math.sin(an)*ry-s/2,s,s); } } x.restore(); };
  ring(R,R,0,.32,1.1,true);
  ring(R,R*(.28+.06*Math.sin(t*.3)),-.35+spin*.6,.5,1.3,true);
  ring(R*(.28+.06*Math.cos(t*.27)),R,.5-spin*.4,.3,1,false);
  ring(R*.78,R*.78,0,.16,1,false); ring(R*1.18,R*1.18,0,.09,1,false);
  // tick ring + gauges (CPU / RAM from the header numbers)
  x.save(); x.translate(cx,cy); x.rotate(t*.02);
  for(let k=0;k<180;k++){ const an=k/180*Math.PI*2, l=k%15?5:11; x.strokeStyle=`rgba(${col},${k%15?.22:.55})`; x.beginPath(); x.moveTo(Math.cos(an)*R*1.26,Math.sin(an)*R*1.26); x.lineTo(Math.cos(an)*(R*1.26+l),Math.sin(an)*(R*1.26+l)); x.stroke(); }
  x.restore();
  const cpu=(parseFloat((document.getElementById("cpu")||{}).textContent)||0)/100, ram=(parseFloat((document.getElementById("ram")||{}).textContent)||0)/100;
  x.lineWidth=3; x.lineCap="round"; x.strokeStyle=`rgba(${col},.9)`; x.beginPath(); x.arc(cx,cy,R*1.38,-2.6,-2.6+Math.max(.02,cpu)*1.25); x.stroke();
  x.strokeStyle="rgba(255,178,62,.85)"; x.beginPath(); x.arc(cx,cy,R*1.38,.3,.3+Math.max(.02,ram)*1.25); x.stroke(); x.lineCap="butt";
  // Orion inside
  const fh=R*1.2, fw=fh*.62, ox=cx-fw/2, oy=cy-fh/2, P=s=>[ox+s[0]*fw,oy+s[1]*fh];
  x.lineWidth=1; LINES.forEach(([a,b],i)=>{ const p=P(STARS[a]),q=P(STARS[b]); x.strokeStyle=`rgba(${col},.42)`; x.beginPath(); x.moveTo(p[0],p[1]); x.lineTo(q[0],q[1]); x.stroke();
    if(think){ const f=(t*.9+i*.17)%1; x.fillStyle=`rgba(${col},.95)`; x.beginPath(); x.arc(p[0]+(q[0]-p[0])*f,p[1]+(q[1]-p[1])*f,1.8,0,7); x.fill(); } });
  STARS.forEach((s,i)=>{ const p=P(s), belt=s[2]===2, sz=(belt?20:11)*(1+(belt?lv*.8:0))*(.9+.1*Math.sin(t*1.3+i));
    const gg=x.createRadialGradient(p[0],p[1],0,p[0],p[1],sz); gg.addColorStop(0,s[3]?"rgba(255,190,140,.9)":"rgba(225,245,255,.95)"); gg.addColorStop(1,`rgba(${col},0)`); x.fillStyle=gg; x.beginPath(); x.arc(p[0],p[1],sz,0,7); x.fill();
    x.fillStyle="#fff"; x.beginPath(); x.arc(p[0],p[1],belt?2.4:1.6,0,7); x.fill(); });
  // leader lines to the callouts
  if(W>=760){ x.strokeStyle=`rgba(${col},.3)`; x.fillStyle=`rgba(${col},.9)`;
    [[-.86,-.62,0],[-.9,.5,1],[.86,-.66,2],[.9,.6,3]].forEach(([dx,dy,i])=>{ const el=document.getElementById("co"+i); if(!el.textContent) return;
      const ax=cx+R*dx, ay=cy+R*dy, r=el.getBoundingClientRect(), cr=core.getBoundingClientRect(); const ex=i<2?r.right-cr.left+6:r.left-cr.left-6, ey=r.top-cr.top+26;
      x.beginPath(); x.moveTo(ax,ay); x.lineTo(ex,ey); x.stroke(); x.beginPath(); x.arc(ax,ay,2.4,0,7); x.fill(); }); } }
function drawHalo(t){ const {cx,cy,R}=geo(), C=acc(); const think=state==="thinking", listen=state==="listening";
  const lv=Math.min(1,(speaking?audioLevel*1.6:0)+(listen?micLevel*2:0)); bg(t);
  const breathe=1+.02*Math.sin(t*1.1)+lv*.06, r=R*breathe;
  for(let k=0;k<3;k++){ const rr=r+k*10; const g=x.createRadialGradient(cx,cy,rr-30,cx,cy,rr+46); g.addColorStop(0,"rgba(127,255,208,0)"); g.addColorStop(.45,`rgba(127,255,208,${.11-k*.03+lv*.08})`); g.addColorStop(.55,`rgba(165,139,255,${.15-k*.04})`); g.addColorStop(1,"rgba(165,139,255,0)"); x.fillStyle=g; x.beginPath(); x.arc(cx,cy,rr+46,0,7); x.fill(); }
  const rot=t*(think?1.6:.22);
  const cg=x.createConicGradient?x.createConicGradient(rot,cx,cy):null;
  if(cg){ const c1=think?"#ffcf6b":listen?"#ff8fb0":"#7fffd0"; cg.addColorStop(0,c1); cg.addColorStop(.33,"#69d7ff"); cg.addColorStop(.66,"#a58bff"); cg.addColorStop(1,c1); x.strokeStyle=cg; } else x.strokeStyle="#7fffd0";
  x.lineWidth=3; x.beginPath(); x.arc(cx,cy,r,0,7); x.stroke();
  x.lineWidth=1; x.strokeStyle="rgba(255,255,255,.1)"; x.beginPath(); x.arc(cx,cy,R*1.45,0,7); x.stroke();
  x.setLineDash([2,8]); x.strokeStyle="rgba(255,255,255,.16)"; x.beginPath(); x.arc(cx,cy,R*1.17,rot*.3,rot*.3+7); x.stroke(); x.setLineDash([]);
  [["#7fffd0",.4],["#a58bff",2.2],["#69d7ff",4.1]].forEach(([c,a])=>{ const an=a+rot; x.fillStyle=c; x.shadowColor=c; x.shadowBlur=14; x.beginPath(); x.arc(cx+Math.cos(an)*r,cy+Math.sin(an)*r,3.6,0,7); x.fill(); }); x.shadowBlur=0; }
function frame(now){ raf=requestAnimationFrame(frame); if(!active()) return; const minGap=lite?900:33; if(now-last<minGap) return; last=now;
  if(!W) size(); const t=now/1000; if(skin()==="halo") drawHalo(t); else drawCore(t); }
raf=requestAnimationFrame(frame);

/* ---------------- words around the core ---------------- */
function hello(){ const h=new Date().getHours(); return h<5?"Late night":h<12?"Good morning":h<18?"Good afternoon":"Good evening"; }
function paintWords(){ const title=(cfg&&cfg.title)||"sir";
  document.getElementById("g7h").innerHTML=`${hello()}, <em>${esc(title)}</em>.`;
  document.getElementById("hg7b").textContent=`${hello().replace("Good ","").replace(/^./,c=>c.toUpperCase())}, ${title}.`;
  const st={idle:"STANDING BY",thinking:"THINKING",listening:"LISTENING"}[state]||"ONLINE";
  document.getElementById("g7s").textContent=`${(cfg&&cfg.name)||"ORION"} CORE · ${speaking?"SPEAKING":st}`;
  const det=(document.getElementById("statusdetail")||{}).textContent||"";
  const nx=GL.find(g=>g.k==="next"), wx=GL.find(g=>g.k==="weather");
  document.getElementById("g7p").textContent=state!=="idle"&&det?det:[nx&&nx.title!=="Nothing booked"?`${nx.title}, ${nx.sub.toLowerCase()}.`:"",wx?`${wx.title}.`:""].join(" ").trim()||"All systems nominal.";
  GL.slice(0,4).forEach((g,i)=>{ const el=document.getElementById("co"+i); el.className="co7"+(i>=2?" r":"")+(g.warn?" warn":""); el.innerHTML=`<small>${esc(g.label)}</small><b>${esc(g.title)}</b><span>${esc(g.sub)}</span>`; });
  document.getElementById("gl7").innerHTML=GL.slice(0,3).map(g=>`<div class="${g.warn?"warn":""}"><small>${esc(g.label.charAt(0)+g.label.slice(1).toLowerCase())}</small><b>${esc(g.title)} · ${esc(g.sub)}</b></div>`).join("");
  orbit.querySelectorAll("button").forEach(b=>b.classList.toggle("on",document.querySelector(`.nav.on[data-page="${b.dataset.o}"]`)!=null)); }
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
window.ghost=function(on){ GHOST=!!on; document.body.classList.toggle("ghost",GHOST); if(GHOST) x.clearRect(0,0,W,H); };
})();
