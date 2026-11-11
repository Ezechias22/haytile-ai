'use client';
import {useEffect, useRef, useState} from 'react';
import {Check, Copy, X} from 'lucide-react';

/** No network request. Keep a manual selection path when browser clipboard APIs are denied. */
async function writeClipboard(text: string) {
  try {
    if (navigator.clipboard?.writeText) { await navigator.clipboard.writeText(text); return true; }
  } catch { /* Older browsers and denied permissions can still support user-initiated copying. */ }
  const previous = document.activeElement as HTMLElement | null;
  const selection = window.getSelection();
  const ranges = selection ? Array.from({length: selection.rangeCount}, (_, i) => selection.getRangeAt(i).cloneRange()) : [];
  const field = document.createElement('textarea');
  field.value = text; field.readOnly = true;
  Object.assign(field.style, {position:'fixed', top:'0', left:'0', opacity:'0', fontSize:'16px'});
  document.body.appendChild(field);
  let success = false;
  try { field.focus({preventScroll:true}); field.select(); field.setSelectionRange(0, text.length); success = document.execCommand('copy'); }
  catch { success = false; }
  finally {
    field.remove(); previous?.focus({preventScroll:true});
    if (selection) { selection.removeAllRanges(); ranges.forEach(range => selection.addRange(range)); }
  }
  return success;
}

export default function ChatCopyButton({text, t, label}: {text:string; t:(key:string)=>string; label?:string}) {
  const [copied,setCopied] = useState(false), [busy,setBusy] = useState(false), [manual,setManual] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const dialog = useRef<HTMLDialogElement>(null);
  const field = useRef<HTMLTextAreaElement>(null);
  useEffect(() => () => { if(timer.current) clearTimeout(timer.current); }, []);
  useEffect(() => {
    if (manual) { dialog.current?.showModal(); field.current?.focus(); field.current?.select(); }
    else dialog.current?.close();
  }, [manual]);
  async function copy() {
    setCopied(false); setBusy(true);
    try {
      if (await writeClipboard(text)) {
        setCopied(true); if(timer.current) clearTimeout(timer.current);
        timer.current = setTimeout(() => setCopied(false), 2000);
      } else setManual(true);
    } finally { setBusy(false); }
  }
  return <>
    <button type="button" className="chat-copy-button" aria-label={label || t('copy')} disabled={busy} onClick={copy} title={label || t('copy')}>
      {copied ? <Check size={15}/> : <Copy size={15}/>}<span aria-live="polite">{copied ? t('copied') : label || t('copy')}</span>
    </button>
    <dialog className="chat-copy-dialog" ref={dialog} onCancel={() => setManual(false)} onClick={event => {if(event.target===dialog.current)setManual(false);}} aria-label={t('chatCopyManualTitle')}>
      <header><strong>{t('chatCopyManualTitle')}</strong><button type="button" aria-label={t('close')} onClick={() => setManual(false)}><X size={18}/></button></header>
      <p>{t('chatCopyManualHelp')}</p>
      <textarea ref={field} readOnly value={text} aria-label={t('chatCopyContent')} onFocus={event => event.currentTarget.select()}/>
    </dialog>
  </>;
}
