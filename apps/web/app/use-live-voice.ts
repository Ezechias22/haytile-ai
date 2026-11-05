'use client';
import { useCallback, useEffect, useRef, useState } from 'react';
import { useScreenWakeLock } from './use-screen-wake-lock';

type Config={available:boolean;models:{model_id:string;label:string}[];credits:number;seconds:number};
type Session={id:string;socket_path:string;credits:number;seconds:number};
type Options={request:<T>(path:string,options?:RequestInit)=>Promise<T>;authenticated:boolean;voice:string;model:string;locale:string;onAuth:()=>void;onError:(error:unknown)=>void;onWalletChange:()=>void;beforeStart:()=>void};
export function useLiveVoice(options:Options) {
 const latest=useRef(options); latest.current=options;
 const [config,setConfig]=useState<Config|null>(null),[session,setSession]=useState<Session|null>(null),[busy,setBusy]=useState(false),[phase,setPhase]=useState('off'),[muted,setMuted]=useState(false),[chargedCredits,setChargedCredits]=useState(0);
 useScreenWakeLock(busy || !!session);
 const ws=useRef<WebSocket|null>(null), context=useRef<AudioContext|null>(null), stream=useRef<MediaStream|null>(null), node=useRef<AudioWorkletNode|null>(null), sources=useRef(new Set<AudioBufferSourceNode>()), nextTime=useRef(0), generation=useRef(0), ready=useRef(false), mute=useRef(false), timer=useRef<ReturnType<typeof setTimeout>|null>(null);
 useEffect(()=>{let alive=true;options.request<Config>('/chat/live/config').then(c=>{if(alive)setConfig(c);}).catch(()=>{});return()=>{alive=false;};},[options.request]);
 const clearPlayback=useCallback(()=>{for(const source of sources.current){try{source.stop();}catch{}}sources.current.clear();nextTime.current=0;},[]);
 const stop=useCallback(()=>{
  generation.current++; ready.current=false;
  if(timer.current)clearTimeout(timer.current);
  const old=ws.current; ws.current=null; if(old){if(old.readyState===WebSocket.OPEN)old.send('stop');old.close();}
  node.current?.disconnect();node.current=null;
  stream.current?.getTracks().forEach(track=>track.stop());stream.current=null;
  clearPlayback(); void context.current?.close();context.current=null;
  setSession(null);setBusy(false);setPhase('off');setMuted(false);mute.current=false;
  latest.current.onWalletChange();
 },[clearPlayback]);
 useEffect(()=>{window.addEventListener('haytile-stop-voice',stop);return()=>window.removeEventListener('haytile-stop-voice',stop);},[stop]);
 useEffect(()=>()=>stop(),[stop]);
 const toggleMute=()=>{mute.current=!mute.current;setMuted(mute.current);stream.current?.getAudioTracks().forEach(track=>{track.enabled=!mute.current;});if(mute.current&&ws.current?.readyState===WebSocket.OPEN)ws.current.send('mute');};
 const begin=async()=>{
  if(!options.authenticated){options.onAuth();return;}
  if(!config?.available){options.onError(new Error('LIVE_VOICE_UNAVAILABLE'));return;}
  options.beforeStart();stop();const turn=++generation.current;setBusy(true);setPhase('starting');setChargedCredits(0);
  try{
   const ac=new AudioContext();context.current=ac;await ac.resume();
   const mic=await navigator.mediaDevices.getUserMedia({audio:{channelCount:1,echoCancellation:true,noiseSuppression:true,autoGainControl:true}});
   if(turn!==generation.current){mic.getTracks().forEach(track=>track.stop());return;}stream.current=mic;
   await ac.audioWorklet.addModule('/audio/live-microphone.js');
   if(turn!==generation.current)return;
   const worklet=new AudioWorkletNode(ac,'haytile-live-microphone');node.current=worklet;
   const silent=ac.createGain();silent.gain.value=0;ac.createMediaStreamSource(mic).connect(worklet);worklet.connect(silent).connect(ac.destination);
   const started=await options.request<Session>('/chat/live/sessions',{method:'POST',body:JSON.stringify({voice_name:options.voice,model_id:options.model,language:options.locale,idempotency_key:crypto.randomUUID()})});
   if(turn!==generation.current)return;
   const url=new URL(started.socket_path,location.href);url.protocol=location.protocol==='https:'?'wss:':'ws:';
   const socket=new WebSocket(url);ws.current=socket;setSession(started);latest.current.onWalletChange();
   worklet.port.onmessage=event=>{if(ready.current&&!mute.current&&socket.readyState===WebSocket.OPEN){if(socket.bufferedAmount>128000){options.onError(new Error('LIVE_CONNECTION_FAILED'));stop();return;}socket.send(event.data);}};
   socket.onmessage=event=>{
    if(turn!==generation.current)return;
    try{
     const packet=JSON.parse(event.data);
     if(packet.type==='billing'){setChargedCredits(previous=>Math.max(previous,packet.credits*packet.period));latest.current.onWalletChange();return;}
     if(packet.type==='reconnecting'){ready.current=false;setPhase('reconnecting');return;}
     if(packet.type==='throttled'){ready.current=false;setPhase('waiting');return;}
     if(packet.type==='ready'){if(timer.current){clearTimeout(timer.current);timer.current=null;}ready.current=true;setBusy(false);setPhase('listening');return;}
     if(packet.type==='interrupted'){clearPlayback();setPhase('listening');return;}
     if(packet.type==='audio'){
      const raw=atob(packet.data);const bytes=new Uint8Array(raw.length);for(let i=0;i<raw.length;i++)bytes[i]=raw.charCodeAt(i);
      const pcm=new DataView(bytes.buffer),length=Math.floor(raw.length/2);const buffer=ac.createBuffer(1,length,packet.rate||24000),channel=buffer.getChannelData(0);
      for(let i=0;i<length;i++)channel[i]=pcm.getInt16(i*2,true)/32768;
      if(nextTime.current-ac.currentTime>10)throw new Error('LIVE_CONNECTION_FAILED');
      const source=ac.createBufferSource();source.buffer=buffer;source.connect(ac.destination);sources.current.add(source);
      source.onended=()=>{sources.current.delete(source);if(!sources.current.size&&turn===generation.current)setPhase(current=>current==='reconnecting'||current==='waiting'?current:'listening');};
      const startAt=Math.max(ac.currentTime+.02,nextTime.current);source.start(startAt);nextTime.current=startAt+buffer.duration;setPhase('speaking');return;
     }
     if(packet.type==='error')throw new Error(packet.code||'LIVE_CONNECTION_FAILED');
     if(packet.type==='ended'){if(packet.reason!=='USER_STOP')options.onError(new Error(packet.reason||'LIVE_CONNECTION_FAILED'));stop();}
    }catch(error){options.onError(error);stop();}
   };
   socket.onerror=()=>{if(turn===generation.current){options.onError(new Error('LIVE_CONNECTION_FAILED'));stop();}};
   socket.onclose=()=>{if(turn===generation.current)stop();};
   timer.current=setTimeout(()=>{if(turn===generation.current){options.onError(new Error('LIVE_CONNECTION_FAILED'));stop();}},45000);
  }catch(error){if(turn===generation.current){options.onError(error);stop();}}
 };
 // Ready cancels only the setup deadline; billing periods do not terminate the call.
 useEffect(()=>{if(phase==='listening'&&timer.current){clearTimeout(timer.current);timer.current=null;}},[phase]);
 return {config,session,busy,phase,muted,chargedCredits,toggleMute,begin,stop,supported:typeof window!=='undefined'&&!!window.AudioContext&&!!navigator.mediaDevices?.getUserMedia};
}
