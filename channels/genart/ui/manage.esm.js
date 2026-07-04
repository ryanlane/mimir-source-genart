const BASE_URL = () => window.mimirServerBaseUrl || window.location.origin;
const API = () => `${BASE_URL()}/api/channels/com.mimir.genart`;

const STYLE_META = {
  wabi:           { label: 'Kyoto Bauhaus',           hint: 'Wabi-Sabi giclée · terracotta / oat / charcoal / sage' },
  constructivist: { label: "Riso Constructivist '66", hint: 'Risograph inks · mustard / teal / burnt orange / cream' },
  phosphor:       { label: 'Phosphor Terminal',       hint: 'ASCII characters · Mimir green on CRT black, scanlines + glow' },
  blueprint:      { label: 'Blueprint Cyanotype',     hint: 'Pale line work · Prussian blue drafting paper' },
  neon:           { label: 'Neon Dusk',               hint: 'Synthwave glow · pink / cyan / violet on indigo (OLED)' },
};

const ALGO_LABELS = {
  auto: 'Auto (per piece)', arches: 'Arch Study', flowfield: 'Sand Currents',
  inkweave: 'Ink Weave', orbits: 'Orbit Rhythm', tatami: 'Tatami Grid', beams: 'Signal Beams',
  interference: 'Standing Waves', flora: 'Quiet Meadow',
};

const STYLES = `
  :host { display: block; font-family: var(--font-base, system-ui, sans-serif); color: var(--color-text, #e8e8e8); }
  .panel { max-width: 720px; }
  h2 { font-size: 1.1rem; margin: 0 0 4px; color: var(--color-text, #e8e8e8); }
  .sub { font-size: 0.82rem; color: var(--color-text-secondary, #888); margin: 0 0 20px; }
  .form-group { margin-bottom: 14px; }
  label { display: block; font-size: 0.82rem; margin-bottom: 4px; color: var(--color-text-secondary, #888); }
  select, input[type=number] {
    width: 100%; box-sizing: border-box;
    background: var(--color-surface, #1a1a1a); border: 1px solid var(--color-border, #333);
    color: var(--color-text, #e8e8e8); border-radius: var(--radius-sm, 4px);
    padding: 8px 10px; font-size: 0.9rem;
  }
  input[type=range] { width: 100%; }
  .hint { font-size: 0.75rem; color: var(--color-text-tertiary, #666); margin-top: 4px; }
  .actions { display: flex; gap: 10px; align-items: center; margin-top: 18px; flex-wrap: wrap; }
  .btn { padding: 8px 18px; border: none; border-radius: var(--radius-sm, 4px); cursor: pointer; font-size: 0.9rem; }
  .btn-primary { background: light-dark(#036600, #2e7a30); color: #fff; }
  .btn-primary:hover { background: light-dark(#024d00, #3a963c); }
  .btn-primary:disabled { opacity: 0.5; cursor: default; }
  .btn-secondary { background: var(--color-surface, #222); color: var(--color-text, #e8e8e8); border: 1px solid var(--color-border, #333); }
  .btn-secondary:hover { background: var(--color-surface-hover, #2a2a2a); }
  .error { color: var(--color-error, #f87171); font-size: 0.82rem; margin-top: 8px; }
  .success-msg { color: var(--color-success, #4ade80); font-size: 0.82rem; margin-top: 8px; }
  .spinner { display: inline-block; width: 14px; height: 14px; border: 2px solid var(--color-accent, #00c851);
    border-top-color: transparent; border-radius: 50%; animation: spin .7s linear infinite; vertical-align: middle; }
  @keyframes spin { to { transform: rotate(360deg); } }
  .divider { border: none; border-top: 1px solid var(--color-border, #333); margin: 20px 0; }
  .section-title { font-size: 0.78rem; font-weight: 700; letter-spacing: 0.06em; text-transform: uppercase;
    color: var(--color-text-tertiary, #666); margin-bottom: 12px; }
  .two-col { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
  .style-cards { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
  .style-card { text-align: left; padding: 12px 14px; border: 1px solid var(--color-border, #333);
    border-radius: var(--radius-md, 8px); background: var(--color-surface, #1a1a1a);
    color: var(--color-text, #e8e8e8); cursor: pointer; }
  .style-card.active { border-color: var(--color-accent, #00c851); box-shadow: inset 3px 0 0 var(--color-accent, #00c851); }
  .style-name { display: block; font-weight: 600; margin-bottom: 3px; }
  .style-hint { display: block; font-size: 0.74rem; color: var(--color-text-tertiary, #666); }
  .preview-box { background: var(--color-background-alt, #111); border: 1px solid var(--color-border, #333);
    border-radius: var(--radius-md, 8px); padding: 14px; margin-bottom: 20px; }
  .preview-row { display: flex; gap: 14px; align-items: flex-start; flex-wrap: wrap; }
  .preview-img { width: 360px; max-width: 100%; aspect-ratio: 5 / 3; border-radius: 4px;
    background: #222; object-fit: cover; }
  .preview-side { display: flex; flex-direction: column; gap: 8px; min-width: 140px; }
  .preview-meta { font-size: 0.75rem; color: var(--color-text-tertiary, #666); line-height: 1.5; }
  @media (max-width: 640px) { .two-col, .style-cards { grid-template-columns: 1fr; } }
`;

class GenArtManager extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
    this._state = {
      loading: true, saving: false, error: null, successMsg: null,
      style: 'wabi', algorithm: 'auto', outputMode: 'static',
      seedMode: 'refresh', seed: 1, density: 'balanced',
      textureStrength: 100, frames: 24, frameMs: 120,
      previewSeed: Math.floor(Math.random() * 100000),
      previewLoading: false,
    };
  }

  connectedCallback() { this._load(); }

  _set(patch) { Object.assign(this._state, patch); this._render(); }

  async _load() {
    try {
      const resp = await fetch(`${API()}/settings`);
      const data = await resp.json();
      const s = data.settings || {};
      this._set({
        loading: false,
        style: s.style || 'wabi',
        algorithm: s.algorithm || 'auto',
        outputMode: s.output_mode || 'static',
        seedMode: s.seed_mode || 'refresh',
        seed: s.seed ?? 1,
        density: s.density || 'balanced',
        textureStrength: s.texture_strength ?? 100,
        frames: s.frames ?? 24,
        frameMs: s.frame_ms ?? 120,
      });
    } catch (e) {
      this._set({ loading: false, error: String(e) });
    }
  }

  async _save() {
    const s = this._state;
    this._set({ saving: true, error: null, successMsg: null });
    try {
      const resp = await fetch(`${API()}/settings`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          style: s.style, algorithm: s.algorithm, output_mode: s.outputMode,
          seed_mode: s.seedMode, seed: Number(s.seed) || 1, density: s.density,
          texture_strength: Number(s.textureStrength), frames: Number(s.frames),
          frame_ms: Number(s.frameMs),
        }),
      });
      const data = await resp.json();
      if (data.success) this._set({ saving: false, successMsg: 'Settings saved.' });
      else this._set({ saving: false, error: data.error || 'Save failed.' });
    } catch (e) {
      this._set({ saving: false, error: String(e) });
    }
  }

  _previewUrl() {
    const s = this._state;
    const algo = s.algorithm === 'auto' ? '' : s.algorithm;
    return `${API()}/preview?width=360&height=216&style=${s.style}&algorithm=${algo}&seed=${s.previewSeed}`;
  }

  _render() {
    const s = this._state;
    this.shadowRoot.innerHTML = `
      <style>${STYLES}</style>
      <div class="panel">
        <h2>Generative Art</h2>
        <p class="sub">Algorithmic art rendered on this server — no external services.
          Static PNG for e-ink displays, seamless animated loops for LCD/OLED.</p>

        ${s.loading ? '<div><span class="spinner"></span> Loading…</div>' : `
          <div class="preview-box">
            <div class="section-title">Preview</div>
            <div class="preview-row">
              <img class="preview-img" id="previewImg" src="${this._previewUrl()}" alt="Preview render">
              <div class="preview-side">
                <button class="btn btn-secondary" id="shuffle">New composition</button>
                <div class="preview-meta">Seed ${s.previewSeed}<br>
                  Previews are static; animation appears on the display.</div>
              </div>
            </div>
          </div>

          <div class="section-title">Style</div>
          <div class="style-cards">
            ${Object.entries(STYLE_META).map(([id, m]) => `
              <button class="style-card ${s.style === id ? 'active' : ''}" data-style="${id}">
                <span class="style-name">${m.label}</span>
                <span class="style-hint">${m.hint}</span>
              </button>`).join('')}
          </div>

          <hr class="divider">
          <div class="section-title">Composition</div>
          <div class="two-col">
            <div class="form-group">
              <label>Algorithm</label>
              <select id="algorithm">
                ${Object.entries(ALGO_LABELS).map(([id, label]) =>
                  `<option value="${id}" ${s.algorithm === id ? 'selected' : ''}>${label}</option>`).join('')}
              </select>
            </div>
            <div class="form-group">
              <label>Density</label>
              <select id="density">
                ${['sparse', 'balanced', 'rich'].map(d =>
                  `<option value="${d}" ${s.density === d ? 'selected' : ''}>${d[0].toUpperCase() + d.slice(1)}</option>`).join('')}
              </select>
            </div>
            <div class="form-group">
              <label>New piece</label>
              <select id="seedMode">
                <option value="refresh" ${s.seedMode === 'refresh' ? 'selected' : ''}>Every refresh</option>
                <option value="hourly"  ${s.seedMode === 'hourly' ? 'selected' : ''}>Hourly</option>
                <option value="daily"   ${s.seedMode === 'daily' ? 'selected' : ''}>Daily</option>
                <option value="fixed"   ${s.seedMode === 'fixed' ? 'selected' : ''}>Fixed seed</option>
              </select>
            </div>
            ${s.seedMode === 'fixed' ? `
              <div class="form-group">
                <label>Fixed seed</label>
                <input type="number" id="seed" value="${s.seed}" min="0">
              </div>` : ''}
          </div>
          <div class="form-group">
            <label>Texture strength — ${s.textureStrength}%</label>
            <input type="range" id="textureStrength" min="0" max="200" step="5" value="${s.textureStrength}">
            <div class="hint">Paper grain, cotton fiber, and risograph ink distress.</div>
          </div>

          <hr class="divider">
          <div class="section-title">Output</div>
          <div class="two-col">
            <div class="form-group">
              <label>Mode</label>
              <select id="outputMode">
                <option value="static"   ${s.outputMode === 'static' ? 'selected' : ''}>Static PNG (e-ink safe)</option>
                <option value="animated" ${s.outputMode === 'animated' ? 'selected' : ''}>Animated WebP loop (LCD/OLED)</option>
              </select>
            </div>
          </div>
          ${s.outputMode === 'animated' ? `
            <div class="two-col">
              <div class="form-group">
                <label>Frames per loop</label>
                <input type="number" id="frames" value="${s.frames}" min="8" max="60">
              </div>
              <div class="form-group">
                <label>Frame duration (ms)</label>
                <input type="number" id="frameMs" value="${s.frameMs}" min="40" max="500" step="10">
              </div>
            </div>
            <div class="hint">Animated renders are heavier — the first render at a new size takes a few
              seconds and is cached. Use static mode for e-ink displays.</div>` : ''}

          <div class="actions">
            <button class="btn btn-primary" id="save" ${s.saving ? 'disabled' : ''}>
              ${s.saving ? '<span class="spinner"></span> Saving…' : 'Save Settings'}
            </button>
          </div>
          ${s.error ? `<div class="error">${s.error}</div>` : ''}
          ${s.successMsg ? `<div class="success-msg">${s.successMsg}</div>` : ''}
        `}
      </div>
    `;

    const $ = id => this.shadowRoot.getElementById(id);
    $('save')?.addEventListener('click', () => this._save());
    $('shuffle')?.addEventListener('click', () =>
      this._set({ previewSeed: Math.floor(Math.random() * 100000) }));
    this.shadowRoot.querySelectorAll('[data-style]').forEach(btn =>
      btn.addEventListener('click', () => this._set({ style: btn.dataset.style })));
    $('algorithm')?.addEventListener('change', e => this._set({ algorithm: e.target.value }));
    $('density')?.addEventListener('change', e => this._set({ density: e.target.value }));
    $('seedMode')?.addEventListener('change', e => this._set({ seedMode: e.target.value }));
    $('seed')?.addEventListener('input', e => { this._state.seed = e.target.value; });
    $('textureStrength')?.addEventListener('input', e => this._set({ textureStrength: Number(e.target.value) }));
    $('outputMode')?.addEventListener('change', e => this._set({ outputMode: e.target.value }));
    $('frames')?.addEventListener('input', e => { this._state.frames = e.target.value; });
    $('frameMs')?.addEventListener('input', e => { this._state.frameMs = e.target.value; });
  }
}

if (!customElements.get('x-genart-manager')) {
  customElements.define('x-genart-manager', GenArtManager);
}
