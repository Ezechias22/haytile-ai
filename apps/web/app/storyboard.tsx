'use client';
import { useState, useEffect } from 'react';
import {
  Plus,
  Film,
  Save,
  RefreshCw,
  Trash2,
  ArrowUp,
  ArrowDown,
  Users,
  Clapperboard,
} from 'lucide-react';
type Character = {
  id: string;
  name: string;
  appearance: string;
  wardrobe: string;
  voice: string;
  language: string;
  reference_asset_id: string | null;
};
type Scene = {
  id: string;
  title: string;
  description: string;
  dialogue: string;
  duration: number;
  character_ids: string[];
  asset_id: string | null;
};
type Document = {
  premise: string;
  continuity: string;
  aspect: '16:9' | '9:16';
  characters: Character[];
  scenes: Scene[];
};
type Project = { id: string; title: string; version: number; document: Document };
type Asset = { id: string; title: string; mime: string };
async function request<T>(path: string, method = 'GET', body?: unknown): Promise<T> {
  const r = await fetch('/api/v1' + path, {
    method,
    headers: { 'Content-Type': 'application/json' },
    ...(body ? { body: JSON.stringify(body) } : {}),
  });
  const data = await r.json();
  if (!r.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'REQUEST_FAILED');
  return data;
}
export default function Storyboard({
  t,
  authenticated,
  onAuth,
  assets,
  videoCredits,
  videoAvailable,
  backgroundProcessing = true,
}: {
  t: (s: string) => string;
  authenticated: boolean;
  onAuth: () => void;
  assets: Asset[];
  videoCredits: number;
  videoAvailable: boolean;
  backgroundProcessing?: boolean;
}) {
  const [projects, setProjects] = useState<Project[]>([]),
    [current, setCurrent] = useState<Project | null>(null),
    [busy, setBusy] = useState(false),
    [message, setMessage] = useState(''),
    [dirty, setDirty] = useState(false);
  const load = async () => setProjects(await request<Project[]>('/projects'));
  useEffect(() => {
    if (authenticated) load().catch(() => {});
  }, [authenticated]);
  const act = async (fn: () => Promise<void>) => {
    setBusy(true);
    setMessage('');
    try {
      await fn();
    } catch (e) {
      setMessage(t('error') + ' (' + (e as Error).message + ')');
    } finally {
      setBusy(false);
    }
  };
  const change = (document: Document) => {
    if (current) {
      setCurrent({ ...current, document });
      setDirty(true);
    }
  };
  const newProject = () => {
    if (!authenticated) {
      onAuth();
      return;
    }
    act(async () => {
      const project = await request<Project>('/projects', 'POST', {
        title: t('newProject'),
        document: { premise: '', continuity: '', aspect: '16:9', characters: [], scenes: [] },
      });
      setCurrent(project);
      setDirty(false);
      await load();
    });
  };
  const save = () =>
    act(async () => {
      if (!current) return;
      const project = await request<Project>('/projects/' + current.id, 'PUT', current);
      setCurrent(project);
      setDirty(false);
      setMessage(t('saved'));
      await load();
    });
  const reload = () =>
    act(async () => {
      const all = await request<Project[]>('/projects');
      setProjects(all);
      if (current) setCurrent(all.find((p) => p.id === current.id) || null);
      setDirty(false);
    });
  const updateScene = (id: string, patch: Partial<Scene>) => {
    if (current)
      change({
        ...current.document,
        scenes: current.document.scenes.map((s) => (s.id === id ? { ...s, ...patch } : s)),
      });
  };
  const updateCharacter = (id: string, patch: Partial<Character>) => {
    if (current)
      change({
        ...current.document,
        characters: current.document.characters.map((c) => (c.id === id ? { ...c, ...patch } : c)),
      });
  };
  const move = (index: number, delta: number) => {
    if (!current) return;
    const scenes = [...current.document.scenes];
    const target = index + delta;
    if (target < 0 || target >= scenes.length) return;
    [scenes[index], scenes[target]] = [scenes[target], scenes[index]];
    change({ ...current.document, scenes });
  };
  const selectProject = (id: string) => {
    if (dirty && !window.confirm(t('discardChanges'))) return;
    setCurrent(projects.find((p) => p.id === id) || null);
    setDirty(false);
  };
  return (
    <section className="panel storyboard">
      <div className="panel-title">
        <Film size={20} />
        <h2>{t('storyboard')}</h2>
        <button className="button small" onClick={newProject} disabled={busy}>
          <Plus size={14} />
          {t('newProject')}
        </button>
      </div>
      <p className="fine-print">{t('storyboardNote')}</p>
      {message && (
        <p className="alert info" role="status">
          {message}
        </p>
      )}
      {authenticated && (
        <label>
          {t('project')}
          <select value={current?.id || ''} onChange={(e) => selectProject(e.target.value)}>
            <option value="">{t('none')}</option>
            {projects.map((p) => (
              <option key={p.id} value={p.id}>
                {p.title}
              </option>
            ))}
          </select>
        </label>
      )}
      {current && (
        <>
          <div className="field-row">
            <label>
              {t('title')}
              <input
                value={current.title}
                onChange={(e) => {
                  setCurrent({ ...current, title: e.target.value });
                  setDirty(true);
                }}
                maxLength={120}
              />
            </label>
            <label>
              {t('aspect')}
              <select
                value={current.document.aspect}
                onChange={(e) =>
                  change({ ...current.document, aspect: e.target.value as '16:9' | '9:16' })
                }
              >
                <option>16:9</option>
                <option>9:16</option>
              </select>
            </label>
          </div>
          <label>
            {t('premise')}
            <textarea
              aria-label={t('premise')}
              value={current.document.premise}
              onChange={(e) => change({ ...current.document, premise: e.target.value })}
              maxLength={4000}
            />
          </label>
          <label>
            {t('continuity')}
            <textarea
              aria-label={t('continuity')}
              value={current.document.continuity}
              onChange={(e) => change({ ...current.document, continuity: e.target.value })}
              maxLength={4000}
            />
          </label>
          <div className="section-heading">
            <h3>{t('characters')}</h3>
            <button
              className="button small"
              disabled={current.document.characters.length >= 20}
              onClick={() =>
                change({
                  ...current.document,
                  characters: [
                    ...current.document.characters,
                    {
                      id: crypto.randomUUID(),
                      name: t('character'),
                      appearance: '',
                      wardrobe: '',
                      voice: '',
                      language: 'ht',
                      reference_asset_id: null,
                    },
                  ],
                })
              }
            >
              <Users size={14} />
              {t('addCharacter')}
            </button>
          </div>
          <div className="storyboard-characters">
            {current.document.characters.map((c) => (
              <div key={c.id} className="storyboard-block">
                <label>
                  {t('name')}
                  <input
                    value={c.name}
                    onChange={(e) => updateCharacter(c.id, { name: e.target.value })}
                    maxLength={80}
                  />
                </label>
                <label>
                  {t('appearance')}
                  <textarea
                    aria-label={t('appearance')}
                    value={c.appearance}
                    onChange={(e) => updateCharacter(c.id, { appearance: e.target.value })}
                    maxLength={1000}
                  />
                </label>
                <label>
                  {t('wardrobe')}
                  <input
                    value={c.wardrobe}
                    onChange={(e) => updateCharacter(c.id, { wardrobe: e.target.value })}
                    maxLength={1000}
                  />
                </label>
                <label>
                  {t('voiceProfile')}
                  <input
                    value={c.voice}
                    onChange={(e) => updateCharacter(c.id, { voice: e.target.value })}
                    maxLength={500}
                  />
                </label>
                <label>
                  {t('reference')}
                  <select
                    value={c.reference_asset_id || ''}
                    onChange={(e) =>
                      updateCharacter(c.id, { reference_asset_id: e.target.value || null })
                    }
                  >
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
                <button
                  className="text-button"
                  onClick={() =>
                    change({
                      ...current.document,
                      characters: current.document.characters.filter((x) => x.id !== c.id),
                      scenes: current.document.scenes.map((s) => ({
                        ...s,
                        character_ids: s.character_ids.filter((id) => id !== c.id),
                      })),
                    })
                  }
                >
                  <Trash2 size={14} />
                  {t('delete')}
                </button>
              </div>
            ))}
          </div>
          <div className="section-heading">
            <h3>
              {t('scenes')} · {current.document.scenes.reduce((a, s) => a + s.duration, 0)}s / 180s
            </h3>
            <button
              className="button small"
              disabled={current.document.scenes.length >= 22}
              onClick={() =>
                change({
                  ...current.document,
                  scenes: [
                    ...current.document.scenes,
                    {
                      id: crypto.randomUUID(),
                      title: t('scene') + ' ' + (current.document.scenes.length + 1),
                      description: '',
                      dialogue: '',
                      duration: 8,
                      character_ids: [],
                      asset_id: null,
                    },
                  ],
                })
              }
            >
              <Plus size={14} />
              {t('addScene')}
            </button>
          </div>
          {current.document.scenes.map((scene, index) => (
            <div className="storyboard-block" key={scene.id}>
              <div className="scene-toolbar">
                <strong>
                  {index + 1}. {scene.title}
                </strong>
                <button onClick={() => move(index, -1)} disabled={index === 0} title={t('moveUp')}>
                  <ArrowUp size={17} />
                </button>
                <button
                  onClick={() => move(index, 1)}
                  disabled={index === current.document.scenes.length - 1}
                  title={t('moveDown')}
                >
                  <ArrowDown size={17} />
                </button>
                <button
                  onClick={() =>
                    change({
                      ...current.document,
                      scenes: current.document.scenes.filter((s) => s.id !== scene.id),
                    })
                  }
                  title={t('delete')}
                >
                  <Trash2 size={17} />
                </button>
              </div>
              <div className="field-row">
                <label>
                  {t('title')}
                  <input
                    value={scene.title}
                    onChange={(e) => updateScene(scene.id, { title: e.target.value })}
                    maxLength={120}
                  />
                </label>
                <label>
                  {t('duration')}
                  <input
                    type="number"
                    min={1}
                    max={10}
                    value={scene.duration}
                    onChange={(e) => updateScene(scene.id, { duration: Number(e.target.value) })}
                  />
                </label>
              </div>
              <label>
                {t('sceneDescription')}
                <textarea
                  aria-label={t('sceneDescription')}
                  value={scene.description}
                  onChange={(e) => updateScene(scene.id, { description: e.target.value })}
                  maxLength={2000}
                />
              </label>
              <label>
                {t('dialogue')}
                <textarea
                  aria-label={t('dialogue')}
                  value={scene.dialogue}
                  onChange={(e) => updateScene(scene.id, { dialogue: e.target.value })}
                  maxLength={4000}
                />
              </label>
              <div className="character-choices">
                {current.document.characters.map((c) => (
                  <label className="checkbox" key={c.id}>
                    <input
                      type="checkbox"
                      checked={scene.character_ids.includes(c.id)}
                      onChange={(e) =>
                        updateScene(scene.id, {
                          character_ids: e.target.checked
                            ? [...scene.character_ids, c.id]
                            : scene.character_ids.filter((id) => id !== c.id),
                        })
                      }
                    />
                    {c.name}
                  </label>
                ))}
              </div>
              <label>
                {t('sceneMedia')}
                <select
                  value={scene.asset_id || ''}
                  onChange={(e) => updateScene(scene.id, { asset_id: e.target.value || null })}
                >
                  <option value="">{t('none')}</option>
                  {assets
                    .filter((a) => a.mime.startsWith('video/'))
                    .map((a) => (
                      <option key={a.id} value={a.id}>
                        {a.title}
                      </option>
                    ))}
                </select>
              </label>
              <button
                className="button small"
                disabled={busy || dirty || !videoAvailable}
                onClick={() => {
                  if (!window.confirm(t('confirmCost') + ': ' + videoCredits + ' ' + t('credits')))
                    return;
                  act(async () => {
                    await request(
                      '/projects/' + current.id + '/scenes/' + scene.id + '/generate',
                      'POST',
                      { idempotency_key: crypto.randomUUID(), confirmed_credits: videoCredits },
                    );
                    setMessage(t('queued'));
                  });
                }}
              >
                <Clapperboard size={14} />
                {t('generateScene')} · {videoCredits} ◈
              </button>
            </div>
          ))}
          <div className="storyboard-actions">
            <button className="button primary" disabled={busy || !dirty} onClick={save}>
              <Save size={15} />
              {t('save')}
            </button>
            <button
              className="button"
              disabled={busy}
              onClick={() => {
                if (dirty && !window.confirm(t('discardChanges'))) return;
                reload();
              }}
            >
              <RefreshCw size={15} />
              {t('refresh')}
            </button>
            <button
              className="button"
              disabled={
                busy ||
                !backgroundProcessing ||
                dirty ||
                !current.document.scenes.length ||
                current.document.scenes.some((s) => !s.asset_id)
              }
              onClick={() =>
                act(async () => {
                  await request('/projects/' + current.id + '/assemble', 'POST', {
                    idempotency_key: crypto.randomUUID(),
                  });
                  setMessage(t('queued'));
                })
              }
            >
              <Film size={15} />
              {t('assemble')}
            </button>
          </div>
          <p className="fine-print">{t('saveBeforeRender')}</p>
        </>
      )}
    </section>
  );
}
