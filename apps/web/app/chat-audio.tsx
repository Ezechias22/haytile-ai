'use client';
import { useEffect, useRef, useState } from 'react';
import { Volume2, LoaderCircle } from 'lucide-react';

type SpeechJob = { id: string; status: string; error?: string; params: { result_asset_id?: string } };
type Props = {
  request: <T>(path: string, options?: RequestInit) => Promise<T>;
  t: (key: string) => string;
  reply: string;
  initialJob?: SpeechJob | null;
  messageId: string;
  conversation: string;
  locale: string;
  voice: string;
  model: string;
  onWalletChange: () => void;
  onError: (error: unknown) => void;
};
export default function ChatAudio({ request, t, reply, initialJob, messageId, conversation, locale, voice, model, onWalletChange, onError }: Props) {
  const [quote, setQuote] = useState<{ credits: number; body: object } | null>(null);
  const [job, setJob] = useState<SpeechJob | null>(initialJob || null);
  const [url, setUrl] = useState('');
  const [busy, setBusy] = useState(false);
  const requestKey = useRef<{ fingerprint: string; key: string } | null>(null);
  useEffect(() => { setQuote(null); }, [voice, model, locale]);
  const active = !!job && ['queued', 'processing', 'quality_check'].includes(job.status);

  const prepare = async () => {
    setBusy(true);
    try {
      const body = { studio: 'voice', model_id: model, title: 'HAYTILE AI · ' + voice, prompt: reply, params: { chat_audio: true, conversation_id: conversation, parent_message_id: messageId, voice_name: voice, language: locale } };
      const q = await request<{ credits: number }>('/quotes', { method: 'POST', body: JSON.stringify(body) });
      setQuote({ credits: q.credits, body });
    } catch (error) { onError(error); }
    finally { setBusy(false); }
  };
  const confirm = async () => {
    if (!quote) return;
    setBusy(true);
    const fingerprint = JSON.stringify(quote.body);
    if (requestKey.current?.fingerprint !== fingerprint) requestKey.current = { fingerprint, key: crypto.randomUUID() };
    try {
      const next = await request<SpeechJob>('/jobs', { method: 'POST', body: JSON.stringify({ ...quote.body, confirmed_credits: quote.credits, idempotency_key: requestKey.current.key }) });
      setJob(next); setQuote(null); setUrl(''); onWalletChange();
      requestKey.current = null;
    } catch (error) { onError(error); }
    finally { setBusy(false); }
  };
  useEffect(() => {
    if (!active || !job) return;
    let alive = true, running = false;
    const poll = async () => {
      if (running || document.visibilityState !== 'visible') return;
      running = true;
      try {
        const next = await request<SpeechJob>('/jobs/' + job.id);
        if (!alive) return;
        setJob(next);
        if (next.status === 'completed') onWalletChange();
        else if (next.status === 'failed') { onWalletChange(); onError(new Error(next.error || 'PROVIDER_ERROR')); }
      } catch (error) { if (alive) onError(error); }
      finally { running = false; }
    };
    const id = setInterval(poll, 2500);
    return () => { alive = false; clearInterval(id); };
  }, [active, job?.id, request]);

  useEffect(() => {
    if (job?.status !== 'completed' || !job.params.result_asset_id) return;
    let alive = true;
    request<{ media_url?: string; path: string }>('/assets/' + job.params.result_asset_id + '/link').then(link => { if (alive) setUrl(link.media_url || '/api' + link.path); }).catch(onError);
    return () => { alive = false; };
  }, [job?.id, job?.status, request]);
  return <div className="chat-audio">
    <button type="button" onClick={prepare} disabled={busy || active || !model || reply.length > 12000}>{busy || active ? <LoaderCircle size={15} className="spin" /> : <Volume2 size={15} />}{active ? t('processing') : t('chatListen')}</button>
    {quote && <div className="chat-audio-consent" role="group" aria-label={t('confirmCost')}><p>{voice} · {quote.credits} {t('credits')}</p><p>{t('reservationNotice')}</p><button onClick={confirm} disabled={busy}>{t('confirm')}</button><button onClick={() => setQuote(null)} disabled={busy}>{t('cancel')}</button></div>}
    {url && <audio src={url} controls aria-label={t('chatAudioReply')} />}
  </div>;
}
