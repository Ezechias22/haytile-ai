'use client';
import { useEffect, useRef, useState } from 'react';

type Person = {
  id: string;
  email: string;
  name: string;
  role: string;
  balance: number | null;
  reserved: number | null;
  plan: string;
  plan_expires_at: string | null;
};
type Props = {
  t: (key: string) => string;
  api: <T>(path: string, options?: RequestInit) => Promise<T>;
  durable: boolean;
  creditStore?: string;
  onSaved: () => Promise<void>;
};
export default function AdminPeople({ t, api, durable, creditStore, onSaved }: Props) {
  const [people, setPeople] = useState<Person[]>([]),
    [search, setSearch] = useState(''),
    [offset, setOffset] = useState(0),
    [total, setTotal] = useState(0);
  const [selected, setSelected] = useState(''),
    [error, setError] = useState(''),
    [busy, setBusy] = useState(false),
    [message, setMessage] = useState(''),
    [version, setVersion] = useState(0);
  const pending = useRef<{ signature: string; key: string } | null>(null);
  useEffect(() => {
    let cancelled = false;
    api<{ users: Person[]; total: number }>(
      '/admin/users?search=' + encodeURIComponent(search) + '&offset=' + offset,
    )
      .then((data) => {
        if (!cancelled) {
          setPeople(data.users);
          setTotal(data.total);
        }
      })
      .catch(() => {
        if (!cancelled) setError(t('error'));
      });
    return () => {
      cancelled = true;
    };
  }, [api, search, offset, version, t]);
  async function submit(event: React.FormEvent<HTMLFormElement>, kind: 'credits' | 'plans') {
    event.preventDefault();
    setBusy(true);
    setError('');
    setMessage('');
    const form = new FormData(event.currentTarget);
    const payload =
      kind === 'credits'
        ? { email: selected, amount: Number(form.get('amount')) }
        : {
            email: selected,
            plan: form.get('plan'),
            days: Number(form.get('days')),
            credits: Number(form.get('credits')),
            reason: form.get('reason'),
          };
    const signature = JSON.stringify({ kind, ...payload });
    if (pending.current?.signature !== signature)
      pending.current = { signature, key: crypto.randomUUID() };
    try {
      await api('/admin/' + kind, {
        method: 'POST',
        body: JSON.stringify({ ...payload, idempotency_key: pending.current.key }),
      });
      setMessage(t('saved'));
      setVersion((x) => x + 1);
      await onSaved();
      pending.current = null;
    } catch {
      setError(t('error'));
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="panel">
      <h2>{t('managePeople')}</h2>
      {creditStore === 'firestore' && <p role="status">{t('walletReady')}</p>}
      {!durable && (
        <p role="status" className="notice">
          {t('adminPersistence')}
        </p>
      )}
      <label>
        {t('adminSearch')}
        <input
          type="search"
          value={search}
          onChange={(e) => {
            setSearch(e.target.value);
            setOffset(0);
          }}
        />
      </label>
      <p>
        {total} {t('users')}
      </p>
      <div style={{ overflowX: 'auto' }}>
        <table>
          <thead>
            <tr>
              <th>{t('email')}</th>
              <th>{t('balance')}</th>
              <th>{t('plan')}</th>
              <th>{t('role')}</th>
            </tr>
          </thead>
          <tbody>
            {people.map((person) => (
              <tr key={person.id}>
                <td>
                  <button
                    className="button"
                    onClick={() => {
                      setSelected(person.email);
                      setMessage('');
                    }}
                  >
                    {person.email}
                  </button>
                  <small>{person.name}</small>
                </td>
                <td>
                  {person.balance ?? '—'} ({person.reserved ?? '—'} {t('reserved')})
                </td>
                <td>
                  {person.plan}
                  {person.plan_expires_at && (
                    <small>{new Date(person.plan_expires_at).toLocaleDateString()}</small>
                  )}
                </td>
                <td>{person.role}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="actions">
        <button
          className="button"
          disabled={offset === 0}
          onClick={() => setOffset((x) => Math.max(0, x - 25))}
        >
          {t('previous')}
        </button>
        <button
          className="button"
          disabled={offset + 25 >= total}
          onClick={() => setOffset((x) => x + 25)}
        >
          {t('next')}
        </button>
      </div>
      <label>
        {t('email')}
        <input type="email" value={selected} onChange={(e) => setSelected(e.target.value)} />
      </label>
      <form onSubmit={(e) => void submit(e, 'credits')}>
        <h3>{t('grant')}</h3>
        <label>
          {t('amount')}
          <input name="amount" type="number" min="1" max="100000" required />
        </label>
        <button className="button primary" disabled={!durable || busy || !selected}>
          {t('grant')}
        </button>
      </form>
      <form onSubmit={(e) => void submit(e, 'plans')}>
        <h3>{t('assignPlan')}</h3>
        <p>{t('manualPlanNote')}</p>
        <label>
          {t('plan')}
          <select name="plan" aria-label={t('plan')}>
            <option value="free">Free</option>
            <option value="creator">Creator</option>
            <option value="pro">Pro</option>
          </select>
        </label>
        <label>
          {t('planDays')}
          <input name="days" type="number" min="1" max="366" defaultValue="30" required />
        </label>
        <label>
          {t('planCredits')}
          <input name="credits" type="number" min="0" max="100000" defaultValue="0" required />
        </label>
        <label>
          {t('reason')}
          <textarea name="reason" minLength={3} maxLength={500} required />
        </label>
        <button className="button primary" disabled={!durable || busy || !selected}>
          {t('assignPlan')}
        </button>
      </form>
      {error && <p role="alert">{error}</p>}
      {message && <p role="status">{message}</p>}
    </section>
  );
}
