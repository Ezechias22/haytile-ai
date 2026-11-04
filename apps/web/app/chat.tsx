'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { ArrowUp, Check, Copy, Download, Mic, MicOff, LoaderCircle, RotateCcw, Sparkles } from 'lucide-react';
import ChatAudio from './chat-audio';
import { useVoiceConversation } from './use-voice-conversation';
import { useSpeechInput } from './speech-input';
import { suggestTitle } from '../../../packages/creation-titles';

type Turn = { audio?: { id: string; status: string; params: { result_asset_id?: string } }; id: string; prompt: string; reply?: string | null; status: string; error?: string | null; title: string };
type Thread = { id: string; title: string };
type Choice = { model_id: string; label: string; available: boolean; unavailable_reason?: string | null };
type Props = {
  request: <T>(path: string, options?: RequestInit) => Promise<T>;
  t: (key: string) => string;
  userId?: string;
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

export default function HaytileChat({ request, t, userId, locale, models, voiceModels, voiceOptions, onWalletChange, available, conversation, setConversation, onThread, onAuth, onError }: Props) {
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
  const pending = useRef<{ fingerprint: string; id: string } | null>(null);
  const chosen = models.find(m => m.model_id === model) || models.find(m => m.available && !m.unavailable_reason);
  const active = turns.some(turn => ['queued', 'processing', 'quality_check'].includes(turn.status));

  const voice = useVoiceConversation({ request, locale, conversation, voice: chatVoice, model: voiceModel, turns, authenticated: !!userId, onAuth, setConversation, onWalletChange, onError, beforeStart: speech.stop, sendText: text => send(text, true), reloadTurns: async () => { const id = voice.session?.conversation_id || conversation; if (id) setTurns(await request<Turn[]>('/chat/conversations/' + encodeURIComponent(id))); } });

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
      <div className="chat-voice-settings"><label>{t('chatVoice')}<select aria-label={t('chatVoice')} value={chatVoice} onChange={event => setChatVoice(event.target.value)} disabled={!!voice.session}>{voiceOptions.map(v => <option key={v.name} value={v.name}>{v.name} · {t(v.gender === 'male' ? 'maleVoiceLabel' : v.gender === 'female' ? 'femaleVoiceLabel' : 'otherVoices')}</option>)}</select></label><label>{t('voiceModel')}<select aria-label={t('voiceModel')} value={voiceModel} onChange={event => setSelectedVoiceModel(event.target.value)} disabled={!!voice.session}>{voiceModels.map(m => <option key={m.model_id} value={m.model_id} disabled={!m.available || !!m.unavailable_reason}>{m.label}</option>)}</select></label><small>{t('chatVoicePriceNotice')}</small></div>
      <section className="voice-conversation" aria-label={t('voiceMode')}>
        {!voice.session && !voice.setup && <button className="button secondary" onClick={voice.prepare} disabled={voice.busy || !voiceModel || !voice.supported || active}><Mic size={17}/>{t('voiceStart')}</button>}
        {voice.setup && <div className="voice-session-setup" role="group" aria-label={t('voiceSessionConsent')}><strong>{t('voiceMode')}</strong><p>{t('voiceSessionNotice')}</p><p>{t('voicePerReply')}: {voice.perReply} {t('credits')} · {chatVoice}</p><label>{t('voiceBudget')}<input aria-label={t('voiceBudget')} type="number" min={voice.perReply} max={5000} value={voice.cap} onChange={event => voice.setCap(event.target.value)}/></label><button className="button primary" onClick={voice.begin} disabled={voice.busy || Number(voice.cap)<voice.perReply || Number(voice.cap)>5000}>{t('voiceConfirm')}</button><button className="button secondary" onClick={() => voice.setSetup(false)} disabled={voice.busy}>{t('cancel')}</button></div>}
        {voice.session && <div className="voice-session-live"><span role="status">{t(voice.phase === 'listening' ? 'voiceListening' : voice.phase === 'speaking' ? 'voiceSpeaking' : voice.phase === 'tapToHear' ? 'voiceTapToHear' : voice.phase === 'thinking' ? 'voiceThinking' : 'voicePreparing')}</span><small>{t('voiceBudgetRemaining')}: {voice.session.remaining} / {voice.session.credit_cap} {t('credits')}</small><button className="button secondary" onClick={voice.stop}>{t('voiceStop')}</button></div>}
        <audio ref={voice.audio} hidden={!voice.audioUrl || !voice.session} controls onEnded={voice.ended} aria-label={t('voiceConversationAudio')}/>
      </section>
      <div className="chat-transcript" role="log" aria-label={t('chatMessages')} aria-live="polite" aria-relevant="additions text">
        <article className="chat-message assistant chat-introduction"><div className="chat-avatar"><img src="/mark.png" width={36} height={36} alt="" /></div><div><strong>HAYTILE AI</strong><h1>{t('chatHello')}</h1><p>{t('chatIntroduction')}</p></div></article>
        {!turns.length && !loading && <div className="chat-suggestions">{['chatIdeaStory', 'chatIdeaLyrics', 'chatIdeaExplain'].map(key => <button key={key} onClick={() => setMessage(t(key))}>{t(key)}<ArrowUp size={15} /></button>)}</div>}
        {loading && <p role="status"><LoaderCircle className="spin" size={16} /> {t('loading')}</p>}
        {turns.map(turn => <div key={turn.id} className="chat-turn"><article className="chat-message user"><div className="chat-user-bubble">{turn.prompt}</div></article><article className="chat-message assistant"><div className="chat-avatar"><img src="/mark.png" width={36} height={36} alt="" /></div><div className="chat-answer"><strong>HAYTILE AI</strong>{turn.status === 'completed' && turn.reply ? <><div className="chat-response">{turn.reply.split(/(```[\s\S]*?```)/g).map((part, index) => part.startsWith('```') ? <pre key={index}><code>{part.slice(3, -3).replace(/^\w+\n/, '')}</code></pre> : <span key={index}>{part}</span>)}</div><div className="chat-answer-actions"><button onClick={() => copy(turn)} aria-label={t('copy')}>{copied === turn.id ? <Check size={15} /> : <Copy size={15} />}{t('copy')}</button><button onClick={() => download(turn)}><Download size={15} />{t('download')}</button></div>{!voice.session && <ChatAudio request={request} t={t} reply={turn.reply} initialJob={turn.audio} messageId={turn.id} conversation={conversation} locale={locale} voice={chatVoice} model={voiceModel} onWalletChange={onWalletChange} onError={onError} />}</> : turn.status === 'failed' ? <div className="chat-failure"><p>{t('chatFailed')} <small>{turn.error}</small></p><button className="button secondary" onClick={() => retry(turn)} disabled={sending}><RotateCcw size={15} />{t('retry')}</button></div> : <p className="chat-thinking"><LoaderCircle className="spin" size={16} />{turn.status === 'queued' ? t('queued') : t('chatThinking')}</p>}</div></article></div>)}
        <div ref={bottom} />
      </div>
      <footer className="chat-footer">
        {syncError && <p role="alert">{t('chatSyncError')}</p>}
        {!available && <p role="status">{t('servicePausedBody')}</p>}
        <form className="chat-input-box" onSubmit={event => { event.preventDefault(); if (voice.session) voice.submitText(message); else send(); }}>
          <textarea aria-label={t('chatMessage')} placeholder={t('chatPlaceholder')} value={message} maxLength={12000} rows={3} onChange={event => setMessage(event.target.value)} onKeyDown={event => { if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); if (voice.session) voice.submitText(message); else send(); } }} />
          <div className="chat-input-actions"><button type="button" className="chat-mic" onClick={speech.toggle} disabled={!speech.supported || sending || active || !!voice.session} aria-label={t(speech.listening ? 'stopRecording' : 'chatSpeak')} aria-pressed={speech.listening}>{speech.listening ? <MicOff size={19} /> : <Mic size={19} />}</button><small>{t('chatEnterHint')}</small><button className="chat-send" type="submit" aria-label={t('chatSend')} disabled={sending || active || !message.trim() || (!!userId && (!chosen || !available))}>{sending ? <LoaderCircle className="spin" size={19} /> : <ArrowUp size={20} />}</button></div>
        </form>
        <p className="chat-disclaimer">{t('chatDisclaimer')} {t(speech.supported ? 'voiceInputNotice' : 'voiceInputUnsupported')}</p>
      </footer>
    </div>
  </section>;
}
