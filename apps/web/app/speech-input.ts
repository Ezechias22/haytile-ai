'use client';
import { useEffect, useRef, useState } from 'react';

type Recognition = {
  lang: string; continuous: boolean; interimResults: boolean;
  onresult: ((event: { results: ArrayLike<ArrayLike<{ transcript: string }>> }) => void) | null;
  onerror: (() => void) | null; onend: (() => void) | null;
  start: () => void; stop: () => void; abort: () => void;
};
type Constructor = new () => Recognition;
export function useSpeechInput(locale: string, onText: (text: string) => void, onError: () => void) {
  const [supported, setSupported] = useState(false);
  const [listening, setListening] = useState(false);
  const current = useRef<Recognition | null>(null);
  useEffect(() => {
    const browser = window as unknown as { SpeechRecognition?: Constructor; webkitSpeechRecognition?: Constructor };
    setSupported(!!(browser.SpeechRecognition || browser.webkitSpeechRecognition));
    return () => { if (current.current) { current.current.onend = null; current.current.onerror = null; current.current.onresult = null; current.current.abort(); } };
  }, []);
  const toggle = () => {
    if (listening) { current.current?.stop(); return; }
    const browser = window as unknown as { SpeechRecognition?: Constructor; webkitSpeechRecognition?: Constructor };
    const Factory = browser.SpeechRecognition || browser.webkitSpeechRecognition;
    if (!Factory) return;
    const recognizer = new Factory();
    recognizer.lang = ({ ht: 'ht-HT', en: 'en-US', fr: 'fr-FR', 'pt-BR': 'pt-BR', es: 'es-ES', ar: 'ar-SA', 'zh-Hans': 'zh-CN', id: 'id-ID', sw: 'sw-KE' } as Record<string, string>)[locale] || locale;
    recognizer.continuous = false; recognizer.interimResults = false;
    recognizer.onresult = event => { const text = Array.from(event.results).map(result => result[0]?.transcript || '').join(' ').trim(); if (text) onText(text); };
    recognizer.onerror = () => { setListening(false); onError(); };
    recognizer.onend = () => { setListening(false); current.current = null; };
    current.current = recognizer;
    try { recognizer.start(); setListening(true); } catch { setListening(false); onError(); }
  };
  return { supported, listening, toggle };
}
