// 버스 하차 지점(= 집합 장소)과 집합 시각. 위치는 이 기기에만 저장하고, 서버에는 푸시 주소와 집합 시각만 보낸다.
(function(){
  "use strict";
  const key="chtf26-meeting", server="https://chtf2026-field-presence.baekgyeong-meokji.workers.dev";
  const $=id=>document.getElementById(id);
  let fix=null;
  const load=()=>{try{return JSON.parse(localStorage.getItem(key))||{}}catch{return {}}};
  const save=m=>{try{localStorage.setItem(key,JSON.stringify(m))}catch{}};
  const time=t=>new Intl.DateTimeFormat("ko-KR",{timeZone:"Asia/Shanghai",month:"numeric",day:"numeric",hour:"2-digit",minute:"2-digit",hourCycle:"h23"}).format(t);
  function meters(a,b){
    const k=111320*Math.cos(a.lat*Math.PI/180);
    return Math.hypot((b.lng-a.lng)*k,(b.lat-a.lat)*110574);
  }
  // 전시장 안은 통로를 돌아가야 해서 직선거리의 1.3배, 분당 75m로 잡는다
  const walkMin=m=>Math.max(1,Math.round(m*1.3/75));
  function summary(m,now=Date.now()){
    const parts=[];
    if(m.due){
      const left=Math.round((m.due-now)/60000);
      parts.push(left>0?`집합까지 ${left>=60?Math.floor(left/60)+"시간 ":""}${left%60}분`:"집합 시각 지남");
    }
    if(m.lat&&fix){const d=meters(fix,m);parts.push(`하차 지점 ${d<1000?Math.round(d/10)*10+"m":(d/1000).toFixed(1)+"km"} · 도보 약 ${walkMin(d)}분`)}
    return parts.join(" · ");
  }
  async function shareWithWorker(m){
    // 서비스 워커가 푸시를 받았을 때 보여 줄 문구 재료
    try{
      const cache=await caches.open("chtf26-meeting");
      await cache.put("meeting-state",new Response(JSON.stringify({due:m.due||0,dist:m.lat&&fix?meters(fix,m):null,at:Date.now()})));
    }catch{}
  }
  const fired=new Set();
  async function localNotice(m){
    if(!m.due||!m.notify||Notification?.permission!=="granted")return;
    const left=(m.due-Date.now())/60000;
    const mark=[30,10].find(n=>left<=n&&left>n-1.5);
    if(!mark||fired.has(mark+":"+m.due))return;
    fired.add(mark+":"+m.due);
    const reg=await navigator.serviceWorker?.ready;
    reg?.showNotification("버스 집합 "+mark+"분 전",{body:summary(m),tag:"chtf26-meeting",renotify:true});
  }
  function render(){
    const m=load(), has=Boolean(m.lat);
    $("meetingPoint").textContent=has?`하차 지점 기록 · ${time(m.at)}`:"버스에서 내린 곳에서 기록해 두세요.";
    $("meetingPin").hidden=true;
    $("meetingForm").hidden=!has;
    $("meetClear").hidden=!has;
    $("meetPush").hidden=!has||!m.due||!("Notification" in window);
    $("meetPush").textContent=m.notify?"집합 알림 켜짐":"집합 알림 켜기";
    if(m.due&&!$("meetTime").value){
      const d=new Date(m.due+8*3600_000);
      $("meetTime").value=d.toISOString().slice(0,16);
    }
    const text=summary(m);
    $("meetingWalk").textContent=text;
    $("meetingSummary").textContent=m.due?time(m.due):has?"기록됨":"";
    const alert=$("meetingAlert"), soon=m.due&&m.due-Date.now()<90*60000&&m.due>Date.now()-10*60000;
    alert.hidden=!soon;
    alert.textContent=soon?"🚌 "+text:"";
    void shareWithWorker(m);
    void localNotice(m);
  }
  window.addEventListener("chtf:fix",e=>{
    const f=e.detail;
    if(!fix||f.acc<=fix.acc||f.t-fix.t>10_000)fix=f;
    render();
  });
  $("markMeeting").addEventListener("click",()=>{
    if(!fix){$("meetStatus").textContent="위치 신호를 기다리는 중입니다. 잠시 후 다시 눌러 주세요.";return}
    save({...load(),lat:fix.lat,lng:fix.lng,at:Date.now()});
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
    if(m.notify)await subscribe({due:0});
    render();
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
