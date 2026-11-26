(function(){
  "use strict";
  const endpoint="https://chtf2026-field-presence.baekgyeong-meokji.workers.dev/presence";
  const regions=window.CHTF_VENUE;
  const permissionKey="chtf26-live-consent";
  const zoneLabel=zone=>zone.startsWith("hall-")?zone.slice(5)+"관":
    ({south:"남측 등록홀",north:"북측 등록홀",venue:"전시장 권역"})[zone]||"";
  let admitted=false, busy=false, published=false, fixTimer;

  const gate=document.createElement("section");
  gate.id="locationGate";
  gate.setAttribute("aria-labelledby","locationGateTitle");
  gate.innerHTML=`<h1 id="locationGateTitle">The 28th China Hi-Tech Fair</h1>
    <p>관람 안내를 이용하려면 위치 허용이 필요합니다.</p>
    <button type="button">위치 허용 및 공유</button>
    <p role="status"></p>
    <div id="locationHelp" hidden></div>`;
  document.body.prepend(gate);
  const start=gate.querySelector("button");
  const status=gate.querySelector("[role=status]");
  const help=gate.querySelector("#locationHelp");
  const agent=navigator.userAgent;
  // 위치를 거부한 사람에게 기기별로 다시 허용하는 방법을 보여 준다
  function steps(){
    if(/KAKAOTALK|NAVER|Instagram|FBAN|FBAV|Line\//i.test(agent))return [
      "카카오톡·네이버 같은 앱 안에서 열린 화면은 위치가 막혀 있을 수 있습니다.",
      "오른쪽 위(또는 아래) 메뉴 → <b>다른 브라우저로 열기</b>(Safari·Chrome)를 누르세요.",
      "새로 열린 브라우저에서 <b>위치 허용</b>을 누르세요."];
    if(/iPhone|iPad/i.test(agent)||(/Macintosh/i.test(agent)&&navigator.maxTouchPoints>1))return /CriOS/i.test(agent)?[
      "iPhone <b>설정</b> 앱 → <b>Chrome</b> → <b>위치</b> → <b>앱을 사용하는 동안</b>을 고르세요.",
      "설정 → 개인정보 보호 및 보안 → <b>위치 서비스</b>가 켜져 있는지 확인하세요.",
      "이 화면으로 돌아와 <b>다시 시도</b>를 누르세요."]:[
      "주소창 왼쪽 <b>가가</b>(또는 ᴀA) 버튼 → <b>웹 사이트 설정</b> → <b>위치</b> → <b>허용</b>을 고르세요.",
      "그래도 안 되면 <b>설정</b> 앱 → 개인정보 보호 및 보안 → <b>위치 서비스</b>를 켜고, 아래 <b>Safari 웹 사이트</b> → <b>앱을 사용하는 동안</b>을 고르세요.",
      "이 화면으로 돌아와 <b>다시 시도</b>를 누르세요. 바로 안 되면 새로고침하세요."];
    if(/Android/i.test(agent))return [
      "주소창 왼쪽 <b>아이콘</b>(설정 모양 또는 자물쇠) → <b>권한</b>(또는 사이트 설정) → <b>위치</b> → <b>허용</b>을 고르세요.",
      "휴대폰 상단을 내려 <b>위치</b>(GPS)가 켜져 있는지 확인하세요.",
      "이 화면으로 돌아와 <b>다시 시도</b>를 누르세요."];
    return [
      "주소창 왼쪽 <b>자물쇠</b>(사이트 정보) 아이콘 → <b>위치</b> → <b>허용</b>을 고르세요.",
      "컴퓨터의 위치 서비스가 꺼져 있다면 켜 주세요.",
      "<b>다시 시도</b>를 누르세요."];
  }
  function showHelp(denied){
    help.hidden=false;
    help.innerHTML=`<p class="help-title">${denied?"위치를 허용해야 이 가이드를 쓸 수 있습니다.":"위치를 확인하지 못했습니다."}</p>
      <p>지금 있는 홀과 내 위치를 지도에 표시하는 데 씁니다. 아래 순서대로 허용해 주세요.</p>
      <ol>${(denied?steps():["휴대폰의 <b>위치</b>(GPS)를 켜 주세요.","실내라면 창가나 출입구 쪽으로 잠시 이동해 보세요.","<b>다시 시도</b>를 누르세요."]).map(t=>`<li>${t}</li>`).join("")}</ol>
      <button type="button" class="secondary" id="locationReload">새로고침</button>`;
    help.querySelector("#locationReload").onclick=()=>location.reload();
    start.textContent="다시 시도";
  }
  // 브라우저 설정에서 허용으로 바꾸면 바로 이어서 진행한다
  navigator.permissions?.query({name:"geolocation"}).then(p=>{
    if(p.state==="denied")showHelp(true);
    p.onchange=()=>{if(p.state==="granted"&&!admitted)void update();else if(p.state==="denied")showHelp(true)};
  }).catch(()=>{});

  function saved(key,value){
    try{
      if(value!==undefined)localStorage.setItem(key,value);
      return localStorage.getItem(key);
    }catch{return null}
  }
  function credentials(){
    const agent=navigator.userAgent;
    const type=/iPhone/i.test(agent)?"iPhone":/iPad/i.test(agent)||(/Macintosh/i.test(agent)&&navigator.maxTouchPoints>1)
      ?"iPad":/Android/i.test(agent)?"Android":/Mobile/i.test(agent)?"Mobile":"Computer";
    let suffix=saved("chtf26-share-alias");
    if(!suffix||!/^[0-9A-F]{4}$/.test(suffix)){
      suffix=crypto.getRandomValues(new Uint16Array(1))[0].toString(16).padStart(4,"0").toUpperCase();
      saved("chtf26-share-alias",suffix);
    }
    let token;
    try{
      token=sessionStorage.getItem("chtf26-live-token");
      if(!token){token=crypto.randomUUID();sessionStorage.setItem("chtf26-live-token",token)}
    }catch{token=crypto.randomUUID()}
    return {token,device:type+"-"+suffix};
  }
  let identity;

  function classify({latitude,longitude,accuracy}){
    if(![latitude,longitude,accuracy].every(Number.isFinite)||accuracy<0)return {zone:"",message:"위치 신호 확인 중"};
    const radius=Math.max(accuracy,15)+8;
    const metersPerLon=111320*Math.cos(latitude*Math.PI/180);
    const contains=polygon=>{
      let inside=false, nearest=Infinity;
      let [lat,lon]=polygon.at(-1);
      for(const [nextLat,nextLon] of polygon){
        const x=(lon-longitude)*metersPerLon, y=(lat-latitude)*111132;
        const dx=(nextLon-lon)*metersPerLon, dy=(nextLat-lat)*111132;
        const t=Math.max(0,Math.min(1,-(x*dx+y*dy)/(dx*dx+dy*dy||1)));
        nearest=Math.min(nearest,Math.hypot(x+t*dx,y+t*dy));
        if((lat>latitude)!==(nextLat>latitude)&&longitude<(nextLon-lon)*(latitude-lat)/(nextLat-lat)+lon)inside=!inside;
        lat=nextLat;lon=nextLon;
      }
      return {inside,nearest};
    };
    const venue=contains(regions.venue[1]);
    if(!venue.inside)return {zone:"",message:venue.nearest>radius?"전시장 밖":"전시장 입구 부근"};
    if(accuracy>150)return {zone:"",message:"위치 신호 약함"};
    // 홀 사이 간격보다 GPS 오차가 커도, 측정 지점이 들어 있는 홀을 가장 가능성 높은 위치로 본다
    const zones=Object.keys(regions).filter(zone=>zone!=="venue"&&contains(regions[zone][1]).inside);
    const zone=zones.length===1?zones[0]:"venue";
    return {zone,message:zone==="venue"?"전시장 권역 · 홀 확인 중":zoneLabel(zone)+" 추정"};
  }

  // 지도용 원시 측정값. 기기 안에서만 쓰고 서버에는 보내지 않는다.
  let watching=false;
  const fix=({coords:c,timestamp})=>window.dispatchEvent(new CustomEvent("chtf:fix",{detail:{lat:c.latitude,lng:c.longitude,acc:c.accuracy,t:timestamp||Date.now()}}));
  function watch(){
    if(watching)return;
    watching=true;
    navigator.geolocation.watchPosition(fix,()=>{},{enableHighAccuracy:true,maximumAge:0,timeout:20_000});
  }
  function emit(detail){
    window.dispatchEvent(new CustomEvent("chtf:position",{detail}));
  }
  async function publish(zone){
    if(!zone&&!published)return [];
    try{
      const response=await fetch(endpoint,{
        method:"POST",headers:{"Content-Type":"application/json"},
        body:JSON.stringify({...identity,zone}),signal:AbortSignal.timeout(7000)
      });
      if(!response.ok)throw new Error("presence");
      const data=await response.json();
      published=Boolean(zone);
      return Array.isArray(data.people)?data.people:[];
    }catch{return null}
  }
  function lock(message){
    admitted=false;
    document.documentElement.classList.add("location-locked");
    gate.hidden=false;
    status.textContent=message;
    start.disabled=false;
    clearInterval(fixTimer);
    if(published)void publish("");
  }
  async function update(){
    if(busy||document.hidden)return;
    if(!navigator.geolocation||!regions){
      lock("이 브라우저에서는 위치를 확인할 수 없습니다.");
      return;
    }
    busy=true;
    if(!admitted){start.disabled=true;status.textContent="위치 확인 중"}
    try{
      const reading=await new Promise((resolve,reject)=>
        navigator.geolocation.getCurrentPosition(resolve,reject,{enableHighAccuracy:true,timeout:12_000,maximumAge:10_000}));
      fix(reading);
      const position=classify(reading.coords);
      if(!admitted){
        admitted=true;
        saved(permissionKey,"yes");
        identity ||= credentials();
        gate.hidden=true;
        help.hidden=true;
        start.textContent="위치 허용 및 공유";
        document.documentElement.classList.remove("location-locked");
        start.disabled=false;
        clearInterval(fixTimer);
        fixTimer=setInterval(update,20_000);
        watch();
      }
      const details={...position,accuracy:Math.round(reading.coords.accuracy),device:identity.device};
      emit(details);
      const people=await publish(position.zone);
      emit({...details,people});
    }catch(error){
      if(error.code===1||!admitted){
        lock("");
        showHelp(error.code===1);
      }else{
        emit({zone:"",message:"위치 신호 확인 중",people:[]});
        await publish("");
      }
    }finally{busy=false}
  }
  start.addEventListener("click",update);
  window.addEventListener("focus",()=>{if(admitted)void update()});
  document.addEventListener("visibilitychange",()=>{if(admitted&&!document.hidden)void update()});
  if(saved(permissionKey)==="yes")void update();
})();
