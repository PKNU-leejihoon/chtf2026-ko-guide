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
    <p role="status"></p>`;
  document.body.prepend(gate);
  const start=gate.querySelector("button");
  const status=gate.querySelector("[role=status]");

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
    if(!venue.inside&&venue.nearest>radius)return {zone:"",message:"전시장 밖"};
    if(venue.nearest<=radius||accuracy>150)return {zone:"",message:"위치 오차로 전시장 경계 확인 중"};
    const zones=Object.keys(regions).filter(zone=>{
      if(zone==="venue")return false;
      const result=contains(regions[zone][1]);
      return result.inside&&result.nearest>radius;
    });
    const zone=zones.length===1?zones[0]:"venue";
    return {zone,message:zone==="venue"?"전시장 권역 · 홀 확인 중":zoneLabel(zone)+" 추정"};
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
      const position=classify(reading.coords);
      if(!admitted){
        admitted=true;
        saved(permissionKey,"yes");
        identity ||= credentials();
        gate.hidden=true;
        document.documentElement.classList.remove("location-locked");
        start.disabled=false;
        clearInterval(fixTimer);
        fixTimer=setInterval(update,20_000);
      }
      const details={...position,accuracy:Math.round(reading.coords.accuracy),device:identity.device};
      emit(details);
      const people=await publish(position.zone);
      emit({...details,people});
    }catch(error){
      if(error.code===1||!admitted){
        lock(error.code===1
          ?"위치 접근이 거절됐습니다. 브라우저와 기기의 위치 설정에서 허용한 뒤 다시 시도해 주세요."
          :"위치를 확인하지 못했습니다. 기기의 위치 서비스를 켜고 다시 시도해 주세요.");
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
