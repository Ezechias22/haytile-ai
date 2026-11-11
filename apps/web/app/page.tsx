'use client';
import StripeBilling from './stripe-billing';
import {
  useState,
  useEffect,
  useCallback,
  useRef,
  type FormEvent,
  type CSSProperties,
} from 'react';
import {
  Home,
  MessageCircle,
  Image as ImageIcon,
  Music2,
  Clapperboard,
  Film,
  Mic2,
  PenLine,
  FolderHeart,
  Wallet,
  Settings,
  HelpCircle,
  ShieldCheck,
  Sparkles,
  ArrowUpRight,
  ArrowRight,
  Plus,
  Search,
  Menu,
  X,
  ChevronDown,
  Upload,
  Download,
  Trash2,
  Pencil,
  Play,
  Check,
  Copy,
  LoaderCircle,
  LogOut,
  Clock,
  AlertCircle,
  Globe2,
  Layers,
  AudioLines,
  FileText,
  CheckCircle2,
} from 'lucide-react';
import { dictionaries, languages } from './i18n';
import Storyboard from './storyboard';
import AdminPeople from './admin-people';
import CreationProgress from './creation-progress';
import HaytileChat from './chat';
import { suggestTitle } from '../../../packages/creation-titles';
type Studio = 'image' | 'music' | 'video' | 'minidrama' | 'voice' | 'text';
type Page = Studio | 'chat' | 'home' | 'library' | 'pricing' | 'settings' | 'help' | 'admin';
type User = {
  id: string;
  name: string;
  email: string;
  locale: string;
  role: string;
  balance: number;
  reserved: number;
};
type Asset = {
  id: string;
  title: string;
  mime: string;
  size: number;
  text: string | null;
  job_id: string | null;
  created_at: string;
};
type Job = {
  id: string;
  title: string;
  studio: Studio;
  prompt: string;
  params: { provider_message?: string; input_params: Record<string, unknown>; completed_scenes?: number; total_scenes?: number };
  status: string;
  progress: number;
  error: string | null;
  credits: number;
  created_at: string;
};
type Model = {
  studio: Studio;
  available: boolean;
  episode_available?: boolean;
  model_id: string | null;
  credits: number;
  reason: string | null;
  options?: { model_id: string; label: string; credits: number; available: boolean; episode_available?: boolean; pricing_url: string; unavailable_reason?: string | null }[];
};
const studios: Studio[] = ['image', 'music', 'video', 'minidrama', 'voice', 'text'];
const visibleStudios: Studio[] = studios.filter(s => s !== 'text');
const icons = {
  home: Home,
  chat: MessageCircle,
  image: ImageIcon,
  music: Music2,
  video: Clapperboard,
  minidrama: Film,
  voice: Mic2,
  text: PenLine,
  library: FolderHeart,
  pricing: Wallet,
  settings: Settings,
  help: HelpCircle,
  admin: ShieldCheck,
};
const colors: Record<Studio, string> = {
  image: '#a692ff',
  music: '#f9aa78',
  video: '#77b8ff',
  minidrama: '#ec8bc1',
  voice: '#7cdbc9',
  text: '#c8b581',
};
async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const r = await fetch('/api/v1' + path, {
    ...options,
    credentials: 'same-origin',
    headers: {
      ...(options.body instanceof FormData ? {} : { 'Content-Type': 'application/json' }),
      ...options.headers,
    },
  });
  const data = await r.json();
  if (!r.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'VALIDATION_ERROR');
  return data;
}
function Artwork({ kind }: { kind: Studio }) {
  return (
    <div className={'artwork art-' + kind} aria-hidden="true">
      {kind === 'image' ? (
        <>
          <div className="planet" />
          <div className="orbit" />
          <div className="mountain m1" />
          <div className="mountain m2" />
          <i className="star s1" />
          <i className="star s2" />
        </>
      ) : kind === 'music' ? (
        <>
          <div className="record">
            <div />
          </div>
          <div className="wave">
            {Array.from({ length: 19 }, (_, i) => (
              <i key={i} style={{ height: 10 + Math.sin(i * 1.4) ** 2 * 38 }} />
            ))}
          </div>
        </>
      ) : kind === 'video' ? (
        <>
          <div className="cinema-frame">
            <div className="cinema-sun" />
            <div className="cinema-hill" />
            <Play fill="currentColor" size={25} />
          </div>
          <div className="frame-line" />
        </>
      ) : kind === 'minidrama' ? (
        <>
          <div className="script-paper">
            <i />
            <i />
            <i />
            <i />
            <i />
            <i />
          </div>
          <div className="clap">
            <div />
            <Film size={35} />
          </div>
        </>
      ) : kind === 'voice' ? (
        <>
          <div className="voice-circle">
            <Mic2 size={38} strokeWidth={1.4} />
          </div>
          <div className="voice-wave">
            {Array.from({ length: 15 }, (_, i) => (
              <i key={i} style={{ height: 8 + Math.cos(i * 0.8) ** 2 * 38 }} />
            ))}
          </div>
        </>
      ) : (
        <>
          <div className="text-paper">
            <span>Aa</span>
            <i />
            <i />
            <i />
          </div>
          <div className="pen">
            <PenLine size={48} strokeWidth={1.5} />
          </div>
        </>
      )}
    </div>
  );
}
export default function App() {
  const [selectedModels, setSelectedModels] = useState<Record<string, string>>({});
  useEffect(() => {
    try {
      const saved = JSON.parse(localStorage.getItem('haytile-model-choices') || '{}');
      if (saved && typeof saved === 'object' && !Array.isArray(saved))
        setSelectedModels(Object.fromEntries(Object.entries(saved).filter(([, value]) => typeof value === 'string')) as Record<string, string>);
    } catch {}
  }, []);
  const [generationPaused, setGenerationPaused] = useState(false);
  const [imagesPaid, setImagesPaid] = useState(true);
  const [temporaryDatabase, setTemporaryDatabase] = useState(false);
  const [durableAccounts, setDurableAccounts] = useState(false);
  const [backgroundProcessing, setBackgroundProcessing] = useState(true);
  const [videoMaximum, setVideoMaximum] = useState(180);
  const [episodeMaximum, setEpisodeMaximum] = useState(180);
  const [miniMode, setMiniMode] = useState('episode');
  useEffect(() => {
    api<{
      free_beta: boolean;
      images_paid?: boolean;
      trial_ai: boolean;
      trial_max_video_seconds: number;
      trial_max_episode_seconds: number;
      provider_generation_disabled: boolean;
      generation_paused: boolean;
      temporary_database: boolean;
      account_store?: string;
      background_processing_enabled: boolean;
    }>('/runtime')
      .then((config) => {
        setGenerationPaused(config.generation_paused);
        setImagesPaid(config.images_paid === true);
        setTemporaryDatabase(config.temporary_database);
        setDurableAccounts(config.account_store === 'firestore');
        setBackgroundProcessing(config.background_processing_enabled !== false);
        setVideoMaximum(config.trial_max_video_seconds || 180);
        setEpisodeMaximum(config.trial_max_episode_seconds || 180);
      })
      .catch(() => {});
  }, []);
  const [page, setPage] = useState<Page>('chat'),
    [locale, setLocale] = useState('ht'),
    [chatConversation, setChatConversation] = useState(''),
    [chatEpoch, setChatEpoch] = useState(0),
    [chatThreads, setChatThreads] = useState<{ id: string; title: string }[]>([]),
    [user, setUser] = useState<User | null>(null),
    [assets, setAssets] = useState<Asset[]>([]),
    [jobs, setJobs] = useState<Job[]>([]),
    [models, setModels] = useState<Model[]>([]),
    [auth, setAuth] = useState<null | 'login' | 'register'>(null),
    [busy, setBusy] = useState(false),
    [toast, setToast] = useState(''),
    [error, setError] = useState(''),
    [menu, setMenu] = useState(false),
    [sidebarCollapsed, setSidebarCollapsed] = useState(false),
    [mobileNavigation, setMobileNavigation] = useState(false),
    [navigationPane, setNavigationPane] = useState<'chat' | 'tools'>('chat'),
    [deleteChat, setDeleteChat] = useState<{ id: string; title: string } | null>(null),
    [preview, setPreview] = useState<Asset | null>(null),
    [previewUrl, setPreviewUrl] = useState(''),
    [rename, setRename] = useState<Asset | null>(null),
    [renameJob, setRenameJob] = useState<Job | null>(null),
    [focusedJob, setFocusedJob] = useState<string | null>(null),
    [syncIssue, setSyncIssue] = useState(false),
    [lastSynced, setLastSynced] = useState<number | null>(null),
    [confirmDelete, setConfirmDelete] = useState<Asset | null>(null),
    [costConfirm, setCostConfirm] = useState(false),
    [search, setSearch] = useState(''),
    [filter, setFilter] = useState('all'),
    [title, setTitle] = useState(''),
    [prompt, setPrompt] = useState(''),
    [aspect, setAspect] = useState('1:1'),
    [duration, setDuration] = useState(8),
    [reference, setReference] = useState(''),
    [outputLanguage, setOutputLanguage] = useState('ht'),
    [voiceName, setVoiceName] = useState('Kore'),
    [voiceOptions, setVoiceOptions] = useState<string[]>([]),
    [voiceDetails, setVoiceDetails] = useState<{ name: string; gender: string }[]>([]),
    [voiceGender, setVoiceGender] = useState('all'),
    [vocalStyle, setVocalStyle] = useState('auto'),
    [dramaVideoModel, setDramaVideoModel] = useState(''),
    [generationQuote, setGenerationQuote] = useState<{ key: string; credits: number; clip_count: number; free: boolean; music_target_seconds?: number } | null>(null),
    [quotePending, setQuotePending] = useState(false),
    [quoteError, setQuoteError] = useState(false),
    [wallet, setWallet] = useState<{
      balance: number;
      reserved: number;
      transactions: { id: string; kind: string; amount: number; created_at: string }[];
    } | null>(null),
    [adminData, setAdminData] = useState<{
      durable_finances: boolean;
      credit_store?: string;
      users: number;
      jobs: number;
      failed: number;
      audit: { action: string; details: unknown; created_at: string }[];
    } | null>(null),
    [catalog, setCatalog] = useState<{ name: string; displayName: string }[]>([]),
    [adminStudio, setAdminStudio] = useState<Studio>('text'),
    [deleteAccount, setDeleteAccount] = useState(false),
    [forgot, setForgot] = useState(false),
    [resetToken, setResetToken] = useState('');
  const uploadRef = useRef<HTMLInputElement>(null),
    pendingKey = useRef<string | null>(null);
  const t = useCallback(
    (key: string) => dictionaries[locale]?.[key] || dictionaries.en[key] || key,
    [locale],
  );
  useEffect(()=>{const value=new URLSearchParams(window.location.search).get('billing');if(value==='return'||value==='cancel')setPage('pricing');},[]);

  const describeError = (e: unknown) => {
    const code = e instanceof Error ? e.message : 'ERROR';
    if (/AUTH_REQUIRED|SESSION_EXPIRED/.test(code)) {
      setAuth('login');
      return t('accountNeeded');
    }
    if (/DURABLE_JOB_BILLING_REQUIRED/.test(code)) return t('creditBillingPending');
    if (/CHAT_ATTACHMENT|CHAT_TOOLS_INVALID|CHAT_LOCATION_INVALID/.test(code)) return t('chatAttachmentError');
    if (/FILE_INVALID_OR_TOO_LARGE/.test(code)) return t('chatFileLimits');
    if (/CHAT_MESSAGE_PROCESSING/.test(code)) return t('chatThinking');
    if (/CHAT_STILL_PROCESSING/.test(code)) return t('chatProcessingDelete');
    if (/VOICE_SESSION_BUDGET_REACHED|VOICE_BUDGET_TOO_SMALL/.test(code)) return t('voiceBudgetReached');
    if (/VOICE_REPLY_TOO_LONG/.test(code)) return t('voiceReplyTooLong');
    if (/BILLING_REVIEW_REQUIRED/.test(code)) return t('stripeReview');
    if (/BILLING_NOT_CONFIGURED|STRIPE_SIGNATURE|STRIPE_MODE_MISMATCH/.test(code)) return t('stripeUnavailable');
    if (/STRIPE_PRICE_UNSUPPORTED|STRIPE_PRICE_TOO_LOW/.test(code)) return t('stripePriceRule');
    if (/SUBSCRIPTION_EXISTS|SUBSCRIPTION_PENDING/.test(code)) return t('stripeExisting');
    if (/BILLING_REVOKE_UNAVAILABLE/.test(code)) return t('stripeRevokeUnavailable');
    if (/STRIPE_REQUEST_FAILED|OFFER_UNAVAILABLE|STRIPE_PAYMENT_MISMATCH/.test(code)) return t('stripeFailed');
    if (/BILLING_ACCOUNT_DELETE_PENDING/.test(code)) return t('stripeDeletePending');
    if (/LIVE_VOICE_UNAVAILABLE/.test(code)) return t('liveVoiceUnavailable');
    if (/LIVE_CONNECTION_FAILED/.test(code)) return t('liveConnectionFailed');
    if (/LIVE_SESSION_LIMIT/.test(code)) return t('liveSessionLimit');
    if (/VOICE_SESSION_ENDED|VOICE_SESSION_SETTINGS_CHANGED/.test(code)) return t('voiceSessionEnded');
    if (/VOICE_INPUT_UNAVAILABLE/.test(code)) return t('voiceInputUnsupported');
    if (/LOGIN_INVALID/.test(code)) return t('authError');
    if (/AI_SERVICE_PAUSED|BACKGROUND_PROCESSING_PAUSED/.test(code)) return t('servicePausedBody');
    if (/WORKER_PREPARATION_FAILED/.test(code)) return t('workerPreparationFailed');
    if (/PROVIDER_CONTENT_REJECTED/.test(code)) return t('providerContentRejected');
    if (/PROVIDER_REQUEST_REJECTED|PROVIDER_HTTP_400/.test(code)) return t('providerRequestRejected');
    if (/MANUAL_RECONCILIATION_REQUIRED/.test(code)) return t('manualReconciliation');
    if (/NEW_REQUEST_CONFIRMATION_REQUIRED/.test(code)) return t('chatInterrupted');
    if (/PROVIDER_QUOTA_EXCEEDED/.test(code)) return t('providerQuota');
    if (/PROVIDER_ACCESS_DENIED|PROVIDER_MODEL_UNAVAILABLE/.test(code)) return t('providerAccess');
    if (/PROVIDER|ADAPTER|MODEL/.test(code)) return t('providerError');
    if (/APP_BURST_LIMIT/.test(code)) return t('appBurstLimit');
    if (/APP_CAPACITY_LIMIT/.test(code)) return t('appCapacityLimit');
    if (/LIMIT|TOO_MANY/.test(code)) return t('limitError');
    if (/INSUFFICIENT/.test(code)) return t('creditsError');
    return t('error') + ' (' + code + ')';
  };
  const run = async (fn: () => Promise<void>) => {
    setBusy(true);
    setError('');
    try {
      await fn();
    } catch (e) {
      setError(describeError(e));
    } finally {
      setBusy(false);
    }
  };
  const refresh = useCallback(async () => {
    const [a, j, w] = await Promise.all([
      api<Asset[]>('/assets'),
      api<Job[]>('/jobs'),
      api<NonNullable<typeof wallet>>('/wallet'),
    ]);
    setAssets(a);
    setJobs(j);
    setWallet(w);
  }, []);
  useEffect(() => {
    const reset = new URLSearchParams(window.location.search).get('reset');
    if (reset) {
      setResetToken(reset);
      history.replaceState(null, '', window.location.pathname);
    }
  }, []);
  useEffect(() => {
    const saved = localStorage.getItem('haytile-locale');
    const detected = navigator.language;
    setLocale(
      saved && languages[saved]
        ? saved
        : languages[detected]
          ? detected
          : languages[detected.split('-')[0]]
            ? detected.split('-')[0]
            : 'ht',
    );
    api<{ voices: string[]; voice_options?: { name: string; gender: string }[] }>('/voices').then(data => { setVoiceOptions(data.voices); setVoiceDetails(data.voice_options || []); }).catch(() => {});
    api<Model[]>('/models')
      .then(setModels)
      .catch(() => {});
    api<User>('/me')
      .then((u) => {
        setUser(u);
        setLocale(u.locale);
      })
      .catch(() => {});
  }, []);
  useEffect(() => {
    let alive = true;
    setChatThreads([]);
    setChatConversation(user ? localStorage.getItem('haytile-chat-' + user.id) || '' : '');
    if (!user) return;
    const load = () => api<{ id: string; title: string }[]>('/chat/conversations').then(rows => { if (alive) setChatThreads(rows); }).catch(() => {});
    load();
    window.addEventListener('focus', load);
    return () => { alive = false; window.removeEventListener('focus', load); };
  }, [user?.id]);
  useEffect(() => {
    document.documentElement.lang = locale;
    document.documentElement.dir = locale === 'ar' ? 'rtl' : 'ltr';
    localStorage.setItem('haytile-locale', locale);
  }, [locale]);
  useEffect(() => {
    if (!user) return;
    refresh().catch(() => {});
    const focused = () => refresh().catch(() => {});
    window.addEventListener('focus', focused);
    return () => window.removeEventListener('focus', focused);
  }, [user, refresh]);
  const hasActiveJobs = jobs.some(j => ['queued', 'processing', 'quality_check'].includes(j.status));
  useEffect(() => {
    if (!user || !backgroundProcessing || !hasActiveJobs) return;
    let cancelled = false, polling = false;
    const seenTerminal = new Set(jobs.filter(j => ['completed', 'failed'].includes(j.status)).map(j => j.id));
    const poll = async () => {
      if (polling || document.visibilityState !== 'visible') return;
      polling = true;
      try {
        const next = await api<Job[]>('/jobs');
        if (cancelled) return;
        setJobs(next); setLastSynced(Date.now()); setSyncIssue(false);
        const finished = next.filter(j => ['completed', 'failed'].includes(j.status) && !seenTerminal.has(j.id));
        finished.forEach(j => seenTerminal.add(j.id));
        if (finished.length) await refresh();
      } catch { if (!cancelled) setSyncIssue(true); }
      finally { polling = false; }
    };
    const id = setInterval(poll, 3000);
    return () => { cancelled = true; clearInterval(id); };
  }, [user?.id, hasActiveJobs, backgroundProcessing, refresh]);
  useEffect(() => {
    if (!toast) return;
    const id = setTimeout(() => setToast(''), 4500);
    return () => clearTimeout(id);
  }, [toast]);
  useEffect(() => {
    if (!preview) {
      setPreviewUrl('');
      return;
    }
    if (!preview.text)
      api<{ path: string; media_url?: string }>('/assets/' + preview.id + '/link')
        .then((x) => setPreviewUrl(x.media_url || '/api' + x.path))
        .catch(() => setError(t('error')));
  }, [preview, t]);
  useEffect(() => {
    if (page === 'admin' && user?.role === 'admin')
      api<NonNullable<typeof adminData>>('/admin/overview')
        .then(setAdminData)
        .catch(() => {});
  }, [page, user]);
  useEffect(() => {
    const query = window.matchMedia('(max-width: 850px)');
    const changed = () => setMobileNavigation(query.matches);
    changed(); query.addEventListener('change', changed);
    setSidebarCollapsed(localStorage.getItem('haytile-sidebar-collapsed') === '1');
    return () => query.removeEventListener('change', changed);
  }, []);
  const toggleSidebar = () => {
    if (window.matchMedia('(max-width: 850px)').matches) setMenu(value => !value);
    else setSidebarCollapsed(value => { localStorage.setItem('haytile-sidebar-collapsed', value ? '0' : '1'); return !value; });
  };
  const navigate = (p: Page) => {
    setPage(p === 'text' ? 'chat' : p);
    if (p === 'chat' || p === 'text') setNavigationPane('chat');
    else if (p !== 'home') setNavigationPane('tools');
    setMenu(false);
    setError('');
    setSearch('');
    setFilter('all');
  };
  const changeLanguage = (value: string) => {
    setLocale(value);
    if (user)
      api<User>('/me', {
        method: 'PATCH',
        body: JSON.stringify({ name: user.name, locale: value }),
      })
        .then(setUser)
        .catch(() => {});
  };
  const studio = visibleStudios.includes(page as Studio) ? (page as Studio) : null,
    studioModel = models.find((m) => m.studio === studio),
    modelOptions = studioModel?.options || (studioModel?.model_id ? [{ ...studioModel, model_id: studioModel.model_id, label: studioModel.model_id, pricing_url: 'https://ai.google.dev/gemini-api/docs/pricing' }] : []),
    activeChoice = modelOptions.find((option) => option.model_id === selectedModels[studio || '']) || modelOptions.find((option) => option.model_id === studioModel?.model_id) || modelOptions[0],
    activeModel = studioModel ? { ...studioModel, ...activeChoice } : undefined;
  const automaticTitle = suggestTitle(prompt, studio ? t(studio) : t('new'));
  const effectiveTitle = title.trim() || automaticTitle;
  const canGenerate =
    !!activeModel?.available &&
    (studio !== 'minidrama' || miniMode !== 'episode' || !!activeModel?.episode_available);
  const quoteParams = {
    aspect: studio === 'video' || (studio === 'minidrama' && miniMode === 'episode') ? aspect === '9:16' ? '9:16' : '16:9' : aspect,
    language: outputLanguage,
    ...(studio === 'voice' ? { voice_name: voiceName } : {}),
    ...(studio === 'music' ? { vocal_style: vocalStyle } : {}),
    ...(studio === 'video' || (studio === 'minidrama' && miniMode === 'episode') ? { duration } : {}),
    ...(studio === 'minidrama' ? { mode: miniMode, ...(dramaVideoModel ? { video_model_id: dramaVideoModel } : {}) } : {}),
    ...(reference ? { reference_asset_id: reference } : {}),
  };
  const quoteRequest = { studio, model_id: activeChoice?.model_id, prompt, params: quoteParams };
  const quoteKey = JSON.stringify(quoteRequest);
  const freeStudio = studio === 'text' || (studio === 'image' && !imagesPaid);
  const quoteReady = freeStudio || generationQuote?.key === quoteKey;
  const quoteCredits = freeStudio ? 0 : quoteReady ? generationQuote?.credits || 0 : activeModel?.credits || 0;
  const costLabel = freeStudio ? t('freeGeneration') : quotePending ? t('calculatingPrice') : generationQuote?.key === quoteKey ? generationQuote.credits ? generationQuote.credits + ' ' + t('credits') : t('freeGeneration') : activeModel?.credits ? t('priceFrom') + ' ' + activeModel.credits + ' ' + t('credits') : t('quoteRequired');
  useEffect(() => {
    if (!user || !studio || !prompt.trim() || !canGenerate || freeStudio) { setQuotePending(false); return; }
    let cancelled = false;
    setQuotePending(true); setQuoteError(false);
    const timer = setTimeout(() => {
      api<{ credits: number; clip_count: number; free: boolean; music_target_seconds?: number }>('/quotes', { method: 'POST', body: quoteKey })
        .then(data => { if (!cancelled) setGenerationQuote({ ...data, key: quoteKey }); })
        .catch(() => { if (!cancelled) setQuoteError(true); })
        .finally(() => { if (!cancelled) setQuotePending(false); });
    }, 600);
    return () => { cancelled = true; clearTimeout(timer); };
  }, [quoteKey, user?.id, canGenerate, freeStudio, studio]);
  const requireUser = () => {
    if (user) return true;
    setAuth('login');
    return false;
  };
  const saveDraft = () => {
    if (!requireUser()) return;
    run(async () => {
      await api('/assets/text', {
        method: 'POST',
        body: JSON.stringify({ title: effectiveTitle, text: prompt }),
      });
      setToast(t('saved'));
      await refresh();
    });
  };
  const generate = () => {
    if (!requireUser()) return;
    if (!quoteReady || quotePending || quoteError) return;
    setCostConfirm(true);
  };
  const submitGeneration = () =>
    run(async () => {
      if (!pendingKey.current) pendingKey.current = crypto.randomUUID();
      const created = await api<Job>('/jobs', {
        method: 'POST',
        body: JSON.stringify({
          studio,
          model_id: activeChoice?.model_id,
          title: effectiveTitle,
          prompt,
          idempotency_key: pendingKey.current,
          params: quoteParams,
          confirmed_credits: quoteCredits,
        }),
      });
      pendingKey.current = null;
      setCostConfirm(false);
      setJobs(previous => [created, ...previous.filter(j => j.id !== created.id)]);
      setFocusedJob(created.id); setLastSynced(Date.now()); setSyncIssue(false);
      navigate('library');
      window.scrollTo({ top: 0, behavior: 'smooth' });
      refresh().catch(() => setSyncIssue(true));
    });
  const upload = async (file: File) => {
    if (!requireUser()) return;
    await run(async () => {
      const body = new FormData();
      body.append('file', file);
      await api('/assets/upload', { method: 'POST', body });
      setToast(t('saved'));
      await refresh();
    });
  };
  const download = async (a: Asset) =>
    run(async () => {
      const { path, download_url } = await api<{ path: string; download_url?: string }>('/assets/' + a.id + '/link');
      if (download_url) {
        const link = document.createElement('a');
        link.href = download_url;
        link.rel = 'noreferrer';
        document.body.appendChild(link);
        link.click();
        link.remove();
        return;
      }
      const r = await fetch('/api' + path);
      if (!r.ok) throw new Error('DOWNLOAD_FAILED');
      const blob = await r.blob(),
        url = URL.createObjectURL(blob),
        link = document.createElement('a');
      link.href = url;
      const ext =
        a.mime === 'text/plain' ? 'txt' : a.mime === 'audio/mpeg' ? 'mp3' : a.mime.split('/')[1];
      link.download = a.title + '.' + ext;
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    });
  const sendTo = (a: Asset, p: Studio) => {
    setPrompt(a.text || '');
    setTitle(a.title);
    setPreview(null);
    navigate(p);
    pendingKey.current = null;
  };
  const visibleAssets = assets.filter(
    (a) =>
      !a.title.startsWith('[Reference] ') && !a.title.startsWith('[Scene] ') && a.title.toLowerCase().includes(search.toLowerCase()) &&
      (filter === 'all' || a.mime.startsWith(filter)),
  );
  const pending = jobs.filter((j) => !['completed', 'failed'].includes(j.status));
  const assetCard = (a: Asset) => (
    <article className="asset-card" key={a.id}>
      <button
        className="asset-preview"
        onClick={() => setPreview(a)}
        aria-label={t('preview') + ' ' + a.title}
      >
        {a.mime.startsWith('image/') ? (
          <AssetImage asset={a} />
        ) : a.mime.startsWith('audio/') ? (
          <AudioLines size={40} />
        ) : a.mime.startsWith('video/') ? (
          <Clapperboard size={40} />
        ) : (
          <div className="text-thumb">
            {a.text?.slice(0, 180)}
            <FileText size={20} />
          </div>
        )}
        <span className="preview-hover">
          <Play size={22} />
        </span>
      </button>
      <div className="asset-details">
        <h3>{a.title}</h3>
        <p>
          {a.mime.split('/')[0]} <span>·</span> {new Date(a.created_at).toLocaleDateString(locale)}
        </p>
        <div className="asset-actions">
          <button title={t('download')} onClick={() => download(a)}>
            <Download size={15} />
          </button>
          <button title={t('rename')} onClick={() => setRename(a)}>
            <Pencil size={15} />
          </button>
          <button title={t('delete')} onClick={() => setConfirmDelete(a)}>
            <Trash2 size={15} />
          </button>
        </div>
      </div>
    </article>
  );
  const modal = (heading: string, content: React.ReactNode, close: () => void) => (
    <div className="modal-backdrop" onClick={close}>
      <section
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-label={heading}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="modal-heading">
          <h2>{heading}</h2>
          <button onClick={close} aria-label={t('close')}>
            <X size={22} />
          </button>
        </div>
        {content}
      </section>
    </div>
  );
  return (
    <div className={'app-shell ' + (sidebarCollapsed ? 'sidebar-collapsed ' : '') + (page === 'chat' ? 'chat-page' : '')}>
      <input
        hidden
        ref={uploadRef}
        type="file"
        accept="image/png,image/jpeg,image/webp,audio/mpeg,audio/wav,audio/ogg,video/mp4,text/plain"
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) upload(f);
          e.target.value = '';
        }}
      />
      {menu && <div className="sidebar-scrim" onClick={() => setMenu(false)} />}
      <aside className={'sidebar ' + (menu ? 'is-open' : '')} aria-hidden={mobileNavigation ? !menu : sidebarCollapsed} inert={mobileNavigation ? !menu : sidebarCollapsed}>
        <button className="brand" onClick={() => navigate('home')}>
          <img src="/mark.png" alt="" width={35} height={35} />
          <span>
            HAYTILE<span className="ai-tag">AI</span>
          </span>
        </button>
        <div className="workspace-label">
          <div className="workspace-avatar">H</div>
          <div>
            Haytile Workspace<small>{t('ready')}</small>
          </div>
          <button className="sidebar-dismiss" onClick={toggleSidebar} aria-label={t('closeSidebar')}><X size={16}/></button>
        </div>
        <nav>
          <button
            className={'nav-item ' + (page === 'home' ? 'active' : '')}
            onClick={() => navigate('home')}
          >
            <Home size={18} />
            {t('home')}
          </button>
          <button className={'nav-item ' + (page === 'chat' ? 'active' : '')} onClick={() => navigate('chat')}><MessageCircle size={18} />HAYTILE Chat</button>
          <div className="sidebar-nav-tabs" role="tablist" aria-label={t('navigationSection')}><button role="tab" aria-selected={navigationPane === 'chat'} onClick={() => setNavigationPane('chat')}>{t('navChats')}</button><button role="tab" aria-selected={navigationPane === 'tools'} onClick={() => setNavigationPane('tools')}>{t('navTools')}</button></div>
          {navigationPane === 'chat' && <div className="sidebar-chat-pane">
          <button className="nav-item" onClick={() => { setChatConversation(''); setChatEpoch(value => value + 1); if (user) localStorage.removeItem('haytile-chat-' + user.id); navigate('chat'); }}><Plus size={18} />{t('newChat')}</button>
          {user && <section className="sidebar-chat-history" aria-label={t('chatHistory')}><p className="nav-label">{t('chatHistory')}</p>{chatThreads.map(thread => <div className="sidebar-chat-row" key={thread.id}><button className={'nav-item sidebar-chat-thread ' + (page === 'chat' && chatConversation === thread.id ? 'active' : '')} title={thread.title} onClick={() => { if (user) localStorage.setItem('haytile-chat-' + user.id, thread.id); setChatConversation(thread.id); navigate('chat'); }}><MessageCircle size={15}/><span>{thread.title}</span></button><button className="sidebar-delete-chat" onClick={() => { window.dispatchEvent(new Event('haytile-stop-voice')); setDeleteChat(thread); }} aria-label={t('deleteChat') + ' ' + thread.title}><Trash2 size={14}/></button></div>)}</section>}
          </div>}
          {navigationPane === 'tools' && <div className="sidebar-tools-pane">
          <p className="nav-label">{t('studios')}</p>
          {visibleStudios.map((s) => {
            const Icon = icons[s];
            return (
              <button
                key={s}
                className={'nav-item ' + (page === s ? 'active' : '')}
                onClick={() => navigate(s)}
              >
                <Icon size={18} style={{ color: colors[s] }} />
                {t(s)}
                {s === 'image' && !imagesPaid && <span className="tiny-badge">{t('freeGeneration')}</span>}
              </button>
            );
          })}
          <p className="nav-label">{t('account')}</p>
          {(['library', 'pricing'] as Page[]).map((p) => {
            const Icon = icons[p];
            return (
              <button
                key={p}
                className={'nav-item ' + (page === p ? 'active' : '')}
                onClick={() => navigate(p)}
              >
                <Icon size={18} />
                {t(p)}
              </button>
            );
          })}
          {user?.role === 'admin' && (
            <button
              className={'nav-item ' + (page === 'admin' ? 'active' : '')}
              onClick={() => navigate('admin')}
            >
              <ShieldCheck size={18} />
              {t('admin')}
            </button>
          )}
          {(['settings', 'help'] as Page[]).map((p) => {
            const Icon = icons[p];
            return (
              <button
                key={p}
                className={'nav-item ' + (page === p ? 'active' : '')}
                onClick={() => navigate(p)}
              >
                <Icon size={17} />
                {t(p)}
              </button>
            );
          })}
          </div>}
        </nav>
        <div className="sidebar-bottom">
          <div className="user-line">
            <span className="user-avatar">{user?.name[0]?.toUpperCase() || 'H'}</span>
            <div>
              <strong>{user?.name || 'Haytile Creator'}</strong>
              <small>{user ? user.email : t('welcome')}</small>
            </div>
            <button
              title={user ? t('signout') : t('signin')}
              onClick={() =>
                user
                  ? run(async () => {
                      await api('/auth/logout', { method: 'POST' });
                      setUser(null);
                      setAssets([]);
                      setJobs([]);
                      setWallet(null);
                      navigate('home');
                    })
                  : setAuth('login')
              }
            >
              {user ? <LogOut size={16} /> : <ArrowRight size={16} />}
            </button>
          </div>
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <div className="breadcrumb">
            <button className="sidebar-toggle" onClick={toggleSidebar} aria-label={t('toggleSidebar')} aria-expanded={mobileNavigation ? menu : !sidebarCollapsed}>
              <Menu size={21} />
            </button>
            <span>{t('workspace')}</span>
            <span className="slash">/</span>
            <strong>{t(page)}</strong>
          </div>
          <div className="topbar-actions">
            <label className="language-switch">
              <Globe2 size={15} />
              <select
                value={locale}
                onChange={(e) => changeLanguage(e.target.value)}
                aria-label={t('language')}
              >
                {Object.entries(languages).map(([key, value]) => (
                  <option key={key} value={key}>
                    {value}
                  </option>
                ))}
              </select>
            </label>
            {user ? (
              <button className="credit-pill" onClick={() => navigate('pricing')}>
                <Sparkles size={14} />
                {(wallet?.balance || 0) - (wallet?.reserved || 0)}
                <span>{t('credits')}</span>
              </button>
            ) : (
              <button className="button small" onClick={() => setAuth('login')}>
                {t('signin')}
                <ArrowUpRight size={14} />
              </button>
            )}
          </div>
        </header>
        <main>
          {generationPaused && (
            <section className="alert info" role="note">
              <AlertCircle size={20} />
              <div>
                <strong>{t('servicePausedTitle')}</strong>
                <p>{t('servicePausedBody')}</p>
              </div>
            </section>
          )}
          {error && (
            <div className="alert error" role="alert">
              <AlertCircle size={18} />
              <span>{error}</span>
              <button onClick={() => setError('')} aria-label={t('close')}>
                <X size={16} />
              </button>
            </div>
          )}
          {page === 'home' && (
            <>
              <section className="hero">
                <div className="hero-content">
                  <div className="hero-tag">
                    <span />
                    {t('heroTag')}
                  </div>
                  <h1>
                    {t('heroTitle')}
                    <br />
                    <em>{t('heroAccent')}</em>
                  </h1>
                  <p>{t('heroDescription')}</p>
                  <div className="hero-actions">
                    <button className="button primary" onClick={() => navigate('image')}>
                      <Sparkles size={17} />
                      {t('start')}
                      <ArrowUpRight size={17} />
                    </button>
                    <button className="text-button" onClick={() => navigate('library')}>
                      {t('explore')}
                      <ArrowRight size={16} />
                    </button>
                  </div>
                  <div className="hero-foot">
                    <span>
                      <Check size={13} />
                      {t('free')}
                    </span>
                    <i />
                    <span>Web · Android · iOS</span>
                  </div>
                </div>
                <div className="hero-visual" aria-hidden="true">
                  <div className="hero-orbit o1" />
                  <div className="hero-orbit o2" />
                  <div className="hero-orbit o3" />
                  <div className="glass-card glass-back">
                    <Music2 size={34} />
                    <div className="mini-wave">
                      {[10, 21, 15, 30, 19, 35, 16, 24, 12].map((v, i) => (
                        <i key={i} style={{ height: v }} />
                      ))}
                    </div>
                  </div>
                  <div className="glass-card glass-front">
                    <div className="dream-scape">
                      <div className="dream-sun" />
                      <div className="dream-mountain" />
                      <div className="dream-mountain mountain-front" />
                    </div>
                    <div className="glass-caption">
                      <Sparkles size={14} />
                      <span>Imagine. Create. Inspire.</span>
                      <span>✦</span>
                    </div>
                  </div>
                  <div className="floating-icon float-one">
                    <ImageIcon size={20} />
                  </div>
                  <div className="floating-icon float-two">
                    <Sparkles size={23} />
                  </div>
                  <div className="hero-star star-one">✦</div>
                  <div className="hero-star star-two">✧</div>
                </div>
              </section>
              <section className="studios-section">
                <div className="section-heading">
                  <div>
                    <h2>{t('choose')}</h2>
                    <p>{t('chooseDescription')}</p>
                  </div>
                  <span className="count-label">
                    {visibleStudios.length} STUDIOS <Layers size={14} />
                  </span>
                </div>
                <div className="studio-grid">
                  {visibleStudios.map((s, i) => {
                    const Icon = icons[s];
                    return (
                      <button
                        className="studio-card"
                        key={s}
                        style={{ '--studio-color': colors[s] } as CSSProperties}
                        onClick={() => navigate(s)}
                      >
                        <Artwork kind={s} />
                        <div className="studio-card-body">
                          <div className="studio-card-title">
                            <span className="studio-icon">
                              <Icon size={17} />
                            </span>
                            <h3>{t(s)}</h3>
                            {i === 0 && !imagesPaid ? (
                              <span className="free-badge">FREE</span>
                            ) : (
                              <ArrowUpRight size={17} className="card-arrow" />
                            )}
                          </div>
                          <p>{t(s + 'Desc')}</p>
                        </div>
                      </button>
                    );
                  })}
                </div>
              </section>
              <section className="creations-section">
                <div className="section-heading">
                  <div>
                    <h2>
                      {t('recent')}
                      <span className="heading-dot" />
                    </h2>
                    <p>{t('privacy')}</p>
                  </div>
                  <button className="text-button muted" onClick={() => navigate('library')}>
                    {t('viewAll')}
                    <ArrowRight size={15} />
                  </button>
                </div>
                {assets.length ? (
                  <div className="asset-grid">{assets.slice(0, 4).map(assetCard)}</div>
                ) : (
                  <div className="empty-state compact">
                    <div className="empty-icon">
                      <FolderHeart size={24} />
                    </div>
                    <h3>{t('empty')}</h3>
                    <p>{t('emptyDescription')}</p>
                    <button className="button" onClick={() => navigate('chat')}>
                      <Plus size={16} />
                      {t('new')}
                    </button>
                  </div>
                )}
              </section>
            </>
          )}
          {page === 'chat' && <HaytileChat onRequestStart={()=>setError('')} key={(user?.id || 'guest') + ':' + chatEpoch} conversation={chatConversation} setConversation={setChatConversation} onThread={thread => setChatThreads(rows => [thread, ...rows.filter(row => row.id !== thread.id)])} request={api} t={t} userId={user?.id} userName={user?.name} locale={locale} voiceOptions={voiceDetails} voiceModels={models.find(m => m.studio === 'voice')?.options || []} onWalletChange={() => refresh().catch(() => setSyncIssue(true))} models={models.find(m => m.studio === 'text')?.options || []} available={!generationPaused && backgroundProcessing && !!models.find(m => m.studio === 'text')?.available} onAuth={() => setAuth('login')} onError={err => setError(describeError(err))} />}
          {studio && (
            <>
              <div className="page-heading studio-heading">
                <div className="eyebrow">
                  <Sparkles size={14} />
                  {t('studios')}
                </div>
                <h1>{t(studio)}</h1>
                <p>{t(studio + 'Desc')}</p>
              </div>
              <div className="studio-workspace">
                <section className="panel composer">
                  <div className="panel-title">
                    <span style={{ color: colors[studio] }}>
                      {(() => {
                        const I = icons[studio];
                        return <I size={20} />;
                      })()}
                    </span>
                    <h2>{t('new')}</h2>
                    <span className="subtle-badge">
                      {studio === 'image' && !imagesPaid
                        ? t('freeGeneration')
                        : activeModel?.model_id || t('notConfigured')}
                    </span>
                  </div>
                  <form
                    onSubmit={(e) => {
                      e.preventDefault();
                      generate();
                    }}
                  >
                    <label>
                      {t('aiModel')}
                      <select
                        aria-label={t('aiModel')}
                        value={activeChoice?.model_id || ''}
                        disabled={!modelOptions.length}
                        onChange={(event) => {
                          const selected = { ...selectedModels, [studio]: event.target.value };
                          setSelectedModels(selected);
                          localStorage.setItem('haytile-model-choices', JSON.stringify(selected));
                          pendingKey.current = null;
                        }}
                      >
                        {!modelOptions.length && <option value="">{t('notConfigured')}</option>}
                        {modelOptions.map((option) => <option key={option.model_id} value={option.model_id} disabled={!!option.unavailable_reason}>{option.label}{option.unavailable_reason ? ' — ' + t('pricingPending') : studio === 'minidrama' ? '' : ' · ' + (option.credits ? option.credits + ' ' + t('credits') + (studio === 'video' ? ' / ' + t('pricingClip') : '') : t('freeGeneration'))}</option>)}
                      </select>
                    </label>
                    <p className="fine-print">{t('modelPricingNotice')} <a href={activeChoice?.pricing_url || 'https://ai.google.dev/gemini-api/docs/pricing'} target="_blank" rel="noreferrer">{t('providerPricing')}</a></p>
                    {studio === 'minidrama' && <p className="fine-print">{t('miniModelChoiceNote')}</p>}
                    {studio === 'video' && <p className="fine-print">{t('videoClipPricingNote')}</p>}
                    <label>
                      {t('title')}
                      <input
                        name="title"
                        aria-label={t('title')}
                        value={title || automaticTitle}
                        onChange={(e) => setTitle(e.target.value)}
                        placeholder={t('title')}
                        maxLength={120}
                      />
                      <span className="title-assist">{t('autoTitleHint')}<button type="button" className="text-button" onClick={() => setTitle('')}>{t('automaticTitle')}</button></span>
                    </label>
                    <label>
                      {t('prompt')}
                      <textarea
                        aria-label={t('prompt')}
                        name="prompt"
                        value={prompt}
                        onChange={(e) => {
                          setPrompt(e.target.value);
                          pendingKey.current = null;
                        }}
                        placeholder={t('promptHint')}
                        rows={9}
                        maxLength={12000}
                        required
                      />
                    </label>
                    {studio === 'minidrama' && miniMode === 'episode' && <label>{t('sceneVideoModel')}<select aria-label={t('sceneVideoModel')} value={dramaVideoModel || models.find(m => m.studio === 'video')?.model_id || ''} onChange={e => { setDramaVideoModel(e.target.value); pendingKey.current = null; }}>{(models.find(m => m.studio === 'video')?.options || []).map(option => <option key={option.model_id} value={option.model_id} disabled={!!option.unavailable_reason}>{option.label}{option.unavailable_reason ? ' — ' + t('pricingPending') : ''}</option>)}</select></label>}
                    {studio === 'voice' && <><div className="voice-filter" role="group" aria-label={t('voiceType')}>{[['all', 'allVoices'], ['male', 'maleVoices'], ['female', 'femaleVoices']].map(([gender, label]) => <button key={gender} type="button" aria-pressed={voiceGender === gender} onClick={() => { setVoiceGender(gender); const first = voiceDetails.find(v => gender === 'all' || v.gender === gender); if (first) setVoiceName(first.name); pendingKey.current = null; }}>{t(label)}</button>)}</div><label>{t('chooseVoice')}<select aria-label={t('chooseVoice')} value={voiceName} onChange={e => { setVoiceName(e.target.value); pendingKey.current = null; }}>{(voiceOptions.length ? voiceOptions : ['Kore']).filter(voice => voiceGender === 'all' || voiceDetails.some(v => v.name === voice && v.gender === voiceGender)).map(voice => { const gender = voiceDetails.find(v => v.name === voice)?.gender; return <option key={voice} value={voice}>{voice}{gender ? ' · ' + t(gender === 'male' ? 'maleVoiceLabel' : gender === 'female' ? 'femaleVoiceLabel' : 'otherVoices') : ''}</option>; })}</select></label></>}
                    {studio === 'music' && <label>{t('vocalStyle')}<select aria-label={t('vocalStyle')} value={vocalStyle} onChange={e => { setVocalStyle(e.target.value); pendingKey.current = null; }}>{[['auto','autoVocal'],['male','maleVocal'],['female','femaleVocal'],['duet','duetVocal'],['instrumental','instrumentalVocal']].map(([key,label]) => <option key={key} value={key}>{t(label)}</option>)}</select></label>}
                    <div className="field-row">
                      <label>
                        {t('language')}
                        <select
                          value={outputLanguage}
                          onChange={(e) => setOutputLanguage(e.target.value)}
                        >
                          {Object.entries(languages).map(([key, value]) => (
                            <option key={key} value={key}>
                              {value}
                            </option>
                          ))}
                        </select>
                      </label>
                      {(studio === 'image' ||
                        studio === 'video' ||
                        (studio === 'minidrama' && miniMode === 'episode')) && (
                        <label>
                          {t('aspect')}
                          <select
                            value={
                              studio === 'image' ? aspect : aspect === '9:16' ? '9:16' : '16:9'
                            }
                            onChange={(e) => setAspect(e.target.value)}
                          >
                            {(studio === 'image'
                              ? ['1:1', '16:9', '9:16', '4:3', '3:4']
                              : ['16:9', '9:16']
                            ).map((v) => (
                              <option key={v}>{v}</option>
                            ))}
                          </select>
                        </label>
                      )}
                    </div>
                    {studio === 'minidrama' && (
                      <label>
                        {t('outputFormat')}
                        <select
                          value={miniMode}
                          onChange={(e) => {
                            setMiniMode(e.target.value);
                            setDuration(
                              e.target.value === 'episode' ? Math.min(60, episodeMaximum) : 8,
                            );
                          }}
                        >
                          <option value="episode">{t('completeEpisode')}</option>
                          <option value="script">{t('scriptOutput')}</option>
                        </select>
                      </label>
                    )}
                    {studio === 'image' && (
                      <label>
                        {t('reference')}
                        <select value={reference} onChange={(e) => setReference(e.target.value)}>
                          <option value="">{t('none')}</option>
                          {assets
                            .filter((a) => a.mime.startsWith('image/'))
                            .map((a) => (
                              <option key={a.id} value={a.id}>
                                {a.title}
                              </option>
                            ))}
                        </select>
                      </label>
                    )}
                    {(studio === 'video' || (studio === 'minidrama' && miniMode === 'episode')) && (
                      <label>
                        {t('duration')}
                        <input
                          type="number"
                          min={8}
                          max={studio === 'minidrama' ? episodeMaximum : videoMaximum}
                          value={duration}
                          onChange={(e) => setDuration(Number(e.target.value))}
                        />
                      </label>
                    )}
                    {(studio === 'video' || (studio === 'minidrama' && miniMode === 'episode')) && <div className="duration-presets" role="group" aria-label={t('duration')}>{[30,60,120,180].filter(seconds => seconds <= (studio === 'minidrama' ? episodeMaximum : videoMaximum)).map(seconds => <button type="button" key={seconds} aria-pressed={duration === seconds} className={'button small ' + (duration === seconds ? 'selected' : '')} onClick={() => { setDuration(seconds); pendingKey.current = null; }}>{seconds < 60 ? seconds + ' s' : seconds / 60 + ' min'}</button>)}</div>}
                    {quoteError && <p className="alert error" role="alert">{t('quoteUnavailable')}</p>}
                    {!canGenerate && (
                      <div className="alert info">
                        <AlertCircle size={18} />
                        <span>{t(generationPaused ? 'servicePausedBody' : 'unavailable')}</span>
                      </div>
                    )}
                    {studio === 'minidrama' && (
                      <p className="fine-print">
                        {t(miniMode === 'episode' ? 'episodeReviewNote' : 'scriptOnly')}
                      </p>
                    )}
                    {studio === 'music' && generationQuote?.key === quoteKey && generationQuote.music_target_seconds && <p className="fine-print" role="status">{t('musicTargetDuration')}: {Math.floor(generationQuote.music_target_seconds / 60)} min {generationQuote.music_target_seconds % 60} s</p>}
                    {studio === 'music' && <p className="fine-print">{t('musicNote')}</p>}
                    {studio === 'voice' && <p className="fine-print">{t('voiceNote')}</p>}
                    {studio === 'video' && quoteReady && generationQuote?.key === quoteKey && <p className="fine-print" role="status">{generationQuote.clip_count} {t('plannedScenes')} · {t('totalPrice')}: {generationQuote.credits} {t('credits')}</p>}
                    <div className="composer-actions">
                      <button
                        type="button"
                        className="button"
                        disabled={busy || !prompt.trim()}
                        onClick={saveDraft}
                      >
                        <FileText size={16} />
                        {t('saveDraft')}
                      </button>
                      <button
                        type="submit"
                        className="button primary"
                        disabled={busy || !canGenerate || !prompt.trim() || (!!user && !freeStudio && (!quoteReady || quotePending || quoteError))}
                      >
                        <Sparkles size={16} />
                        {t('generate')}
                        <span className="button-price">{costLabel}</span>
                      </button>
                    </div>
                  </form>
                </section>
                <aside className="studio-side">
                  <div className="panel studio-inspiration">
                    <Artwork kind={studio} />
                    <h3>{t('mode')}</h3>
                    <p>{t('promptHint')}</p>
                    <div className="privacy-note">
                      <ShieldCheck size={16} />
                      {t('privacy')}
                    </div>
                  </div>
                  <div className="panel">
                    <div className="panel-title">
                      <Clock size={18} />
                      <h3>{t('jobs')}</h3>
                    </div>
                    <JobList
                      jobs={jobs.filter((j) => j.studio === studio).slice(0, 5)}
                      t={t}
                      rename={setRenameJob}
                      retry={(j) =>
                        run(async () => {
                          await api('/jobs/' + j.id + '/retry', { method: 'POST' });
                          await refresh();
                        })
                      }
                    />
                  </div>
                </aside>
              </div>
            </>
          )}
          {page === 'minidrama' && (
            <Storyboard
              t={t}
              authenticated={!!user}
              onAuth={() => setAuth('login')}
              assets={assets}
              videoCredits={models.find((m) => m.studio === 'video')?.credits || 0}
              videoAvailable={models.find((m) => m.studio === 'video')?.available || false}
              backgroundProcessing={backgroundProcessing}
              onQueued={id => { setFocusedJob(id); navigate('library'); refresh().catch(() => setSyncIssue(true)); }}
            />
          )}
          {page === 'library' && (
            <>
              <div className="page-heading heading-row library-heading">
                <div>
                  <div className="eyebrow">
                    <FolderHeart size={14} />
                    {t('account')}
                  </div>
                  <h1>{t('library')}</h1>
                  <p>{t('privacy')}</p>
                </div>
                <button
                  className="button primary"
                  onClick={() => requireUser() && uploadRef.current?.click()}
                  disabled={busy}
                >
                  <Upload size={16} />
                  {t('upload')}
                </button>
              </div>
              <div className="creation-overview" aria-label={t('library')}>
                <div><span>{t('inProgress')}</span><strong>{pending.length}</strong></div>
                <div><span>{t('completed')}</span><strong>{jobs.filter(j => j.status === 'completed').length}</strong></div>
                <div><span>{t('savedFiles')}</span><strong>{assets.length}</strong></div>
              </div>
              <CreationProgress jobs={jobs} assets={assets} focused={focusedJob} issue={syncIssue} synced={lastSynced} t={t} rename={job => setRenameJob(jobs.find(j => j.id === job.id) || null)} open={id => setPreview(assets.find(a => a.id === id) || null)} retry={job => run(async () => { const next = await api<Job>('/jobs/' + job.id + '/retry', { method: 'POST' }); setJobs(previous => previous.map(j => j.id === next.id ? next : j)); setFocusedJob(next.id); })} />
              <div className="collection-heading"><div><h2>{t('savedFiles')}</h2><p className="fine-print">{t('uploadHint')}</p></div></div>
              <div className="library-toolbar">
                <div className="filter-tabs">
                  {['all', 'image', 'audio', 'video', 'text'].map((f) => (
                    <button
                      key={f}
                      className={filter === f ? 'selected' : ''}
                      onClick={() => setFilter(f)}
                    >
                      {t(f === 'audio' ? 'music' : f === 'text' ? 'textFiles' : f)}
                    </button>
                  ))}
                </div>
                <label className="search-input">
                  <Search size={16} />
                  <input
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    placeholder={t('search')}
                  />
                </label>
              </div>
              {visibleAssets.length ? (
                <div className="asset-grid">{visibleAssets.map(assetCard)}</div>
              ) : pending.length ? (
                <p className="library-waiting">{t('resultsWillAppear')}</p>
              ) : (
                <div className="empty-state">
                  <FolderHeart size={34} />
                  <h2>{t('empty')}</h2>
                  <p>{t('emptyDescription')}</p>
                  <button className="button" onClick={() => navigate('chat')}>
                    <Plus size={16} />
                    {t('new')}
                  </button>
                </div>
              )}
              <div className="panel jobs-panel">
                <div className="panel-title">
                  <Clock size={19} />
                  <h2>{t('jobs')}</h2>
                  <span className="subtle-badge">{pending.length}</span>
                </div>
                <JobList
                  jobs={jobs}
                  t={t}
                  rename={setRenameJob}
                  retry={(j) =>
                    run(async () => {
                      await api('/jobs/' + j.id + '/retry', { method: 'POST' });
                      await refresh();
                    })
                  }
                />
              </div>
            </>
          )}
          {page === 'pricing' && (
            <>
              <div className="page-heading">
                <div className="eyebrow">
                  <Wallet size={14} />
                  {t('account')}
                </div>
                <h1>{t('pricing')}</h1>
                <p>{t('freeNote')}</p>
              </div>
              <div className="stats-grid">
                <div className="panel stat">
                  <span>{t('balance')}</span>
                  <strong>
                    {(wallet?.balance || 0) - (wallet?.reserved || 0)} <small>◈</small>
                  </strong>
                </div>
                <div className="panel stat">
                  <span>{t('reserved')}</span>
                  <strong>{wallet?.reserved || 0}</strong>
                </div>
                <div className="panel stat">
                  <span>{t('free')}</span>
                  <strong>
                    0 <small>{t('credits')}</small>
                  </strong>
                </div>
              </div>
              <div className="panel plan-panel">
                <div className="plan-icon">
                  <Sparkles size={27} />
                </div>
                <h2>{t('freePlan')}</h2>
                <p>{t('freePlanDescription')}</p>
                <button className="button primary" onClick={() => navigate('chat')}>
                  {t('start')}
                  <ArrowRight size={16} />
                </button>
              </div>
              <StripeBilling request={api} t={t} authenticated={!!user} onAuth={()=>setAuth('login')} onError={err=>setError(describeError(err))} onWalletChange={()=>refresh().catch(()=>setSyncIssue(true))}/>
              <section className="panel">
                <div className="panel-title">
                  <Clock size={18} />
                  <h2>{t('transactions')}</h2>
                </div>
                {wallet?.transactions.length ? (
                  <div className="transaction-list">
                    {wallet.transactions.map((tx) => (
                      <div key={tx.id}>
                        <span>{tx.kind === 'stripe_payment' ? t('stripePayment') : tx.kind === 'stripe_sandbox' ? t('stripeSandboxBalance') : tx.kind === 'stripe_risk_resolve' ? t('stripeAdjustment') : tx.kind}</span>
                        <span>{new Date(tx.created_at).toLocaleDateString(locale)}</span>
                        <strong>
                          {tx.amount > 0 ? '+' : ''}
                          {tx.amount}
                        </strong>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="muted">{t('noTransactions')}</p>
                )}
              </section>
            </>
          )}
          {page === 'settings' && (
            <>
              {temporaryDatabase && <p className="alert info" role="note">{t(durableAccounts ? 'durableAccountsNotice' : 'accountRetentionNotice')}</p>}
              <div className="page-heading">
                <h1>{t('settings')}</h1>
                <p>{t('privacy')}</p>
              </div>
              {!user ? (
                <button className="button primary" onClick={() => setAuth('login')}>
                  {t('signin')}
                </button>
              ) : (
                <div className="settings-grid">
                  {user.role !== 'admin' && <section className="panel">
                    <h2>{t('activateAdmin')}</h2><p>{t('activationHelp')}</p>
                    <form onSubmit={e => { e.preventDefault(); const code = new FormData(e.currentTarget).get('activationCode'); run(async () => { await api('/admin/activate', { method: 'POST', body: JSON.stringify({ code }) }); await refresh(); setUser(await api('/me')); setToast(t('saved')); }); }}>
                      <label>{t('activationCode')}<input name="activationCode" type="password" minLength={32} maxLength={200} autoComplete="off" required /></label>
                      <button className="button primary" disabled={busy}>{t('activateAdmin')}</button>
                    </form>
                  </section>}
                  <section className="panel">
                    <div className="panel-title">
                      <Settings size={18} />
                      <h2>{t('profile')}</h2>
                    </div>
                    <form
                      key={user.id}
                      onSubmit={(e) => {
                        e.preventDefault();
                        const form = new FormData(e.currentTarget);
                        run(async () => {
                          const u = await api<User>('/me', {
                            method: 'PATCH',
                            body: JSON.stringify({
                              name: form.get('name'),
                              locale: form.get('locale'),
                            }),
                          });
                          setUser(u);
                          setLocale(u.locale);
                          setToast(t('saved'));
                        });
                      }}
                    >
                      <label>
                        {t('name')}
                        <input name="name" defaultValue={user.name} required maxLength={80} />
                      </label>
                      <label>
                        {t('email')}
                        <input value={user.email} disabled />
                      </label>
                      <label>
                        {t('language')}
                        <select name="locale" defaultValue={locale}>
                          {Object.entries(languages).map(([key, value]) => (
                            <option key={key} value={key}>
                              {value}
                            </option>
                          ))}
                        </select>
                      </label>
                      <button className="button primary" disabled={busy}>
                        {t('save')}
                      </button>
                    </form>
                  </section>
                  <div>
                    <section className="panel">
                      <ShieldCheck size={25} />
                      <h2>{t('account')}</h2>
                      <p className="muted">{t('privacy')}</p>
                      <button
                        className="button"
                        onClick={() =>
                          run(async () => {
                            const data = await api('/me/export');
                            const url = URL.createObjectURL(
                              new Blob([JSON.stringify(data, null, 2)], {
                                type: 'application/json',
                              }),
                            );
                            const a = document.createElement('a');
                            a.href = url;
                            a.download = 'haytile-data.json';
                            a.click();
                            URL.revokeObjectURL(url);
                          })
                        }
                      >
                        <Download size={16} />
                        {t('export')}
                      </button>
                    </section>
                    <section className="panel danger-panel">
                      <h3>{t('deleteAccount')}</h3>
                      <p>{t('deleteWarning')}</p>
                      <button className="button danger" onClick={() => setDeleteAccount(true)}>
                        {t('deleteAccount')}
                      </button>
                    </section>
                  </div>
                </div>
              )}
            </>
          )}
          {page === 'help' && (
            <>
              <div className="page-heading">
                <div className="eyebrow">
                  <HelpCircle size={14} />
                  HAYTILE AI
                </div>
                <h1>{t('helpTitle')}</h1>
              </div>
              <div className="faq-list">
                {[1, 2, 3, 4, 5].map((i) => (
                  <details className="panel" key={i}>
                    <summary>
                      {t('faq' + i)}
                      <Plus size={18} />
                    </summary>
                    <p>{t('answer' + i)}</p>
                  </details>
                ))}
              </div>
            </>
          )}
          {page === 'admin' && user?.role === 'admin' && (
            <>
              <StripeBilling administration request={api} t={t} authenticated={!!user} onAuth={()=>setAuth('login')} onError={err=>setError(describeError(err))} onWalletChange={()=>refresh().catch(()=>setSyncIssue(true))}/>

              <div className="page-heading">
                <h1>{t('admin')}</h1>
              </div>
              <div className="stats-grid">
                {[
                  ['users', adminData?.users],
                  ['jobs', adminData?.jobs],
                  ['failed', adminData?.failed],
                ].map(([key, v]) => (
                  <div className="panel stat" key={key}>
                    <span>{t(String(key))}</span>
                    <strong>{v || 0}</strong>
                  </div>
                ))}
              </div>
              <div className="settings-grid">
                <section className="panel">
                  <h2>{t('studio')}</h2>
                  <button
                    className="button"
                    onClick={() => run(async () => setCatalog(await api('/admin/discover')))}
                    disabled={busy}
                  >
                    {t('discover')}
                  </button>
                  <form
                    onSubmit={(e) => {
                      e.preventDefault();
                      const f = new FormData(e.currentTarget);
                      run(async () => {
                        await api('/admin/models', {
                          method: 'PUT',
                          body: JSON.stringify({
                            studio: adminStudio,
                            model_id: f.get('model_id'),
                            credits: Number(f.get('credits')),
                            enabled: f.get('enabled') === 'on',
                            price_source: f.get('price_source'),
                            operator_billing_ack: f.get('ack') === 'on',
                          }),
                        });
                        setModels(await api('/models'));
                        setToast(t('saved'));
                      });
                    }}
                  >
                    <label>
                      {t('studio')}
                      <select
                        value={adminStudio}
                        onChange={(e) => setAdminStudio(e.target.value as Studio)}
                      >
                        {studios.map((s) => (
                          <option key={s} value={s}>
                            {t(s === 'text' ? 'chat' : s)}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label>
                      {t('modelId')}
                      <input
                        name="model_id"
                        list="account-models"
                        required
                        pattern="[A-Za-z0-9._-]+"
                      />
                      <datalist id="account-models">
                        {catalog.map((m) => (
                          <option key={m.name} value={m.name.replace('models/', '')}>
                            {m.displayName}
                          </option>
                        ))}
                      </datalist>
                    </label>
                    <label>
                      {t('credits')}
                      <input
                        name="credits"
                        type="number"
                        min={0}
                        max={100000}
                        defaultValue={0}
                        required
                      />
                    </label>
                    <label>
                      {t('priceSource')}
                      <input
                        name="price_source"
                        type="url"
                        defaultValue="https://ai.google.dev/gemini-api/docs/pricing"
                        required
                      />
                    </label>
                    <label className="checkbox">
                      <input name="enabled" type="checkbox" />
                      {t('enabled')}
                    </label>
                    <label className="checkbox">
                      <input name="ack" type="checkbox" />
                      {t('billingAck')}
                    </label>
                    <button className="button primary" disabled={busy}>
                      {t('save')}
                    </button>
                  </form>
                </section>
                <AdminPeople t={t} api={api} durable={adminData?.durable_finances === true} creditStore={adminData?.credit_store} onSaved={async () => { setAdminData(await api('/admin/overview')); await refresh(); }} />
                <section className="panel">
                  <h3 className="mt">{t('audit')}</h3>
                  {adminData?.audit.map((a, i) => (
                    <div className="audit-row" key={i}>
                      <strong>{a.action}</strong>
                      <small>{JSON.stringify(a.details)}</small>
                      <small>{new Date(a.created_at).toLocaleString(locale)}</small>
                    </div>
                  ))}
                </section>
              </div>
            </>
          )}
          <footer>
            <span>© {new Date().getFullYear()} HAYTILE AI</span>
            <span>
              {t('copyright')} <span className="footer-star">✦</span>
            </span>
            <button onClick={() => navigate('help')}>
              {t('help')}
              <ArrowUpRight size={12} />
            </button>
          </footer>
        </main>
      </div>
      {toast && (
        <div className="toast" role="status">
          <CheckCircle2 size={18} />
          {toast}
        </div>
      )}
      {busy && (
        <div className="busy-indicator" aria-label="Loading">
          <LoaderCircle className="spin" size={18} />
        </div>
      )}
      {auth &&
        modal(
          t(auth === 'login' ? 'signin' : 'signup'),
          <form
            onSubmit={(e) => {
              e.preventDefault();
              const f = new FormData(e.currentTarget);
              run(async () => {
                const data = await api<{ user: User }>(
                  '/auth/' + (auth === 'login' ? 'login' : 'register'),
                  {
                    method: 'POST',
                    body: JSON.stringify({
                      email: f.get('email'),
                      password: f.get('password'),
                      name: f.get('name'),
                      locale,
                    }),
                  },
                );
                setUser(data.user);
                setLocale(data.user.locale);
                setAuth(null);
                setToast(t('welcome'));
              });
            }}
          >
            <p className="muted">{t('loginDescription')}</p>
            {auth === 'register' && (
              <label>
                {t('name')}
                <input name="name" autoComplete="name" required maxLength={80} />
              </label>
            )}
            <label>
              {t('email')}
              <input name="email" type="email" autoComplete="email" required />
            </label>
            <label>
              {t('password')}
              <input
                name="password"
                type="password"
                minLength={auth === 'register' ? 12 : 1}
                maxLength={200}
                autoComplete={auth === 'login' ? 'current-password' : 'new-password'}
                required
                placeholder={auth === 'register' ? t('passwordHint') : ''}
              />
            </label>
            {error && (
              <p className="form-error" role="alert">
                {error}
              </p>
            )}
            <button className="button primary full" disabled={busy}>
              {t(auth === 'login' ? 'signin' : 'signup')}
              <ArrowRight size={17} />
            </button>
            {auth === 'login' && (
              <button
                className="text-button full center"
                type="button"
                onClick={() => {
                  setAuth(null);
                  setForgot(true);
                }}
              >
                {t('forgotPassword')}
              </button>
            )}
            <button
              className="text-button full center"
              type="button"
              onClick={() => {
                setAuth(auth === 'login' ? 'register' : 'login');
                setError('');
              }}
            >
              {t(auth === 'login' ? 'signup' : 'signin')}
            </button>
          </form>,
          () => {
            setAuth(null);
            setError('');
          },
        )}
      {forgot &&
        modal(
          t('forgotPassword'),
          <form
            onSubmit={(e) => {
              e.preventDefault();
              const f = new FormData(e.currentTarget);
              run(async () => {
                await api('/auth/password-reset', {
                  method: 'POST',
                  body: JSON.stringify({ email: f.get('email') }),
                });
                setForgot(false);
                setToast(t('resetSent'));
              });
            }}
          >
            <label>
              {t('email')}
              <input name="email" type="email" required />
            </label>
            {error && <p className="form-error">{error}</p>}
            <button className="button primary full" disabled={busy}>
              {t('confirm')}
            </button>
          </form>,
          () => setForgot(false),
        )}
      {resetToken &&
        modal(
          t('resetPassword'),
          <form
            onSubmit={(e) => {
              e.preventDefault();
              const f = new FormData(e.currentTarget);
              run(async () => {
                await api('/auth/password-reset/confirm', {
                  method: 'POST',
                  body: JSON.stringify({ token: resetToken, password: f.get('password') }),
                });
                setResetToken('');
                setUser(null);
                setAssets([]);
                setJobs([]);
                setAuth('login');
                setToast(t('saved'));
              });
            }}
          >
            <label>
              {t('password')}
              <input
                name="password"
                type="password"
                minLength={12}
                maxLength={200}
                autoComplete="new-password"
                required
              />
            </label>
            {error && <p className="form-error">{error}</p>}
            <button className="button primary full" disabled={busy}>
              {t('confirm')}
            </button>
          </form>,
          () => setResetToken(''),
        )}
      {preview &&
        modal(
          preview.title,
          <>
            <div className="preview-content">
              {preview.text ? (
                <pre>{preview.text}</pre>
              ) : previewUrl ? (
                preview.mime.startsWith('image/') ? (
                  <img src={previewUrl} alt={preview.title} />
                ) : preview.mime.startsWith('audio/') ? (
                  <audio src={previewUrl} controls />
                ) : (
                  <video src={previewUrl} controls />
                )
              ) : (
                <LoaderCircle className="spin" />
              )}
            </div>
            <div className="modal-actions">
              <button className="button" onClick={() => download(preview)}>
                <Download size={16} />
                {t('download')}
              </button>
              {preview.text && (
                <button
                  className="button"
                  onClick={() =>
                    run(async () => {
                      await navigator.clipboard.writeText(preview.text!);
                      setToast(t('copied'));
                    })
                  }
                >
                  <Copy size={16} />
                  {t('copy')}
                </button>
              )}
            </div>
            {preview.text && (
              <div className="handoff">
                <label>{t('sendTo')}</label>
                <div>
                  {visibleStudios.map((s) => (
                    <button className="button small" key={s} onClick={() => sendTo(preview, s)}>
                      {t(s)}
                      <ArrowUpRight size={13} />
                    </button>
                  ))}
                </div>
              </div>
            )}
          </>,
          () => setPreview(null),
        )}
      {deleteChat && modal(t('deleteChat'), <><p>{t('deleteChatWarning')}</p><p><strong>{deleteChat.title}</strong></p><div className="modal-actions"><button className="button" onClick={() => setDeleteChat(null)} disabled={busy}>{t('cancel')}</button><button className="button danger" disabled={busy} onClick={() => run(async () => { const id = deleteChat.id; await api('/chat/conversations/' + encodeURIComponent(id), { method: 'DELETE' }); setChatThreads(rows => rows.filter(row => row.id !== id)); if (chatConversation === id) { setChatConversation(''); setChatEpoch(value => value + 1); if (user) localStorage.removeItem('haytile-chat-' + user.id); } setDeleteChat(null); })}>{t('delete')}</button></div></>, () => setDeleteChat(null))}
      {renameJob && modal(t('rename'), <form onSubmit={e => { e.preventDefault(); const value = new FormData(e.currentTarget).get('title'); run(async () => { await api('/jobs/' + renameJob.id, { method: 'PATCH', body: JSON.stringify({ title: value }) }); setRenameJob(null); await refresh(); }); }}><input name="title" defaultValue={renameJob.title} maxLength={120} required aria-label={t('title')}/><button className="button primary full" disabled={busy}>{t('save')}</button></form>, () => setRenameJob(null))}
      {rename &&
        modal(
          t('rename'),
          <form
            onSubmit={(e) => {
              e.preventDefault();
              const f = new FormData(e.currentTarget);
              run(async () => {
                await api('/assets/' + rename.id, {
                  method: 'PATCH',
                  body: JSON.stringify({ title: f.get('title') }),
                });
                setRename(null);
                await refresh();
              });
            }}
          >
            <input
              name="title"
              defaultValue={rename.title}
              maxLength={120}
              required
              aria-label={t('title')}
            />
            <button className="button primary full" disabled={busy}>
              {t('save')}
            </button>
          </form>,
          () => setRename(null),
        )}
      {confirmDelete &&
        modal(
          t('delete'),
          <>
            <p>{t('deleteConfirm')}</p>
            <div className="modal-actions">
              <button className="button" onClick={() => setConfirmDelete(null)}>
                {t('cancel')}
              </button>
              <button
                className="button danger"
                disabled={busy}
                onClick={() =>
                  run(async () => {
                    await api('/assets/' + confirmDelete.id, { method: 'DELETE' });
                    setConfirmDelete(null);
                    setToast(t('deleteSuccess'));
                    await refresh();
                  })
                }
              >
                {t('delete')}
              </button>
            </div>
          </>,
          () => setConfirmDelete(null),
        )}
      {costConfirm &&
        modal(
          t('confirmCost'),
          <>
            <div className="cost-display">
              <Sparkles size={24} />
              <strong className="cost-label">{costLabel}</strong>
            </div>
            <p className="muted">{activeModel?.model_id}</p>
            {(studio === 'video' || (studio === 'minidrama' && miniMode === 'episode')) && <p>{duration} s · {generationQuote?.clip_count || Math.ceil(duration / 8)} {t('plannedScenes')}</p>}
            {quoteCredits > 0 && <p className="fine-print">{t('reservationNotice')}</p>}
            <p className="fine-print">{t('privacy')}</p>
            <p className="fine-print">{t('providerBillingNotice')}</p>
            <div className="modal-actions">
              <button className="button" onClick={() => setCostConfirm(false)}>
                {t('cancel')}
              </button>
              <button className="button primary" disabled={busy || !quoteReady || quotePending} onClick={submitGeneration}>
                {t('confirm')}
              </button>
            </div>
          </>,
          () => setCostConfirm(false),
        )}
      {deleteAccount &&
        modal(
          t('deleteAccount'),
          <form
            onSubmit={(e) => {
              e.preventDefault();
              const f = new FormData(e.currentTarget);
              run(async () => {
                await api('/me', {
                  method: 'DELETE',
                  body: JSON.stringify({ password: f.get('password') }),
                });
                setUser(null);
                setAssets([]);
                setJobs([]);
                setWallet(null);
                setDeleteAccount(false);
                navigate('home');
              });
            }}
          >
            <p>{t('deleteWarning')}</p>
            <input
              name="password"
              type="password"
              autoComplete="current-password"
              required
              aria-label={t('password')}
            />
            <button className="button danger full" disabled={busy}>
              {t('deleteAccount')}
            </button>
          </form>,
          () => setDeleteAccount(false),
        )}
    </div>
  );
}
function AssetImage({ asset }: { asset: Asset }) {
  const [url, setUrl] = useState('');
  useEffect(() => {
    let live = true;
    api<{ path: string; media_url?: string }>('/assets/' + asset.id + '/link')
      .then((x) => {
        if (live) setUrl(x.media_url || '/api' + x.path);
      })
      .catch(() => {});
    return () => {
      live = false;
    };
  }, [asset.id]);
  return url ? <img src={url} alt={asset.title} loading="lazy" /> : <ImageIcon size={32} />;
}
function JobList({
  jobs,
  t,
  retry,
  rename,
}: {
  jobs: Job[];
  t: (key: string) => string;
  retry: (j: Job) => void;
  rename?: (j: Job) => void;
}) {
  return jobs.length ? (
    <div className="job-list">
      {jobs.map((j) => (
        <div className="job-row" key={j.id}>
          <div className="job-title">
            <strong>{j.title}</strong>
            {rename && <button className="icon-button" aria-label={t('rename') + ' ' + j.title} onClick={() => rename(j)}><Pencil size={14}/></button>}
            <span className={'status status-' + j.status}>{t(j.status)}</span>
          </div>
          {!['failed', 'completed'].includes(j.status) && (
            <div className="progress-track">
              <i style={{ width: j.progress + '%' }} />
            </div>
          )}
          {j.error && (
            <p className="job-error">
              {j.error === 'PROVIDER_QUOTA_EXCEEDED'
                ? t('providerQuota')
                : j.error === 'PROVIDER_ACCESS_DENIED' || j.error === 'PROVIDER_MODEL_UNAVAILABLE'
                  ? t('providerAccess')
                  : j.error === 'PROVIDER_CONTENT_REJECTED' ? t('providerContentRejected') : j.error === 'PROVIDER_REQUEST_REJECTED' || j.error === 'PROVIDER_HTTP_400' ? t('providerRequestRejected') : j.error}
            </p>
          )}
          {j.params.provider_message && <details className="job-error"><summary>{t('failureDetails')}</summary><p>{j.params.provider_message}</p></details>}
          {j.status === 'failed' && j.error !== 'PROVIDER_CONTENT_REJECTED' && (
            <button className="text-button" onClick={() => retry(j)}>
              {t('retry')}
              <ArrowRight size={13} />
            </button>
          )}
        </div>
      ))}
    </div>
  ) : (
    <p className="muted fine-print">{t('noJobs')}</p>
  );
}
