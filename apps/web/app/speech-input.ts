'use client';
import { useCallback, useEffect, useRef, useState } from 'react';

type Recognition = {
  lang: string; continuous: boolean; interimResults: boolean;
  onresult: ((event: { results: ArrayLike<ArrayLike<{ transcript: string }>> }) => void) | null;
  onerror: ((event?: { error?: string }) => void) | null; onend: (() => void) | null;
  start: () => void; stop: () => void; abort: () => void;
};
type Constructor = new () => Recognition;
export function useSpeechInput(locale: string, onText: (text: string) => void, onError: (code?: string) => void) {
  const [supported, setSupported] = useState(false);
  const [listening, setListening] = useState(false);
  const current = useRef<Recognition | null>(null);
  const textCallback = useRef(onText), errorCallback = useRef(onError);
  textCallback.current = onText; errorCallback.current = onError;
  const stop = useCallback(() => {
    const recognizer = current.current; current.current = null;
    setListening(false);
    if (recognizer) { recognizer.onend = null; recognizer.onerror = null; recognizer.onresult = null; recognizer.abort(); }
  }, []);
  useEffect(() => {
    const browser = window as unknown as { SpeechRecognition?: Constructor; webkitSpeechRecognition?: Constructor };
    setSupported(!!(browser.SpeechRecognition || browser.webkitSpeechRecognition));
    return () => { const recognizer = current.current; current.current = null; if (recognizer) { recognizer.onend = null; recognizer.onerror = null; recognizer.onresult = null; recognizer.abort(); } };
  }, []);
  const start = useCallback(() => {
    if (current.current) return;
    const browser = window as unknown as { SpeechRecognition?: Constructor; webkitSpeechRecognition?: Constructor };
    const Factory = browser.SpeechRecognition || browser.webkitSpeechRecognition;
    if (!Factory) { errorCallback.current('unsupported'); return; }
    const recognizer = new Factory();
    recognizer.lang = ({ ht: 'ht-HT', en: 'en-US', fr: 'fr-FR', 'pt-BR': 'pt-BR', es: 'es-ES', ar: 'ar-SA', 'zh-Hans': 'zh-CN', id: 'id-ID', sw: 'sw-KE' } as Record<string, string>)[locale] || locale;
    recognizer.continuous = false; recognizer.interimResults = false;
    recognizer.onresult = event => { if (current.current !== recognizer) return; const text = Array.from(event.results).map(result => result[0]?.transcript || '').join(' ').trim(); if (text) textCallback.current(text); };
    recognizer.onerror = event => { if (current.current !== recognizer) return; current.current = null; setListening(false); if (event?.error !== 'no-speech' && event?.error !== 'aborted') errorCallback.current(event?.error); };
    recognizer.onend = () => { if (current.current === recognizer) { current.current = null; setListening(false); } };
    current.current = recognizer;
    try { recognizer.start(); setListening(true); } catch { current.current = null; setListening(false); errorCallback.current('start-failed'); }
  }, [locale]);
  const toggle = useCallback(() => { if (current.current) stop(); else start(); }, [start, stop]);
  return { supported, listening, toggle, start, stop };
}
