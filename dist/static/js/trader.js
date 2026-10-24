/* CryptoAI — trader page: scanner, setup sheet, Monte Carlo, Telegram draft.
   Data: /api/trader/candles (server, live Binance) → CSV upload → seeded sample fallback. */

(() => {
"use strict";
/* ---------- utils ---------- */
const $ = id => document.getElementById(id);
const css = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const faNum = s => String(s).replace(/\d/g, d => "۰۱۲۳۴۵۶۷۸۹"[d]);
function mulberry32(a){return function(){a|=0;a=a+0x6D2B79F5|0;let t=Math.imul(a^a>>>15,1|a);t=t+Math.imul(t^t>>>7,61|t)^t;return((t^t>>>14)>>>0)/4294967296}}
function gauss(r){let u=0,v=0;while(!u)u=r();while(!v)v=r();return Math.sqrt(-2*Math.log(u))*Math.cos(2*Math.PI*v)}
function fmt(p){
  if(!isFinite(p))return "–";
  const a=Math.abs(p);
  if(a>=1000)return p.toLocaleString("en-US",{maximumFractionDigits:0});
  if(a>=10)return p.toFixed(2);
  if(a>=1)return p.toFixed(3);
  if(a>=0.01)return p.toFixed(4);
  return p.toPrecision(3);
}
const fmtX = p => p>=1 ? p.toLocaleString("en-US",{minimumFractionDigits:2,maximumFractionDigits:p>=10?2:4}) : p.toPrecision(4);
const pct = x => (x>=0?"+":"")+(x*100).toFixed(2)+"%";
const L = x => "\u2066"+x+"\u2069";

/* ---------- sample market (seeded, clearly labelled) ---------- */
const COINS=[
 ["BTC",67000,.006,"breakoutUp"],["ETH",2600,.008,"doubleBottom"],["SOL",150,.011,"squeeze"],["BNB",590,.006,"random"],
 ["XRP",.55,.009,"breakoutDown"],["DOGE",.12,.012,"trendUp"],["TON",5.2,.010,"random"],["ADA",.36,.010,"trendDown"],
 ["AVAX",26,.012,"squeeze"],["LINK",11.5,.011,"breakoutUp"],["DOT",4.3,.010,"random"],["TRX",.16,.005,"trendUp"],
 ["POL",.40,.012,"doubleTop"],["LTC",68,.009,"random"],["NEAR",4.8,.013,"breakoutUp"],["APT",8.5,.013,"trendDown"],
 ["ARB",.55,.013,"squeeze"],["OP",1.6,.013,"random"],["SUI",1.9,.015,"breakoutUp"],["PEPE",.0000095,.017,"random"],
 ["SHIB",.000017,.012,"doubleBottom"],["ATOM",4.5,.010,"random"],["INJ",20,.014,"breakoutDown"],["FET",1.3,.015,"trendUp"]
];
function genCandles(seed,start,vol,scn){
  const r=mulberry32(seed), N=240, out=[]; let c=start*Math.exp(gauss(r)*vol*4);
  const t0=Date.UTC(2026,9,14,0)/1000;
  const targets=new Array(N).fill(null);
  // scenario shaping over the last 60 candles
  const S=N-60;
  if(scn==="doubleBottom"||scn==="doubleTop"){
    const s=scn==="doubleBottom"?1:-1, k=[0,14,26,40,57,60], f=[1,1-.06*s,1-.025*s,1-.058*s,1-.012*s,1-.004*s];
    for(let i=0;i<k.length-1;i++)for(let j=k[i];j<k[i+1];j++){const w=(j-k[i])/(k[i+1]-k[i]);targets[S+j]=f[i]+(f[i+1]-f[i])*w}
  }
  let anchor=null;
  for(let i=0;i<N;i++){
    let v=vol, mu=0, volMul=1;
    if(scn==="trendUp"&&i>=N-90)mu=.32*vol;
    if(scn==="trendDown"&&i>=N-90)mu=-.32*vol;
    const sq=(scn==="squeeze"||scn==="breakoutUp"||scn==="breakoutDown");
    if(sq&&i>=N-34&&i<N-3){v=vol*.33; if(anchor===null)anchor=c; mu=Math.log(anchor/c)*.25}
    if(scn==="squeeze"&&i>=N-3){v=vol*.33;mu=Math.log(anchor/c)*.25}
    if(scn==="breakoutUp"&&i>=N-3){mu=vol*1.5;v=vol*.6;volMul=3.2}
    if(scn==="breakoutDown"&&i>=N-3){mu=-vol*1.5;v=vol*.6;volMul=3.2}
    let ret;
    if(targets[i]!==null){ if(anchor===null)anchor=c; ret=Math.log(anchor*targets[i]/c)*.55+gauss(r)*vol*.35 }
    else ret=mu+gauss(r)*v;
    const o=c; c=o*Math.exp(ret);
    const h=Math.max(o,c)*(1+Math.abs(gauss(r))*v*.55), l=Math.min(o,c)*(1-Math.abs(gauss(r))*v*.55);
    const vbase=1e6/start*1000;
    const vv=vbase*(.6+Math.abs(ret)/vol*.5)*Math.exp(gauss(r)*.3)*volMul;
    out.push({t:t0+i*3600,o,h,l,c,v:vv});
  }
  return out;
}

/* ---------- indicators ---------- */
function ema(a,n){const k=2/(n+1),o=[];let e=a[0];for(const x of a){e=x*k+e*(1-k);o.push(e)}return o}
function rsi(c,n=14){let g=0,l=0;for(let i=1;i<=n;i++){const d=c[i]-c[i-1];d>0?g+=d:l-=d}g/=n;l/=n;const o=new Array(n).fill(50);o.push(100-100/(1+g/(l||1e-12)));
  for(let i=n+1;i<c.length;i++){const d=c[i]-c[i-1];g=(g*(n-1)+Math.max(d,0))/n;l=(l*(n-1)+Math.max(-d,0))/n;o.push(100-100/(1+g/(l||1e-12)))}return o}

/* ---------- pattern detectors ---------- */
function analyze(sym,cs){
  const C=cs.map(x=>x.c),H=cs.map(x=>x.h),L=cs.map(x=>x.l),V=cs.map(x=>x.v),n=cs.length,last=C[n-1];
  const e20=ema(C,20),e50=ema(C,50),R=rsi(C);
  const win=cs.slice(n-27,n-3);
  const rh=Math.max(...win.map(x=>x.h)), rl=Math.min(...win.map(x=>x.l));
  const width=(rh-rl)/((rh+rl)/2);
  const widths=[];for(let i=24;i<n-27;i+=6){const w=cs.slice(i-24,i);const a=Math.max(...w.map(x=>x.h)),b=Math.min(...w.map(x=>x.l));widths.push((a-b)/((a+b)/2))}
  widths.sort((a,b)=>a-b);const medW=widths[Math.floor(widths.length/2)]||width;
  const wk=cs.slice(n-168), wh=Math.max(...wk.map(x=>x.h)), wl=Math.min(...wk.map(x=>x.l));
  const tags=[];
  const add=(id,label,dir,detail)=>tags.push({id,label,dir,detail});
  const tight=width<medW*.85;
  if(tight&&last>rh) add("bo_up","شکست سقف رنج",1,`بستهٔ آخر بالای سقف رنج ۲۴ ساعته (${fmt(rh)}) است؛ رنج ${(width*100).toFixed(1)}٪ عرض داشت، کمتر از معمول این کوین (${(medW*100).toFixed(1)}٪).`);
  else if(tight&&last<rl) add("bo_dn","شکست کف رنج",-1,`بستهٔ آخر زیر کف رنج ۲۴ ساعته (${fmt(rl)}) است؛ رنج قبلی فشرده بود (${(width*100).toFixed(1)}٪).`);
  else if(width<medW*.6) add("sqz","فشردگی",0,`رنج ۲۴ ساعته فقط ${(width*100).toFixed(1)}٪ است؛ حدود ${Math.round(width/medW*100)}٪ رنج معمول. فشردگی معمولاً قبل از حرکت بزرگ دیده می‌شود، جهتش معلوم نیست.`);
  // double bottom / top on last 60
  const seg=60, base=n-seg, sw=[],sh=[];
  for(let i=base+3;i<n-3;i++){
    if(L[i]<=Math.min(...L.slice(i-3,i))&&L[i]<=Math.min(...L.slice(i+1,i+4)))sw.push(i);
    if(H[i]>=Math.max(...H.slice(i-3,i))&&H[i]>=Math.max(...H.slice(i+1,i+4)))sh.push(i);
  }
  const pair=(idx,arr,cmp)=>{let best=null;for(let a=0;a<idx.length;a++)for(let b=a+1;b<idx.length;b++){const i=idx[a],j=idx[b];if(j-i<8)continue;const d=Math.abs(arr[i]-arr[j])/arr[i];if(d<.012&&(!best||cmp(arr[i]+arr[j],best.s)))best={i,j,s:arr[i]+arr[j]}}return best};
  const db=pair(sw,L,(x,y)=>x<y);
  const dbNeck=db?Math.max(...H.slice(db.i,db.j+1)):0;
  if(db&&Math.min(L[db.i],L[db.j])<=Math.min(...L.slice(base))*1.004&&dbNeck/L[db.i]-1>.025&&(last>dbNeck||db.j>=n-20)){
    const neck=dbNeck;
    if(last>neck)add("dbl_b","کف دوقلو (تأیید)",1,`دو کف نزدیک در ${fmt(L[db.i])} و ${fmt(L[db.j])}؛ قیمت از خط گردن ${fmt(neck)} عبور کرده.`);
    else if(last>L[db.j])add("dbl_b2","کف دوقلو (در حال شکل‌گیری)",0,`دو کف نزدیک در ${fmt(L[db.i])} و ${fmt(L[db.j])}؛ خط گردن ${fmt(neck)} هنوز شکسته نشده.`);
  }
  const dt=pair(sh,H,(x,y)=>x>y);
  const dtNeck=dt?Math.min(...L.slice(dt.i,dt.j+1)):0;
  if(dt&&Math.max(H[dt.i],H[dt.j])>=Math.max(...H.slice(base))*.996&&1-dtNeck/H[dt.i]>.025&&(last<dtNeck||dt.j>=n-20)){
    const neck=dtNeck;
    if(last<neck)add("dbl_t","سقف دوقلو (تأیید)",-1,`دو سقف نزدیک در ${fmt(H[dt.i])} و ${fmt(H[dt.j])}؛ قیمت زیر خط گردن ${fmt(neck)} بسته شده.`);
    else if(last<H[dt.j])add("dbl_t2","سقف دوقلو (در حال شکل‌گیری)",0,`دو سقف نزدیک در ${fmt(H[dt.i])} و ${fmt(H[dt.j])}؛ خط گردن ${fmt(neck)} هنوز شکسته نشده.`);
  }
  // EMA cross in last 6
  for(let i=n-6;i<n;i++){
    if(e20[i-1]<=e50[i-1]&&e20[i]>e50[i]){add("x_up","کراس طلایی EMA",1,"EMA 20 در ۶ کندل اخیر از بالای EMA 50 عبور کرده.");break}
    if(e20[i-1]>=e50[i-1]&&e20[i]<e50[i]){add("x_dn","کراس مرگ EMA",-1,"EMA 20 در ۶ کندل اخیر به زیر EMA 50 رفته.");break}
  }
  const r=R[n-1];
  if(r>70)add("ob","اشباع خرید",0,`RSI 14 برابر ${r.toFixed(0)} است؛ حرکت کشیده شده و احتمال استراحت بیشتر است.`);
  if(r<30)add("os","اشباع فروش",0,`RSI 14 برابر ${r.toFixed(0)} است؛ فروش شدید بوده.`);
  const avgV=V.slice(n-53,n-3).reduce((a,b)=>a+b,0)/50, mv=Math.max(...V.slice(n-3));
  if(mv>avgV*2.3)add("vol","حجم غیرعادی",0,`حجم یکی از ۳ کندل اخیر ${(mv/avgV).toFixed(1)} برابر میانگین ۵۰ کندل است.`);
  // bias
  let score=tags.reduce((s,t)=>s+t.dir,0);
  const trend=(last>e50[n-1]&&e20[n-1]>e50[n-1]&&e50[n-1]>e50[n-12])?1:(last<e50[n-1]&&e20[n-1]<e50[n-1]&&e50[n-1]<e50[n-12])?-1:0;
  score+=trend;
  const bias=score>=1?1:score<=-1?-1:0;
  const chg=last/C[n-25]-1;
  return {sym,cs,C,e50,last,chg,rh,rl,wh,wl,width,medW,rsi:r,tags,trend,bias};
}

/* ---------- monte carlo ---------- */
function simulate(a,horizon,paths,seed){
  const C=a.C,n=C.length,rets=[];
  for(let i=n-168;i<n;i++)rets.push(Math.log(C[i]/C[i-1]));
  const m=rets.reduce((x,y)=>x+y,0)/rets.length; for(let i=0;i<rets.length;i++)rets[i]-=m;
  const r=mulberry32(seed), B=4, P0=a.last;
  const fin=new Float64Array(paths),mx=new Float64Array(paths),mn=new Float64Array(paths),grid=new Float32Array(paths*horizon);
  let done=0;
  function step(count){
    const end=Math.min(paths,done+count);
    for(let p=done;p<end;p++){
      let lp=0,hi=P0,lo=P0,t=0;
      while(t<horizon){const s=Math.floor(r()*(rets.length-B));for(let b=0;b<B&&t<horizon;b++,t++){lp+=rets[s+b];const px=P0*Math.exp(lp);grid[p*horizon+t]=px;if(px>hi)hi=px;if(px<lo)lo=px}}
      fin[p]=P0*Math.exp(lp);mx[p]=hi;mn[p]=lo;
    }
    done=end;return done;
  }
  return {step,get done(){return done},fin,mx,mn,grid,horizon,paths,P0};
}
function quant(sorted,q){const i=(sorted.length-1)*q,a=Math.floor(i),b=Math.ceil(i);return sorted[a]+(sorted[b]-sorted[a])*(i-a)}
function fanFromGrid(sim){
  const {grid,horizon,paths}=sim,out=[],col=new Float32Array(paths);
  for(let t=0;t<horizon;t++){for(let p=0;p<paths;p++)col[p]=grid[p*horizon+t];col.sort();out.push([.05,.25,.5,.75,.95].map(q=>quant(col,q)))}
  return out;
}

/* ---------- state ---------- */
const state={list:[],sel:0,filter:"all",horizon:24,sim:null,fan:null,simDone:false,source:"sample",csv:false};
function buildSample(){
  state.list=COINS.map(([s,p,v,scn],i)=>analyze(s,genCandles(1000+i*7919,p,v,scn)));
  state.source="sample";
}
async function loadLive(){
  if(window.SITE_MODE!=="server")return false;
  try{
    const syms=COINS.map(c=>c[0]).join(",");
    const ac=new AbortController(),to=setTimeout(()=>ac.abort(),25000);
    const r=await fetch(window.API_BASE+"/api/trader/candles?interval=1h&limit=240&symbols="+syms,{signal:ac.signal});clearTimeout(to);
    const j=await r.json();
    if(!j.ok)return false;
    const list=[];
    for(const [sym] of COINS){const rows=j.data[sym];if(!rows||rows.length<200)continue;
      list.push(analyze(sym,rows.map(x=>({t:x[0],o:x[1],h:x[2],l:x[3],c:x[4],v:x[5]}))))}
    if(list.length<5)return await loadFromBrowser();
    state.list=list;state.source="live";state.fetched=j.fetched_at;state.liveSource=j.source||"";return true;
  }catch(e){return await loadFromBrowser()}
}
/* fallback: the visitor's browser asks Binance directly (works even if the server's network is blocked) */
async function loadFromBrowser(){
  try{
    const one=async sym=>{
      const r=await fetch(`https://data-api.binance.vision/api/v3/klines?symbol=${sym}USDT&interval=1h&limit=240`);
      if(!r.ok)return null;const k=await r.json();
      return k.length>=200?analyze(sym,k.map(x=>({t:x[0]/1000,o:+x[1],h:+x[2],l:+x[3],c:+x[4],v:+x[5]}))):null;
    };
    const res=await Promise.all(COINS.map(c=>one(c[0]).catch(()=>null)));
    const list=res.filter(Boolean);
    if(list.length<5)return false;
    state.list=list;state.source="live";state.fetched=new Date().toISOString();state.liveSource="Binance";return true;
  }catch(e){return false}
}
function setDataPill(){
  const p=$("data-pill");
  if(state.source==="live"){p.className="pill live";p.textContent="● زنده"}
  else{p.className="pill warn";p.textContent="اتصال به بازار برقرار نشد؛ نمایش نمونه"}
}

/* ---------- canvas helpers ---------- */
function prep(cv){const dpr=window.devicePixelRatio||1,w=cv.clientWidth,h=cv.clientHeight;if(cv.width!==Math.round(w*dpr)||cv.height!==Math.round(h*dpr)){cv.width=Math.round(w*dpr);cv.height=Math.round(h*dpr)}const g=cv.getContext("2d");g.setTransform(dpr,0,0,dpr,0,0);g.clearRect(0,0,w,h);return {g,w,h}}
function spark(cv,a){
  const {g,w,h}=prep(cv),c=a.C.slice(-72),mn=Math.min(...c),mx=Math.max(...c);
  const col=a.chg>=0?css("--up"):css("--down");
  g.beginPath();c.forEach((v,i)=>{const x=i/(c.length-1)*w,y=h-2-(v-mn)/(mx-mn||1)*(h-4);i?g.lineTo(x,y):g.moveTo(x,y)});
  g.strokeStyle=col;g.lineWidth=1.4;g.stroke();
  g.lineTo(w,h);g.lineTo(0,h);g.closePath();g.globalAlpha=.12;g.fillStyle=col;g.fill();g.globalAlpha=1;
}

/* ---------- scanner ---------- */
function renderGrid(){
  const grid=$("grid");grid.textContent="";
  let hits=0;
  state.list.forEach((a,i)=>{
    const has=a.tags.length>0; if(has)hits++;
    const show=state.filter==="all"||(state.filter==="hit"&&has)||(state.filter==="up"&&a.bias===1)||(state.filter==="down"&&a.bias===-1);
    const b=document.createElement("button");b.className="tile"+(show?"":" dim");b.type="button";
    b.setAttribute("aria-current",i===state.sel?"true":"false");
    b.dataset.sym=a.sym;b.innerHTML=`<div class="r1"><span class="sym">${a.sym}</span><span class="chg num ${a.chg>=0?"up":"down"}">${pct(a.chg)}</span></div><canvas></canvas><div class="tags"></div>`;
    const tg=b.querySelector(".tags");
    a.tags.slice(0,2).forEach(t=>{const s=document.createElement("span");s.className="chip "+(t.dir>0?"up":t.dir<0?"down":"flat");s.textContent=t.label;tg.append(s)});
    b.onclick=()=>select(i);
    grid.append(b);
    requestAnimationFrame(()=>spark(b.querySelector("canvas"),a));
  });
  $("hits").textContent=faNum(hits);
  $("hits-of").textContent=`الگو در ${faNum(state.list.length)} کوین اسکن‌شده`;
}

/* ---------- setup sheet ---------- */
const biasTxt=b=>b>0?["صعودی","up"]:b<0?["نزولی","down"]:["خنثی","flat"];
function renderSheet(){
  const a=state.list[state.sel];
  $("s-name").innerHTML=`${a.sym} <small>/ ${a.csv?"CSV":"USDT"}</small>`;
  const [bt,bc]=biasTxt(a.bias);const bb=$("s-bias");bb.className="bias "+bc;bb.textContent="جهت ساختار: "+bt;
  const lp=a.livePrice||a.last,lc=a.liveChg!==undefined?a.liveChg:a.chg;
  $("c-price").textContent=fmtX(lp);
  const ce=$("c-chg");ce.className="s num "+(lc>=0?"up":"down");ce.textContent=pct(lc)+" (24h)"+(a.livePrice?" · لحظه‌ای":"");
  $("c-res").textContent=fmt(a.rh);$("c-res-d").textContent=pct(a.rh/a.last-1)+" تا قیمت فعلی";
  $("c-sup").textContent=fmt(a.rl);$("c-sup-d").textContent=pct(a.rl/a.last-1)+" تا قیمت فعلی";
  const f=$("findings");f.textContent="";
  const items=a.tags.length?a.tags:[{label:"الگوی مشخصی دیده نشد",dir:0,detail:"قیمت داخل رنج عادی خودش حرکت می‌کند. سطوح رنج و نتیجهٔ شبیه‌سازی همچنان معتبرند."}];
  const tr={label:"روند (EMA 20/50)",dir:a.trend,detail:a.trend>0?"قیمت بالای EMA 50 و EMA 20 بالای EMA 50، با شیب مثبت.":a.trend<0?"قیمت زیر EMA 50 و EMA 20 زیر EMA 50، با شیب منفی.":"میانگین‌ها هم‌جهت نیستند؛ روند مشخصی نیست."};
  [...items,tr].forEach(t=>{const d=document.createElement("div");d.className="finding";
    d.innerHTML=`<span class="dot ${t.dir>0?"up":t.dir<0?"down":"flat"}"></span><div><b></b><p></p></div>`;
    d.querySelector("b").textContent=t.label;d.querySelector("p").textContent=t.detail;f.append(d)});
  drawMain();
}
function drawMain(){
  const a=state.list[state.sel],cv=$("cv-main"),{g,w,h}=prep(cv);
  const K=96,cs=a.cs.slice(-K),e=a.e50.slice(-K),H=state.horizon,fan=state.fan;
  const padR=58,padT=10,padB=22,total=K+(fan?H:0),cw=(w-padR-6)/total;
  let hi=Math.max(...cs.map(x=>x.h),a.rh),lo=Math.min(...cs.map(x=>x.l),a.rl);
  if(fan){for(const q of fan){hi=Math.max(hi,q[4]);lo=Math.min(lo,q[0])}}
  const pad=(hi-lo)*.06;hi+=pad;lo-=pad;
  const Y=v=>padT+(hi-v)/(hi-lo)*(h-padT-padB), X=i=>6+i*cw+cw/2;
  const fg=css("--muted"),line=css("--line"),up=css("--up"),dn=css("--down"),fanc=css("--fan");
  g.font="11px "+css("--f-mono");g.fillStyle=fg;g.strokeStyle=line;g.lineWidth=1;g.textAlign="left";g.direction="ltr";
  for(let k=0;k<=4;k++){const v=lo+(hi-lo)*k/4,y=Y(v);g.globalAlpha=.6;g.beginPath();g.moveTo(6,y);g.lineTo(w-padR,y);g.stroke();g.globalAlpha=1;g.fillText(fmt(v),w-padR+6,y+4)}
  // now divider
  if(fan){const x=6+K*cw;g.setLineDash([2,4]);g.beginPath();g.moveTo(x,padT);g.lineTo(x,h-padB);g.stroke();g.setLineDash([]);g.fillText("now",x+4,h-6)}
  g.fillText(new Date(cs[0].t*1000).toISOString().slice(5,13).replace("T"," ")+"h",6,h-6);
  // fan
  if(fan){
    const x0=6+K*cw, band=(lo_i,hi_i,al)=>{g.beginPath();g.moveTo(x0,Y(a.last));fan.forEach((q,t)=>g.lineTo(X(K+t),Y(q[hi_i])));for(let t=fan.length-1;t>=0;t--)g.lineTo(X(K+t),Y(fan[t][lo_i]));g.lineTo(x0,Y(a.last));g.closePath();g.globalAlpha=al;g.fillStyle=fanc;g.fill();g.globalAlpha=1};
    band(0,4,.13);band(1,3,.26);
    g.beginPath();g.moveTo(x0,Y(a.last));fan.forEach((q,t)=>g.lineTo(X(K+t),Y(q[2])));g.strokeStyle=fanc;g.lineWidth=1.2;g.setLineDash([4,3]);g.stroke();g.setLineDash([]);
  }
  // levels
  const lvl=(v,c)=>{g.strokeStyle=c;g.lineWidth=1.2;g.setLineDash([6,4]);g.beginPath();g.moveTo(X(K-27),Y(v));g.lineTo(w-padR,Y(v));g.stroke();g.setLineDash([]);g.fillStyle=c;g.fillRect(w-padR+2,Y(v)-8,padR-4,16);g.fillStyle=css("--bg");g.fillText(fmt(v),w-padR+5,Y(v)+4)};
  // ema
  g.beginPath();e.forEach((v,i)=>i?g.lineTo(X(i),Y(v)):g.moveTo(X(i),Y(v)));g.strokeStyle=fg;g.globalAlpha=.7;g.lineWidth=1.2;g.stroke();g.globalAlpha=1;
  // candles
  const bw=Math.max(1,cw*.62);
  cs.forEach((k,i)=>{const c=k.c>=k.o?up:dn,x=X(i);g.strokeStyle=c;g.fillStyle=c;g.lineWidth=1;g.beginPath();g.moveTo(x,Y(k.h));g.lineTo(x,Y(k.l));g.stroke();const y1=Y(Math.max(k.o,k.c)),y2=Y(Math.min(k.o,k.c));g.fillRect(x-bw/2,y1,bw,Math.max(1,y2-y1))});
  lvl(a.rh,dn);lvl(a.rl,up);
}

/* ---------- simulation UI ---------- */
let runId=0;
function runSim(){
  const a=state.list[state.sel],id=++runId,PATHS=10000;
  state.fan=null;state.simDone=false;
  const sim=simulate(a,state.horizon,PATHS,4242+state.sel*31+state.horizon);
  state.sim=sim;
  const reduce=matchMedia("(prefers-reduced-motion: reduce)").matches;
  const tick=()=>{
    if(id!==runId)return;
    const d=sim.step(reduce?PATHS:700);
    $("sim-n").textContent=d.toLocaleString("en-US");
    if(d<PATHS){requestAnimationFrame(tick);return}
    state.fan=fanFromGrid(sim);state.simDone=true;
    renderSimResults();drawMain();renderPost();
  };
  $("sim-l").textContent=`مسیر از ۱۰٬۰۰۰ · ${state.horizon===24?"۲۴ ساعت":"۷۲ ساعت"} آینده · ${a.sym}`;
  tick();
}
function simStats(){
  const a=state.list[state.sel],s=state.sim,fin=Float64Array.from(s.fin).sort();
  const q=[.05,.25,.5,.75,.95].map(x=>quant(fin,x));
  const levels=[
    ["سقف رنج ۲۴h",a.rh],["کف رنج ۲۴h",a.rl],
    ["سقف ۷ روز",a.wh],["کف ۷ روز",a.wl],
    ["+۵٪",a.last*1.05],["−۵٪",a.last*.95]
  ].map(([name,v])=>{let hit=0;if(v>=a.last){for(let i=0;i<s.paths;i++)if(s.mx[i]>=v)hit++}else{for(let i=0;i<s.paths;i++)if(s.mn[i]<=v)hit++}return {name,v,d:v/a.last-1,p:hit/s.paths}});
  return {q,levels,fin};
}
function renderSimResults(){
  const st=simStats(),a=state.list[state.sel];
  const pc=$("sim-pcts");pc.textContent="";
  [["میانه",st.q[2]],["بازهٔ ۵۰٪",fmt(st.q[1])+" – "+fmt(st.q[3])],["بازهٔ ۹۰٪",fmt(st.q[0])+" – "+fmt(st.q[4])]].forEach(([k,v])=>{const s=document.createElement("span");s.className="pill";s.innerHTML=`${k} <b class="num"></b>`;s.querySelector("b").textContent=typeof v==="number"?fmt(v):v;pc.append(s)});
  const tb=$("lv-body");tb.textContent="";
  st.levels.forEach(l=>{const tr=document.createElement("tr");tr.innerHTML=`<td></td><td class="num"></td><td class="num ${l.d>=0?"up":"down"}"></td><td><div class="row" style="flex-wrap:nowrap"><span class="num" style="min-width:3.2em"></span><div class="bar" style="flex:1"><span></span></div></div></td>`;
    const td=tr.children;td[0].textContent=l.name;td[1].textContent=fmt(l.v);td[2].textContent=pct(l.d);td[3].querySelector(".num").textContent=Math.round(l.p*100)+"%";td[3].querySelector(".bar span").style.width=(l.p*100)+"%";tb.append(tr)});
  drawHist(st);
}
function drawHist(st){
  const cv=$("cv-hist"),{g,w,h}=prep(cv),a=state.list[state.sel],f=st.fin;
  const lo=quant(f,.005),hi=quant(f,.995),B=40,bins=new Array(B).fill(0);
  for(const v of f){if(v<lo||v>hi)continue;bins[Math.min(B-1,Math.floor((v-lo)/(hi-lo)*B))]++}
  const mx=Math.max(...bins),padB=22,bw=w/B,acc=css("--fan"),mut=css("--muted");
  g.font="11px "+css("--f-mono");g.direction="ltr";
  bins.forEach((c,i)=>{const bh=c/mx*(h-padB-14),x=i*bw,mid=lo+(i+.5)/B*(hi-lo);g.fillStyle=acc;g.globalAlpha=(mid>=st.q[1]&&mid<=st.q[3])?.85:.35;g.fillRect(x+1,h-padB-bh,bw-2,bh)});
  g.globalAlpha=1;
  const X=v=>(v-lo)/(hi-lo)*w;
  [[a.last,"now",mut],[a.rh,"R",css("--down")],[a.rl,"S",css("--up")]].forEach(([v,t,c])=>{if(v<lo||v>hi)return;const x=X(v);g.strokeStyle=c;g.setLineDash([3,3]);g.beginPath();g.moveTo(x,4);g.lineTo(x,h-padB);g.stroke();g.setLineDash([]);g.fillStyle=c;g.textAlign="center";g.fillText(t,Math.min(w-14,Math.max(14,x)),12)});
  g.fillStyle=mut;g.textAlign="left";g.fillText(fmt(lo),2,h-6);g.textAlign="right";g.fillText(fmt(hi),w-2,h-6);g.textAlign="center";g.fillText(fmt(st.q[2]),X(st.q[2]),h-6);
}

/* ---------- telegram post ---------- */
function postData(){
  const a=state.list[state.sel],st=state.simDone?simStats():null;
  return {coin:a.sym,price:fmt(a.last),change24h:pct(a.chg),structure:biasTxt(a.bias)[0],trend:a.trend,
    patterns:a.tags.map(t=>t.label+": "+t.detail),resistance:fmt(a.rh),support:fmt(a.rl),
    sim: st?{horizonHours:state.horizon,paths:10000,median:fmt(st.q[2]),range50:[fmt(st.q[1]),fmt(st.q[3])],range90:[fmt(st.q[0]),fmt(st.q[4])],
      touch:st.levels.map(l=>`${l.name} ${fmt(l.v)}: ${Math.round(l.p*100)}%`)}:null,
    dataNote:a.csv?"real data from user CSV":state.source==="live"?"live Binance data":"SAMPLE DATA, not real market prices"};
}
function renderPost(){
  if(!$("tg"))return;
  const a=state.list[state.sel],d=postData(),st=state.simDone?simStats():null;
  const dot=a.bias>0?"🟢":a.bias<0?"🔴":"⚪️";
  let t=`📊 ${a.sym}/USDT · تحلیل ساختار بازار\n\nقیمت: ${L(d.price)}\nتغییر ۲۴ ساعت: ${L(d.change24h)}\nجهت ساختار: ${d.structure} ${dot}\n`;
  if(a.tags.length)t+=`\nالگوهای شناسایی‌شده:\n`+a.tags.map(x=>"• "+x.label).join("\n")+"\n";
  t+=`\nسطوح کلیدی:\nسقف رنج ${L(d.resistance)} · کف رنج ${L(d.support)}\n`;
  if(st){const r=st.levels[0],s=st.levels[1];
    t+=`\nشبیه‌سازی ۱۰٬۰۰۰ مسیر برای ${state.horizon===24?"۲۴ ساعت":"۳ روز"} آینده:\n۵۰٪ مسیرها بین ${L(fmt(st.q[1]))} و ${L(fmt(st.q[3]))} بسته شدند.\nاحتمال لمس سقف رنج: ${Math.round(r.p*100)}٪ · احتمال لمس کف رنج: ${Math.round(s.p*100)}٪\n`}
  t+=`\n⚠️ این تحلیل آموزشی است و سیگنال خرید یا فروش نیست.\n#${a.sym} #کریپتو`;
  const el=$("tg");el.dir="rtl";el.textContent=t;$("copy-s").textContent="";
}
if($("copy"))$("copy").onclick=async()=>{const t=$("tg").textContent,s=$("copy-s");
  try{await navigator.clipboard.writeText(t);s.textContent="کپی شد"}
  catch(e){const r=document.createRange();r.selectNodeContents($("tg"));const sel=getSelection();sel.removeAllRanges();sel.addRange(r);s.textContent="متن انتخاب شد؛ Ctrl+C بزنید"}};

/* ---------- AI writing (server LLM or Claude on the preview) ---------- */
let ctl=null;
(async()=>{
  if(!$("ai-write"))return;   // the post-writing tools are for the site admin only
  const st=await AI.status(),s=$("ai-s");
  if(!st.ok){s.textContent="هوش مصنوعی در دسترس نیست؛ متن آماده بالا قابل استفاده است.";return}
  s.textContent="آماده";$("ai-write").disabled=false;$("img-box").hidden=!st.images;
  const LN={fa:"Persian (Farsi)",en:"English",ar:"Arabic"};
  const busy=b=>{$("ai-write").disabled=b;$("img").disabled=b;$("ai-stop").hidden=!b};
  $("ai-stop").onclick=()=>ctl&&ctl.abort();
  async function go(prompt,opts,lang){
    ctl=new AbortController();busy(true);s.textContent="در حال فکر کردن…";
    const el=$("tg");el.dir=lang==="en"?"ltr":"rtl";
    try{const text=await AI.ask(prompt,{...opts,signal:ctl.signal,onText:({text})=>{el.textContent=text;s.textContent="در حال نوشتن…"}});
      el.textContent=text;s.textContent="نوشته شد. قبل از انتشار بخوانید و تأیید کنید."}
    catch(e){s.textContent=AI.errorText(e)}
    finally{busy(false)}
  }
  $("ai-write").onclick=()=>{
    const lang=$("lang").value,d=postData();
    go(`You write Telegram channel posts for a crypto analysis channel.
Write ONE post in ${LN[lang]} from the JSON data below.
Rules:
- Describe market structure, detected chart patterns, key levels and the Monte Carlo simulation result in plain language.
- Never give an entry point, target, stop-loss, or any buy/sell recommendation. No "buy", "sell", "long", "short" advice.
- Max 130 words. Short lines. A few relevant emojis are fine. End with a one-line disclaimer that this is educational, not financial advice, and 2 hashtags.
- If dataNote says SAMPLE DATA, add a first line stating the figures are a demo.
- Output only the post text.

DATA:
${JSON.stringify(d,null,1)}`,{},lang);
  };
  $("img").onchange=e=>{
    const f=e.target.files&&e.target.files[0];if(!f)return;
    const lang=$("lang").value;
    go(`The attached image is a screenshot of a crypto price chart. Answer in ${LN[lang]}.
1) Name the coin and timeframe if visible.
2) Describe the trend and market structure (bullish / bearish / neutral).
3) List chart patterns you can actually see (ranges, breakouts, double tops/bottoms, triangles, flags), with the approximate price levels.
4) List key support and resistance levels.
Do NOT give entry points, targets, stop-losses or buy/sell advice. If something is unclear in the image, say so instead of guessing. Max 180 words. End with a one-line educational disclaimer.`,{images:[f]},lang);
    e.target.value="";
  };
})();

/* ---------- send draft to the Telegram approval bot (server only) ---------- */
if(window.SITE_MODE==="server"&&window.IS_ADMIN&&$("send-tg")){
  $("send-tg").hidden=false;
  $("send-tg").onclick=async()=>{
    const s=$("copy-s");s.textContent="در حال ارسال…";$("send-tg").disabled=true;
    try{const r=await fetch(window.API_BASE+"/api/trader/send",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({symbol:state.list[state.sel].sym,text:$("tg").textContent})});
      const j=await r.json();s.textContent=j.ok?"برای تأیید به ربات فرستاده شد":(j.error||"ارسال نشد")}
    catch(e){s.textContent="ارسال نشد: سرور در دسترس نیست"}
    finally{$("send-tg").disabled=false}
  };
}

/* ---------- CSV upload ---------- */
$("csv").onchange=e=>{
  const f=e.target.files&&e.target.files[0];if(!f)return;
  const rd=new FileReader();
  rd.onload=()=>{
    try{
      const rows=String(rd.result).trim().split(/\r?\n/).map(l=>l.split(/[,;\t]/).map(x=>x.trim().replace(/^"|"$/g,"")));
      let head=rows[0].map(x=>x.toLowerCase()),start=1;
      const idx=k=>head.findIndex(x=>x===k||x.startsWith(k));
      let io=idx("open"),ih=idx("high"),il=idx("low"),ic=idx("close"),iv=idx("vol"),it=idx("time");
      if(ic<0){/* Binance raw klines: no header */head=[];start=0;it=0;io=1;ih=2;il=3;ic=4;iv=5}
      const cs=[];
      for(let i=start;i<rows.length;i++){const r=rows[i];const o=+r[io],h=+r[ih],l=+r[il],c=+r[ic];if(!(o>0&&h>0&&l>0&&c>0))continue;
        let t=r[it];t=isFinite(+t)?(+t>1e12?+t/1000:+t):Date.parse(t)/1000;cs.push({t:t||i*3600,o,h,l,c,v:iv>=0?(+r[iv]||1):1})}
      if(cs.length<200)throw new Error(`فقط ${cs.length} کندل معتبر پیدا شد؛ حداقل ۲۰۰ کندل لازم است.`);
      if(cs[0].t>cs[cs.length-1].t)cs.reverse();
      const name=f.name.replace(/\.[^.]+$/,"").toUpperCase().slice(0,10);
      const a=analyze(name,cs);a.csv=true;
      state.list=state.list.filter(x=>!x.csv);state.list.unshift(a);state.csv=true;
      $("data-pill").className="pill live";$("data-pill").textContent="CSV شما: "+name+(state.source==="live"?" · بقیه زنده":" · بقیه نمونه");
      renderGrid();select(0);
    }catch(err){$("data-pill").textContent=String(err.message||"CSV قابل خواندن نبود")}
    e.target.value="";
  };
  rd.readAsText(f);
};

/* ---------- wiring ---------- */
function select(i){state.sel=i;renderGrid();renderSheet();renderPost();runSim()}
document.querySelectorAll("[data-f]").forEach(b=>b.onclick=()=>{state.filter=b.dataset.f;document.querySelectorAll("[data-f]").forEach(x=>x.setAttribute("aria-pressed",x===b?"true":"false"));renderGrid()});
document.querySelectorAll("[data-h]").forEach(b=>b.onclick=()=>{state.horizon=+b.dataset.h;document.querySelectorAll("[data-h]").forEach(x=>x.setAttribute("aria-pressed",x===b?"true":"false"));runSim()});
$("rerun").onclick=runSim;
let rz;addEventListener("resize",()=>{clearTimeout(rz);rz=setTimeout(()=>{drawMain();if(state.simDone)drawHist(simStats());document.querySelectorAll(".tile canvas").forEach((c,i)=>spark(c,state.list[i]))},120)});
(async()=>{
  if(!(await loadLive()))buildSample();
  setDataPill();
  const firstHit=state.list.findIndex(a=>a.tags.some(t=>t.id==="bo_up"||t.id==="dbl_b"));
  select(firstHit>=0?firstHit:0);
  if(state.source==="live"){
    // tick-by-tick price from the exchange for every tile and the setup card
    const flash=(el,up)=>{el.style.transition="none";el.style.color=up?"var(--up)":"var(--down)";requestAnimationFrame(()=>{el.style.transition="color 1.2s";el.style.color=""})};
    LivePrices.subscribe(COINS.map(c=>c[0]),(sym,v)=>{
      const a=state.list.find(x=>x.sym===sym&&!x.csv);if(!a)return;
      const prev=a.livePrice||a.last;a.livePrice=v.price;if(isFinite(v.chg24h))a.liveChg=v.chg24h;
      const t=document.querySelector(`.tile[data-sym="${sym}"] .chg`);
      if(t&&isFinite(v.chg24h)){t.textContent=pct(v.chg24h);t.className="chg num "+(v.chg24h>=0?"up":"down")}
      if(state.list[state.sel]===a){
        const cp=$("c-price");cp.textContent=fmtX(v.price);if(v.price!==prev)flash(cp,v.price>prev);
        if(isFinite(v.chg24h)){const ce=$("c-chg");ce.className="s num "+(v.chg24h>=0?"up":"down");ce.textContent=pct(v.chg24h)+" (24h) · لحظه‌ای "+v.source}
      }
    },st=>{if(st.live){state.liveSource=st.source;setDataPill()}});
    // refresh live candles every 2 minutes, keep the selected coin
    setInterval(async()=>{
      if(document.hidden)return;
      const sym=state.list[state.sel]&&state.list[state.sel].sym,csv=state.list.filter(x=>x.csv);
      if(!(await loadLive()))return;
      state.list=[...csv,...state.list];setDataPill();
      const i=state.list.findIndex(a=>a.sym===sym);select(i>=0?i:0);
    },120000);
  }
})();
})();
