'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { ArrowUp, Check, Copy, Download, LoaderCircle, MessageCircle, Plus, RotateCcw, Sparkles } from 'lucide-react';
import { suggestTitle } from '../../../packages/creation-titles';

type Turn = { id: string; prompt: string; reply?: string | null; status: string; error?: string | null; title: string };
type Thread = { id: string; title: string };
type Choice = { model_id: string; label: string; available: boolean; unavailable_reason?: string | null };
type Props = {
  request: <T>(path: string, options?: RequestInit) => Promise<T>;
  t: (key: string) => string;
  userId?: string;
  locale: string;
  models: Choice[];
  available: boolean;
  onAuth: () => void;
  onError: (error: unknown) => void;
};

export default function HaytileChat({ request, t, userId, locale, models, available, onAuth, onError }: Props) {
  const [conversation, setConversation] = useState('');
  const [threads, setThreads] = useState<Thread[]>([]);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [message, setMessage] = useState('');
  const [model, setModel] = useState('');
  const [sending, setSending] = useState(false);
  const [loading, setLoading] = useState(false);
  const [syncError, setSyncError] = useState(false);
  const [copied, setCopied] = useState('');
  const bottom = useRef<HTMLDivElement>(null);
  const pending = useRef<{ fingerprint: string; id: string } | null>(null);
  const generation = useRef(0);
  const chosen = models.find(m => m.model_id === model) || models.find(m => m.available && !m.unavailable_reason);
  const active = turns.some(turn => ['queued', 'processing', 'quality_check'].includes(turn.status));

  useEffect(() => {
    const token = ++generation.current;
    setTurns([]); setThreads([]); setMessage(''); setSyncError(false);
    setConversation(userId ? localStorage.getItem('haytile-chat-' + userId) || '' : '');
    if (!userId) return;
    request<Thread[]>('/chat/conversations').then(rows => { if (token === generation.current) setThreads(rows); }).catch(() => setSyncError(true));
  }, [userId, request]);

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

  const fresh = () => {
    setConversation(''); setTurns([]); setMessage(''); pending.current = null;
    if (userId) localStorage.removeItem('haytile-chat-' + userId);
  };
  const send = async () => {
    if (!userId) { onAuth(); return; }
    if (!message.trim() || sending || active || !chosen || !available) return;
    const cid = conversation || crypto.randomUUID();
    const parent = [...turns].reverse().find(turn => turn.status === 'completed');
    const draft = { studio: 'text', prompt: message.trim(), title: turns[0]?.title || suggestTitle(message, t('newChat')), model_id: chosen.model_id, confirmed_credits: 0, params: { chat: true, conversation_id: cid, parent_job_id: parent?.id || null, language: locale } };
    const fingerprint = JSON.stringify(draft);
    if (pending.current?.fingerprint !== fingerprint) pending.current = { fingerprint, id: crypto.randomUUID() };
    setSending(true);
    try {
      const turn = await request<Turn>('/jobs', { method: 'POST', body: JSON.stringify({ ...draft, idempotency_key: pending.current.id }) });
      if (!conversation) { setConversation(cid); localStorage.setItem('haytile-chat-' + userId, cid); }
      setTurns(rows => rows.some(row => row.id === turn.id) ? rows : [...rows, turn]);
      setThreads(rows => [{ id: cid, title: draft.title }, ...rows.filter(row => row.id !== cid)]);
      setMessage(''); pending.current = null;
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
    <aside className="chat-history">
      <button className="button secondary" onClick={fresh} disabled={sending}><Plus size={17} />{t('newChat')}</button>
      <p className="eyebrow">{t('chatHistory')}</p>
      {threads.map(thread => <button key={thread.id} className={'chat-thread ' + (thread.id === conversation ? 'selected' : '')} onClick={() => setConversation(thread.id)} disabled={sending}><MessageCircle size={15} /><span>{thread.title}</span></button>)}
    </aside>
    <div className="chat-main">
      <header className="chat-toolbar"><div><Sparkles size={20} /><strong>HAYTILE AI</strong><span className="subtle-badge">{t('freeGeneration')}</span></div><label className="chat-model-label"><span className="sr-only">{t('chooseModel')}</span><select aria-label={t('chooseModel')} value={chosen?.model_id || ''} onChange={event => setModel(event.target.value)} disabled={active || sending}>{models.map(choice => <option key={choice.model_id} value={choice.model_id} disabled={!choice.available || !!choice.unavailable_reason}>{choice.label}</option>)}</select></label></header>
      <div className="chat-transcript" role="log" aria-label={t('chatMessages')} aria-live="polite" aria-relevant="additions text">
        <article className="chat-message assistant chat-introduction"><div className="chat-avatar"><Sparkles size={20} /></div><div><strong>HAYTILE AI</strong><h1>{t('chatHello')}</h1><p>{t('chatIntroduction')}</p></div></article>
        {!turns.length && !loading && <div className="chat-suggestions">{['chatIdeaStory', 'chatIdeaLyrics', 'chatIdeaExplain'].map(key => <button key={key} onClick={() => setMessage(t(key))}>{t(key)}<ArrowUp size={15} /></button>)}</div>}
        {loading && <p role="status"><LoaderCircle className="spin" size={16} /> {t('loading')}</p>}
        {turns.map(turn => <div key={turn.id} className="chat-turn"><article className="chat-message user"><div className="chat-user-bubble">{turn.prompt}</div></article><article className="chat-message assistant"><div className="chat-avatar"><Sparkles size={18} /></div><div className="chat-answer"><strong>HAYTILE AI</strong>{turn.status === 'completed' && turn.reply ? <><div className="chat-response">{turn.reply.split(/(```[\s\S]*?```)/g).map((part, index) => part.startsWith('```') ? <pre key={index}><code>{part.slice(3, -3).replace(/^\w+\n/, '')}</code></pre> : <span key={index}>{part}</span>)}</div><div className="chat-answer-actions"><button onClick={() => copy(turn)} aria-label={t('copy')}>{copied === turn.id ? <Check size={15} /> : <Copy size={15} />}{t('copy')}</button><button onClick={() => download(turn)}><Download size={15} />{t('download')}</button></div></> : turn.status === 'failed' ? <div className="chat-failure"><p>{t('chatFailed')} <small>{turn.error}</small></p><button className="button secondary" onClick={() => retry(turn)} disabled={sending}><RotateCcw size={15} />{t('retry')}</button></div> : <p className="chat-thinking"><LoaderCircle className="spin" size={16} />{turn.status === 'queued' ? t('queued') : t('chatThinking')}</p>}</div></article></div>)}
        <div ref={bottom} />
      </div>
      <footer className="chat-footer">
        {syncError && <p role="alert">{t('chatSyncError')}</p>}
        {!available && <p role="status">{t('servicePausedBody')}</p>}
        <form className="chat-input-box" onSubmit={event => { event.preventDefault(); send(); }}>
          <textarea aria-label={t('chatMessage')} placeholder={t('chatPlaceholder')} value={message} maxLength={12000} rows={3} onChange={event => setMessage(event.target.value)} onKeyDown={event => { if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); send(); } }} />
          <div className="chat-input-actions"><small>{t('chatEnterHint')}</small><button className="chat-send" type="submit" aria-label={t('chatSend')} disabled={sending || active || !message.trim() || (!!userId && (!chosen || !available))}>{sending ? <LoaderCircle className="spin" size={19} /> : <ArrowUp size={20} />}</button></div>
        </form>
        <p className="chat-disclaimer">{t('chatDisclaimer')}</p>
      </footer>
    </div>
  </section>;
}
