'use client';
import { useCallback, useEffect, useRef, useState } from 'react';
import { useSpeechInput } from './speech-input';

type VoiceSession = { id: string; conversation_id: string; model_id: string; voice_name: string; remaining: number; credit_cap: number; per_reply: number; active: boolean };
type VoiceJob = { id: string; status: string; error?: string; params: { result_asset_id?: string } };
type Turn = { id: string; status: string; reply?: string | null; error?: string | null };
type Options = {
  request: <T>(path: string, options?: RequestInit) => Promise<T>;
  locale: string; conversation: string; voice: string; model: string; turns: Turn[];
  sendText: (text: string) => Promise<string | undefined>;
  setConversation: (id: string) => void;
  reloadTurns: () => Promise<void>;
  onWalletChange: () => void; onError: (error: unknown) => void;
  beforeStart: () => void; onAuth: () => void; authenticated: boolean;
};
export function useVoiceConversation(options: Options) {
  const latest = useRef(options); latest.current = options;
  const [setup, setSetup] = useState(false), [perReply, setPerReply] = useState(0), [cap, setCap] = useState('100');
  const [session, setSession] = useState<VoiceSession | null>(null);
  const current = useRef<VoiceSession | null>(null);
  const [phase, setPhase] = useState('off');
  const [busy, setBusy] = useState(false), [audioUrl, setAudioUrl] = useState('');
  const [target, setTarget] = useState(''), [job, setJob] = useState<VoiceJob | null>(null);
  const submitted = useRef('');
  const audio = useRef<HTMLAudioElement>(null);
  const stopRef = useRef<() => void>(() => {});
  async function submitText(text: string) {
    if (!current.current) return;
    setPhase('thinking');
    try {
      const id = await latest.current.sendText(text);
      if (current.current && id) { submitted.current = ''; setTarget(id); }
      else if (!id) stopRef.current();
    } catch (error) { latest.current.onError(error); stopRef.current(); }
  }
  const speech = useSpeechInput(options.locale, submitText, () => { latest.current.onError(new Error('VOICE_INPUT_UNAVAILABLE')); stopRef.current(); });

  const stop = useCallback(() => {
    const old = current.current; current.current = null;
    speech.stop(); audio.current?.pause();
    setSession(null); setPhase('off'); setTarget(''); setJob(null); setAudioUrl('');
    if (old) latest.current.request('/chat/voice-sessions/' + old.id + '/stop', { method: 'POST', keepalive: true }).catch(() => {});
  }, [speech.stop]);
  stopRef.current = stop;
  useEffect(() => { window.addEventListener('haytile-stop-voice', stop); return () => window.removeEventListener('haytile-stop-voice', stop); }, [stop]);
  useEffect(() => () => { const old = current.current; current.current = null; audio.current?.pause(); if (old) latest.current.request('/chat/voice-sessions/' + old.id + '/stop', { method: 'POST', keepalive: true }).catch(() => {}); }, []);
  useEffect(() => { if (current.current && current.current.conversation_id !== options.conversation) stop(); }, [options.conversation, stop]);
  useEffect(() => { setSetup(false); setPerReply(0); }, [options.voice, options.model]);
  useEffect(() => {
    if (!session || phase !== 'listening' || speech.listening) return;
    const timer = setTimeout(speech.start, 300);
    return () => clearTimeout(timer);
  }, [session?.id, phase, speech.listening, speech.start]);
  useEffect(() => { if (phase !== 'listening') speech.stop(); }, [phase, speech.stop]);

  const prepare = async () => {
    if (!options.authenticated) { options.onAuth(); return; }
    setBusy(true);
    try {
      const q = await options.request<{ credits: number }>('/quotes', { method: 'POST', body: JSON.stringify({ studio: 'voice', model_id: options.model, prompt: 'a'.repeat(1000), params: { voice_name: options.voice } }) });
      setPerReply(q.credits); setSetup(true);
    } catch (error) { options.onError(error); }
    finally { setBusy(false); }
  };
  const begin = async () => {
    options.beforeStart(); setBusy(true); setPhase('starting');
    // Resume media playback from the user gesture; actual AI audio arrives later.
    if (audio.current) { audio.current.src = 'data:audio/wav;base64,UklGRgQCAABXQVZFZm10IBAAAAABAAEAwF0AAIC7AAACABAAZGF0YeABAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA='; void audio.current.play().catch(() => {}); }
    try {
      const cid = options.conversation || crypto.randomUUID();
      options.setConversation(cid);
      const next = await options.request<VoiceSession>('/chat/voice-sessions', { method: 'POST', body: JSON.stringify({ conversation_id: cid, model_id: options.model, voice_name: options.voice, credit_cap: Number(cap), confirmed_per_reply: perReply }) });
      current.current = next; setSession(next); setSetup(false); setPhase('listening');
    } catch (error) { setPhase('off'); options.onError(error); }
    finally { setBusy(false); }
  };

  useEffect(() => {
    const turn = options.turns.find(row => row.id === target);
    const approved = current.current;
    if (!approved || !turn || !target || submitted.current === target) return;
    if (turn.status === 'failed') { latest.current.onError(new Error(turn.error || 'PROVIDER_ERROR')); stop(); return; }
    if (turn.status !== 'completed' || !turn.reply) return;
    submitted.current = target;
    const reply = turn.reply;
    setPhase('preparingVoice');
    (async () => {
      try {
        const params = { chat_audio: true, conversation_id: approved.conversation_id, parent_message_id: target, voice_name: approved.voice_name, language: latest.current.locale, voice_session_id: approved.id, session_model_id: approved.model_id };
        const q = await latest.current.request<{ credits: number }>('/quotes', { method: 'POST', body: JSON.stringify({ studio: 'voice', model_id: approved.model_id, prompt: reply, params }) });
        if (current.current?.id !== approved.id) return;
        if (reply.length > 1000 || q.credits > approved.per_reply || q.credits > approved.remaining) throw new Error(reply.length > 1000 ? 'VOICE_REPLY_TOO_LONG' : 'VOICE_SESSION_BUDGET_REACHED');
        const next = await latest.current.request<VoiceJob>('/jobs', { method: 'POST', body: JSON.stringify({ studio: 'voice', title: 'HAYTILE AI · ' + approved.voice_name, model_id: approved.model_id, prompt: reply, params, confirmed_credits: q.credits, idempotency_key: approved.id + ':' + target }) });
        if (current.current?.id !== approved.id) return;
        setJob(next); latest.current.onWalletChange();
        const fresh = await latest.current.request<VoiceSession>('/chat/voice-sessions/' + approved.id);
        if (current.current?.id === approved.id) { current.current = fresh; setSession(fresh); }
      } catch (error) { latest.current.onError(error); stop(); }
    })();
  }, [target, options.turns, stop]);

  useEffect(() => {
    if (!job || !session || !['queued', 'processing', 'quality_check'].includes(job.status)) return;
    let alive = true, polling = false;
    const sid = session.id;
    const poll = async () => {
      if (polling || document.visibilityState !== 'visible') return;
      polling = true;
      try {
        const next = await latest.current.request<VoiceJob>('/jobs/' + job.id);
        if (!alive || current.current?.id !== sid) return;
        if (next.status === 'failed') throw new Error(next.error || 'PROVIDER_ERROR');
        if (next.status === 'completed' && next.params.result_asset_id) {
          const link = await latest.current.request<{ media_url?: string; path: string }>('/assets/' + next.params.result_asset_id + '/link');
          if (!alive || current.current?.id !== sid) return;
          const url = link.media_url || '/api' + link.path;
          setAudioUrl(url); setPhase('speaking'); latest.current.onWalletChange();
          await latest.current.reloadTurns();
          if (!alive || current.current?.id !== sid) return;
          if (audio.current) { audio.current.src = url; try { await audio.current.play(); } catch { if (current.current?.id === sid) setPhase('tapToHear'); } }
          setJob(next);
        }
      } catch (error) { if (alive) { latest.current.onError(error); stop(); } }
      finally { polling = false; }
    };
    const timer = setInterval(poll, 1500);
    return () => { alive = false; clearInterval(timer); };
  }, [job?.id, job?.status, session?.id, stop]);
  const ended = () => { if (current.current && ['speaking','tapToHear'].includes(phase)) { if (current.current.remaining < current.current.per_reply) { latest.current.onError(new Error('VOICE_SESSION_BUDGET_REACHED')); stop(); } else { setTarget(''); setJob(null); setPhase('listening'); } } };
  return { submitText, session, setup, setSetup, perReply, cap, setCap, busy, phase, prepare, begin, stop, audio, audioUrl, ended, supported: speech.supported, listening: speech.listening };
}
