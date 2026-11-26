import { DurableObject } from "cloudflare:workers";

const minute=60_000;
const providers=new Set(["fcm.googleapis.com","updates.push.services.mozilla.com","web.push.apple.com","wns2-bl2p.notify.windows.com"]);
const base64=bytes=>btoa(String.fromCharCode(...new Uint8Array(bytes))).replaceAll("+","-").replaceAll("/","_").replace(/=+$/,"");
const encoded=value=>base64(new TextEncoder().encode(JSON.stringify(value)));

export function pushEndpoint(value){
  if(typeof value!=="string"||value.length>2048)return null;
  try{
    const u=new URL(value);
    if(u.protocol==="https:"&&!u.port&&!u.username&&!u.password&&!u.hash&&u.pathname.length>1&&
       (providers.has(u.hostname)||u.hostname.endsWith(".push.apple.com")||u.hostname.endsWith(".notify.windows.com")))return u;
  }catch{}
  return null;
}

export class MeetingReminder extends DurableObject {
  async getKeys(){
    return this.ctx.blockConcurrencyWhile(async()=>{
      let keys=await this.ctx.storage.get("keys");
      if(!keys){
        const pair=await crypto.subtle.generateKey({name:"ECDSA",namedCurve:"P-256"},true,["sign","verify"]);
        keys={publicKey:base64(await crypto.subtle.exportKey("raw",pair.publicKey)),privateKey:await crypto.subtle.exportKey("jwk",pair.privateKey)};
        await this.ctx.storage.put("keys",keys);
      }
      return keys;
    });
  }
  async publicKey(){return (await this.getKeys()).publicKey}
  async authorization(origin){
    const {publicKey,privateKey}=await this.getKeys();
    const now=Math.floor(Date.now()/1000);
    this.tokens??=new Map();
    const prior=this.tokens.get(origin);
    if(prior&&prior.exp>now+300)return prior.value;
    const exp=now+8*3600;
    const unsigned=encoded({typ:"JWT",alg:"ES256"})+"."+encoded({aud:origin,exp,sub:"https://github.com/PKNU-leejihoon/chtf2026-ko-guide"});
    const key=await crypto.subtle.importKey("jwk",privateKey,{name:"ECDSA",namedCurve:"P-256"},false,["sign"]);
    const signature=await crypto.subtle.sign({name:"ECDSA",hash:"SHA-256"},key,new TextEncoder().encode(unsigned));
    const value="vapid t="+unsigned+"."+base64(signature)+", k="+publicKey;
    this.tokens.set(origin,{exp,value});
    return value;
  }
  async schedule(endpoint,due){
    await this.ctx.blockConcurrencyWhile(async()=>{
      if(!due){
        await this.ctx.storage.deleteAlarm();
        await this.ctx.storage.delete("meeting");
        return;
      }
      const prev=await this.ctx.storage.get("meeting");
      if(prev?.due===due)return;
      const now=Date.now();
      const times=[due-30*minute,due-10*minute].filter(t=>t>now);
      if(!times.length)times.push(now+1000);
      await this.ctx.storage.put("meeting",{endpoint,due,times});
      await this.ctx.storage.setAlarm(times[0]);
    });
  }
  async alarm(){
    await this.ctx.blockConcurrencyWhile(async()=>{
      const state=await this.ctx.storage.get("meeting");
      if(!state)return;
      const now=Date.now();
      if(now>=state.due){await this.ctx.storage.delete("meeting");return}
      if(state.times[0]>now){await this.ctx.storage.setAlarm(state.times[0]);return}
      const origin=new URL(state.endpoint).origin;
      const signer=this.env.MEETINGS.getByName("vapid-keys");
      const result=await fetch(state.endpoint,{method:"POST",redirect:"error",headers:{
        Authorization:await signer.authorization(origin),TTL:String(Math.min(120,Math.ceil((state.due-now)/1000))),Urgency:"high"
      },signal:AbortSignal.timeout(8000)});
      if(result.status===429||result.status>=500)throw new Error("Push service temporarily unavailable");
      state.times=state.times.filter(t=>t>now);
      if(result.ok&&state.times.length){
        await this.ctx.storage.put("meeting",state);
        await this.ctx.storage.setAlarm(state.times[0]);
      }else await this.ctx.storage.delete("meeting");
    });
  }
}
