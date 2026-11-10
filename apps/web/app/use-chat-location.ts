'use client';
import {useEffect, useRef, useState} from 'react';

export type ChatPosition = {latitude:number;longitude:number;accuracy_m:number;captured_at:string};
type Preference = {known:boolean;enabled:boolean;position:ChatPosition|null;version:number};
const empty:Preference={known:false,enabled:false,position:null,version:0};
type Props={request:<T>(path:string, options?:RequestInit)=>Promise<T>;userId?:string;onError:(e:unknown)=>void};

export function useChatLocation({request,userId,onError}:Props){
  const [profile,setProfile]=useState<Preference>(empty);
  const [busy,setBusy]=useState(false);
  const [unavailable,setUnavailable]=useState(false);
  const [permission,setPermission]=useState<PermissionState>('prompt');
  const [tracking,setTracking]=useState(false);
  const state=useRef(profile); state.current=profile;
  const epoch=useRef(0), lastSent=useRef(0), posting=useRef(false);
  useEffect(()=>{
    const current=++epoch.current;
    setProfile(empty);setUnavailable(false);setBusy(false);
    if(userId) request<Preference>('/chat/location').then(value=>{if(current===epoch.current)setProfile(value);}).catch(()=>{});
    let status:PermissionStatus|undefined; let alive=true;
    const changed=()=>{if(alive&&status)setPermission(status.state);};
    navigator.permissions?.query({name:'geolocation'}).then(value=>{if(!alive)return;status=value;changed();status.addEventListener('change',changed);}).catch(()=>{});
    return ()=>{alive=false;epoch.current++;status?.removeEventListener('change',changed);};
  },[request,userId]);
  const normalize=(value:GeolocationPosition):ChatPosition=>({latitude:value.coords.latitude,longitude:value.coords.longitude,accuracy_m:value.coords.accuracy,captured_at:new Date(value.timestamp).toISOString()});
  const disable=async()=>{
    epoch.current++; // Discard any pending position callback immediately.
    state.current={...state.current,enabled:false,position:null};setProfile(state.current);setTracking(false);
    try{const value=await request<Preference>('/chat/location',{method:'DELETE'});state.current=value;setProfile(value);}
    catch(error){onError(error);}
  };
  const enable=async():Promise<ChatPosition|null>=>{
    if(!userId||!navigator.geolocation||busy){setUnavailable(true);return null;}
    const current=epoch.current;setBusy(true);setUnavailable(false);
    try{
      const raw=await new Promise<GeolocationPosition>((resolve,reject)=>navigator.geolocation.getCurrentPosition(resolve,reject,{enableHighAccuracy:true,timeout:20000,maximumAge:30000}));
      if(current!==epoch.current)return null;
      const fix=normalize(raw);
      const value=await request<Preference>('/chat/location',{method:'PATCH',body:JSON.stringify({...fix,authorize:true})});
      if(current!==epoch.current)return null;
      state.current=value;setProfile(value);setPermission('granted');lastSent.current=Date.now();return fix;
    }catch(error){
      if(current===epoch.current){setUnavailable(true);if((error as GeolocationPositionError).code===1)await disable();else if(error instanceof Error)onError(error);}
      return null;
    }finally{setBusy(false);}
  };
  useEffect(()=>{if(userId&&profile.enabled&&permission==='denied')void disable();},[userId,profile.enabled,permission]);
  useEffect(()=>{
    if(!userId||!profile.enabled||permission!=='granted'||!navigator.geolocation)return;
    let watch:number|undefined,active=false,closed=false;
    const stop=()=>{active=false;if(watch!==undefined)navigator.geolocation.clearWatch(watch);watch=undefined;setTracking(false);};
    const start=()=>{
      if(closed||document.visibilityState!=='visible'||!state.current.enabled)return;
      active=true;setTracking(true);
      watch=navigator.geolocation.watchPosition(async raw=>{
        if(!active||closed||!state.current.enabled)return;
        const fix=normalize(raw);setUnavailable(false);setProfile(previous=>({...previous,position:fix}));
        if(posting.current||Date.now()-lastSent.current<30000)return;
        posting.current=true;lastSent.current=Date.now();
        const version=state.current.version;
        try{
          const value=await request<Preference>('/chat/location',{method:'PATCH',body:JSON.stringify({...fix,consent_version:version})});
          if(active&&!closed&&state.current.enabled&&state.current.version===version){state.current=value;setProfile(value);}
        }catch(error){
          if(active&&!closed){setUnavailable(true);if(error instanceof Error&&error.message.includes('CHAT_LOCATION_REVOKED')){try{const value=await request<Preference>('/chat/location');if(active&&!closed){state.current=value;setProfile(value);}}catch{/* Keep the last position marked unavailable until the next foreground fix. */}}}
        }finally{posting.current=false;}
      },()=>{if(active&&!closed)setUnavailable(true);},{enableHighAccuracy:true,timeout:20000,maximumAge:30000});
    };
    const visibility=()=>{stop();if(document.visibilityState==='visible')start();};
    start();document.addEventListener('visibilitychange',visibility);
    return ()=>{closed=true;stop();document.removeEventListener('visibilitychange',visibility);};
  },[userId,profile.enabled,permission,request]);
  return {profile,busy,unavailable,tracking,enable,disable,version:()=>state.current.version};
}
