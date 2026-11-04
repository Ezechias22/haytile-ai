'use client';
import { useCallback, useEffect, useRef, useState } from 'react';
type Offer = {
  id: string;
  label: string;
  credits: number;
  plan: string;
  unit_amount: number;
  currency: string;
  mode: string;
  interval: string;
  price_id?: string;
  enabled?: number;
  livemode?: number;
};
type Catalog = {
  available: boolean;
  has_customer: boolean;
  test_mode: boolean;
  sandbox_balance?: number;
  offers: Offer[];
};
type Risk = { id: string; user_id: string; kind: string; livemode: number };
type Status = {
  key_configured: boolean;
  webhook_configured: boolean;
  durable: boolean;
  live: boolean;
  ready: boolean;
  sandbox_balance: number;
  offers: Offer[];
  risks: Risk[];
};
type Props = {
  request: <T>(path: string, options?: RequestInit) => Promise<T>;
  t: (key: string) => string;
  authenticated: boolean;
  onAuth: () => void;
  onError: (error: unknown) => void;
  onWalletChange: () => void;
  administration?: boolean;
};
export default function StripeBilling({
  request,
  t,
  authenticated,
  onAuth,
  onError,
  onWalletChange,
  administration = false,
}: Props) {
  const [catalog, setCatalog] = useState<Catalog | null>(null),
    [status, setStatus] = useState<Status | null>(null),
    [busy, setBusy] = useState(false),
    [loading, setLoading] = useState(true),
    [returned, setReturned] = useState(false),
    [verified, setVerified] = useState(false);
  const keys = useRef(new Map<string, string>()),
    refreshWallet = useRef(onWalletChange);
  refreshWallet.current = onWalletChange;
  const load = useCallback(async () => {
    if (!authenticated) {
      setLoading(false);
      return;
    }
    setLoading(true);
    try {
      if (administration) setStatus(await request<Status>('/admin/billing'));
      else setCatalog(await request<Catalog>('/billing/catalog'));
    } catch (error) {
      onError(error);
    } finally {
      setLoading(false);
    }
  }, [authenticated, administration, request]);
  useEffect(() => {
    void load();
  }, [load]);
  useEffect(() => {
    if (administration || !authenticated) return;
    const query = new URLSearchParams(location.search),
      pid = query.get('purchase_id');
    if (query.get('billing') !== 'return') return;
    refreshWallet.current();
    if (!pid || !/^[a-f0-9]{64}$/.test(pid)) return;
    setReturned(true);
    let alive = true,
      ticks = 0;
    let timer: ReturnType<typeof setInterval>;
    const poll = async () => {
      try {
        const receipt = await request<{ status: string }>('/billing/purchases/' + pid);
        if (!alive) return;
        if (receipt.status === 'paid') {
          setVerified(true);
          refreshWallet.current();
          void load();
          if (timer) clearInterval(timer);
        } else if (++ticks >= 10 && timer) clearInterval(timer);
      } catch {
        if (timer) clearInterval(timer);
      }
    };
    timer = setInterval(() => {
      refreshWallet.current();
      void load();
      void poll();
    }, 3000);
    void poll();
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, [authenticated, administration, request, load]);

  async function checkout(offer: Offer) {
    if (!authenticated) {
      onAuth();
      return;
    }
    setBusy(true);
    try {
      const key = keys.current.get(offer.id) || crypto.randomUUID();
      keys.current.set(offer.id, key);
      const result = await request<{ url: string }>('/billing/checkout', {
        method: 'POST',
        body: JSON.stringify({ offer_id: offer.id, idempotency_key: key }),
      });
      location.assign(result.url);
    } catch (error) {
      onError(error);
      setBusy(false);
    }
  }
  async function portal() {
    setBusy(true);
    try {
      const result = await request<{ url: string }>('/billing/portal', { method: 'POST' });
      location.assign(result.url);
    } catch (error) {
      onError(error);
      setBusy(false);
    }
  }
  async function save(form: HTMLFormElement) {
    const f = new FormData(form);
    setBusy(true);
    try {
      await request('/admin/billing/offers', {
        method: 'POST',
        body: JSON.stringify({
          id: f.get('id'),
          price_id: f.get('price_id'),
          credits: Number(f.get('credits')),
          plan: f.get('plan'),
          enabled: f.get('enabled') === 'on',
        }),
      });
      await load();
      form.reset();
    } catch (error) {
      onError(error);
    } finally {
      setBusy(false);
    }
  }
  async function resolve(id: string, form: HTMLFormElement) {
    const f = new FormData(form);
    setBusy(true);
    try {
      await request('/admin/billing/risks/' + id + '/resolve', {
        method: 'POST',
        body: JSON.stringify({ revoke_credits: Number(f.get('revoke')), reason: f.get('reason') }),
      });
      await load();
      refreshWallet.current();
    } catch (error) {
      onError(error);
    } finally {
      setBusy(false);
    }
  }
  const price = (offer: Offer) =>
    new Intl.NumberFormat(undefined, {
      style: 'currency',
      currency: offer.currency.toUpperCase(),
    }).format(offer.unit_amount / 100);
  if (!authenticated)
    return (
      <section className="panel">
        <h2>Stripe</h2>
        <p>{t('stripeLogin')}</p>
        <button className="button primary" onClick={onAuth}>
          {t('signin')}
        </button>
      </section>
    );
  if (loading && !catalog && !status)
    return (
      <section className="panel" role="status">
        {t('loading')}
      </section>
    );
  if (administration)
    return (
      <section className="panel stripe-admin">
        <h2>{t('stripeAdmin')}</h2>
        <p>{t('stripeSetup')}</p>
        {status && (
          <>
            <p>
              STRIPE_SECRET_KEY: {status.key_configured ? '✓' : '—'} · STRIPE_WEBHOOK_SECRET:{' '}
              {status.webhook_configured ? '✓' : '—'} · Firebase: {status.durable ? '✓' : '—'}
            </p>
            <p>{t(status.live ? 'stripeLive' : 'stripeSandbox')}</p>
            {!status.live && (
              <p>
                {t('stripeSandboxBalance')}: {status.sandbox_balance} {t('credits')}
              </p>
            )}
          </>
        )}
        <form
          className="stripe-offer-form"
          onSubmit={(event) => {
            event.preventDefault();
            void save(event.currentTarget);
          }}
        >
          <label>
            {t('stripeOfferId')}
            <input name="id" required pattern={'[a-z0-9\\-]{3,60}'} maxLength={60} />
          </label>
          <label>
            Stripe Price ID
            <input
              name="price_id"
              required
              pattern="price_[a-zA-Z0-9]{5,70}"
              placeholder="price_…"
            />
          </label>
          <label>
            {t('credits')}
            <input type="number" name="credits" required min={100} max={1000000} />
          </label>
          <label>
            {t('plan')}
            <select name="plan">
              <option value="free">Free · {t('stripeCreditPack')}</option>
              <option value="creator">Creator</option>
              <option value="pro">Pro</option>
            </select>
          </label>
          <label className="checkbox">
            <input type="checkbox" name="enabled" defaultChecked />
            {t('stripeOfferEnabled')}
          </label>
          <button className="button primary" disabled={busy || !status?.key_configured}>
            {t('save')}
          </button>
        </form>
        <div className="stripe-offers">
          {status?.offers.map((offer) => (
            <article key={offer.id}>
              <strong>{offer.label}</strong>
              <p>
                {offer.id} · {price(offer)} · {offer.credits} {t('credits')} · {offer.plan} ·{' '}
                {offer.enabled ? '✓' : '—'}
              </p>
            </article>
          ))}
        </div>
        {!!status?.risks.length && (
          <>
            <h3>{t('stripeReview')}</h3>
            {status.risks.map((risk) => (
              <form
                key={risk.id}
                className="stripe-risk"
                onSubmit={(e) => {
                  e.preventDefault();
                  void resolve(risk.id, e.currentTarget);
                }}
              >
                <p>
                  {risk.user_id} · {risk.kind} · {t(risk.livemode ? 'stripeLive' : 'stripeSandbox')}
                </p>
                <label>
                  {t('stripeRevoke')}
                  <input
                    type="number"
                    name="revoke"
                    min={0}
                    max={1000000}
                    defaultValue={0}
                    required
                  />
                </label>
                <label>
                  {t('reason')}
                  <input name="reason" minLength={5} maxLength={500} required />
                </label>
                <p>{t('stripeRiskNote')}</p>
                <button className="button secondary" disabled={busy}>
                  {t('stripeResolve')}
                </button>
              </form>
            ))}
          </>
        )}
      </section>
    );
  return (
    <section className="panel stripe-payments">
      <div className="panel-title">
        <h2>{t('stripeTitle')}</h2>
        {catalog?.available && catalog.has_customer && (
          <button className="button secondary" onClick={portal} disabled={busy}>
            {t('stripePortal')}
          </button>
        )}
      </div>
      {returned && <p role="status">{t(verified ? 'stripeVerified' : 'stripePending')}</p>}
      {catalog?.available ? (
        <>
          {catalog.test_mode && (
            <p className="alert info">
              {t('stripeSandbox')} · {t('stripeSandboxBalance')}: {catalog.sandbox_balance || 0}{' '}
              {t('credits')}
            </p>
          )}
          <p>{t('stripeCheckoutNotice')}</p>
          <div className="stripe-offers">
            {catalog.offers.map((offer) => (
              <article key={offer.id}>
                <h3>{offer.label}</h3>
                <strong>{price(offer)}</strong>
                <p>
                  {offer.credits} {t('credits')} ·{' '}
                  {offer.mode === 'subscription'
                    ? t(offer.interval === 'year' ? 'stripeYear' : 'stripeMonth')
                    : t('stripeCreditPack')}
                </p>
                <button className="button primary" disabled={busy} onClick={() => checkout(offer)}>
                  {t(offer.mode === 'subscription' ? 'stripeSubscribe' : 'stripeBuy')}
                </button>
              </article>
            ))}
          </div>
          {!catalog.offers.length && <p>{t('plansNotice')}</p>}
        </>
      ) : (
        <p>{t('plansNotice')}</p>
      )}
    </section>
  );
}
