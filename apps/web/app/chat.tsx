'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { AudioLines, Square, ArrowUp, Check, Copy, Download, Mic, MicOff, LoaderCircle, RotateCcw, Sparkles } from 'lucide-react';
import ChatAudio from './chat-audio';
import { useLiveVoice } from './use-live-voice';
import { useSpeechInput } from './speech-input';
import { suggestTitle } from '../../../packages/creation-titles';

type Turn = { audio?: { id: string; status: string; params: { result_asset_id?: string } }; id: string; prompt: string; reply?: string | null; status: string; error?: string | null; title: string };
type Thread = { id: string; title: string };
type Choice = { model_id: string; label: string; available: boolean; unavailable_reason?: string | null };
type Props = {
  request: <T>(path: string, options?: RequestInit) => Promise<T>;
  t: (key: string) => string;
  userId?: string;
  userName?: string;
  locale: string;
  models: Choice[];
  voiceModels: Choice[];
  voiceOptions: { name: string; gender: string }[];
  onWalletChange: () => void;
  available: boolean;
  conversation: string;
  setConversation: (id: string) => void;
  onThread: (thread: Thread) => void;
  onAuth: () => void;
  onError: (error: unknown) => void;
};

export default function HaytileChat({ request, t, userId, userName, locale, models, voiceModels, voiceOptions, onWalletChange, available, conversation, setConversation, onThread, onAuth, onError }: Props) {
  const [introduce, setIntroduce] = useState(false);
  const [greeting, setGreeting] = useState('');
  useEffect(() => {
    const hour = new Date().getHours();
    const key = hour < 12 ? 'chatMorning' : hour < 18 ? 'chatAfternoon' : 'chatEvening';
    setGreeting(t(key) + (userName?.trim() ? ', ' + userName.trim().split(/\s+/)[0] : ''));
  }, [conversation, locale, userName, t]);
  useEffect(() => {
    if (!userId) { setIntroduce(false); return; }
    let alive = true;
    request<{ introduce: boolean }>('/chat/welcome', { method: 'POST' })
      .then(value => { if (alive) setIntroduce(value.introduce); })
      .catch(() => { if (alive) setIntroduce(false); });
    return () => { alive = false; };
  }, [userId, request]);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [message, setMessage] = useState('');
  const [model, setModel] = useState('');
  const [chatVoice, setChatVoice] = useState('Puck');
  const speech = useSpeechInput(locale, text => setMessage(previous => previous ? previous + ' ' + text : text), () => onError(new Error('VOICE_INPUT_UNAVAILABLE')));
  const [selectedVoiceModel, setSelectedVoiceModel] = useState('');
  const voiceModel = voiceModels.find(m => m.model_id === selectedVoiceModel && m.available)?.model_id || voiceModels.find(m => m.available && !m.unavailable_reason)?.model_id || '';
  const [sending, setSending] = useState(false);
  const [loading, setLoading] = useState(false);
  const [syncError, setSyncError] = useState(false);
  const [copied, setCopied] = useState('');
  const bottom = useRef<HTMLDivElement>(null);
  const composerInput = useRef<HTMLTextAreaElement>(null);
  useEffect(()=>{const input=composerInput.current;if(input){input.style.height='auto';input.style.height=Math.min(96,input.scrollHeight)+'px';}},[message]);
  const pending = useRef<{ fingerprint: string; id: string } | null>(null);
  const chosen = models.find(m => m.model_id === model) || models.find(m => m.available && !m.unavailable_reason);
  const active = turns.some(turn => ['queued', 'processing', 'quality_check'].includes(turn.status));

  const [liveModel, setLiveModel] = useState('');
  const voice = useLiveVoice({ request, locale, voice: chatVoice, model: liveModel || 'gemini-2.5-flash-native-audio-preview-12-2025', authenticated: !!userId, onAuth, onWalletChange, onError, beforeStart: speech.stop });

  const load = useCallback(async (id: string) => {
    const rows = await request<Turn[]>('/chat/conversations/' + encodeURIComponent(id));
    return rows;
  }, [request]);

  useEffect(() => {
    let alive = true;
    setTurns([]); setSyncError(false); setLoading(false);
    if (!userId || !conversation) return;
    localStorage.setItem('haytile-chat-' + userId, conversation);
    setLoading(true);
    load(conversation).then(rows => { if (alive) setTurns(rows); }).catch(() => { if (alive) setSyncError(true); }).finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [conversation, userId, load]);

  useEffect(() => {
    if (!active || !conversation || !userId) return;
    let alive = true, running = false;
    const poll = async () => {
      if (running || document.visibilityState !== 'visible') return;
      running = true;
      try { const rows = await load(conversation); if (alive) { setTurns(rows); setSyncError(false); } }
      catch { if (alive) setSyncError(true); }
      finally { running = false; }
    };
    const interval = setInterval(poll, 2500);
    window.addEventListener('focus', poll);
    return () => { alive = false; clearInterval(interval); window.removeEventListener('focus', poll); };
  }, [active, conversation, userId, load]);

  useEffect(() => { bottom.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' }); }, [turns.length, turns.map(turn => turn.status).join(',')]);

  const send = async (content = message, voiceTurn = false) => {
    if (!userId) { onAuth(); return; }
    if (!content.trim() || sending || active || !chosen || !available) return;
    const cid = conversation || crypto.randomUUID();
    const parent = [...turns].reverse().find(turn => turn.status === 'completed');
    const draft = { studio: 'text', prompt: content.trim(), title: turns[0]?.title || suggestTitle(content, t('newChat')), model_id: chosen.model_id, confirmed_credits: 0, params: { chat: true, conversation_id: cid, parent_job_id: parent?.id || null, language: locale, ...(voiceTurn ? { voice_conversation: true } : {}) } };
    const fingerprint = JSON.stringify(draft);
    if (pending.current?.fingerprint !== fingerprint) pending.current = { fingerprint, id: crypto.randomUUID() };
    setSending(true);
    try {
      const turn = await request<Turn>('/jobs', { method: 'POST', body: JSON.stringify({ ...draft, idempotency_key: pending.current.id }) });
      if (!conversation) { setConversation(cid); localStorage.setItem('haytile-chat-' + userId, cid); }
      setTurns(rows => rows.some(row => row.id === turn.id) ? rows : [...rows, turn]);
      onThread({ id: cid, title: draft.title });
      setMessage(''); pending.current = null;
      return turn.id;
    } catch (error) { onError(error); }
    finally { setSending(false); }
  };
  const copy = async (turn: Turn) => {
    try { await navigator.clipboard.writeText(turn.reply || ''); setCopied(turn.id); setTimeout(() => setCopied(''), 2000); }
    catch (error) { onError(error); }
  };
  const download = (turn: Turn) => {
    const url = URL.createObjectURL(new Blob([turn.reply || ''], { type: 'text/plain;charset=utf-8' }));
    const link = document.createElement('a'); link.href = url; link.download = turn.title.replace(/[/\\]/g, '-') + '.txt'; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  };
  const retry = async (turn: Turn) => {
    setSending(true);
    try { await request('/jobs/' + turn.id + '/retry', { method: 'POST' }); setTurns(await load(conversation)); }
    catch (error) { onError(error); }
    finally { setSending(false); }
  };

  return <section className="haytile-chat" aria-label="HAYTILE AI Chat">
    <div className="chat-main">
      <header className="chat-toolbar"><div><Sparkles size={20} /><strong>HAYTILE AI</strong><span className="subtle-badge">{t('freeGeneration')}</span></div><label className="chat-model-label"><span className="sr-only">{t('chooseModel')}</span><select aria-label={t('chooseModel')} value={chosen?.model_id || ''} onChange={event => setModel(event.target.value)} disabled={active || sending || !!voice.session}>{models.map(choice => <option key={choice.model_id} value={choice.model_id} disabled={!choice.available || !!choice.unavailable_reason}>{choice.label}</option>)}</select></label></header>

      <div className="chat-transcript" role="log" aria-label={t('chatMessages')} aria-live="polite" aria-relevant="additions text">
        {!turns.length && !loading && <article className="chat-message assistant chat-introduction"><div className="chat-avatar"><img src="/mark.png" width={36} height={36} alt="" /></div><div><strong>HAYTILE AI</strong><h1>{greeting}</h1>{introduce && <p>{t('chatIntroduction')}</p>}</div></article>}
        {loading && <p role="status"><LoaderCircle className="spin" size={16} /> {t('loading')}</p>}
        {turns.map(turn => <div key={turn.id} className="chat-turn"><article className="chat-message user"><div className="chat-user-bubble">{turn.prompt}</div></article><article className="chat-message assistant"><div className="chat-avatar"><img src="/mark.png" width={36} height={36} alt="" /></div><div className="chat-answer"><strong>HAYTILE AI</strong>{turn.status === 'completed' && turn.reply ? <><div className="chat-response">{turn.reply.split(/(```[\s\S]*?```)/g).map((part, index) => part.startsWith('```') ? <pre key={index}><code>{part.slice(3, -3).replace(/^\w+\n/, '')}</code></pre> : <span key={index}>{part}</span>)}</div><div className="chat-answer-actions"><button onClick={() => copy(turn)} aria-label={t('copy')}>{copied === turn.id ? <Check size={15} /> : <Copy size={15} />}{t('copy')}</button><button onClick={() => download(turn)}><Download size={15} />{t('download')}</button></div>{!voice.session && <ChatAudio request={request} t={t} reply={turn.reply} initialJob={turn.audio} messageId={turn.id} conversation={conversation} locale={locale} voice={chatVoice} model={voiceModel} onWalletChange={onWalletChange} onError={onError} />}</> : turn.status === 'failed' ? <div className="chat-failure"><p>{t('chatFailed')} <small>{turn.error}</small></p><button className="button secondary" onClick={() => retry(turn)} disabled={sending}><RotateCcw size={15} />{t('retry')}</button></div> : <p className="chat-thinking"><LoaderCircle className="spin" size={16} />{turn.status === 'queued' ? t('queued') : t('chatThinking')}</p>}</div></article></div>)}
        <div ref={bottom} />
      </div>
      <footer className="chat-footer">
        {syncError && <p role="alert">{t('chatSyncError')}</p>}
        {!available && <p role="status">{t('servicePausedBody')}</p>}
        {(voice.session || voice.busy) && <div className="live-call-overlay" role="dialog" aria-modal="true" aria-label={t('voiceMode')}><div className="live-call-card"><span className={'live-voice-orb '+voice.phase} aria-hidden="true"><AudioLines size={64}/></span><h2>HAYTILE AI</h2><p role="status">{t(voice.busy ? 'voicePreparing' : voice.phase === 'speaking' ? 'voiceSpeaking' : 'voiceListening')}</p><p>{t('liveVoiceNotice')}</p><div className="live-call-actions"><button type="button" className="button secondary" onClick={voice.toggleMute} aria-pressed={voice.muted}>{voice.muted ? <MicOff size={20}/> : <Mic size={20}/>} {t(voice.muted ? 'liveUnmute' : 'liveMute')}</button><button type="button" className="button primary" onClick={voice.stop}>{t('voiceStop')}</button></div></div></div>}
        <form className="chat-input-box" onSubmit={event => { event.preventDefault(); send(); }}>
          <textarea ref={composerInput} aria-label={t('chatMessage')} placeholder={t('chatPlaceholder')} value={message} maxLength={12000} rows={1} onChange={event => setMessage(event.target.value)} onKeyDown={event => { if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); send(); } }} />
          <div className="chat-input-actions"><small>{t('chatEnterHint')}</small><div className="chat-composer-controls"><button type="button" className="chat-mic" onClick={speech.toggle} disabled={!speech.supported || sending || active || !!voice.session || voice.busy} aria-label={t(speech.listening ? 'stopRecording' : 'chatSpeak')} aria-pressed={speech.listening}>{speech.listening ? <MicOff size={19} /> : <Mic size={19} />}</button><button type="button" className="chat-voice-toggle" hidden={!!message.trim() && !voice.session} onClick={voice.session ? voice.stop : voice.begin} disabled={voice.busy || (!voice.session && (!voice.config?.available || !voice.supported || active || sending || !available))} aria-label={t(voice.session ? 'voiceStop' : 'voiceStart')} aria-pressed={!!voice.session} title={t('chatVoicePriceNotice')}>{voice.busy ? <LoaderCircle className="spin" size={20}/> : voice.session ? <Square size={18}/> : <AudioLines size={22}/>}</button><button className="chat-send" hidden={!message.trim() && !sending} type="submit" aria-label={t('chatSend')} disabled={sending || active || !message.trim() || (!!userId && (!chosen || !available))}>{sending ? <LoaderCircle className="spin" size={19} /> : <ArrowUp size={20} />}</button></div></div>
        </form>

        <details className="chat-voice-preferences"><summary><Mic size={12}/> {chatVoice}{voice.config?.available && <> · {voice.config.credits} {t('credits')} / {voice.config.seconds}s</>}</summary><div className="chat-voice-settings"><label>{t('chatVoice')}<select aria-label={t('chatVoice')} value={chatVoice} onChange={event => setChatVoice(event.target.value)} disabled={!!voice.session}>{voiceOptions.map(v => <option key={v.name} value={v.name}>{v.name} · {t(v.gender === 'male' ? 'maleVoiceLabel' : v.gender === 'female' ? 'femaleVoiceLabel' : 'otherVoices')}</option>)}</select></label><label>{t('voiceModel')}<select aria-label={t('voiceModel')} value={voiceModel} onChange={event => setSelectedVoiceModel(event.target.value)} disabled={!!voice.session}>{voiceModels.map(m => <option key={m.model_id} value={m.model_id} disabled={!m.available || !!m.unavailable_reason}>{m.label}</option>)}</select></label><label>{t('liveVoiceModel')}<select aria-label={t('liveVoiceModel')} value={liveModel || voice.config?.models[0]?.model_id || ''} onChange={event=>setLiveModel(event.target.value)} disabled={!!voice.session}>{voice.config?.models.map(m=><option key={m.model_id} value={m.model_id}>{m.label}</option>)}</select></label><p className="chat-voice-cost">{t('chatVoicePriceNotice')}{voice.config?.available && <> · {voice.config.credits} {t('credits')} {t('livePriceUnit')} {voice.config.seconds}s</>}</p><p className="chat-disclaimer">{t('chatDisclaimer')} {t(speech.supported ? 'voiceInputNotice' : 'voiceInputUnsupported')}</p></div></details>

      </footer>
    </div>
  </section>;
}
