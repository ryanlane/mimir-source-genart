/**
 * Mimir Generative Art Channel Manager
 * Custom element: <x-genart-manager channel-id="com.mimir.genart">
 *
 * A Gallery is one named, saved generative-art configuration — assign
 * different galleries to different programs and displays. This manager
 * lists galleries, edits one at a time with a live preview, and shows a
 * first-run explainer when none exist yet.
 */
class GenArtManager extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
    this._state = {
      loading:        true,
      galleries:      [],
      styles:         [],   // [{id, name, description}]
      algorithms:     [],   // [{id, name, description}]
      editingId:      null, // null=list, ''=new, 'uuid'=editing
      form:           this._blankForm(),
      saving:         false,
      previewUrl:     null,
      previewLoading: false,
      message:        null,
    };
    this._previewTimer = null;
  }

  get channelId() { return this.getAttribute('channel-id') || 'com.mimir.genart'; }
  get apiBase()   { return `/api/channels/${this.channelId}`; }

  connectedCallback() {
    this.shadowRoot.addEventListener('click',  e => this._handleClick(e));
    this.shadowRoot.addEventListener('change', e => this._handleChange(e));
    this.shadowRoot.addEventListener('input',  e => this._handleChange(e));
    this._load();
  }

  _blankForm() {
    return {
      name: 'My Gallery', style: 'wabi', algorithm: 'auto', output_mode: 'static',
      seed_mode: 'refresh', seed: 1, density: 'balanced', texture_strength: 100,
      frames: 24, frame_ms: 120,
    };
  }

  async _load() {
    this._setState({ loading: true });
    try {
      const status = await fetch(`${this.apiBase}/status`).then(r => r.json());
      this._setState({
        loading:    false,
        galleries:  status.galleries || [],
        styles:     status.styles || [],
        algorithms: status.algorithms || [],
      });
    } catch (e) {
      this._setState({ loading: false, message: { type: 'error', text: `Load failed: ${e.message}` } });
    }
  }

  _setState(patch) {
    this._state = { ...this._state, ...patch };
    this._render();
  }

  // ── Preview ──────────────────────────────────────────────────────────
  _schedulePreview() {
    clearTimeout(this._previewTimer);
    this._previewTimer = setTimeout(() => this._loadPreview(), 500);
  }

  async _loadPreview() {
    this._setState({ previewLoading: true });
    try {
      const r = await fetch(`${this.apiBase}/preview`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ config: this._state.form, w: 360, h: 216 }),
      });
      if (!r.ok) throw new Error(await r.text());
      const blob = await r.blob();
      const url = URL.createObjectURL(blob);
      this._setState({ previewLoading: false, previewUrl: url });
    } catch (e) {
      this._setState({ previewLoading: false });
    }
  }

  // ── API calls ────────────────────────────────────────────────────────
  async _saveGallery() {
    const { editingId, form } = this._state;
    const isNew = editingId === '';
    const url = isNew ? `${this.apiBase}/subchannels` : `${this.apiBase}/subchannels/${editingId}`;
    this._setState({ saving: true });
    try {
      const r = await fetch(url, {
        method: isNew ? 'POST' : 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(form),
      });
      if (!r.ok) throw new Error(await r.text());
      this._setState({
        saving: false, editingId: null,
        message: { type: 'success', text: isNew ? 'Gallery created.' : 'Gallery saved.' },
      });
      this._load();
    } catch (e) {
      this._setState({ saving: false, message: { type: 'error', text: e.message } });
    }
  }

  async _deleteGallery(id) {
    if (!confirm('Delete this gallery? Displays using it will show a configuration error until reassigned.')) return;
    try {
      await fetch(`${this.apiBase}/subchannels/${id}`, { method: 'DELETE' });
      this._load();
    } catch (e) {
      this._setState({ message: { type: 'error', text: e.message } });
    }
  }

  _openEdit(id) {
    if (id === '') {
      this._setState({ editingId: '', form: this._blankForm(), previewUrl: null, message: null });
      this._schedulePreview();
      return;
    }
    const g = this._state.galleries.find(x => x.id === id);
    fetch(`${this.apiBase}/subchannels/${id}`).then(r => r.json()).then(data => {
      this._setState({ editingId: id, form: { ...this._blankForm(), ...data }, previewUrl: null, message: null });
      this._schedulePreview();
    }).catch(e => this._setState({ message: { type: 'error', text: e.message } }));
    void g; // list already has summary fields; full detail comes from the fetch above
  }

  // ── Event dispatch ──────────────────────────────────────────────────
  _handleClick(e) {
    const action = e.target.closest('[data-action]')?.dataset.action;
    const id     = e.target.closest('[data-id]')?.dataset.id;
    if (!action) return;
    switch (action) {
      case 'add-gallery':    this._openEdit('');        break;
      case 'edit-gallery':   this._openEdit(id);        break;
      case 'delete-gallery': this._deleteGallery(id);   break;
      case 'cancel-edit':    this._setState({ editingId: null, previewUrl: null }); break;
      case 'save-gallery':   this._saveGallery();       break;
    }
  }

  _handleChange(e) {
    const field = e.target.dataset.field;
    if (!field) return;
    let value = e.target.value;
    if (['seed', 'texture_strength', 'frames', 'frame_ms'].includes(field)) {
      value = Number(value);
    }
    this._setState({ form: { ...this._state.form, [field]: value } });
    this._schedulePreview();
  }

  _esc(s) {
    return String(s ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  }

  // ── Render ──────────────────────────────────────────────────────────
  _render() {
    const root = this.shadowRoot;
    const active = root.activeElement;
    const focusField = active?.dataset?.field;
    const focusSel = active?.selectionStart;
    const focusEnd = active?.selectionEnd;

    root.innerHTML = `<style>${this._css()}</style>${this._html()}`;

    if (focusField) {
      const el = root.querySelector(`[data-field="${focusField}"]`);
      if (el) {
        el.focus();
        if (focusSel !== null && focusSel !== undefined && el.setSelectionRange) {
          try { el.setSelectionRange(focusSel, focusEnd); } catch (_) {}
        }
      }
    }
  }

  _html() {
    const s = this._state;
    if (s.loading) return `<div class="loading">Loading…</div>`;
    if (s.editingId !== null) return this._editPanel();
    return this._listPanel();
  }

  _listPanel() {
    const s = this._state;
    if (s.galleries.length === 0) return this._oobePanel();
    return `
      <div class="panel">
        ${this._messageBar()}
        <div class="section-header">
          <span>Galleries</span>
          <button class="btn btn-primary" data-action="add-gallery">+ Add Gallery</button>
        </div>
        ${s.galleries.map(g => this._galleryCard(g)).join('')}
      </div>`;
  }

  _oobePanel() {
    return `
      <div class="panel">
        ${this._messageBar()}
        <div class="oobe">
          <div class="oobe-icon">◆</div>
          <h2>Welcome to Generative Art</h2>
          <p>
            Every piece is algorithmic art rendered right here on this server —
            no external services, no API keys. A <strong>gallery</strong> is a
            named, saved configuration: a print style, a composition algorithm,
            and how often a new piece appears.
          </p>
          <p>
            Create as many galleries as you like and assign different ones to
            different programs and displays — a calm watercolor meadow in the
            hallway, glowing ASCII waves on the office OLED, whatever fits.
          </p>
          <button class="btn btn-primary btn-lg" data-action="add-gallery">Create Your First Gallery</button>
        </div>
      </div>`;
  }

  _galleryCard(g) {
    const styleName = this._state.styles.find(s => s.id === g.style)?.name
      || (g.style === 'random' ? '🎲 Random' : g.style);
    const algoName = this._state.algorithms.find(a => a.id === g.algorithm)?.name
      || (g.algorithm === 'auto' ? 'Auto' : g.algorithm);
    const modeLabel = g.output_mode === 'animated' ? '◐ Animated' : '▢ Static';
    return `
      <div class="gallery-card">
        <div class="gallery-info">
          <div class="gallery-name">${this._esc(g.name)}</div>
          <div class="gallery-meta">${this._esc(styleName)} · ${this._esc(algoName)} · ${modeLabel}</div>
        </div>
        <div class="gallery-actions">
          <button class="btn btn-ghost btn-sm" data-action="edit-gallery" data-id="${g.id}">Edit</button>
          <button class="btn btn-danger btn-sm" data-action="delete-gallery" data-id="${g.id}">Delete</button>
        </div>
      </div>`;
  }

  _editPanel() {
    const s = this._state;
    const f = s.form;
    const isNew = s.editingId === '';

    const opt = (val, label, cur) =>
      `<option value="${val}" ${cur === val ? 'selected' : ''}>${label}</option>`;

    const styleOpts = [opt('random', '🎲 Random (a different style each piece)', f.style)]
      .concat(s.styles.map(st => opt(st.id, st.name, f.style)));
    const algoOpts = [opt('auto', 'Auto (a different algorithm each piece)', f.algorithm)]
      .concat(s.algorithms.map(a => opt(a.id, a.name, f.algorithm)));

    const styleDesc = s.styles.find(st => st.id === f.style)?.description || '';
    const algoDesc = s.algorithms.find(a => a.id === f.algorithm)?.description || '';

    return `
      <div class="edit-panel">
        <div class="edit-header">
          <h2>${isNew ? 'New Gallery' : 'Edit Gallery'}</h2>
          ${this._messageBar()}
        </div>
        <div class="edit-body">

          <div class="form-col">
            <div class="field-group">
              <label class="field-label">Gallery Name</label>
              <input class="form-input" data-field="name" value="${this._esc(f.name)}" placeholder="e.g. Hallway Watercolor">
            </div>

            <div class="field-group">
              <label class="field-label">Style</label>
              <select class="form-select" data-field="style">${styleOpts.join('')}</select>
              ${styleDesc ? `<div class="field-hint-block">${this._esc(styleDesc)}</div>` : ''}
            </div>

            <div class="field-group">
              <label class="field-label">Algorithm</label>
              <select class="form-select" data-field="algorithm">${algoOpts.join('')}</select>
              ${algoDesc ? `<div class="field-hint-block">${this._esc(algoDesc)}</div>` : ''}
            </div>

            <div class="divider"></div>

            <div class="field-row">
              <div class="field-group">
                <label class="field-label">Output</label>
                <select class="form-select" data-field="output_mode">
                  ${opt('static', 'Static PNG (e-ink safe)', f.output_mode)}
                  ${opt('animated', 'Animated loop (LCD/OLED)', f.output_mode)}
                </select>
              </div>
              <div class="field-group">
                <label class="field-label">Density</label>
                <select class="form-select" data-field="density">
                  ${opt('sparse', 'Sparse', f.density)}
                  ${opt('balanced', 'Balanced', f.density)}
                  ${opt('rich', 'Rich', f.density)}
                </select>
              </div>
            </div>

            <div class="field-row">
              <div class="field-group">
                <label class="field-label">New Piece</label>
                <select class="form-select" data-field="seed_mode">
                  ${opt('refresh', 'Every refresh', f.seed_mode)}
                  ${opt('hourly', 'Hourly', f.seed_mode)}
                  ${opt('daily', 'Daily', f.seed_mode)}
                  ${opt('fixed', 'Fixed seed', f.seed_mode)}
                </select>
              </div>
              ${f.seed_mode === 'fixed' ? `
                <div class="field-group">
                  <label class="field-label">Fixed Seed</label>
                  <input class="form-input" type="number" data-field="seed" value="${f.seed}" min="0">
                </div>` : ''}
            </div>

            <div class="field-group">
              <label class="field-label">Texture Strength — ${f.texture_strength}%</label>
              <input type="range" data-field="texture_strength" min="0" max="200" step="5" value="${f.texture_strength}">
            </div>

            ${f.output_mode === 'animated' ? `
              <div class="field-row">
                <div class="field-group">
                  <label class="field-label">Frames per loop</label>
                  <input class="form-input" type="number" data-field="frames" value="${f.frames}" min="8" max="60">
                </div>
                <div class="field-group">
                  <label class="field-label">Frame duration (ms)</label>
                  <input class="form-input" type="number" data-field="frame_ms" value="${f.frame_ms}" min="40" max="500" step="10">
                </div>
              </div>
              <div class="field-hint-block">Preview below is always a static frame — the animated loop is confirmed on the display after saving.</div>
            ` : ''}
          </div>

          <div class="preview-col">
            <div class="preview-frame">
              ${s.previewLoading
                ? `<div class="preview-placeholder">Rendering…</div>`
                : s.previewUrl
                  ? `<img class="preview-img" src="${s.previewUrl}" alt="preview">`
                  : `<div class="preview-placeholder">Preview will appear here</div>`}
            </div>
            <div class="preview-size">360 × 216 preview</div>
          </div>

        </div>

        <div class="edit-footer">
          <button class="btn btn-ghost" data-action="cancel-edit">Cancel</button>
          <button class="btn btn-primary" data-action="save-gallery" ${s.saving ? 'disabled' : ''}>
            ${s.saving ? 'Saving…' : (isNew ? 'Create Gallery' : 'Save Changes')}
          </button>
        </div>
      </div>`;
  }

  _messageBar() {
    const m = this._state.message;
    if (!m) return '';
    return `<div class="message message-${m.type}">${this._esc(m.text)}</div>`;
  }

  _css() {
    return `
      :host { display: block; font-family: system-ui, -apple-system, sans-serif; font-size: 14px; }
      * { box-sizing: border-box; }

      .loading { padding: 32px; text-align: center; color: var(--color-text-secondary, #888); }

      .panel { display: flex; flex-direction: column; gap: 16px; padding: 4px 0; }

      .message { padding: 10px 14px; border-radius: 6px; font-size: 0.85rem; }
      .message-error   { background: rgba(198,40,40,0.12); color: #e57373; border: 1px solid rgba(198,40,40,0.25); }
      .message-success { background: rgba(0,200,81,0.10);  color: #4caf50; border: 1px solid rgba(0,200,81,0.2);  }

      /* OOBE */
      .oobe { text-align: center; padding: 36px 24px; background: var(--color-surface, #1e2428);
        border: 1px solid var(--color-border, #2a3035); border-radius: 10px; }
      .oobe-icon { font-size: 2rem; color: var(--color-accent, #00C851); margin-bottom: 8px; }
      .oobe h2 { font-size: 1.2rem; margin: 0 0 14px; }
      .oobe p { max-width: 480px; margin: 0 auto 12px; color: var(--color-text-secondary, #999); line-height: 1.6; font-size: 0.9rem; }
      .oobe .btn-lg { margin-top: 12px; padding: 10px 24px; font-size: 0.95rem; }

      .section-header { display: flex; align-items: center; justify-content: space-between; }
      .section-header span { font-weight: 600; font-size: 0.9rem; color: var(--color-text-secondary, #888); text-transform: uppercase; letter-spacing: 0.06em; }

      .gallery-card { display: flex; align-items: center; gap: 12px; padding: 12px 14px;
        background: var(--color-surface, #1e2428); border: 1px solid var(--color-border, #2a3035); border-radius: 8px; }
      .gallery-info { flex: 1; min-width: 0; }
      .gallery-name { font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
      .gallery-meta { font-size: 0.78rem; color: var(--color-text-secondary, #888); margin-top: 2px; }
      .gallery-actions { display: flex; gap: 6px; flex-shrink: 0; }

      .edit-panel { display: flex; flex-direction: column; height: 100%; gap: 0; }
      .edit-header { padding-bottom: 12px; border-bottom: 1px solid var(--color-border, #2a3035); margin-bottom: 16px; }
      .edit-header h2 { font-size: 1.1rem; font-weight: 700; margin-bottom: 8px; }
      .edit-body { display: flex; gap: 20px; flex: 1; min-height: 0; overflow: auto; }
      .edit-footer { display: flex; justify-content: flex-end; gap: 8px; padding-top: 16px; border-top: 1px solid var(--color-border, #2a3035); margin-top: 16px; }

      .form-col { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 14px; }
      .field-group { display: flex; flex-direction: column; gap: 5px; }
      .field-row { display: flex; gap: 12px; }
      .field-row .field-group { flex: 1; }
      .field-label { font-size: 0.78rem; font-weight: 600; color: var(--color-text-secondary, #888); text-transform: uppercase; letter-spacing: 0.06em; }
      .field-hint-block { font-size: 0.78rem; color: var(--color-text-tertiary, #666); line-height: 1.5; margin-top: -2px; }
      .form-input, .form-select {
        background: var(--color-background, #111518); border: 1px solid var(--color-border, #2a3035);
        color: var(--color-text, #e0e0e0); border-radius: 6px; padding: 7px 10px; font-size: 0.85rem; width: 100%;
      }
      .form-input:focus, .form-select:focus { outline: 2px solid var(--color-accent, #00C851); outline-offset: -1px; }
      input[type=range] { width: 100%; }
      .divider { border: none; border-top: 1px solid var(--color-border, #2a3035); }

      .preview-col { width: 340px; flex-shrink: 0; display: flex; flex-direction: column; gap: 8px; }
      .preview-frame { background: #000; border: 1px solid var(--color-border, #2a3035); border-radius: 6px;
        overflow: hidden; display: flex; align-items: center; justify-content: center; min-height: 200px; position: relative; }
      .preview-img { width: 100%; height: auto; display: block; }
      .preview-placeholder { color: var(--color-text-secondary, #555); font-size: 0.8rem; padding: 32px; text-align: center; }
      .preview-size { font-size: 0.68rem; color: var(--color-text-tertiary, #555); text-align: center; letter-spacing: 0.05em; }

      .btn { padding: 7px 14px; border-radius: 6px; font-size: 0.83rem; font-weight: 600; cursor: pointer; border: 1px solid transparent; transition: opacity .15s; }
      .btn:disabled { opacity: .5; cursor: default; }
      .btn-primary { background: var(--color-accent, #00C851); color: #000; }
      .btn-primary:hover:not(:disabled) { opacity: .85; }
      .btn-danger  { background: rgba(198,40,40,0.15); color: #e57373; border-color: rgba(198,40,40,0.3); }
      .btn-danger:hover:not(:disabled) { background: rgba(198,40,40,0.25); }
      .btn-ghost   { background: transparent; color: var(--color-text, #e0e0e0); border-color: var(--color-border, #2a3035); }
      .btn-ghost:hover:not(:disabled) { background: var(--color-surface, #1e2428); }
      .btn-sm { padding: 4px 10px; font-size: 0.76rem; }
    `;
  }
}

if (!customElements.get('x-genart-manager')) {
  customElements.define('x-genart-manager', GenArtManager);
}
