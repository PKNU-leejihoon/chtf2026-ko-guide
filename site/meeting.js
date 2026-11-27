// 버스 하차 지점(= 집합 장소)과 집합 시각. 위치는 이 기기에만 저장하고, 서버에는 푸시 주소와 집합 시각만 보낸다.
(function(){
  "use strict";
  const key="chtf26-meeting", server="https://chtf2026-field-presence.baekgyeong-meokji.workers.dev";
  const $=id=>document.getElementById(id);
  let fix=null;
  const load=()=>{try{return JSON.parse(localStorage.getItem(key))||{}}catch{return {}}};
  const save=m=>{try{localStorage.setItem(key,JSON.stringify(m))}catch{}};
  const time=t=>new Intl.DateTimeFormat("ko-KR",{timeZone:"Asia/Shanghai",month:"numeric",day:"numeric",hour:"2-digit",minute:"2-digit",hourCycle:"h23"}).format(t);
  const hasPoint=p=>Number.isFinite(p?.lat)&&Number.isFinite(p?.lng);
  const currentFix=()=>fix&&Date.now()-fix.t<60_000?fix:null;
  const distanceLabel=d=>d<1000?Math.round(d/10)*10+"m":(d/1000).toFixed(1)+"km";
  function renderMap(m,current){
    const map=$("meetingMap"), has=hasPoint(m);
    map.hidden=!has;
    if(!has)return null;

    // 북쪽을 위로 놓고 두 지점이 지도 안에 들어오도록 확대한다.
    const origin=current||m;
    const lonScale=111320*Math.cos(origin.lat*Math.PI/180);
    const [east,north]=[(m.lng-origin.lng)*lonScale,(m.lat-origin.lat)*110574];
    const distance=Math.hypot(east,north);
    const scale=Math.min(1,276/Math.abs(east),180/Math.abs(north));
    const project=(lat,lng)=>[
      180+((lng-origin.lng)*lonScale-east/2)*scale,
      135-((lat-origin.lat)*110574-north/2)*scale
    ];
    const [pinX,pinY]=project(m.lat,m.lng);
    const [meX,meY]=project(origin.lat,origin.lng);
    const accuracy=current?.acc||0;
    const showDirection=Boolean(current&&distance>Math.max(15,accuracy+(m.acc||0)));
    const zones=window.CHTF_VENUE||{};
    const drawZone=(zone,label)=>{
      const points=zones[zone][1].map(([lat,lng])=>project(lat,lng));
      const xs=points.map(p=>p[0]), ys=points.map(p=>p[1]);
      const left=Math.min(...xs), right=Math.max(...xs), top=Math.min(...ys), bottom=Math.max(...ys);
      if(right<0||left>360||bottom<0||top>270)return "";
      const labelLeft=Math.max(6,left), labelRight=Math.min(354,right);
      const labelTop=Math.max(6,top), labelBottom=Math.min(264,bottom);
      return `<polygon class="${zone==="venue"?"venue-outline":"venue-hall"}" points="${points.map(p=>p.map(v=>v.toFixed(1)).join(",")).join(" ")}"/>`
        +(label&&labelRight-labelLeft>=label.length*11&&labelBottom-labelTop>=13
          ?`<text x="${(labelLeft+labelRight)/2}" y="${(labelTop+labelBottom)/2}" text-anchor="middle" dominant-baseline="central">${label}</text>`:"");
    };
    let layer=zones.venue?drawZone("venue",""):"";
    for(const zone of Object.keys(zones)){
      if(zone==="venue")continue;
      layer+=drawZone(zone,zone==="north"?"북측 등록홀":zone==="south"?"남측 등록홀":Number(zone.slice(5))+"관");
    }
    if(current&&accuracy>0){
      layer+=`<circle cx="${meX}" cy="${meY}" r="${accuracy*scale}" fill="#2563eb" fill-opacity=".12"/>`;
    }
    if(showDirection){
      layer+=`<line x1="${meX}" y1="${meY}" x2="${pinX-5*east/distance}" y2="${pinY+5*north/distance}" stroke="#c44320" stroke-width="2.5" stroke-dasharray="6 4" marker-end="url(#meetingArrow)"/>`;
    }
    if(current)layer+=`<circle cx="${meX}" cy="${meY}" r="6" fill="#2563eb" stroke="#fff" stroke-width="2"/>`;
    layer+=`<path d="M0 0C-3-5-9-10-9-16a9 9 0 0 1 18 0C9-10 3-5 0 0Z" transform="translate(${pinX} ${pinY})" fill="#c44320" stroke="#fff" stroke-width="1.5"/>`;
    $("meetingMapLayer").innerHTML=layer;
    $("meetingLineLegend").hidden=!showDirection;
    let direction="내 위치 신호를 확인하는 중입니다.";
    if(current){
      const degrees=(Math.atan2(east,north)*180/Math.PI+360)%360;
      const compass=["북","북동","동","남동","남","남서","서","북서"][Math.round(degrees/45)%8];
      direction=showDirection?`${compass}쪽 · 직선거리 약 ${distanceLabel(distance)}`:
        `직선거리 약 ${distanceLabel(distance)} · 가까이 있거나 GPS 오차로 방향을 확인하기 어렵습니다.`;
    }
    $("meetingDirection").textContent=direction;
    return current?distance:null;
  }
  function summary(m,dist,now=Date.now()){
    const parts=[];
    if(m.due){
      const left=Math.round((m.due-now)/60000);
      parts.push(left>0?`집합까지 ${left>=60?Math.floor(left/60)+"시간 ":""}${left%60}분`:"집합 시각 지남");
    }
    if(dist!==null)parts.push(`하차 지점까지 직선거리 약 ${distanceLabel(dist)}`);
    return parts.join(" · ");
  }
  async function shareWithWorker(m,dist){
    // 서비스 워커가 푸시를 받았을 때 보여 줄 문구 재료
    try{
      const cache=await caches.open("chtf26-meeting");
      await cache.put("meeting-state",new Response(JSON.stringify({due:m.due||0,dist,at:Date.now()})));
    }catch{}
  }
  const fired=new Set();
  async function localNotice(m,text){
    if(!m.due||!m.notify||Notification?.permission!=="granted")return;
    const left=(m.due-Date.now())/60000;
    const mark=[30,10].find(n=>left<=n&&left>n-1.5);
    if(!mark||fired.has(mark+":"+m.due))return;
    fired.add(mark+":"+m.due);
    const reg=await navigator.serviceWorker?.ready;
    reg?.showNotification("버스 집합 "+mark+"분 전",{body:text,tag:"chtf26-meeting",renotify:true});
  }
  function render(){
    const m=load(), has=hasPoint(m), distance=renderMap(m,currentFix());
    $("meetingPoint").textContent=has?`하차 지점 기록 · ${time(m.at)}`:"버스에서 내린 곳에서 기록해 두세요.";
    $("meetingForm").hidden=!has;
    $("meetClear").hidden=!has;
    $("meetPush").hidden=!has||!m.due||!("Notification" in window);
    $("meetPush").textContent=m.notify?"집합 알림 켜짐":"집합 알림 켜기";
    if(m.due&&!$("meetTime").value){
      const d=new Date(m.due+8*3600_000);
      $("meetTime").value=d.toISOString().slice(0,16);
    }
    const text=summary(m,distance);
    $("meetingSummary").textContent=m.due?time(m.due):has?"기록됨":"";
    const alert=$("meetingAlert"), soon=m.due&&m.due-Date.now()<90*60000&&m.due>Date.now()-10*60000;
    alert.hidden=!soon;
    alert.textContent=soon?"🚌 "+text:"";
    void shareWithWorker(m,distance);
    void localNotice(m,text);
  }
  window.addEventListener("chtf:fix",e=>{
    const f=e.detail;
    if(!hasPoint(f)||!Number.isFinite(f.acc)||!Number.isFinite(f.t))return;
    if(!fix||f.acc<=fix.acc||f.t-fix.t>10_000)fix=f;
    render();
  });
  $("markMeeting").addEventListener("click",()=>{
    const current=currentFix();
    if(!current){$("meetStatus").textContent="위치 신호를 기다리는 중입니다. 잠시 후 다시 눌러 주세요.";return}
    save({...load(),lat:current.lat,lng:current.lng,acc:current.acc,at:Date.now()});
    $("meetStatus").textContent="";
    render();
  });
  $("meetingForm").addEventListener("submit",async e=>{
    e.preventDefault();
    const v=$("meetTime").value;
    if(!v)return;
    const due=Date.parse(v+":00+08:00");
    const m={...load(),due};
    save(m);
    render();
    if(m.notify)await subscribe(m);
  });
  $("meetClear").addEventListener("click",async()=>{
    const m=load();
    localStorage.removeItem(key);
    $("meetTime").value="";
    render();
    if(m.notify)await subscribe({due:0});
  });
  async function subscribe(m){
    const status=$("meetStatus");
    try{
      const reg=await navigator.serviceWorker.ready;
      if(!reg.pushManager)throw new Error("nopush");
      let sub=await reg.pushManager.getSubscription();
      if(!sub){
        const {publicKey}=await (await fetch(server+"/meeting-key")).json();
        const raw=Uint8Array.from(atob(publicKey.replace(/-/g,"+").replace(/_/g,"/")),c=>c.charCodeAt(0));
        sub=await reg.pushManager.subscribe({userVisibleOnly:true,applicationServerKey:raw});
      }
      const r=await fetch(server+"/meeting",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({endpoint:sub.endpoint,due:m.due||0})});
      if(!r.ok)throw new Error("server");
      status.textContent=m.due?"30분 전, 10분 전에 알려 드립니다.":"";
      return true;
    }catch{
      status.textContent=/iPhone|iPad/.test(navigator.userAgent)&&!navigator.standalone
        ?"iPhone은 공유 → 홈 화면에 추가한 뒤 그 아이콘으로 열면 알림을 받을 수 있습니다."
        :"이 화면을 열어 두는 동안 알려 드립니다.";
      return false;
    }
  }
  $("meetPush").addEventListener("click",async()=>{
    if(await Notification.requestPermission()!=="granted"){$("meetStatus").textContent="알림이 차단되어 있습니다. 브라우저 설정에서 허용해 주세요.";return}
    const m={...load(),notify:true};
    save(m);
    render();
    await subscribe(m);
  });
  setInterval(render,30_000);
  render();
})();
