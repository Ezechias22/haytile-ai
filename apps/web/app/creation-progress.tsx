'use client';
import { useEffect, useState } from 'react';
import {
  AudioLines,
  CheckCircle2,
  Clapperboard,
  Clock,
  Image,
  LoaderCircle,
  Pencil,
  ArrowUpRight,
  AlertCircle,
} from 'lucide-react';
type Job = {
  id: string;
  title: string;
  studio: string;
  status: string;
  progress: number;
  credits: number;
  created_at: string;
  error: string | null;
  params?: { completed_scenes?: number; total_scenes?: number };
};
type Props = {
  jobs: Job[];
  assets: { id: string; job_id: string | null }[];
  focused: string | null;
  issue: boolean;
  synced: number | null;
  t: (key: string) => string;
  rename: (job: Job) => void;
  open: (id: string) => void;
  retry: (job: Job) => void;
};
export default function CreationProgress({
  jobs,
  assets,
  focused,
  issue,
  synced,
  t,
  rename,
  open,
  retry,
}: Props) {
  const [now, setNow] = useState(Date.now());
  const active = jobs.filter((j) => !['completed', 'failed'].includes(j.status));
  const featured = jobs.find((j) => j.id === focused) || jobs[0];
  const shown = [
    ...active,
    ...(featured && !active.some((j) => j.id === featured.id) ? [featured] : []),
  ];
  useEffect(() => {
    if (!active.length) return;
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, [active.length]);
  if (!shown.length) return null;
  return (
    <section className="creation-live" aria-label={t('generationActivity')}>
      <p className="sr-only" aria-live="polite">
        {shown.map((j) => j.title + ' · ' + t(j.status)).join('; ')}
      </p>
      <div className="creation-live-heading">
        <div>
          <span className={'live-dot ' + (issue ? 'offline' : '')} />
          <strong>
            {t(issue ? 'syncInterrupted' : active.length ? 'liveUpdates' : 'completed')}
          </strong>
          <p>{t('stageUpdatesNote')}</p>
        </div>
        {synced && (
          <small>
            {t('lastSynced')} {new Date(synced).toLocaleTimeString()}
          </small>
        )}
      </div>
      {shown.map((job) => {
        const running = !['completed', 'failed'].includes(job.status);
        const Icon = ['music', 'voice'].includes(job.studio)
          ? AudioLines
          : ['video', 'minidrama', 'assembly'].includes(job.studio)
            ? Clapperboard
            : Image;
        const asset = assets.find((a) => a.job_id === job.id);
        const seconds = Math.max(0, Math.floor((now - Date.parse(job.created_at)) / 1000));
        const stage = ['queued', 'processing', 'quality_check', 'completed'].indexOf(job.status);
        return (
          <article
            key={job.id}
            className={
              'creation-task ' +
              (job.id === focused ? 'is-focused ' : '') +
              (job.status === 'failed' ? 'has-failed' : '')
            }
            data-job-id={job.id}
          >
            <div className={'creation-task-art studio-' + job.studio} aria-hidden="true">
              <Icon size={32} />
              {running && (
                <div className="creation-pulse">
                  {[1, 2, 3, 4, 5].map((i) => (
                    <i key={i} style={{ animationDelay: `${i * 0.15}s` }} />
                  ))}
                </div>
              )}
            </div>
            <div className="creation-task-content">
              <div className="creation-task-top">
                <span className="creation-kind">{t(job.studio)}</span>
                <span className={'status status-' + job.status}>{t(job.status)}</span>
              </div>
              <div className="creation-task-title">
                <h2>{job.title}</h2>
                <button
                  className="icon-button"
                  aria-label={t('rename') + ' ' + job.title}
                  onClick={() => rename(job)}
                >
                  <Pencil size={16} />
                </button>
              </div>
              <div className="creation-task-meta">
                {job.params?.total_scenes && (
                  <span>
                    {job.params.completed_scenes || 0} / {job.params.total_scenes}{' '}
                    {t('plannedScenes')}
                  </span>
                )}
                <span>
                  {['image', 'text'].includes(job.studio)
                    ? t('freeGeneration')
                    : job.credits > 0
                      ? job.credits +
                        ' ' +
                        t('credits') +
                        ' · ' +
                        t(
                          job.status === 'completed'
                            ? 'debited'
                            : job.status === 'failed'
                              ? 'released'
                              : 'reserved',
                        )
                      : t('noHaytileDebit')}
                </span>
                {running && (
                  <span>
                    <Clock size={13} /> {Math.floor(seconds / 60)}:
                    {String(seconds % 60).padStart(2, '0')}
                  </span>
                )}
              </div>
              {running && (
                <>
                  <div
                    className="progress-track creation-progress"
                    role="progressbar"
                    aria-label={job.title}
                    aria-valuemin={0}
                    aria-valuemax={100}
                    aria-valuenow={job.progress}
                    aria-valuetext={t(job.status)}
                  >
                    <i style={{ width: `${job.progress}%` }} />
                  </div>
                  <ol className="creation-stages">
                    {['queued', 'processing', 'quality_check', 'completed'].map((s, i) => (
                      <li key={s} className={i < stage ? 'passed' : i === stage ? 'current' : ''}>
                        {i < stage ? (
                          <CheckCircle2 size={13} />
                        ) : i === stage ? (
                          <LoaderCircle size={13} className="spin" />
                        ) : (
                          <span className="stage-dot" />
                        )}
                        {t(s)}
                      </li>
                    ))}
                  </ol>
                </>
              )}
              {job.status === 'completed' && (
                <div className="creation-result">
                  <CheckCircle2 size={17} />
                  <span>{t(asset ? 'resultReady' : 'resultUnavailable')}</span>
                  {asset && (
                    <button className="button primary small" onClick={() => open(asset.id)}>
                      {t('preview')}
                      <ArrowUpRight size={15} />
                    </button>
                  )}
                </div>
              )}
              {job.status === 'failed' && (
                <div className="creation-failure">
                  <AlertCircle size={17} />
                  <span>
                    {t(
                      job.error === 'PROVIDER_QUOTA_EXCEEDED'
                        ? 'providerQuota'
                        : 'generationFailed',
                    )}
                  </span>
                  <button className="button small" onClick={() => retry(job)}>
                    {t('retry')}
                  </button>
                </div>
              )}
            </div>
          </article>
        );
      })}
    </section>
  );
}
