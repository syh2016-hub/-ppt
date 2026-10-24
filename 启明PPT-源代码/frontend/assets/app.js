/* 启明 PPT — single-page application.
   No framework, no CDN, no telemetry. Everything runs on the local server. */
(() => {
  'use strict';

  const { icon, logoMark } = window.QmIcons;
  const root = document.getElementById('app');
  const toastRoot = document.getElementById('toast-root');
  const modalRoot = document.getElementById('modal-root');
  const DEFAULT_COLORS = {
    bg: '#F7F3EA', bg2: '#ECE5D6', surface: '#FFFFFF', surface_alt: '#F1EBDD',
    ink: '#181713', muted: '#6C675D', primary: '#E54B2A', primary_soft: '#F6C9BA',
    accent: '#1F4BFF', line: '#D8D0C0', on_primary: '#FFFFFF',
  };
  const TYPE_LABELS = {
    cover: '封面', agenda: '目录', section: '章节页', bullets: '内容页',
    stats: '数据页', quote: '金句页', summary: '总结页', end: '结束页',
  };
  const PROVIDER_LABELS = {
    auto: '自动选择', deepseek: 'DeepSeek', doubao: '豆包', custom: '自定义模型', local: '启明内置 AI',
  };
  const TONE_LABELS = {
    professional: '专业克制', inspiring: '有感染力', story: '故事感', academic: '学术严谨', friendly: '轻松亲切',
  };
  const EXAMPLE_PROMPTS = [
    { icon: 'zap', title: 'AI 与教育', text: '帮我做一份关于人工智能如何改变教育行业的 PPT，面向中学教师，重点讲个性化学习和教师角色变化。' },
    { icon: 'chart', title: '季度复盘', text: '做一份 2026 年第三季度工作复盘汇报，面向管理层，包含目标完成、关键问题、经验总结和下一阶段计划。' },
    { icon: 'palette', title: '品牌提案', text: '为新中式茶饮品牌「山间」做一份品牌升级提案，面向创始团队，风格克制、有东方感。' },
    { icon: 'compass', title: '课程设计', text: '设计一份面向初中生的科学课课件，主题是「身边的能源」，需要互动任务和课堂小结。' },
    { icon: 'globe', title: '行业趋势', text: '2026 年新能源汽车行业趋势与机会，面向投资人和产业伙伴，包含市场变化、技术路线和投资判断。' },
    { icon: 'sparkles', title: '个人分享', text: '做一份关于「如何建立自己的知识管理系统」的分享，面向年轻职场人，轻松、有故事感。' },
  ];

  const EXAMPLE_PROMPTS_EN = [
    { icon: 'zap', title: 'AI & Education', text: 'Create an English presentation about how AI is changing education, for middle school teachers, focusing on personalized learning and the changing role of teachers.' },
    { icon: 'chart', title: 'Business Review', text: 'Create an English quarterly business review for the leadership team, covering goals, key issues, lessons learned, and next-quarter priorities.' },
    { icon: 'compass', title: 'Lesson Plan', text: 'Design an English science lesson about energy for middle school students, with interactive tasks, a short reading passage, and a classroom summary.' },
    { icon: 'globe', title: 'Industry Trends', text: 'Create an English presentation on 2026 electric vehicle trends and opportunities for investors and industry partners.' },
  ];

  const state = {
    meta: null,
    user: null,
    templates: [],
    categories: [],
    featured: [],
    create: {
      prompt: '', slides: 10, audience: '', tone: 'professional', provider: 'auto',
      enable_search: false, include_agenda: true, include_summary: true, include_qa: true, language: 'zh',
    },
    outline: null,
    template: null,
    templateUseImage: true,
    project: null,
    references: [],
    useReferenceCover: false,
    uploadingReferences: false,
    referenceErrors: [],
    readingText: '',
    readingTitle: '',
    readingSource: '',
    voices: [],
    selectedSlide: 0,
    route: '',
    viewToken: 0,
    generationTimer: null,
    projectTimer: null,
    authMode: 'login',
    busy: false,
    onlineTemplates: [],
    onlineQuery: '',
    onlineLoading: false,
    onlineTried: false,
    galleryTab: 'builtin',
    galleryCategory: '全部',
    galleryQuery: '',
    pickTab: 'builtin',
    pickCategory: '全部',
    pickQuery: '',
    settingsTab: 'ai',
    aiSettings: null,
    sessions: null,
    draftSnapshot: null,
    player: { index: 0, playing: false, timer: null, speaking: false },
    codeTimer: null,
    codeCooldownUntil: 0,
  };

  /* ------------------------------------------------------------------ utils */
  const $ = (selector, scope = document) => scope.querySelector(selector);
  const $$ = (selector, scope = document) => Array.from(scope.querySelectorAll(selector));

  function e(value) {
    return String(value ?? '')
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#039;');
  }

  function safeColor(value, fallback) {
    return /^#[0-9A-Fa-f]{6}$/.test(String(value || '')) ? value : fallback;
  }

  function debounce(fn, wait = 250) {
    let timer = null;
    return (...args) => {
      clearTimeout(timer);
      timer = setTimeout(() => fn(...args), wait);
    };
  }

  // Slide previews use a fixed 100-unit coordinate system. A ResizeObserver
  // translates each preview's actual width into a CSS variable, keeping
  // typography proportional in thumbnails, the editor, modals and the player.
  const pvResizeObserver = typeof ResizeObserver !== 'undefined' ? new ResizeObserver((entries) => {
    for (const entry of entries) {
      const width = entry.target.clientWidth || entry.target.getBoundingClientRect().width;
      if (width > 0) entry.target.style.setProperty('--pv-unit', `${width / 100}px`);
    }
  }) : null;
  function syncPvUnits(scope = document) {
    scope.querySelectorAll?.('.pv').forEach((node) => {
      if (!node.dataset.pvObserved) {
        node.dataset.pvObserved = '1';
        pvResizeObserver?.observe(node);
      }
      const width = node.clientWidth;
      if (width > 0) node.style.setProperty('--pv-unit', `${width / 100}px`);
    });
  }
  if (typeof MutationObserver !== 'undefined') {
    let scheduled = false;
    new MutationObserver(() => {
      if (scheduled) return;
      scheduled = true;
      requestAnimationFrame(() => { scheduled = false; syncPvUnits(document); });
    }).observe(document.documentElement, { childList: true, subtree: true });
  }

  function initials(name) {
    const text = String(name || '启').trim();
    return text.slice(0, 1).toUpperCase();
  }

  function formatDate(value) {
    if (!value) return '—';
    try {
      const d = new Date(value);
      if (Number.isNaN(d.getTime())) return String(value).slice(0, 16);
      return new Intl.DateTimeFormat('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }).format(d);
    } catch (_) { return String(value).slice(0, 16); }
  }

  function greeting() {
    const hour = new Date().getHours();
    if (hour < 6) return '夜深了';
    if (hour < 11) return '早上好';
    if (hour < 14) return '中午好';
    if (hour < 18) return '下午好';
    return '晚上好';
  }

  function typeLabel(type) { return TYPE_LABELS[type] || '内容页'; }
  function providerLabel(provider) { return PROVIDER_LABELS[provider] || provider || '启明内置 AI'; }
  function statusLabel(status) {
    return { draft: '草稿', ready: '已完成', failed: '生成失败', generating: '生成中', queued: '排队中', running: '生成中' }[status] || '草稿';
  }

  function typeDotClass(type) {
    return ['agenda', 'section', 'stats', 'quote', 'summary', 'end'].includes(type) ? type : '';
  }

  function themeOf(template) {
    const t = template || state.templates[0] || {};
    return { ...t, colors: { ...DEFAULT_COLORS, ...(t.colors || {}) } };
  }

  function templateById(id) {
    return state.templates.find((item) => item.id === id) || null;
  }

  function avatar(user, size = '') {
    const hue = Number(user?.avatar_hue || 220);
    return `<span class="avatar ${size}" style="--hue:${hue}">${e(initials(user?.display_name || user?.username || '启'))}</span>`;
  }

  function themeVars(theme) {
    const c = themeOf(theme).colors;
    return [
      `--pv-bg:${safeColor(c.bg, DEFAULT_COLORS.bg)}`,
      `--pv-bg2:${safeColor(c.bg2, DEFAULT_COLORS.bg2)}`,
      `--pv-surface:${safeColor(c.surface, DEFAULT_COLORS.surface)}`,
      `--pv-ink:${safeColor(c.ink, DEFAULT_COLORS.ink)}`,
      `--pv-muted:${safeColor(c.muted, DEFAULT_COLORS.muted)}`,
      `--pv-primary:${safeColor(c.primary, DEFAULT_COLORS.primary)}`,
      `--pv-soft:${safeColor(c.primary_soft, DEFAULT_COLORS.primary_soft)}`,
      `--pv-accent:${safeColor(c.accent, DEFAULT_COLORS.accent)}`,
      `--pv-line:${safeColor(c.line, DEFAULT_COLORS.line)}`,
    ].join(';');
  }

  function swatches(theme) {
    const c = themeOf(theme).colors;
    return ['bg', 'primary', 'accent', 'primary_soft'].map((key) =>
      `<span class="swatch" style="background:${safeColor(c[key], '#ddd')}" title="${e(key)}"></span>`
    ).join('');
  }

  /* -------------------------------------------------------------------- API */
  class ApiError extends Error {
    constructor(message, status = 0, data = {}) {
      super(message);
      this.status = status;
      this.data = data;
    }
  }

  let authRendering = false;
  async function api(path, options = {}) {
    const { method = 'GET', body, signal } = options;
    const headers = { Accept: 'application/json' };
    const init = { method, credentials: 'same-origin', headers, signal };
    if (body !== undefined) {
      headers['Content-Type'] = 'application/json';
      init.body = JSON.stringify(body);
    }
    let response;
    try {
      response = await fetch(path, init);
    } catch (err) {
      if (err?.name === 'AbortError') throw err;
      throw new ApiError('网络连接失败，请确认本地服务仍在运行', 0, { code: 'NETWORK' });
    }
    let data = {};
    const text = await response.text();
    if (text) { try { data = JSON.parse(text); } catch (_) { data = { error: text.slice(0, 200) }; } }
    if (!response.ok || data.ok === false) {
      if (response.status === 401 && state.user && !path.startsWith('/api/auth/')) {
        state.user = null;
        if (!authRendering) renderAuth('login');
      }
      throw new ApiError(data.error || `请求失败（${response.status}）`, response.status, data);
    }
    return data;
  }

  async function apiUpload(path, formData) {
    let response;
    try {
      response = await fetch(path, { method: 'POST', credentials: 'same-origin', body: formData });
    } catch (_) {
      throw new ApiError('上传失败，请检查本地服务是否运行', 0, { code: 'NETWORK' });
    }
    let data = {};
    const text = await response.text();
    if (text) { try { data = JSON.parse(text); } catch (_) { data = { error: text.slice(0, 200) }; } }
    if (!response.ok || data.ok === false) {
      throw new ApiError(data.error || `上传失败（${response.status}）`, response.status, data);
    }
    return data;
  }

  /* ---------------------------------------------------------------- feedback */
  function toast(message, type = 'info', detail = '') {
    const id = `toast-${Date.now()}-${Math.random().toString(16).slice(2)}`;
    const iconName = type === 'success' ? 'check' : type === 'error' ? 'alert' : 'info';
    const node = document.createElement('div');
    node.className = `toast ${type}`;
    node.id = id;
    node.innerHTML = `<span class="t-ic">${icon(iconName, 13)}</span><div class="t-body"><strong>${e(message)}</strong>${detail ? `<span>${e(detail)}</span>` : ''}</div>`;
    toastRoot.appendChild(node);
    setTimeout(() => {
      node.classList.add('out');
      setTimeout(() => node.remove(), 260);
    }, type === 'error' ? 5200 : 3800);
  }

  function closeModal() {
    modalRoot.innerHTML = '';
    document.body.classList.remove('modal-open');
    if (window.speechSynthesis) window.speechSynthesis.cancel();
  }

  function openModal(html, className = '') {
    modalRoot.innerHTML = `<div class="modal-backdrop" data-modal-backdrop><div class="modal ${className}" role="dialog" aria-modal="true">${html}</div></div>`;
    document.body.classList.add('modal-open');
    modalRoot.querySelectorAll('[data-close-modal]').forEach((btn) => btn.addEventListener('click', closeModal));
    const backdrop = $('[data-modal-backdrop]');
    if (backdrop) {
      backdrop.addEventListener('mousedown', (ev) => {
        if (ev.target === backdrop) closeModal();
      });
    }
    return modalRoot;
  }

  function confirmDialog({ title = '确认操作', message = '', confirmText = '确认', danger = false } = {}) {
    return new Promise((resolve) => {
      const host = openModal(`
        <div class="modal-head">
          <div><h2>${e(title)}</h2><p>${e(message)}</p></div>
          <button class="modal-close" data-close-modal aria-label="关闭">${icon('close', 15)}</button>
        </div>
        <div class="modal-foot" style="padding-top:18px">
          <button class="btn btn-ghost" data-confirm-no>取消</button>
          <button class="btn ${danger ? 'btn-danger' : 'btn-primary'}" data-confirm-yes>${e(confirmText)}</button>
        </div>`);
      let settled = false;
      const finish = (value) => {
        if (settled) return;
        settled = true;
        closeModal();
        resolve(value);
      };
      host.querySelector('[data-confirm-no]')?.addEventListener('click', () => finish(false));
      host.querySelector('[data-confirm-yes]')?.addEventListener('click', () => finish(true));
      host.querySelector('.modal-close')?.addEventListener('click', () => finish(false));
      host.querySelector('[data-modal-backdrop]')?.addEventListener('mousedown', (ev) => {
        if (ev.target === ev.currentTarget) finish(false);
      });
    });
  }

  function showBusy({ title, subtitle, steps = [] }) {
    document.querySelectorAll('.busy-layer').forEach((node) => node.remove());
    const layer = document.createElement('div');
    layer.className = 'busy-layer';
    layer.innerHTML = `
      <div class="busy-card">
        <div class="ai-orbit"><div class="ring r1"></div><div class="ring r2"></div><div class="ring r3"></div><div class="core"></div></div>
        <div class="busy-title">${e(title)}</div>
        <div class="busy-sub">${e(subtitle || '')}</div>
        <div class="busy-steps">
          ${steps.map((step, i) => `<div class="busy-step ${i === 0 ? 'active' : ''}" data-busy-step="${i}"><span class="bs-dot">${icon('check', 9)}</span><span>${e(step)}</span></div>`).join('')}
        </div>
      </div>`;
    document.body.appendChild(layer);
    let index = 0;
    const interval = setInterval(() => {
      const rows = layer.querySelectorAll('.busy-step');
      if (!rows.length) return;
      rows.forEach((row, i) => {
        row.classList.toggle('done', i < index);
        row.classList.toggle('active', i === index);
      });
      if (index < rows.length - 1) index += 1;
    }, 1100);
    return {
      close(delay = 250) {
        clearInterval(interval);
        layer.querySelectorAll('.busy-step').forEach((row) => { row.classList.add('done'); row.classList.remove('active'); });
        setTimeout(() => {
          layer.style.opacity = '0';
          layer.style.transition = 'opacity .25s';
          setTimeout(() => layer.remove(), 260);
        }, delay);
      },
      fail(message) {
        clearInterval(interval);
        layer.querySelector('.busy-title').textContent = '遇到了一点问题';
        layer.querySelector('.busy-sub').textContent = message || '请稍后再试';
        layer.querySelector('.busy-steps').innerHTML = `<button class="btn btn-ghost" style="color:#f8f3e8" data-close-busy>关闭</button>`;
        layer.querySelector('[data-close-busy]')?.addEventListener('click', () => layer.remove());
      },
    };
  }

  async function copyText(text) {
    try {
      await navigator.clipboard.writeText(text);
      toast('已复制到剪贴板', 'success');
    } catch (_) {
      const input = document.createElement('textarea');
      input.value = text;
      document.body.appendChild(input);
      input.select();
      try { document.execCommand('copy'); toast('已复制到剪贴板', 'success'); }
      catch (err) { toast('复制失败，请手动选择', 'error'); }
      input.remove();
    }
  }

  function downloadUrl(url) {
    const link = document.createElement('a');
    link.href = url;
    link.rel = 'noopener';
    document.body.appendChild(link);
    link.click();
    link.remove();
  }

  function openExternal(url) {
    if (!url) return;
    if (window.pywebview?.api?.open_external) {
      window.pywebview.api.open_external(url);
    } else {
      window.open(url, '_blank', 'noopener,noreferrer');
    }
  }

  /* ------------------------------------------------------------------ draft */
  const DRAFT_KEY = 'qiming_draft_v1';
  function saveDraft(immediate = false) {
    if (!state.outline) return;
    const snapshot = {
      prompt: state.create.prompt,
      create: state.create,
      outline: state.outline,
      template: state.template,
      templateUseImage: state.templateUseImage,
      references: state.references,
      useReferenceCover: state.useReferenceCover,
      readingText: state.readingText,
      readingTitle: state.readingTitle,
      readingSource: state.readingSource,
      projectId: state.project?.id || null,
      savedAt: new Date().toISOString(),
    };
    try { localStorage.setItem(DRAFT_KEY, JSON.stringify(snapshot)); } catch (_) {}
    state.draftSnapshot = snapshot;
    saveReferenceIds();
  }
  function saveReferenceIds() {
    try {
      localStorage.setItem('qiming_reference_ids_v1', JSON.stringify((state.references || []).map((item) => item.id)));
    } catch (_) {}
  }
  async function restoreReferences() {
    if (!state.user) return;
    let ids = [];
    try {
      ids = JSON.parse(localStorage.getItem('qiming_reference_ids_v1') || '[]');
    } catch (_) { ids = []; }
    if (!Array.isArray(ids) || !ids.length) return;
    try {
      const data = await api(`/api/references?ids=${ids.join(',')}`);
      state.references = data.items || [];
      if (!state.references.some((item) => item.kind === 'image')) state.useReferenceCover = false;
    } catch (_) {
      state.references = [];
    }
  }
  function readDraft() {
    try {
      const raw = localStorage.getItem(DRAFT_KEY);
      if (!raw) return null;
      const data = JSON.parse(raw);
      if (!data?.outline?.slides?.length) return null;
      return data;
    } catch (_) { return null; }
  }
  function clearDraft() {
    try { localStorage.removeItem(DRAFT_KEY); } catch (_) {}
    state.draftSnapshot = null;
  }
  /* ------------------------------------------------------------- slide view */
  function pvFooter(index, total, label) {
    return `<div class="pv-footer"><span>${e(label || '')}</span><span class="pv-page">${String(index + 1).padStart(2, '0')} / ${String(total).padStart(2, '0')}</span></div>`;
  }

  function renderSlide(slide, theme, index = 0, total = 1) {
    const t = themeOf(theme);
    const c = t.colors;
    const type = slide?.type || 'bullets';
    const title = String(slide?.title || '未命名页面');
    const subtitle = String(slide?.subtitle || '');
    const eyebrow = String(slide?.eyebrow || '');
    const bullets = Array.isArray(slide?.bullets) ? slide.bullets.slice(0, 4) : [];
    const style = `style="${themeVars(t)}"`;
    const foot = pvFooter(index, total, eyebrow || (type === 'section' ? 'SECTION' : ''));
    const titleClass = title.length > 22 ? 'long' : '';

    if (type === 'cover') {
      return `<div class="pv pv-cover" ${style}>
        <div class="pv-art"></div><div class="pv-ring one"></div><div class="pv-ring two"></div>
        <div class="pv-eyebrow">${e(eyebrow || '2026 · 主题分享')}</div>
        <div class="pv-title ${title.length > 21 ? 'long' : ''}">${e(title)}</div>
        <div class="pv-rule"></div>
        <div class="pv-sub">${e(subtitle || '从洞察到行动的一份完整提案')}</div>
        <div class="pv-meta">2026 · PRESENTATION</div>
        <div class="pv-index">01</div>
      </div>`;
    }

    if (type === 'agenda') {
      const cards = (bullets.length ? bullets : ['01 内容展开 · 从一个清晰的问题开始']).slice(0, 4).map((raw, i) => {
        const match = String(raw).match(/^(\d{1,2})\s+(.*?)\s*[·\-]\s*(.*)$/);
        const name = match ? match[2] : String(raw);
        const desc = match ? match[3] : '';
        return `<div class="pv-card"><span class="pv-num">${String(i + 1).padStart(2, '0')}</span><div class="pv-card-body"><strong>${e(name)}</strong><span>${e(desc)}</span></div></div>`;
      }).join('');
      return `<div class="pv pv-inner pv-agenda" ${style}>
        <div class="pv-eyebrow">${e(eyebrow || 'CONTENTS')}</div>
        <div class="pv-title ${titleClass}">${e(title)}</div>
        ${subtitle ? `<div class="pv-sub">${e(subtitle)}</div>` : ''}
        <div class="pv-cards">${cards}</div>
        <div class="pv-giant">目录</div>${foot}
      </div>`;
    }

    if (type === 'section') {
      const number = (String(eyebrow).match(/\d{1,2}/) || [String(index + 1).padStart(2, '0')])[0];
      return `<div class="pv pv-section" ${style}>
        <div class="pv-big">${e(number)}</div><div class="pv-ring one"></div>
        <div class="pv-content">
          <div class="pv-eyebrow">${e(eyebrow || 'SECTION')}</div>
          <div class="pv-title">${e(title)}</div>
          <div class="pv-sub">${e(subtitle)}</div>
          <div class="pv-rule"></div>
        </div>${foot}
      </div>`;
    }

    if (type === 'stats') {
      const stats = (Array.isArray(slide?.stats) ? slide.stats : []).slice(0, 3);
      const safeStats = stats.length ? stats : [
        { value: '3', label: '关键动作', note: '先聚焦，再扩展' },
        { value: '90', label: '验证周期', note: '建议按实际调整' },
        { value: '1', label: '反馈机制', note: '让数据持续回流' },
      ];
      return `<div class="pv pv-inner pv-stats" ${style}>
        <div class="pv-eyebrow">${e(eyebrow || 'MEASURE')}</div>
        <div class="pv-title ${titleClass}">${e(title)}</div>
        ${subtitle ? `<div class="pv-sub">${e(subtitle)}</div>` : ''}
        <div class="pv-stat-row">${safeStats.map((s) => `<div class="pv-stat"><div class="v">${e(s.value)}</div><div class="l">${e(s.label)}</div><div class="n">${e(s.note)}</div></div>`).join('')}</div>
        ${foot}
      </div>`;
    }

    if (type === 'quote') {
      const quote = slide?.quote || '把问题讲清楚，答案就已经出现了一半。';
      return `<div class="pv pv-quote" ${style}>
        <div class="mark">“</div>
        <div class="q">${e(quote)}</div>
        <div class="line"></div>
        <div class="a">—— ${e(slide?.author || '本次分享')}</div>
        <div class="pv-ring one" style="width:calc(var(--pv-unit) * 24);height:calc(var(--pv-unit) * 24);right:calc(var(--pv-unit) * 5);bottom:calc(var(--pv-unit) * -6);top:auto;opacity:.25"></div>
        ${foot}
      </div>`;
    }

    if (type === 'reading') {
      const passage = String(slide?.reading_text || slide?.notes || '课文会显示在这里。');
      const short = passage.length > 760 ? `${passage.slice(0, 760)}……` : passage;
      return `<div class="pv pv-inner pv-reading" ${style}>
        <div class="pv-eyebrow">${e(eyebrow || 'READING · 课文朗读')}</div>
        <div class="pv-title ${titleClass}">${e(title)}</div>
        <div class="pv-sub">${e(subtitle || '请跟着旁白朗读')}</div>
        <div class="pv-reading-text">${e(short).replace(/\n/g, '<br>')}</div>
        <div class="pv-reading-audio">${icon('audio', 11)} 进入页面自动朗读</div>
        ${foot}
      </div>`;
    }

    if (type === 'summary') {
      return `<div class="pv pv-inner pv-summary" ${style}>
        <div class="pv-eyebrow">${e(eyebrow || 'TAKEAWAYS')}</div>
        <div class="pv-title ${titleClass}">${e(title)}</div>
        ${subtitle ? `<div class="pv-sub">${e(subtitle)}</div>` : ''}
        <div class="pv-takeaways">
          ${(bullets.length ? bullets : ['定义问题', '建立方法', '盯住反馈']).map((b, i) => `<div class="pv-takeaway"><span class="no">${String(i + 1).padStart(2, '0')}</span><p>${e(b)}</p></div>`).join('')}
        </div>${foot}
      </div>`;
    }

    if (type === 'end') {
      return `<div class="pv pv-end" ${style}>
        <div class="pv-ring one"></div>
        <div class="pv-eyebrow">${e(eyebrow || 'THANK YOU')}</div>
        <div class="title">${e(title || '谢谢聆听')}</div>
        <div class="line"></div>
        <div class="sub">${e(subtitle || '欢迎交流与提问')}</div>
        <div class="thanks-mark">Thanks</div>
      </div>`;
    }

    if (index % 3 === 1 && bullets.length > 1) {
      return `<div class="pv pv-inner pv-bullets" ${style}>
        <div class="pv-top"><div><div class="pv-eyebrow">${e(eyebrow || 'INSIGHT')}</div><div class="pv-title ${titleClass}">${e(title)}</div>${subtitle ? `<div class="pv-sub">${e(subtitle)}</div>` : ''}</div><div class="pv-section-tag">${String(index + 1).padStart(2, '0')}</div></div>
        <div class="pv-cards">${bullets.slice(0, 4).map((b, i) => `<div class="pv-card"><div class="accent"></div><div class="idx">${String(i + 1).padStart(2, '0')}</div><p>${e(b)}</p></div>`).join('')}</div>
        ${foot}
      </div>`;
    }

    return `<div class="pv pv-inner pv-bullets" ${style}>
      <div class="pv-top"><div><div class="pv-eyebrow">${e(eyebrow || 'INSIGHT')}</div><div class="pv-title ${titleClass}">${e(title)}</div>${subtitle ? `<div class="pv-sub">${e(subtitle)}</div>` : ''}</div><div class="pv-section-tag">${String(index + 1).padStart(2, '0')}</div></div>
      <div class="pv-bullet-list right">
        ${(bullets.length ? bullets : ['把问题定义清楚', '找到关键变量', '开始一个最小行动']).map((b, i) => `<div class="pv-bullet"><span class="pv-chip">${i + 1}</span><span class="pv-bullet-text">${e(b)}</span></div>`).join('')}
      </div>
      <div class="pv-big-index">${String(index + 1).padStart(2, '0')}</div>
      ${foot}
    </div>`;
  }

  function onlineCover(t) {
    const src = t.thumb_url || '';
    return `<div class="online-cover"><img src="${e(src)}" alt="" loading="lazy"><div class="oc-shade"></div><div class="oc-copy"><span>${e(t.category || '联网灵感')}</span><strong>${e(t.name || '在线灵感')}</strong></div></div>`;
  }

  function templateThumb(t, index = 0) {
    if (t.thumb_url) return onlineCover(t);
    const english = state.create.language === 'en';
    const sample = {
      type: 'cover',
      eyebrow: t.category || 'THEME',
      title: english ? 'Ideas, made visible.' : '想法，被看见。',
      subtitle: t.description || (english ? 'A presentation with judgment and rhythm.' : '一份有判断、有节奏的演示。'),
    };
    return renderSlide(sample, t, 0, 1);
  }

  function projectCover(project) {
    const outline = project?.outline;
    const first = outline?.slides?.[0];
    return renderSlide(first || { type: 'cover', title: project?.title || '未命名演示', subtitle: '', eyebrow: 'PRESENTATION' }, project?.template, 0, Math.max(1, outline?.slides?.length || 1));
  }

  /* --------------------------------------------------------------- navigation */
  function navigate(hash) {
    if (!hash.startsWith('#')) hash = `#${hash}`;
    if (location.hash === hash) {
      handleRoute();
    } else {
      location.hash = hash;
    }
  }

  function clearViewTimers() {
    state.viewToken += 1;
    if (state.generationTimer) { clearInterval(state.generationTimer); state.generationTimer = null; }
    if (state.projectTimer) { clearInterval(state.projectTimer); state.projectTimer = null; }
    if (state.player.timer) { clearInterval(state.player.timer); state.player.timer = null; }
    if (window.speechSynthesis) window.speechSynthesis.cancel();
  }

  function closePlayer() {
    document.querySelector('.player-overlay')?.remove();
    document.body.classList.remove('modal-open');
    if (state.player.timer) { clearInterval(state.player.timer); state.player.timer = null; }
    if (window.speechSynthesis) window.speechSynthesis.cancel();
    state.player.playing = false;
  }

  /* ------------------------------------------------------------------- auth */
  function renderAuth(mode = 'login') {
    authRendering = true;
    const registrationOpen = state.meta?.registration_enabled !== false;
    if (mode === 'register' && !registrationOpen) mode = 'login';
    state.authMode = mode;
    state.user = null;
    const isRegister = mode === 'register';
    const emailVerification = isRegister && state.meta?.email_verification_enabled === true;
    const emailReady = state.meta?.email_verification_ready !== false;
    if (state.codeTimer) { clearInterval(state.codeTimer); state.codeTimer = null; }
    root.innerHTML = `
      <div class="auth-shell">
        <section class="auth-visual">
          <div class="auth-orb one"></div><div class="auth-orb two"></div><div class="auth-orb three"></div>
          <div class="auth-brand">
            ${logoMark(38)}
            <div><div class="brand-name">启明 PPT</div><div class="brand-sub">QIMING STUDIO</div></div>
          </div>
          <div class="auth-visual-main">
            <div class="auth-kicker">AI PRESENTATION STUDIO</div>
            <h1 class="auth-headline">把想法，<br>讲成一场<em>好戏</em>。</h1>
            <p class="auth-lead">从一个模糊的念头，到结构清晰的大纲、好看的模板，再到会动的幻灯片。启明把整条创作链路，收进一个安静的工作台。</p>
            <div class="auth-features">
              <div class="auth-feature"><span class="feature-ic">${icon('wand', 15)}</span><div><strong>AI 先帮你想清楚</strong><span>领域化叙事大纲，可逐页编辑</span></div></div>
              <div class="auth-feature"><span class="feature-ic">${icon('palette', 15)}</span><div><strong>20 套原创主题</strong><span>还能联网寻找灵感与配色</span></div></div>
              <div class="auth-feature"><span class="feature-ic">${icon('zap', 15)}</span><div><strong>每一页都动起来</strong><span>元素入场 + 翻页转场 + 旁白</span></div></div>
              <div class="auth-feature"><span class="feature-ic">${icon('download', 15)}</span><div><strong>无水印导出</strong><span>PPTX / PDF，完全免费</span></div></div>
            </div>
          </div>
          <div class="auth-bottom"><span>LOCAL-FIRST · YOUR DATA STAYS HERE</span><span>EST. 2026</span></div>
        </section>
        <section class="auth-panel">
          <div class="auth-card">
            <div class="auth-mobile-brand">${logoMark(34)}<strong>启明 PPT</strong></div>
            <h2 class="auth-title">${isRegister ? '创建你的工作台' : '欢迎回来'}</h2>
            <p class="auth-desc">${isRegister ? (emailVerification ? '输入邀请码，并完成邮箱验证码校验，开启你的创作工作台。' : '输入管理员提供的邀请码，开启一段把想法讲清楚的旅程。') : '登录后，继续完成你的上一场演示。'}</p>
            <div class="auth-tabs">
              <button class="auth-tab ${!isRegister ? 'active' : ''}" data-auth-mode="login">登录</button>
              <button class="auth-tab ${isRegister ? 'active' : ''}" data-auth-mode="register" ${registrationOpen ? '' : 'disabled title="管理员已暂停注册"'}>${registrationOpen ? '注册' : '注册已暂停'}</button>
            </div>
            <form class="auth-form" id="auth-form" novalidate>
              ${isRegister ? `
                <div class="form-row">
                  <div class="field" data-field="display_name"><label class="field-label" for="display_name">昵称</label><input class="input" id="display_name" name="display_name" autocomplete="nickname" placeholder="怎么称呼你" maxlength="30"></div>
                  <div class="field" data-field="username"><label class="field-label" for="username">用户名</label><input class="input" id="username" name="username" autocomplete="username" placeholder="3—20 位" maxlength="20"></div>
                </div>
                <div class="field invite-highlight" data-field="invite_code">
                  <label class="field-label" for="invite_code">邀请码 <small>必填</small></label>
                  <div class="input-wrap">${icon('key', 17)}<input class="input" id="invite_code" name="invite_code" placeholder="请输入管理员提供的邀请码" autocomplete="off"></div>
                  <div class="invite-lock">${icon('lock', 13)}<span>仅持有指定邀请码的用户可以注册。邀请码区分大小写。</span></div>
                </div>
                <div class="field" data-field="email"><label class="field-label" for="email">邮箱 ${emailVerification ? '<small>必填 · 接收验证码</small>' : '<small>选填</small>'}</label><input class="input" id="email" name="email" type="email" autocomplete="email" placeholder="${emailVerification ? '用于接收注册验证码' : '用于找回账号（选填）'}"></div>
                ${emailVerification ? `<div class="field" data-field="email_code">
                  <label class="field-label" for="email_code">邮箱验证码 <small>6 位数字 · 10 分钟内有效</small></label>
                  <div class="code-row"><input class="input" id="email_code" name="email_code" inputmode="numeric" autocomplete="one-time-code" maxlength="6" placeholder="请输入验证码"><button class="btn btn-outline code-send-btn" type="button" data-action="send-code" ${emailReady ? '' : 'disabled'}>获取验证码</button></div>
                  <div class="hint" id="code-hint">${emailReady ? '验证码会发送到你填写的邮箱，请同时检查垃圾邮件。' : '管理员尚未配置发件邮箱，暂时无法发送验证码。'}</div>
                </div>` : ''}
                <div class="field" data-field="password"><label class="field-label" for="password">设置密码 <small>至少 6 位</small></label><div class="input-wrap">${icon('lock', 17)}<input class="input" id="password" name="password" type="password" autocomplete="new-password" placeholder="至少 6 位字符"><button class="btn btn-icon btn-sm btn-ghost password-toggle" type="button" data-toggle-password="password" aria-label="显示密码">${icon('eye', 15)}</button></div></div>
              ` : `
                <div class="field" data-field="username"><label class="field-label" for="username">用户名</label><div class="input-wrap">${icon('user', 17)}<input class="input" id="username" name="username" autocomplete="username" placeholder="输入用户名" autofocus></div></div>
                <div class="field" data-field="password"><label class="field-label" for="password">密码</label><div class="input-wrap">${icon('lock', 17)}<input class="input" id="password" name="password" type="password" autocomplete="current-password" placeholder="输入密码"><button class="btn btn-icon btn-sm btn-ghost password-toggle" type="button" data-toggle-password="password" aria-label="显示密码">${icon('eye', 15)}</button></div></div>
              `}
              <button class="btn btn-primary btn-lg btn-block auth-submit" type="submit" id="auth-submit">${isRegister ? '注册并进入' : '登录'}</button>
              <div class="error-text" id="auth-error" style="display:none;text-align:center"></div>
            </form>
            <div class="auth-switch-line">${registrationOpen ? (isRegister ? `已经有账号？<button data-auth-mode="login">直接登录</button>` : `还没有账号？<button data-auth-mode="register">使用邀请码注册</button>`) : '新用户注册已暂停，请联系管理员。'}</div>
            <div class="auth-note">启明 PPT 完全免费 · 导出无水印 · 数据保存在本机<br><a href="/admin">管理员入口</a></div>
          </div>
        </section>
      </div>`;
    authRendering = false;
    $$('[data-auth-mode]').forEach((btn) => btn.addEventListener('click', () => renderAuth(btn.dataset.authMode)));
    $$('[data-toggle-password]').forEach((btn) => {
      btn.addEventListener('click', () => {
        const input = document.getElementById(btn.dataset.togglePassword);
        if (!input) return;
        const visible = input.type === 'text';
        input.type = visible ? 'password' : 'text';
        btn.innerHTML = icon(visible ? 'eye' : 'eyeOff', 15);
      });
    });
    $('#auth-form')?.addEventListener('submit', submitAuth);
    $('[data-action="send-code"]')?.addEventListener('click', sendEmailCode);
    if (isRegister && emailVerification && state.codeCooldownUntil > Date.now()) {
      startCodeCountdown(Math.ceil((state.codeCooldownUntil - Date.now()) / 1000));
    }
    setTimeout(() => document.getElementById(isRegister ? 'display_name' : 'username')?.focus(), 120);
  }

  function startCodeCountdown(seconds = 60) {
    if (state.codeTimer) clearInterval(state.codeTimer);
    state.codeCooldownUntil = Date.now() + Math.max(0, seconds) * 1000;
    const render = () => {
      const button = $('[data-action="send-code"]');
      if (!button) return;
      const left = Math.ceil((state.codeCooldownUntil - Date.now()) / 1000);
      if (left <= 0) {
        clearInterval(state.codeTimer);
        state.codeTimer = null;
        button.disabled = false;
        button.textContent = '重新获取';
        const hint = document.getElementById('code-hint');
        if (hint) hint.textContent = '如果没有收到，请检查垃圾邮件，或 60 秒后重新发送。';
      } else {
        button.disabled = true;
        button.textContent = `${left}s 后重发`;
      }
    };
    render();
    if (state.codeCooldownUntil > Date.now()) state.codeTimer = setInterval(render, 1000);
  }

  async function sendEmailCode() {
    const form = document.getElementById('auth-form');
    if (!form) return;
    const email = document.getElementById('email')?.value.trim() || '';
    const invite = document.getElementById('invite_code')?.value.trim() || '';
    const errorBox = document.getElementById('auth-error');
    const button = $('[data-action="send-code"]');
    const hint = document.getElementById('code-hint');
    const fail = (message, fieldName) => {
      if (errorBox) { errorBox.textContent = message; errorBox.style.display = 'block'; }
      $$('.field.has-error', form).forEach((node) => node.classList.remove('has-error'));
      if (fieldName) {
        const field = form.querySelector(`[data-field="${fieldName}"]`);
        field?.classList.add('has-error');
        field?.querySelector('input')?.focus();
      }
      if (button) { button.disabled = false; button.textContent = '获取验证码'; }
    };
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) return fail('请先填写正确的邮箱地址', 'email');
    if (!invite) return fail('请先填写邀请码', 'invite_code');
    if (errorBox) errorBox.style.display = 'none';
    if (button) { button.disabled = true; button.innerHTML = '<span class="spinner dark"></span> 发送中'; }
    if (hint) hint.textContent = '正在连接邮件服务…';
    try {
      const data = await api('/api/auth/send-code', {
        method: 'POST',
        body: { email, invite_code: invite },
      });
      if (hint) hint.textContent = `验证码已发送到 ${email}，10 分钟内有效。`;
      toast('验证码已发送', 'success', '请检查收件箱与垃圾邮件');
      startCodeCountdown(data.cooldown || 60);
      document.getElementById('email_code')?.focus();
    } catch (err) {
      if (err.data?.cooldown) startCodeCountdown(err.data.cooldown);
      else if (button) { button.disabled = false; button.textContent = '获取验证码'; }
      if (hint) hint.textContent = err.message || '发送失败，请稍后重试';
      if (errorBox) { errorBox.textContent = err.message || '发送失败'; errorBox.style.display = 'block'; }
      if (err.data?.field) {
        const field = form.querySelector(`[data-field="${err.data.field}"]`);
        field?.classList.add('has-error');
      }
    }
  }

  async function submitAuth(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const button = $('#auth-submit');
    const errorBox = $('#auth-error');
    if (!button) return;
    const data = Object.fromEntries(new FormData(form).entries());
    const isRegister = state.authMode === 'register';
    const emailVerification = isRegister && state.meta?.email_verification_enabled === true;
    const fail = (message, fieldName) => {
      errorBox.textContent = message;
      errorBox.style.display = 'block';
      $$('.field.has-error', form).forEach((node) => node.classList.remove('has-error'));
      if (fieldName) {
        const field = form.querySelector(`[data-field="${fieldName}"]`);
        field?.classList.add('has-error');
        field?.querySelector('input')?.focus();
      }
      button.disabled = false;
      button.innerHTML = isRegister ? '注册并进入' : '登录';
    };
    errorBox.style.display = 'none';
    if (!data.username?.trim()) return fail('请输入用户名', 'username');
    if (!data.password) return fail('请输入密码', 'password');
    if (isRegister && !data.invite_code?.trim()) return fail('请填写邀请码', 'invite_code');
    if (isRegister && String(data.password).length < 6) return fail('密码至少需要 6 位', 'password');
    if (emailVerification) {
      if (!data.email?.trim()) return fail('请填写用于接收验证码的邮箱', 'email');
      if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(data.email.trim())) return fail('邮箱格式不正确', 'email');
      if (!state.meta?.email_verification_ready) return fail('管理员尚未完成邮件服务配置', 'email');
      if (!data.email_code?.trim()) return fail('请填写邮箱验证码', 'email_code');
      if (!/^\d{6}$/.test(data.email_code.trim())) return fail('验证码应为 6 位数字', 'email_code');
    } else if (isRegister && data.email?.trim() && !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(data.email.trim())) {
      return fail('邮箱格式不正确', 'email');
    }
    button.disabled = true;
    button.innerHTML = `<span class="spinner"></span>${isRegister ? '正在创建…' : '正在登录…'}`;
    try {
      const path = isRegister ? '/api/auth/register' : '/api/auth/login';
      const response = await api(path, { method: 'POST', body: data });
      if (state.codeTimer) { clearInterval(state.codeTimer); state.codeTimer = null; }
      state.codeCooldownUntil = 0;
      state.user = response.user;
      state.meta.user = response.user;
      if (!state.templates.length) await loadTemplates();
      toast(isRegister ? '注册成功，欢迎来到启明' : '登录成功', 'success', response.user.display_name || response.user.username);
      await enterApp();
      if (response.user.role === 'admin') toast('管理员账号已登录', 'info', '左侧菜单可进入管理后台');
    } catch (err) {
      fail(err.message || '操作失败', err.data?.field);
    }
  }

  /* ------------------------------------------------------------------- boot */
  async function loadTemplates() {
    try {
      const data = await api('/api/templates');
      state.templates = data.items || [];
      state.categories = data.categories || ['全部'];
      state.featured = data.featured || [];
    } catch (err) {
      state.templates = [];
      state.categories = ['全部'];
    }
  }

  async function bootApp() {
    try {
      const meta = await api('/api/meta');
      state.meta = meta;
      state.user = meta.user;
      state.categories = meta.categories || ['全部'];
      state.featured = meta.featured || [];
      state.create = {
        ...state.create,
        ...(meta.default_options ? {
          enable_search: false,
          include_agenda: true,
          include_summary: true,
          include_qa: true,
        } : {}),
      };
      await loadTemplates();
      state.draftSnapshot = readDraft();
      document.getElementById('boot')?.classList.add('done');
      setTimeout(() => document.getElementById('boot')?.remove(), 600);
      if (state.user) {
        await enterApp();
      } else {
        renderAuth('login');
      }
    } catch (err) {
      document.getElementById('boot')?.classList.add('done');
      setTimeout(() => document.getElementById('boot')?.remove(), 600);
      renderAuth('login');
      setTimeout(() => toast('无法连接本地服务，请重新启动启明 PPT', 'error', err.message), 400);
    }
  }

  async function enterApp() {
    if (!state.user) return;
    if (!location.hash) history.replaceState(null, '', '#/dashboard');
    await restoreReferences();
    await handleRoute();
    // Close the mobile sidebar when the viewport is narrow.
    document.querySelector('.sidebar')?.classList.remove('open');
  }

  /* --------------------------------------------------------------- app shell */
  const NAV_FOR_ROUTE = {
    dashboard: 'dashboard', projects: 'projects', create: 'create', outline: 'create',
    'pick-template': 'create', generate: 'create', library: 'library', settings: 'settings',
    project: 'projects',
  };

  function navItem(href, iconName, label, key, active, extra = '') {
    return `<a class="nav-item ${active === key ? 'active' : ''} ${extra}" href="${href}" data-nav="${href}">${icon(iconName, 18)}<span>${label}</span></a>`;
  }

  function renderShell({ title, subtitle, content, active = 'dashboard', actions = '' }) {
    const user = state.user || {};
    const isAdmin = user.role === 'admin';
    root.innerHTML = `
      <div class="shell">
        <aside class="sidebar" id="sidebar">
          <a class="side-brand" href="#/dashboard" data-nav="#/dashboard">
            ${logoMark(38)}
            <div class="brand-text"><div class="name">启明 PPT</div><div class="sub">QIMING STUDIO</div></div>
          </a>
          <nav class="side-nav">
            <div class="nav-label">工作台</div>
            ${navItem('#/dashboard', 'dashboard', '总览', 'dashboard', active)}
            ${navItem('#/projects', 'folder', '我的项目', 'projects', active)}
            ${navItem('#/create', 'plus', '新建演示', 'create', active, 'nav-create')}
            <div class="nav-label">灵感</div>
            ${navItem('#/library', 'grid', '模板库', 'library', active)}
            ${navItem('#/settings', 'settings', 'AI 与账户', 'settings', active)}
            ${isAdmin ? `<div class="nav-label">系统</div>${navItem('/admin', 'shield', '管理后台', 'admin', active, 'js-admin-link')}` : ''}
          </nav>
          <div class="sidebar-spacer"></div>
          <div class="side-promo">
            <h4>永久免费 · 无水印</h4>
            <p>从大纲到动画，所有能力都在这台电脑上完成。你的内容只属于你。</p>
            <span class="promo-tag">NO WATERMARK / NO PAYWALL</span>
          </div>
          <div class="side-user">
            ${avatar(user)}
            <div class="who"><strong>${e(user.display_name || user.username)}</strong><span>${isAdmin ? '管理员' : '创作者'} · ${e(user.username)}</span></div>
            <button class="logout-btn" data-action="logout" title="退出登录" aria-label="退出登录">${icon('logout', 15)}</button>
          </div>
          <div class="sidebar-foot"><span>v${e(state.meta?.app?.version || '1.5.0')}</span><span>LOCAL</span></div>
        </aside>
        <div class="main">
          <header class="topbar">
            <button class="btn btn-icon btn-ghost mobile-menu-btn" data-action="toggle-sidebar" aria-label="打开导航">${icon('menu', 18)}</button>
            <div class="topbar-left">
              <div class="crumb"><span>工作台</span><span class="sep">/</span><span class="current">${e(title)}</span></div>
            </div>
            <div class="topbar-actions">
              <span class="free-pill"><span class="dot"></span>永久免费 · 无水印</span>
              ${actions}
              <button class="btn btn-icon btn-outline" data-action="open-settings" title="设置" aria-label="设置">${icon('settings', 17)}</button>
            </div>
          </header>
          <main class="page">
            ${content}
          </main>
        </div>
      </div>`;
    bindShell();
  }

  function bindShell() {
    // data-nav links are handled by the global delegated click listener.
    $$('.nav-item').forEach((item) => {
      if (item.dataset.nav?.startsWith('/')) item.addEventListener('click', (event) => { event.preventDefault(); location.href = item.dataset.nav; });
    });
    document.querySelector('[data-action="logout"]')?.addEventListener('click', async () => {
      const yes = await confirmDialog({ title: '退出登录', message: '退出后需要重新登录才能继续创作。', confirmText: '退出登录' });
      if (!yes) return;
      try { await api('/api/auth/logout', { method: 'POST' }); } catch (_) {}
      state.user = null;
      state.references = [];
      state.useReferenceCover = false;
      state.readingText = '';
      state.readingTitle = '';
      state.readingSource = '';
      try { localStorage.removeItem('qiming_reference_ids_v1'); } catch (_) {}
      clearViewTimers();
      closeModal();
      renderAuth('login');
      toast('已退出登录', 'info');
    });
    document.querySelector('[data-action="toggle-sidebar"]')?.addEventListener('click', () => {
      document.querySelector('.sidebar')?.classList.toggle('open');
    });
    document.querySelector('[data-action="open-settings"]')?.addEventListener('click', () => navigate('#/settings'));
    document.querySelector('.js-admin-link')?.addEventListener('click', (event) => {
      event.preventDefault();
      location.href = '/admin';
    });
  }

  function pageHead(title, subtitle, actions = '') {
    return `<div class="page-head"><div><h1 class="page-title">${title}</h1>${subtitle ? `<p class="page-sub">${subtitle}</p>` : ''}</div>${actions ? `<div class="page-actions">${actions}</div>` : ''}</div>`;
  }

  function flowSteps(current) {
    const steps = [
      ['描述想法', 1], ['AI 大纲', 2], ['选择模板', 3], ['生成下载', 4],
    ];
    return `<div class="flow-steps">${steps.map(([label, no], index) => {
      const cls = no < current ? 'done' : no === current ? 'active' : '';
      return `<div class="flow-step ${cls}"><span class="step-no">${no < current ? icon('check', 10) : no}</span>${label}</div>${index < steps.length - 1 ? '<span class="flow-divider"></span>' : ''}`;
    }).join('')}</div>`;
  }

  function providerOptions(selected) {
    const active = state.meta?.active_provider || 'local';
    const providers = [
      ['auto', '自动', '推荐'],
      ['deepseek', 'DeepSeek', '深度思考'],
      ['doubao', '豆包', '火山方舟'],
      ['custom', '自定义', 'OpenAI 兼容'],
      ['local', '内置 AI', '离线可用'],
    ];
    return `<div class="provider-select">${providers.map(([key, name, hint]) => `<button type="button" class="provider-option ${selected === key ? 'active' : ''}" data-create-provider="${key}">${name}<small>${hint}${key === active ? ' · 已配置' : ''}</small></button>`).join('')}</div>`;
  }

  /* ------------------------------------------------------------------ routes */
  async function handleRoute() {
    if (!state.user) { renderAuth('login'); return; }
    const hash = (location.hash || '#/dashboard').replace(/^#\/?/, '');
    const parts = hash.split('/').filter(Boolean);
    const view = parts[0] || 'dashboard';
    state.route = view;
    const token = ++state.viewToken;
    // Reset transient timers for the previous view.
    if (state.generationTimer) { clearInterval(state.generationTimer); state.generationTimer = null; }
    if (state.projectTimer) { clearInterval(state.projectTimer); state.projectTimer = null; }
    closePlayer();
    window.scrollTo({ top: 0, behavior: 'instant' });
    try {
      if (view === 'dashboard') return await renderDashboard(token);
      if (view === 'projects') return await renderProjects(token);
      if (view === 'create') return renderCreate();
      if (view === 'outline') return renderOutline();
      if (view === 'pick-template') return renderPickTemplate(token);
      if (view === 'generate') return await renderGenerate(token);
      if (view === 'library') return renderLibrary();
      if (view === 'settings') return await renderSettings(token);
      if (view === 'project') return await renderProjectDetail(Number(parts[1]), token);
      navigate('#/dashboard');
    } catch (err) {
      console.error(err);
      renderShell({ title: '出了点问题', content: `<div class="empty"><div class="empty-icon">${icon('alert', 24)}</div><h3>页面加载失败</h3><p>${e(err.message)}</p><button class="btn btn-primary" data-nav="#/dashboard" style="margin-top:18px">回到总览</button></div>`, active: 'dashboard' });
    }
  }

  window.addEventListener('hashchange', () => {
    if (!state.user) return;
    handleRoute();
  });

  window.addEventListener('beforeunload', () => {
    if (state.outline) saveDraft();
  });

  document.addEventListener('click', (event) => {
    const nav = event.target.closest('[data-nav]');
    if (nav) {
      const href = nav.dataset.nav;
      if (href.startsWith('/')) return;
      event.preventDefault();
      document.querySelector('.sidebar')?.classList.remove('open');
      navigate(href);
      return;
    }
    if (event.target.matches('[data-modal-backdrop]')) closeModal();
  });

  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') {
      if (document.querySelector('.player-overlay')) closePlayer();
      else if ($('[data-modal-backdrop]')) closeModal();
      else document.querySelector('.sidebar')?.classList.remove('open');
      return;
    }
    if (document.querySelector('.player-overlay')) {
      if (event.key === 'ArrowLeft') { event.preventDefault(); window.__qimingPlayerPrev?.(); }
      if (event.key === 'ArrowRight' || event.key === ' ') { event.preventDefault(); window.__qimingPlayerNext?.(); }
    }
  });

  /* --------------------------------------------------------------- dashboard */
  async function renderDashboard(token) {
    renderShell({
      title: '总览',
      active: 'dashboard',
      content: `<div class="page-head"><div><h1 class="page-title">正在准备你的工作台</h1><p class="page-sub">稍等片刻，正在整理最近的作品。</p></div></div>
        <div class="dash-hero"><div class="hero-copy"><div class="skeleton" style="width:120px;height:12px;margin-bottom:18px"></div><div class="skeleton" style="width:70%;height:48px;margin-bottom:14px"></div><div class="skeleton" style="width:46%;height:14px"></div></div><div class="hero-art"></div></div>
        <div class="stats-grid">${[1, 2, 3, 4].map(() => '<div class="stat-card"><div class="skeleton" style="width:60%;height:10px"></div><div class="skeleton" style="width:42%;height:32px;margin-top:15px"></div></div>').join('')}</div>`,
    });
    let data;
    try {
      data = await api('/api/dashboard');
    } catch (err) {
      if (token !== state.viewToken) return;
      renderShell({ title: '总览', active: 'dashboard', content: `<div class="empty"><div class="empty-icon">${icon('alert', 24)}</div><h3>无法读取工作台</h3><p>${e(err.message)}</p></div>` });
      return;
    }
    if (token !== state.viewToken) return;
    const stats = data.stats || {};
    const recent = data.recent || [];
    const today = new Intl.DateTimeFormat('zh-CN', { month: 'long', day: 'numeric', weekday: 'long' }).format(new Date());
    const draft = state.draftSnapshot;
    const featured = (state.featured.length ? state.featured : state.templates.slice(0, 6).map((t) => t.id))
      .map((id) => templateById(id)).filter(Boolean).slice(0, 6);

    const content = `
      ${pageHead(`${greeting()}，${e(state.user?.display_name || '创作者')}`, `${today} · 把一个念头，变成一场值得被看见的演示。`, `<button class="btn btn-outline" data-nav="#/library">${icon('grid', 16)} 浏览模板</button><button class="btn btn-primary" data-nav="#/create">${icon('plus', 16)} 新建演示</button>`)}
      <section class="dash-hero">
        <div class="hero-copy">
          <div class="hero-kicker"><span class="dot"></span> AI PRESENTATION STUDIO</div>
          <h2 class="hero-title">不要从空白页开始。<br>从一个<em>好问题</em>开始。</h2>
          <p class="hero-sub">描述你想讲什么，启明会为你梳理叙事、生成大纲，再配上一套好看的模板。最后，让每一页、每一个元素都动起来。</p>
          <div class="hero-actions">
            <button class="btn btn-primary btn-lg" data-nav="#/create">${icon('sparkles', 17)} 开始一次创作</button>
            ${draft ? `<button class="btn btn-ghost" style="color:rgba(248,243,232,.7)" data-action="resume-draft">${icon('clock', 15)} 继续上次的「${e(String(draft.outline?.title || '大纲').slice(0, 12))}」</button>` : `<span class="hero-note">${icon('shield', 13)} 本地运行 · 内容不离开这台电脑</span>`}
          </div>
        </div>
        <div class="hero-art" aria-hidden="true">
          <div class="art-slide one"><div class="as-kicker">STRATEGY / 2026</div><div class="as-title">让复杂的事，<br>被简单看见。</div><div class="as-line"></div><div class="as-bars"><span></span><span></span></div><div class="as-ring"></div></div>
          <div class="art-slide two"><div class="as-kicker">AI OUTLINE</div><div class="as-title">从洞察<br>到行动</div><div class="as-line" style="background:#5eead4"></div><div class="as-bars"><span></span><span></span></div></div>
          <div class="art-slide three"><div class="as-kicker">MOTION</div><div class="as-title">每一页<br>都在呼吸</div></div>
          <div class="art-star">✦</div>
        </div>
      </section>

      <div class="stats-grid">
        <div class="stat-card accent"><div class="stat-label">${icon('folder', 14)} 我的演示</div><div class="stat-value">${stats.projects || 0}<small>份</small></div><div class="stat-foot">其中 ${stats.ready || 0} 份已完成</div></div>
        <div class="stat-card"><div class="stat-label">${icon('slides', 14)} 累计页面</div><div class="stat-value">${stats.slides || 0}<small>页</small></div><div class="stat-foot">每一页都是一次表达</div></div>
        <div class="stat-card"><div class="stat-label">${icon('download', 14)} 下载次数</div><div class="stat-value">${stats.downloads || 0}<small>次</small></div><div class="stat-foot">PPTX 与 PDF 均无水印</div></div>
        <div class="stat-card"><div class="stat-label">${icon('sparkles', 14)} 可用主题</div><div class="stat-value">${state.templates.length}<small>套</small></div><div class="stat-foot">另有联网灵感模板</div></div>
      </div>

      <div class="section-head"><h2 class="section-title">最近的作品 <span class="count">${recent.length}</span></h2><button class="section-link" data-nav="#/projects">查看全部 ${icon('arrowRight', 14)}</button></div>
      ${recent.length ? `<div class="project-grid">${recent.map(projectCard).join('')}</div>` : `
        <div class="empty"><div class="empty-icon">${icon('slides', 25)}</div><h3>你的第一份演示，正在等你</h3><p>不需要准备完整的文案。告诉我一个主题，AI 会先帮你把它想清楚。</p><button class="btn btn-primary" data-nav="#/create" style="margin-top:18px">${icon('plus', 15)} 创建第一份演示</button></div>`}

      <div class="section-head"><h2 class="section-title">精选模板 <span class="count">${featured.length}</span></h2><button class="section-link" data-nav="#/library">进入模板库 ${icon('arrowRight', 14)}</button></div>
      <div class="template-strip">${featured.map((t) => `<div class="tpl-mini" data-template-preview="${e(t.id)}"><div class="mini-thumb">${templateThumb(t)}</div><div class="mini-name"><span>${e(t.name)}</span><span>${e(t.category)}</span></div></div>`).join('')}</div>

      <div class="section-head"><h2 class="section-title">不知道讲什么？从这些开始</h2><span class="kicker">ONE IDEA IS ENOUGH</span></div>
      <div class="inspiration-grid">${EXAMPLE_PROMPTS.slice(0, 4).map((item) => `<button class="inspire-card" data-idea="${e(item.text)}"><span class="insp-ic">${icon(item.icon, 15)}</span><div><strong>${e(item.title)}</strong><span>${e(item.text.slice(0, 30))}…</span></div></button>`).join('')}</div>
    `;
    renderShell({ title: '总览', active: 'dashboard', content, actions: `<button class="btn btn-sm btn-outline" data-nav="#/create">${icon('plus', 14)} 新建</button>` });
    bindDashboard();
  }

  function bindDashboard() {
    $$('[data-template-preview]').forEach((node) => node.addEventListener('click', () => {
      const t = templateById(node.dataset.templatePreview);
      if (t) openTemplatePreview(t, { source: 'dashboard' });
    }));
    $$('[data-idea]').forEach((node) => node.addEventListener('click', () => {
      state.create.prompt = node.dataset.idea || '';
      navigate('#/create');
    }));
    $$('[data-project]').forEach((node) => node.addEventListener('click', (event) => {
      if (event.target.closest('[data-project-action]')) return;
      navigate(`#/project/${node.dataset.project}`);
    }));
    $('[data-action="resume-draft"]')?.addEventListener('click', resumeDraft);
  }

  async function resumeDraft() {
    const draft = state.draftSnapshot || readDraft();
    if (!draft) { toast('没有找到上次的草稿', 'info'); return; }
    state.create = { ...state.create, ...(draft.create || { prompt: draft.prompt || '' }) };
    state.outline = draft.outline;
    state.template = draft.template || null;
    state.templateUseImage = draft.templateUseImage !== false;
    state.references = draft.references || state.references || [];
    state.useReferenceCover = !!draft.useReferenceCover;
    state.readingText = draft.readingText || state.readingText || '';
    state.readingTitle = draft.readingTitle || state.readingTitle || '';
    state.readingSource = draft.readingSource || state.readingSource || '';
    state.selectedSlide = 0;
    if (draft.projectId) {
      try {
        const data = await api(`/api/projects/${draft.projectId}`);
        state.project = data.project;
        state.outline = data.project.outline || state.outline;
        state.template = data.project.template || state.template;
        if (data.project.references?.length) state.references = data.project.references;
      } catch (_) { state.project = null; }
    } else {
      state.project = null;
    }
    if (!state.references.length) await restoreReferences();
    navigate('#/outline');
  }

  function projectCard(project) {
    const status = project.status || 'draft';
    const badgeClass = status === 'ready' ? 'badge-mint' : status === 'failed' ? 'badge-coral' : status === 'generating' || status === 'running' || status === 'queued' ? 'badge-amber' : 'badge-muted';
    return `<article class="project-card" data-project="${project.id}">
      <div class="project-cover">${projectCover(project)}<span class="cover-badge badge ${badgeClass}">${statusLabel(status)}</span><span class="cover-play">${icon('play', 13)}</span></div>
      <div class="project-info">
        <h3 class="clamp-2">${e(project.title || '未命名演示')}</h3>
        <div class="project-meta"><span>${project.slide_count || 0} 页</span><i class="dot"></i><span>${e(project.template?.name || '自定义模板')}</span><i class="dot"></i><span>${e(project.updated_at_text || formatDate(project.updated_at))}</span></div>
        <div class="project-foot"><span class="status ${status}"><span class="dot"></span>${status === 'ready' ? `${project.download_count || 0} 次下载` : statusLabel(status)}</span><span class="open-link">${project.status === 'ready' ? '下载 / 查看' : '继续编辑'} ${icon('arrowRight', 12)}</span></div>
      </div>
    </article>`;
  }

  /* ---------------------------------------------------------------- projects */
  async function renderProjects(token) {
    renderShell({ title: '我的项目', active: 'projects', content: `<div class="page-head"><div><h1 class="page-title">我的项目</h1><p class="page-sub">正在整理你的作品…</p></div></div><div class="skeleton" style="height:200px;border-radius:20px"></div>` });
    let data;
    try { data = await api('/api/projects'); }
    catch (err) {
      if (token !== state.viewToken) return;
      renderShell({ title: '我的项目', active: 'projects', content: `<div class="empty"><div class="empty-icon">${icon('alert', 24)}</div><h3>读取失败</h3><p>${e(err.message)}</p></div>` });
      return;
    }
    if (token !== state.viewToken) return;
    state.projects = data.items || [];
    const content = `
      ${pageHead('我的项目', `共 ${state.projects.length} 份演示 · 草稿、生成中与已完成的作品都在这里。`, `<button class="btn btn-primary" data-nav="#/create">${icon('plus', 16)} 新建演示</button>`)}
      <div class="filter-row">
        <div class="chips" id="project-filters">
          ${['全部', '已完成', '草稿', '生成中'].map((label, i) => `<button class="chip ${i === 0 ? 'active' : ''}" data-project-filter="${label}">${label}</button>`).join('')}
        </div>
        <span class="count">${state.projects.length} 份作品</span>
      </div>
      <div id="project-list">${state.projects.length ? `<div class="project-grid">${state.projects.map(projectCard).join('')}</div>` : `<div class="empty"><div class="empty-icon">${icon('folder', 26)}</div><h3>这里还没有项目</h3><p>开始一次创作，你的第一份演示会出现在这里。</p><button class="btn btn-primary" data-nav="#/create" style="margin-top:18px">${icon('plus', 15)} 新建演示</button></div>`}</div>`;
    renderShell({ title: '我的项目', active: 'projects', content, actions: `<button class="btn btn-sm btn-outline" data-nav="#/create">${icon('plus', 14)} 新建</button>` });
    let currentFilter = '全部';
    const filterProjects = () => {
      const items = state.projects.filter((p) => {
        if (currentFilter === '全部') return true;
        if (currentFilter === '已完成') return p.status === 'ready';
        if (currentFilter === '草稿') return p.status === 'draft' || p.status === 'failed';
        return ['generating', 'running', 'queued'].includes(p.status);
      });
      const host = document.getElementById('project-list');
      if (!host) return;
      host.innerHTML = items.length ? `<div class="project-grid">${items.map(projectCard).join('')}</div>` : `<div class="empty"><div class="empty-icon">${icon('search', 24)}</div><h3>这个分类下还没有作品</h3><p>换一个筛选条件，或者开始新的创作。</p></div>`;
      $$('[data-project]', host).forEach((node) => node.addEventListener('click', () => navigate(`#/project/${node.dataset.project}`)));
    };
    $$('[data-project-filter]').forEach((btn) => btn.addEventListener('click', () => {
      currentFilter = btn.dataset.projectFilter;
      $$('[data-project-filter]').forEach((b) => b.classList.toggle('active', b === btn));
      filterProjects();
    }));
    $$('[data-project]').forEach((node) => node.addEventListener('click', () => navigate(`#/project/${node.dataset.project}`)));
  }

  /* ------------------------------------------------------------------ create */
  function referenceListHTML() {
    if (!state.references.length) return '';
    return `<div class="reference-list">${state.references.map((item) => `
      <div class="reference-item" title="${e(item.warning || item.filename)}">
        <div class="ref-thumb">${item.kind === 'image' && item.thumb_url ? `<img src="${e(item.thumb_url)}" alt="">` : icon(item.kind === 'image' ? 'image' : 'file', 20)}</div>
        <div class="ref-info">
          <strong>${e(item.filename)}</strong>
          <span>${e(item.type_label || item.ext)} · ${item.kind === 'image' ? `${item.width}×${item.height}` : `${item.char_count || 0} 字`} · ${e(item.size_human || '')}</span>
          ${item.palette?.length ? `<span class="ref-palette">${item.palette.slice(0, 5).map((color) => `<i style="background:${e(color)}"></i>`).join('')}</span>` : ''}
          ${item.warning ? `<em>${e(item.warning)}</em>` : ''}
        </div>
        <button class="ref-remove" type="button" data-remove-reference="${item.id}" title="移除">${icon('close', 13)}</button>
      </div>`).join('')}</div>`;
  }

  async function uploadReferenceFiles(fileList) {
    if (state.uploadingReferences) return;
    const remaining = Math.max(0, 8 - state.references.length);
    if (!remaining) { toast('最多上传 8 个参考文件', 'info'); return; }
    const all = Array.from(fileList || []);
    const files = all.slice(0, remaining);
    if (all.length > remaining) toast(`最多再上传 ${remaining} 个文件`, 'info');
    if (!files.length) return;
    const tooLarge = files.find((file) => file.size > 20 * 1024 * 1024);
    if (tooLarge) { toast(`${tooLarge.name} 超过 20 MB`, 'error'); return; }
    state.uploadingReferences = true;
    state.referenceErrors = [];
    renderCreate();
    const form = new FormData();
    files.forEach((file) => form.append('files', file, file.name));
    try {
      const data = await apiUpload('/api/references/upload', form);
      const items = data.items || [];
      state.references = [...items, ...state.references].slice(0, 8);
      state.referenceErrors = data.errors || [];
      if (!state.references.some((item) => item.kind === 'image')) state.useReferenceCover = false;
      saveReferenceIds();
      saveDraft();
      toast(`已解析 ${items.length} 个参考文件`, items.length ? 'success' : 'info', data.errors?.[0]?.error || '');
      if (state.outline) saveDraft();
      if (!state.readingText && items.length) {
        void extractReading(true);
      }
    } catch (err) {
      state.referenceErrors = [{ filename: '上传失败', error: err.message }];
      toast('参考素材上传失败', 'error', err.message);
    } finally {
      state.uploadingReferences = false;
      renderCreate();
    }
  }

  async function removeReference(referenceId) {
    try {
      await api(`/api/references/${referenceId}`, { method: 'DELETE' });
      state.references = state.references.filter((item) => Number(item.id) !== Number(referenceId));
      if (!state.references.some((item) => item.kind === 'image')) state.useReferenceCover = false;
      state.referenceErrors = [];
      saveReferenceIds();
      saveDraft();
      renderCreate();
      toast('参考文件已移除', 'success');
    } catch (err) {
      toast('移除失败', 'error', err.message);
    }
  }

  function isTeachingPrompt(text) {
    return /教学|课件|课堂|课文|朗读|语文课|英语课|lesson|teaching|reading|passage/i.test(String(text || ''));
  }

  async function extractReading(silent = false) {
    const refs = state.references || [];
    if (!refs.length) {
      if (!silent) toast('请先上传含课文的文档或课文图片', 'info');
      return;
    }
    try {
      const data = await api('/api/references/reading', { method: 'POST', body: { reference_ids: refs.map((item) => item.id) } });
      const reading = data.reading || {};
      if (!reading.text) { if (!silent) toast('没有识别到可朗读的课文，请手动粘贴', 'info'); return; }
      state.readingText = reading.text;
      state.readingTitle = reading.title || '课文朗读';
      state.readingSource = reading.source || '';
      const imageNote = reading.image_count ? ` · 检测到 ${reading.image_count} 张图片` : '';
      if (!silent) toast('已识别课文', 'success', `${reading.text.length} 字${imageNote} · 来源 ${reading.source || '参考素材'}`);
      saveDraft();
      renderCreate();
    } catch (err) {
      if (!silent) toast('识别课文失败', 'error', err.message);
    }
  }

  function renderCreate() {
    const draft = state.draftSnapshot || readDraft();
    const c = state.create;
    const examples = c.language === 'en' ? EXAMPLE_PROMPTS_EN : EXAMPLE_PROMPTS;
    const readingImageCount = (state.references || []).filter((item) => item.kind === 'image').length;
    c.slides = Math.max(6, Math.min(50, Number(c.slides) || 10));
    const activeProvider = state.meta?.active_provider || 'local';
    const content = `
      ${pageHead('描述你的演示', '不需要想好每一页。先告诉我：你想对谁、讲什么、希望他们带走什么。', '')}
      ${draft && draft.outline ? `<div class="project-status-banner ready" style="margin-bottom:18px">${icon('clock', 17)}<div><strong>发现上次未完成的草稿：${e(draft.outline.title || '未命名大纲')}</strong><br>${draft.outline.slides?.length || 0} 页 · 保存于 ${formatDate(draft.savedAt)}</div><div class="banner-actions"><button class="btn btn-sm btn-outline" data-action="resume-draft">继续编辑</button><button class="btn btn-sm btn-ghost" data-action="discard-draft">忽略</button></div></div>` : ''}
      ${flowSteps(1)}
      <div class="create-grid">
        <div class="create-left">
        <section class="prompt-card">
          <div class="prompt-head"><span class="eyebrow">YOUR BRIEF</span><span class="prompt-tip">${icon('sparkles', 12)} 写得越具体，大纲越懂你</span></div>
          <textarea class="prompt-area" id="prompt-input" maxlength="3000" placeholder="例如：帮我做一份关于「AI 如何改变教育」的分享，面向中学老师，重点讲个性化学习、教师角色变化和落地建议，风格专业但不枯燥…">${e(c.prompt)}</textarea>
          <div class="prompt-footer">
            <span class="prompt-counter"><span id="prompt-count">${c.prompt.length}</span> / 3000</span>
            <span class="hint">Ctrl / ⌘ + Enter 快速生成</span>
          </div>
          <div class="idea-chips">${examples.slice(0, 4).map((item) => `<button type="button" class="idea-chip" data-idea="${e(item.text)}">${icon(item.icon, 11)}${e(item.title)}</button>`).join('')}</div>
          <div class="prompt-note">${icon('info', 13)}<span>启明会先判断主题领域，再设计叙事线。涉及事实与趋势时，可以打开右侧的「联网检索」补充最新资料。</span></div>
        </section>
        <section class="reference-card">
          <div class="reference-head">
            <div><h3>${icon('paperclip', 16)} 参考素材 <span class="badge badge-muted">可选</span></h3><p>上传图片或文档，AI 会先读你的材料，再开始写大纲。</p></div>
            <span class="hint">${state.references.length} / 8</span>
          </div>
          <div class="reference-drop" id="reference-drop">
            <input type="file" id="reference-input" multiple hidden>
            <div class="ref-drop-icon">${icon('upload', 20)}</div>
            <div class="ref-drop-copy"><strong>${state.uploadingReferences ? '正在解析参考素材…' : '拖入文件，或点击上传'}</strong><span>图片 · PDF · Word · PPT · Excel · TXT / Markdown · CSV</span></div>
            <button class="btn btn-outline btn-sm" type="button" data-action="pick-references" ${state.uploadingReferences || state.references.length >= 8 ? 'disabled' : ''}>${state.uploadingReferences ? '<span class="spinner dark"></span> 解析中' : `${icon('plus', 13)} 选择文件`}</button>
          </div>
          ${referenceListHTML()}
          ${state.references.some((item) => item.kind === 'image') ? `<label class="checkbox reference-cover-option"><input type="checkbox" id="use-reference-cover" ${state.useReferenceCover ? 'checked' : ''}><span>把列表第一张图片用作封面背景<br><small>文档只提取文字；图片会提取配色，此项可选</small></span></label>` : ''}
          ${state.referenceErrors.length ? `<div class="warn-list reference-errors">${state.referenceErrors.map((item) => `<div class="warn-item">${icon('alert', 12)}<span>${e(item.filename)}：${e(item.error)}</span></div>`).join('')}</div>` : ''}
          <div class="hint reference-footnote">文档会提取正文供 AI 参考；旧版 .doc / .ppt / .xls 会尝试用本机 LibreOffice 转换。单个文件不超过 20 MB。</div>
        </section>
        <section class="reading-card">
          <div class="reference-head"><div><h3>${icon('audio', 16)} 课文朗读 <span class="badge badge-muted">可选</span>${readingImageCount ? `<span class="badge badge-mint">检测到 ${readingImageCount} 张图片</span>` : ''}</h3><p>自动读取上传的文档和图片（Windows OCR），识别出课文后生成朗读页，并用你选择的声音读出来。英文课文也能读。</p></div><button class="section-link" type="button" data-action="extract-reading">${icon('wand', 12)} 从参考文档识别</button></div>
          <div class="field" style="margin-top:8px"><label class="field-label">朗读标题</label><input class="input" id="reading-title" maxlength="80" value="${e(state.readingTitle || '')}" placeholder="例如：课文《春》"></div>
          <div class="field" style="margin-top:9px"><label class="field-label">课文 / 朗读文本 <small>英文自动切换英文声音</small></label><textarea class="textarea" id="reading-text" rows="5" maxlength="3000" placeholder="上传含课文的 Word / PDF / TXT 或课文照片，再点右上角自动识别；也可以直接粘贴课文。">${e(state.readingText || '')}</textarea></div>
          <div class="hint">${state.readingSource ? `已识别来源：${e(state.readingSource)}` : '上传文档或课文照片后会自动扫描；图片文字通过 Windows OCR 识别。也可以在生成演示页自己选声音。'}</div>
        </section>
        </div>
        <aside class="settings-card">
          <h3>${icon('sliders', 16)} 演示参数</h3>
          <p>这些设置只影响生成方式，之后还能随时修改。</p>
          <div class="setting-block">
            <div class="sb-head"><label for="slides-range">页数</label><span class="value" id="slides-value">${c.slides} 页</span></div>
            <input class="range" type="range" id="slides-range" min="6" max="50" step="1" value="${c.slides}" style="--range-fill:${((c.slides - 6) / 44) * 100}%">
            <div class="range-scale"><span>6 页 · 精简</span><span>50 页 · 长演示</span></div>
            <div class="slide-presets">${[10, 20, 30, 50].map((count) => `<button type="button" class="slide-preset ${c.slides === count ? 'active' : ''}" data-slides="${count}">${count} 页</button>`).join('')}</div>
            <div class="hint" style="margin-top:7px">超过 20 页时，AI 会自动拆分更多章节，避免内容重复。</div>
          </div>
          <div class="setting-block">
            <div class="sb-head"><label>表达基调</label></div>
            <select class="select" id="tone-select">${Object.entries(TONE_LABELS).map(([key, label]) => `<option value="${key}" ${c.tone === key ? 'selected' : ''}>${label}</option>`).join('')}</select>
          </div>
          <div class="setting-block">
            <div class="sb-head"><label for="language-select">输出语言</label></div>
            <select class="select" id="language-select"><option value="zh" ${c.language === 'zh' ? 'selected' : ''}>中文</option><option value="en" ${c.language === 'en' ? 'selected' : ''}>English（英文课件）</option></select>
          </div>
          <div class="setting-block">
            <div class="sb-head"><label for="audience-input">目标听众</label><span class="value" style="color:var(--muted-2)">选填</span></div>
            <input class="input" id="audience-input" maxlength="60" placeholder="例如：中学老师 / 管理层 / 投资人" value="${e(c.audience)}">
          </div>
          <div class="setting-block">
            <div class="sb-head"><label>AI 引擎</label><span class="badge ${activeProvider === 'local' ? 'badge-muted' : 'badge-mint'}">${activeProvider === 'local' ? '内置可用' : '已连接'}</span></div>
            ${providerOptions(c.provider)}
          </div>
          <div class="setting-block" style="padding-bottom:4px">
            <div class="toggle-line"><div class="tl-text"><strong>联网检索</strong><span>从公开网页补充趋势与案例</span></div><label class="switch"><input type="checkbox" data-create-toggle="enable_search" ${c.enable_search ? 'checked' : ''}><span></span></label></div>
            <div class="toggle-line"><div class="tl-text"><strong>生成目录</strong><span>让听众先看到完整地图</span></div><label class="switch"><input type="checkbox" data-create-toggle="include_agenda" ${c.include_agenda ? 'checked' : ''}><span></span></label></div>
            <div class="toggle-line"><div class="tl-text"><strong>总结页</strong><span>用三句话收束全场</span></div><label class="switch"><input type="checkbox" data-create-toggle="include_summary" ${c.include_summary ? 'checked' : ''}><span></span></label></div>
            <div class="toggle-line"><div class="tl-text"><strong>问答引导</strong><span>结尾留出交流空间</span></div><label class="switch"><input type="checkbox" data-create-toggle="include_qa" ${c.include_qa ? 'checked' : ''}><span></span></label></div>
          </div>
          <button class="btn btn-primary btn-lg btn-block create-submit" data-action="generate-outline" ${!c.prompt.trim() ? 'disabled' : ''}>${icon('wand', 17)} 生成大纲 <span style="opacity:.55;font-weight:400">→</span></button>
          <div class="hint" style="text-align:center;margin-top:10px">完全免费 · 无需信用卡 · 生成后仍可逐页修改</div>
        </aside>
      </div>`;
    renderShell({ title: '新建演示', active: 'create', content });
    bindCreate();
  }

  function bindCreate() {
    const prompt = document.getElementById('prompt-input');
    const counter = document.getElementById('prompt-count');
    const submit = $('[data-action="generate-outline"]');
    const syncSubmit = () => {
      if (submit) submit.disabled = !prompt.value.trim();
    };
    prompt?.addEventListener('input', () => {
      state.create.prompt = prompt.value;
      if (counter) counter.textContent = prompt.value.length;
      syncSubmit();
    });
    prompt?.addEventListener('keydown', (event) => {
      if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') {
        event.preventDefault();
        submitOutline();
      }
    });
    $$('[data-idea]').forEach((node) => node.addEventListener('click', () => {
      state.create.prompt = node.dataset.idea || '';
      if (prompt) { prompt.value = state.create.prompt; prompt.focus(); }
      if (counter) counter.textContent = state.create.prompt.length;
      syncSubmit();
    }));
    const range = document.getElementById('slides-range');
    const value = document.getElementById('slides-value');
    range?.addEventListener('input', () => {
      state.create.slides = Number(range.value);
      if (value) value.textContent = `${range.value} 页`;
      range.style.setProperty('--range-fill', `${((Number(range.value) - 6) / 44) * 100}%`);
      $$('.slide-preset').forEach((node) => node.classList.toggle('active', Number(node.dataset.slides) === Number(range.value)));
    });
    $$('[data-slides]').forEach((btn) => btn.addEventListener('click', () => {
      const count = Number(btn.dataset.slides);
      state.create.slides = count;
      if (range) {
        range.value = String(count);
        range.style.setProperty('--range-fill', `${((count - 6) / 44) * 100}%`);
      }
      if (value) value.textContent = `${count} 页`;
      $$('.slide-preset').forEach((node) => node.classList.toggle('active', node === btn));
    }));
    document.getElementById('tone-select')?.addEventListener('change', (event) => {
      state.create.tone = event.target.value;
    });
    document.getElementById('language-select')?.addEventListener('change', (event) => {
      state.create.language = event.target.value === 'en' ? 'en' : 'zh';
      renderCreate();
    });
    document.getElementById('audience-input')?.addEventListener('input', (event) => {
      state.create.audience = event.target.value;
    });
    $$('[data-create-provider]').forEach((btn) => btn.addEventListener('click', () => {
      state.create.provider = btn.dataset.createProvider;
      $$('[data-create-provider]').forEach((node) => node.classList.toggle('active', node === btn));
    }));
    $$('[data-create-toggle]').forEach((input) => input.addEventListener('change', () => {
      state.create[input.dataset.createToggle] = input.checked;
    }));
    const refInput = document.getElementById('reference-input');
    const refDrop = document.getElementById('reference-drop');
    $('[data-action="pick-references"]')?.addEventListener('click', (event) => {
      event.stopPropagation();
      refInput?.click();
    });
    refDrop?.addEventListener('click', (event) => {
      if (event.target.closest('button')) return;
      refInput?.click();
    });
    refInput?.addEventListener('change', () => {
      uploadReferenceFiles(refInput.files);
      refInput.value = '';
    });
    if (refDrop) {
      ['dragenter', 'dragover'].forEach((name) => refDrop.addEventListener(name, (event) => {
        event.preventDefault();
        refDrop.classList.add('dragging');
      }));
      ['dragleave', 'drop'].forEach((name) => refDrop.addEventListener(name, (event) => {
        event.preventDefault();
        refDrop.classList.remove('dragging');
      }));
      refDrop.addEventListener('drop', (event) => {
        if (event.dataTransfer?.files?.length) uploadReferenceFiles(event.dataTransfer.files);
      });
    }
    $$('[data-remove-reference]').forEach((btn) => btn.addEventListener('click', () => removeReference(Number(btn.dataset.removeReference))));
    $('#use-reference-cover')?.addEventListener('change', (event) => {
      state.useReferenceCover = event.target.checked;
      saveDraft();
    });
    document.getElementById('reading-title')?.addEventListener('input', (event) => {
      state.readingTitle = event.target.value;
    });
    document.getElementById('reading-text')?.addEventListener('input', (event) => {
      state.readingText = event.target.value;
    });
    $('[data-action="extract-reading"]')?.addEventListener('click', () => extractReading(false));
    $('[data-action="generate-outline"]')?.addEventListener('click', submitOutline);
    $('[data-action="resume-draft"]')?.addEventListener('click', resumeDraft);
    $('[data-action="discard-draft"]')?.addEventListener('click', async () => {
      const yes = await confirmDialog({ title: '忽略这份草稿？', message: '草稿会从本机移除，但已经生成的项目不会被删除。', confirmText: '忽略草稿', danger: true });
      if (yes) { clearDraft(); renderCreate(); }
    });
    setTimeout(() => prompt?.focus(), 120);
  }

  async function submitOutline() {
    if (state.uploadingReferences) {
      toast('参考素材还在解析，请稍等一下', 'info');
      return;
    }
    const prompt = (document.getElementById('prompt-input')?.value || state.create.prompt || '').trim();
    if (prompt.length < 4) {
      toast('请先描述一下你的演示需求', 'error');
      document.getElementById('prompt-input')?.focus();
      return;
    }
    state.create.prompt = prompt;
    if (state.create.audience === undefined) state.create.audience = '';
    const busy = showBusy({
      title: state.create.slides >= 24 ? '正在搭建一份长演示' : '正在把想法变成结构',
      subtitle: `主题：${prompt.slice(0, 42)}${prompt.length > 42 ? '…' : ''}${state.create.slides >= 24 ? ' · 长演示可能需要 1—2 分钟' : ''}`,
      steps: [
        state.references.length ? '优先阅读你上传的参考素材' : '读懂你的主题与听众',
        '搭建一条有起伏的叙事线',
        '为每一页写出具体判断',
        '检查节奏、页数与行动落点',
      ],
    });
    const started = Date.now();
    try {
      const data = await api('/api/ai/outline', {
        method: 'POST',
        body: {
          prompt,
          slides: state.create.slides,
          audience: state.create.audience,
          tone: state.create.tone,
          provider: state.create.provider,
          enable_search: state.create.enable_search,
          include_agenda: state.create.include_agenda,
          include_summary: state.create.include_summary,
          include_qa: state.create.include_qa,
          language: state.create.language || 'zh',
          reference_ids: state.references.map((item) => item.id),
        },
      });
      const wait = Math.max(0, 700 - (Date.now() - started));
      if (wait) await new Promise((resolve) => setTimeout(resolve, wait));
      state.outline = data.outline;
      state.project = null;
      state.template = null;
      state.selectedSlide = 0;
      saveDraft();
      busy.close(200);
      navigate('#/outline');
      toast('大纲已生成，可以逐页修改', 'success', `${data.outline.slides?.length || 0} 页 · ${providerLabel(data.provider_used)}`);
      if (data.warnings?.length) setTimeout(() => toast(data.warnings[0], 'info'), 900);
    } catch (err) {
      busy.close(100);
      toast('大纲生成失败', 'error', err.message);
    }
  }

  /* ----------------------------------------------------------------- outline */
  function renderOutline() {
    if (!state.outline?.slides?.length) {
      renderShell({ title: 'AI 大纲', active: 'create', content: `<div class="empty"><div class="empty-icon">${icon('wand', 26)}</div><h3>还没有大纲</h3><p>先描述你的演示需求，AI 会为你生成一份可以逐页修改的结构。</p><button class="btn btn-primary" data-nav="#/create" style="margin-top:18px">去描述想法</button></div>` });
      return;
    }
    const outline = state.outline;
    const slides = outline.slides;
    state.selectedSlide = Math.max(0, Math.min(state.selectedSlide, slides.length - 1));
    const index = state.selectedSlide;
    const current = slides[index];
    const theme = themeOf(state.template || state.templates[0]);
    const sources = outline.sources || [];
    const warnings = outline.warnings || [];

    const content = `
      <div class="outline-top">
        <div class="title-wrap">
          <span class="eyebrow">STEP 02 · SHAPE THE STORY</span>
          <input class="outline-title-input" id="outline-title" value="${e(outline.title || '未命名演示')}" maxlength="72" aria-label="演示标题">
          <div class="outline-meta">
            <span class="badge badge-muted">${slides.length} 页</span>
            <span class="badge badge-cobalt">${e(providerLabel(outline.provider_used))}</span>
            ${outline.language === 'en' ? '<span class="badge badge-mint">English</span>' : ''}
            <span class="badge badge-outline">${e(outline.audience || '通用听众')}</span>
            ${(outline.reference_files || state.references || []).length ? `<span class="badge badge-amber">${icon('paperclip', 10)} ${(outline.reference_files || state.references).length} 个参考素材</span>` : ''}
          </div>
        </div>
        <div class="page-actions">
          <button class="btn btn-outline" data-action="outline-back">${icon('arrowLeft', 15)} 上一步</button>
          <button class="btn btn-outline" data-action="outline-preview">${icon('play', 15)} 放映预览</button>
          <button class="btn btn-outline" data-action="regen-all">${icon('refresh', 15)} 重新生成</button>
          <button class="btn btn-primary" data-action="outline-next">选模板 ${icon('arrowRight', 15)}</button>
        </div>
      </div>
      ${flowSteps(2)}
      ${warnings.length ? `<div class="warn-list" style="margin-bottom:14px">${warnings.slice(0, 3).map((w) => `<div class="warn-item">${icon('info', 12)}<span>${e(w)}</span></div>`).join('')}</div>` : ''}
      <div class="outline-layout">
        <aside class="outline-list" id="outline-list">
          <div class="outline-list-head"><span>PAGES / ${String(slides.length).padStart(2, '0')}</span><button data-action="outline-add-page" title="添加页面">${icon('plus', 15)}</button></div>
          ${slides.map((slide, i) => `<button class="outline-item ${i === index ? 'active' : ''}" data-outline-select="${i}">
            <span class="oi-no">${String(i + 1).padStart(2, '0')}</span>
            <span class="oi-body"><span class="oi-type"><i class="type-dot ${typeDotClass(slide.type)}"></i>${typeLabel(slide.type)}</span><span class="oi-title">${e(slide.title || '未命名页面')}</span></span>
            <span class="oi-drag">${icon('more', 14)}</span>
          </button>`).join('')}
        </aside>
        <section class="editor-panel">
          <div class="slide-preview-shell">
            <div class="slide-preview-bar"><span>LIVE PREVIEW · 16:9</span><div class="slide-preview-actions"><span class="badge badge-outline">${typeLabel(current.type)}</span></div></div>
            <div class="slide-canvas-wrap" id="slide-preview">${renderSlide(current, theme, index, slides.length)}</div>
          </div>
          <div class="editor-body">
            <div class="editor-section-title"><h3>${icon('edit', 14)} 编辑这一页</h3><span class="hint">所有修改会实时反映在预览中</span></div>
            <div class="editor-fields" id="editor-fields">${editorFields(current, index)}</div>
            <div class="editor-footer">
              <div class="left">
                <button class="btn btn-sm btn-outline" data-action="move-up" ${index <= 1 || current.type === 'cover' || current.type === 'end' ? 'disabled' : ''}>${icon('arrowUp', 13)} 上移</button>
                <button class="btn btn-sm btn-outline" data-action="move-down" ${index >= slides.length - 2 || current.type === 'cover' || current.type === 'end' ? 'disabled' : ''}>${icon('arrowDown', 13)} 下移</button>
                <button class="btn btn-sm btn-ghost" data-action="regen-slide">${icon('refresh', 13)} 重写此页</button>
              </div>
              <div class="right">
                <button class="btn btn-sm btn-danger" data-action="delete-slide" ${current.type === 'cover' || current.type === 'end' ? 'disabled' : ''}>${icon('trash', 13)} 删除</button>
                <button class="btn btn-sm btn-outline" data-action="outline-add-page">${icon('plus', 13)} 添加页面</button>
              </div>
            </div>
          </div>
          ${sources.length ? `<div class="side-card" style="margin-top:14px"><h3>${icon('globe', 14)} 参考来源 <span>联网检索</span></h3><div class="sources-list">${sources.map((s) => `<a class="source-row" href="${e(s.url)}" target="_blank" rel="noopener noreferrer" data-external="${e(s.url)}"><strong>${e(s.title || '网页资料')}</strong><br>${e((s.snippet || '').slice(0, 110))}</a>`).join('')}</div></div>` : ''}
        </section>
      </div>
      <div class="outline-bottom-bar">
        <span class="hintline">${icon('info', 13)} 大纲满意后，下一步从 ${state.templates.length} 套原创主题里挑一个。之后仍然可以回来修改。</span>
        <div class="actions"><button class="btn btn-ghost btn-sm" data-action="outline-back">返回</button><button class="btn btn-primary" data-action="outline-next">选择模板 ${icon('arrowRight', 14)}</button></div>
      </div>`;
    renderShell({ title: 'AI 大纲', active: 'create', content, actions: `<span class="badge badge-mint">${icon('check', 11)} 已保存草稿</span>` });
    bindOutline();
    saveDraft();
  }

  function editorFields(slide, index) {
    const type = slide.type || 'bullets';
    const common = `
      <div class="field"><label class="field-label">页面眉标 <small>显示在标题上方</small></label><input class="input" data-field="eyebrow" value="${e(slide.eyebrow || '')}" maxlength="44" placeholder="例如：01 / INSIGHT"></div>
      <div class="field"><label class="field-label">页面标题</label><textarea class="textarea" data-field="title" rows="2" maxlength="88" style="min-height:64px">${e(slide.title || '')}</textarea></div>
      <div class="field"><label class="field-label">副标题 <small>选填</small></label><input class="input" data-field="subtitle" value="${e(slide.subtitle || '')}" maxlength="180" placeholder="一句解释或过渡"></div>`;
    let body = '';
    if (['agenda', 'bullets', 'summary'].includes(type)) {
      body = `<div class="field"><label class="field-label">内容要点 <small>每行一条，建议 3—4 条</small></label><div class="bullet-editor" id="bullet-editor">
        ${(slide.bullets || []).map((b, i) => `<div class="bullet-row"><span class="bullet-no">${i + 1}</span><input class="input" data-bullet-index="${i}" value="${e(b)}" maxlength="140"><button class="remove-bullet" data-remove-bullet="${i}" title="删除这一条" type="button">${icon('close', 12)}</button></div>`).join('')}
        <button class="add-bullet" type="button" data-action="add-bullet">${icon('plus', 12)} 添加一条</button>
      </div></div>`;
    } else if (type === 'stats') {
      body = `<div class="field"><label class="field-label">数据卡片 <small>建议使用“目标/过程指标”，不要编造事实</small></label><div class="bullet-editor">
        ${[0, 1, 2].map((i) => { const s = (slide.stats || [])[i] || { value: '', label: '', note: '' }; return `<div class="bullet-row" style="align-items:flex-start"><span class="bullet-no">0${i + 1}</span><div style="flex:1;display:grid;grid-template-columns:76px 1fr;gap:6px"><input class="input" data-stat-index="${i}" data-stat-field="value" value="${e(s.value)}" maxlength="16" placeholder="90"><input class="input" data-stat-index="${i}" data-stat-field="label" value="${e(s.label)}" maxlength="26" placeholder="验证天数"><input class="input" data-stat-index="${i}" data-stat-field="note" value="${e(s.note)}" maxlength="44" placeholder="建议目标，可按实际调整" style="grid-column:span 2"></div></div>`; }).join('')}
      </div></div>`;
    } else if (type === 'quote') {
      body = `<div class="field"><label class="field-label">金句</label><textarea class="textarea" data-field="quote" rows="3" maxlength="180">${e(slide.quote || '')}</textarea></div>
        <div class="field"><label class="field-label">出处 / 署名 <small>选填</small></label><input class="input" data-field="author" value="${e(slide.author || '')}" maxlength="50" placeholder="本次分享"></div>`;
    } else if (type === 'reading') {
      body = `<div class="field"><label class="field-label">课文正文 <small>会显示在幻灯片上，并作为朗读音频文稿</small></label><textarea class="textarea" data-field="reading_text" rows="8" maxlength="3000">${e(slide.reading_text || '')}</textarea></div>`;
    } else if (type === 'section') {
      body = '';
    } else if (type === 'end') {
      body = '';
    }
    return `${common}${body}
      <div class="field"><label class="field-label">演讲者备注 <small>会写入 PPT 备注，也是音频旁白的文稿</small></label><textarea class="textarea" data-field="notes" rows="3" maxlength="1200" placeholder="这一页你想怎么讲？">${e(slide.notes || '')}</textarea></div>`;
  }

  function bindOutline() {
    const outline = state.outline;
    if (!outline) return;
    const index = state.selectedSlide;
    const current = outline.slides[index];
    const updatePreview = () => {
      const host = document.getElementById('slide-preview');
      if (host) host.innerHTML = renderSlide(outline.slides[state.selectedSlide], themeOf(state.template || state.templates[0]), state.selectedSlide, outline.slides.length);
      const titleNode = document.querySelectorAll('.outline-item')[state.selectedSlide]?.querySelector('.oi-title');
      if (titleNode) titleNode.textContent = outline.slides[state.selectedSlide].title || '未命名页面';
    };
    const saveSoon = debounce(() => saveDraft(), 280);
    document.getElementById('outline-title')?.addEventListener('input', (event) => {
      outline.title = event.target.value;
      if (outline.slides[0]?.type === 'cover') outline.slides[0].title = event.target.value;
      updatePreview();
      saveSoon();
    });
    $$('[data-outline-select]').forEach((btn) => btn.addEventListener('click', () => {
      state.selectedSlide = Number(btn.dataset.outlineSelect);
      renderOutline();
    }));
    $$('[data-field]', document.getElementById('editor-fields') || document).forEach((input) => {
      input.addEventListener('input', () => {
        const field = input.dataset.field;
        if (!field) return;
        outline.slides[state.selectedSlide][field] = input.value;
        if (field === 'reading_text') outline.slides[state.selectedSlide].notes = input.value;
        if (field === 'title') {
          const item = document.querySelectorAll('.outline-item')[state.selectedSlide]?.querySelector('.oi-title');
          if (item) item.textContent = input.value;
        }
        updatePreview();
        saveSoon();
      });
    });
    $$('[data-bullet-index]').forEach((input) => input.addEventListener('input', () => {
      const i = Number(input.dataset.bulletIndex);
      outline.slides[state.selectedSlide].bullets[i] = input.value;
      updatePreview();
      saveSoon();
    }));
    $$('[data-remove-bullet]').forEach((btn) => btn.addEventListener('click', () => {
      const i = Number(btn.dataset.removeBullet);
      outline.slides[state.selectedSlide].bullets.splice(i, 1);
      renderOutline();
    }));
    $('[data-action="add-bullet"]')?.addEventListener('click', () => {
      const list = outline.slides[state.selectedSlide].bullets || [];
      if (list.length >= 5) { toast('每页最多 5 条内容', 'info'); return; }
      list.push('');
      renderOutline();
      setTimeout(() => document.querySelector(`[data-bullet-index="${list.length - 1}"]`)?.focus(), 50);
    });
    $$('[data-stat-index]').forEach((input) => input.addEventListener('input', () => {
      const slide = outline.slides[state.selectedSlide];
      const i = Number(input.dataset.statIndex);
      slide.stats = slide.stats || [];
      slide.stats[i] = slide.stats[i] || { value: '', label: '', note: '' };
      slide.stats[i][input.dataset.statField] = input.value;
      updatePreview();
      saveSoon();
    }));
    $('[data-action="outline-back"]')?.addEventListener('click', () => navigate('#/create'));
    $('[data-action="outline-next"]')?.addEventListener('click', goPickTemplate);
    $('[data-action="outline-preview"]')?.addEventListener('click', () => openPlayer(outline, themeOf(state.template || state.templates[0]), state.project?.options || {}));
    $('[data-action="outline-add-page"]')?.addEventListener('click', openAddSlideModal);
    $$('[data-action="add-bullet"]').length;
    $('[data-action="regen-slide"]')?.addEventListener('click', regenerateCurrentSlide);
    $('[data-action="regen-all"]')?.addEventListener('click', regenerateAll);
    $('[data-action="delete-slide"]')?.addEventListener('click', deleteCurrentSlide);
    $('[data-action="move-up"]')?.addEventListener('click', () => moveSlide(-1));
    $('[data-action="move-down"]')?.addEventListener('click', () => moveSlide(1));
    $$('[data-external]').forEach((link) => link.addEventListener('click', (event) => {
      event.preventDefault();
      openExternal(link.dataset.external);
    }));
  }

  async function goPickTemplate() {
    if (!state.outline) return;
    const slides = state.outline.slides || [];
    const readingText = (state.readingText || '').trim();
    if (readingText) {
      let reading = slides.find((slide) => slide.type === 'reading');
      if (reading) {
        reading.reading_text = readingText;
        reading.notes = readingText;
        reading.title = state.readingTitle || reading.title || '课文朗读';
      } else if (slides.length < 50) {
        const insertAt = Math.min(2, slides.length - 1);
        slides.splice(insertAt, 0, {
          type: 'reading',
          eyebrow: 'READING · 课文朗读',
          title: state.readingTitle || '课文朗读',
          subtitle: state.readingSource ? `来源：${state.readingSource}` : '请跟着旁白朗读',
          bullets: [],
          stats: [],
          quote: '',
          author: '',
          notes: readingText,
          reading_text: readingText,
          section: 0,
        });
        state.selectedSlide = insertAt;
        toast('已加入课文朗读页', 'success');
      } else {
        toast('已到 50 页上限，未加入朗读页；删掉一页后再试', 'info');
      }
    }
    saveDraft();
    if (state.project?.id) {
      try {
        await api(`/api/projects/${state.project.id}`, {
          method: 'PATCH',
          body: { title: state.outline.title, outline: state.outline },
        });
      } catch (err) {
        toast('大纲保存失败', 'error', err.message);
        return;
      }
    }
    navigate('#/pick-template');
  }

  function openAddSlideModal() {
    if ((state.outline?.slides || []).length >= 50) {
      toast('一份演示最多 50 页', 'info');
      return;
    }
    const types = [
      ['bullets', '内容页', '标题 + 3—4 条判断', 'edit'],
      ['section', '章节页', '为一个新段落开场', 'layers'],
      ['stats', '数据页', '三个指标讲清进展', 'chart'],
      ['quote', '金句页', '给听众一个停顿', 'sparkles'],
      ['reading', '课文朗读', '显示课文并自动朗读', 'audio'],
      ['summary', '总结页', '收束三个关键判断', 'check'],
    ];
    const host = openModal(`
      <div class="modal-head"><div><h2>添加一页</h2><p>选择页面类型，之后仍可修改内容和样式。</p></div><button class="modal-close" data-close-modal>${icon('close', 15)}</button></div>
      <div class="modal-body"><div class="provider-grid" style="grid-template-columns:1fr 1fr">${types.map(([type, label, desc, ic]) => `<button class="provider-card" data-add-slide-type="${type}" style="padding:15px"><div class="pc-top"><span class="pc-name">${icon(ic, 14)} ${label}</span></div><p>${desc}</p></button>`).join('')}</div></div>`, '');
    $$('[data-add-slide-type]', host).forEach((btn) => btn.addEventListener('click', () => {
      const type = btn.dataset.addSlideType;
      const base = {
        type, eyebrow: type === 'section' ? 'SECTION 04' : type === 'stats' ? 'MEASURE' : type === 'quote' ? 'A PAUSE' : type === 'summary' ? 'TAKEAWAYS' : 'INSIGHT',
        title: type === 'section' ? '新的章节' : type === 'stats' ? '用三个数字，盯住进展' : type === 'quote' ? '留一句话，给今天的讨论' : type === 'summary' ? '带走这三件事' : '新的内容页',
        subtitle: '', bullets: type === 'bullets' ? ['第一个判断', '第二个判断', '第三个判断'] : type === 'summary' ? ['先定义问题', '再建立方法', '最后盯住反馈'] : [],
        stats: type === 'stats' ? [{ value: '3', label: '关键动作', note: '建议目标' }, { value: '90', label: '验证天数', note: '小步快跑' }, { value: '1', label: '反馈机制', note: '持续复盘' }] : [],
        quote: type === 'quote' ? '把问题讲清楚，答案就已经出现了一半。' : '', author: type === 'quote' ? '本次分享' : '',
        notes: '这一页围绕新的判断展开，可以先抛出一个问题，再给出你的观察。', reading_text: '', section: 0,
      };
      const insertAt = outlineEndInsertIndex();
      state.outline.slides.splice(insertAt, 0, base);
      state.selectedSlide = insertAt;
      closeModal();
      renderOutline();
      toast('已添加一页', 'success');
    }));
  }

  function outlineEndInsertIndex() {
    const slides = state.outline?.slides || [];
    const selected = state.selectedSlide;
    if (selected >= slides.length - 1 || slides[selected]?.type === 'end') return Math.max(1, slides.length - 1);
    return selected + 1;
  }

  async function deleteCurrentSlide() {
    const slides = state.outline?.slides || [];
    const current = slides[state.selectedSlide];
    if (!current || ['cover', 'end'].includes(current.type)) return;
    if (slides.length <= 6) { toast('至少需要保留 6 页', 'error'); return; }
    const yes = await confirmDialog({ title: '删除这一页？', message: `将删除「${current.title || '未命名页面'}」，此操作不能撤销。`, confirmText: '删除页面', danger: true });
    if (!yes) return;
    slides.splice(state.selectedSlide, 1);
    state.selectedSlide = Math.max(0, state.selectedSlide - 1);
    saveDraft();
    renderOutline();
    toast('页面已删除', 'success');
  }

  function moveSlide(direction) {
    const slides = state.outline?.slides || [];
    const from = state.selectedSlide;
    const to = from + direction;
    if (to <= 0 || to >= slides.length - 1) return;
    if (['cover', 'end'].includes(slides[from].type)) return;
    [slides[from], slides[to]] = [slides[to], slides[from]];
    state.selectedSlide = to;
    saveDraft();
    renderOutline();
  }

  async function regenerateCurrentSlide() {
    const button = $('[data-action="regen-slide"]');
    if (button) { button.disabled = true; button.innerHTML = `<span class="spinner dark"></span> 重写中`; }
    try {
      const data = await api('/api/ai/slide', {
        method: 'POST',
        body: { outline: state.outline, index: state.selectedSlide, provider: state.create.provider },
      });
      state.outline.slides[state.selectedSlide] = data.slide;
      state.outline = data.outline || state.outline;
      saveDraft();
      renderOutline();
      toast('这一页已重写', 'success');
    } catch (err) {
      toast('重写失败', 'error', err.message);
      if (button) { button.disabled = false; button.innerHTML = `${icon('refresh', 13)} 重写此页`; }
    }
  }

  async function regenerateAll() {
    const yes = await confirmDialog({ title: '重新生成整份大纲？', message: '当前大纲会被新的大纲替换。已经手动修改的内容不会保留。', confirmText: '重新生成', danger: true });
    if (!yes) return;
    const prompt = state.create.prompt || state.outline?.title || '';
    const busy = showBusy({ title: '正在重新构思整份大纲', subtitle: prompt.slice(0, 46), steps: ['重新判断主题与听众', '调整叙事结构', '重写每一页的判断', '校验页数与节奏'] });
    try {
      const data = await api('/api/ai/outline', {
        method: 'POST',
        body: {
          prompt, slides: state.outline.slides.length,
          audience: state.create.audience, tone: state.create.tone, provider: state.create.provider,
          enable_search: state.create.enable_search, include_agenda: state.create.include_agenda,
          include_summary: state.create.include_summary, include_qa: state.create.include_qa,
        },
      });
      state.outline = data.outline;
      state.selectedSlide = 0;
      saveDraft();
      busy.close(100);
      renderOutline();
      toast('整份大纲已更新', 'success');
    } catch (err) {
      busy.fail(err.message);
    }
  }

  /* ---------------------------------------------------------------- templates */
  function filteredBuiltIn(mode) {
    const query = (mode === 'pick' ? state.pickQuery : state.galleryQuery).trim().toLowerCase();
    const category = mode === 'pick' ? state.pickCategory : state.galleryCategory;
    return state.templates.filter((t) => {
      if (category !== '全部' && t.category !== category) return false;
      if (!query) return true;
      const haystack = `${t.name} ${t.english} ${t.description} ${(t.tags || []).join(' ')} ${t.category}`.toLowerCase();
      return haystack.includes(query);
    });
  }

  function templateGalleryMarkup(mode) {
    const tab = mode === 'pick' ? state.pickTab : state.galleryTab;
    const query = mode === 'pick' ? state.pickQuery : state.galleryQuery;
    const category = mode === 'pick' ? state.pickCategory : state.galleryCategory;
    if (tab === 'online') {
      if (state.onlineLoading) {
        return `<div class="tpl-grid">${[1, 2, 3, 4, 5, 6].map(() => `<div class="template-card"><div class="tpl-thumb skeleton"></div><div class="tpl-info"><div class="skeleton" style="width:55%;height:11px"></div><div class="skeleton" style="width:80%;height:9px;margin-top:9px"></div></div></div>`).join('')}</div>`;
      }
      if (!state.onlineTemplates.length) {
        return `<div class="empty"><div class="empty-icon">${icon('globe', 25)}</div><h3>去公开互联网找一点灵感</h3><p>输入一个风格词，启明会从图片搜索结果中提取配色，生成一套只属于你的在线模板。</p><div class="online-search" style="margin-top:18px;width:min(460px,100%)"><input class="input" id="online-query" value="${e(state.onlineQuery)}" placeholder="例如：极简 商务 / 东方 留白 / 深色 科技"><button class="btn btn-primary" data-action="online-search">${icon('search', 15)} 搜索</button></div><div class="chips" style="justify-content:center;margin-top:12px">${['极简 商务', '东方 留白', '深色 科技', '春日 清新'].map((q) => `<button class="chip" data-online-suggest="${q}">${q}</button>`).join('')}</div></div>`;
      }
      return `<div class="online-note">${icon('info', 14)}<span>在线模板由公开图片搜索结果与提取配色生成。图片仅作设计参考，商用前请确认来源授权；勾选“仅提取配色”可获得完全原创的配色模板。${state.onlineQuery ? ` 当前关键词：${e(state.onlineQuery)}` : ''}</span></div>
        <div class="tpl-grid">${state.onlineTemplates.map((t) => `<article class="template-card ${state.template?.id === t.id ? 'selected' : ''}" data-online-template="${e(t.id)}">
          <div class="tpl-thumb">${onlineCover(t)}<span class="tpl-check">${state.template?.id === t.id ? icon('check', 13) : ''}</span></div>
          <div class="tpl-info"><div class="row"><h3>${e(t.name)}</h3><span class="cat">联网</span></div><div class="en">WEB INSPIRATION</div><p>${e(t.description || '')}</p><div class="swatches" style="display:flex;gap:4px;margin-top:9px">${['primary', 'accent', 'bg'].map((key) => `<span style="width:15px;height:15px;border-radius:4px;border:1px solid rgba(0,0,0,.08);background:${e(t.colors?.[key] || '#ddd')}"></span>`).join('')}</div></div>
        </article>`).join('')}</div>`;
    }
    const items = filteredBuiltIn(mode);
    if (!items.length) return `<div class="empty"><div class="empty-icon">${icon('search', 24)}</div><h3>没有找到匹配的模板</h3><p>试试更短的关键词，或切换到「全部」分类。</p></div>`;
    return `<div class="tpl-grid">${items.map((t) => `<article class="template-card ${state.template?.id === t.id ? 'selected' : ''}" data-builtin-template="${e(t.id)}">
      <div class="tpl-thumb">${templateThumb(t)}<span class="tpl-check">${state.template?.id === t.id ? icon('check', 13) : ''}</span></div>
      <div class="tpl-info"><div class="row"><div><h3>${e(t.name)}</h3><div class="en">${e(t.english)}</div></div><span class="cat">${e(t.category)}</span></div><p>${e(t.description)}</p><div class="tags">${(t.tags || []).slice(0, 3).map((tag) => `<span>${e(tag)}</span>`).join('')}</div></div>
    </article>`).join('')}</div>`;
  }

  function templateToolbar(mode) {
    const tab = mode === 'pick' ? state.pickTab : state.galleryTab;
    const query = mode === 'pick' ? state.pickQuery : state.galleryQuery;
    return `<div class="template-toolbar">
      <div class="template-tabs"><button class="template-tab ${tab === 'builtin' ? 'active' : ''}" data-template-tab="builtin" data-mode="${mode}">${icon('palette', 13)} 内置精选</button><button class="template-tab ${tab === 'online' ? 'active' : ''}" data-template-tab="online" data-mode="${mode}">${icon('globe', 13)} 联网灵感</button></div>
      <div class="search-box">${icon('search', 16)}<input id="template-search-${mode}" value="${e(query)}" placeholder="搜索模板，例如：商务 / 东方 / 深色 / 极简" ${tab === 'online' ? 'disabled' : ''}></div>
      ${tab === 'online' ? `<button class="btn btn-primary btn-sm" data-action="online-search">${icon('search', 14)} 搜索</button>` : ''}
    </div>`;
  }

  function renderPickTemplate(token) {
    if (!state.outline) {
      renderShell({ title: '选择模板', active: 'create', content: `<div class="empty"><div class="empty-icon">${icon('palette', 25)}</div><h3>先有内容，再选风格</h3><p>生成大纲之后，再来挑选最适合这场表达的模板。</p><button class="btn btn-primary" data-nav="#/create" style="margin-top:18px">去生成大纲</button></div>` });
      return;
    }
    const category = state.pickCategory;
    const content = `
      <div class="outline-top">
        <div class="title-wrap"><span class="eyebrow">STEP 03 · DRESS THE IDEA</span><h1 class="page-title" style="font-size:32px;margin-top:6px">给它一张好看的脸</h1><p class="page-sub" style="margin-top:7px">${state.templates.length} 套原创主题，或联网寻找一套只属于你的配色。</p></div>
        <div class="page-actions"><button class="btn btn-outline" data-nav="#/outline">${icon('arrowLeft', 15)} 返回大纲</button><button class="btn btn-primary" data-action="template-next" ${state.template ? '' : 'disabled'}>下一步 ${icon('arrowRight', 15)}</button></div>
      </div>
      ${flowSteps(3)}
      ${templateToolbar('pick')}
      ${state.pickTab === 'builtin' ? `<div class="filter-row"><div class="chips">${state.categories.map((cat) => `<button class="chip ${category === cat ? 'active' : ''}" data-template-category="${e(cat)}" data-mode="pick">${e(cat)}</button>`).join('')}</div><span class="count">${filteredBuiltIn('pick').length} 套模板</span></div>` : `<div class="online-search"><input class="input" id="online-query" value="${e(state.onlineQuery)}" placeholder="输入风格词，例如：极简 商务 / 东方 留白 / 深色 科技"><button class="btn btn-primary" data-action="online-search">${icon('search', 15)} 搜索在线灵感</button></div>`}
      <div id="template-gallery">${templateGalleryMarkup('pick')}</div>
      <div class="outline-bottom-bar" style="margin-top:22px">
        <span class="hintline">${state.template ? `已选择：${e(state.template.name)}${state.template.custom && !state.templateUseImage ? ' · 仅提取配色' : ''}` : '还没有选择模板。选一个，让内容真正被看见。'} ${icon('info', 12)}</span>
        <div class="actions"><button class="btn btn-ghost btn-sm" data-nav="#/outline">返回修改大纲</button><button class="btn btn-primary" data-action="template-next" ${state.template ? '' : 'disabled'}>下一步：设置生成 ${icon('arrowRight', 14)}</button></div>
      </div>`;
    renderShell({ title: '选择模板', active: 'create', content });
    bindTemplatePage('pick');
    if (state.pickTab === 'online' && !state.onlineTemplates.length && !state.onlineLoading && !state.onlineTried) {
      setTimeout(() => runOnlineSearch('pick', token), 80);
    }
  }

  function renderLibrary() {
    const content = `
      ${pageHead('模板库', `一套模板，是内容的第一层语气。${state.templates.length} 套原创主题，也可以联网找灵感。`, `<button class="btn btn-primary" data-action="library-use">${icon('sparkles', 16)} 用模板开始创作</button>`)}
      ${templateToolbar('library')}
      ${state.galleryTab === 'builtin' ? `<div class="filter-row"><div class="chips">${state.categories.map((cat) => `<button class="chip ${state.galleryCategory === cat ? 'active' : ''}" data-template-category="${e(cat)}" data-mode="library">${e(cat)}</button>`).join('')}</div><span class="count">${filteredBuiltIn('library').length} 套模板</span></div>` : `<div class="online-search"><input class="input" id="online-query" value="${e(state.onlineQuery)}" placeholder="输入风格词，例如：极简 商务 / 东方 留白 / 深色 科技"><button class="btn btn-primary" data-action="online-search">${icon('search', 15)} 搜索在线灵感</button></div>`}
      <div id="template-gallery">${templateGalleryMarkup('library')}</div>
      <div class="online-note" style="margin-top:22px">${icon('info', 14)}<span>所有模板导出时都不会添加水印。在线图片仅作设计参考，商用前请确认来源授权。</span></div>`;
    renderShell({ title: '模板库', active: 'library', content });
    bindTemplatePage('library');
    if (state.galleryTab === 'online' && !state.onlineTemplates.length && !state.onlineLoading && !state.onlineTried) {
      setTimeout(() => runOnlineSearch('library'), 80);
    }
  }

  function bindTemplatePage(mode) {
    $$('[data-template-tab]').forEach((btn) => btn.addEventListener('click', () => {
      if (mode === 'pick') state.pickTab = btn.dataset.templateTab;
      else state.galleryTab = btn.dataset.templateTab;
      if (btn.dataset.templateTab === 'online' && !state.onlineTemplates.length) state.onlineTried = false;
      if (mode === 'pick') state.pickCategory = '全部'; else state.galleryCategory = '全部';
      if (btn.dataset.templateTab === 'online' && mode === 'pick') state.onlineTemplates = state.onlineTemplates;
      if (mode === 'pick') renderPickTemplate(); else renderLibrary();
    }));
    const search = document.getElementById(`template-search-${mode}`);
    search?.addEventListener('input', debounce(() => {
      if (mode === 'pick') state.pickQuery = search.value;
      else state.galleryQuery = search.value;
      refreshTemplateGallery(mode);
    }, 120));
    $$('[data-template-category]').forEach((btn) => btn.addEventListener('click', () => {
      if (mode === 'pick') state.pickCategory = btn.dataset.templateCategory;
      else state.galleryCategory = btn.dataset.templateCategory;
      if (mode === 'pick') renderPickTemplate(); else renderLibrary();
    }));
    bindTemplateCards(mode);
    $('[data-action="template-next"]')?.addEventListener('click', createProjectFromTemplate);
    $('[data-action="library-use"]')?.addEventListener('click', () => {
      if (state.template) { navigate('#/create'); }
      else { toast('先从下面选一套模板', 'info'); }
    });
    $('[data-action="online-search"]')?.addEventListener('click', () => runOnlineSearch(mode));
    document.getElementById('online-query')?.addEventListener('keydown', (event) => {
      if (event.key === 'Enter') runOnlineSearch(mode);
    });
    $$('[data-online-suggest]').forEach((btn) => btn.addEventListener('click', () => {
      state.onlineQuery = btn.dataset.onlineSuggest;
      runOnlineSearch(mode);
    }));
  }

  function bindTemplateCards(mode) {
    $$('[data-builtin-template]').forEach((card) => card.addEventListener('click', () => {
      const t = templateById(card.dataset.builtinTemplate);
      if (t) openTemplatePreview(t, { mode });
    }));
    $$('[data-online-template]').forEach((card) => card.addEventListener('click', () => {
      const t = state.onlineTemplates.find((item) => item.id === card.dataset.onlineTemplate);
      if (t) openTemplatePreview(t, { mode });
    }));
  }

  function refreshTemplateGallery(mode) {
    const host = document.getElementById('template-gallery');
    if (host) {
      host.innerHTML = templateGalleryMarkup(mode);
      bindTemplateCards(mode);
    }
    const count = document.querySelector('.filter-row .count');
    if (count) count.textContent = `${filteredBuiltIn(mode).length} 套模板`;
  }

  async function runOnlineSearch(mode, token = null) {
    if (state.onlineLoading) return;
    const input = document.getElementById('online-query');
    if (input?.value !== undefined) state.onlineQuery = input.value.trim();
    if (mode === 'pick') state.pickTab = 'online'; else state.galleryTab = 'online';
    state.onlineLoading = true;
    state.onlineTried = true;
    refreshTemplateGallery(mode);
    try {
      const data = await api(`/api/templates/online?q=${encodeURIComponent(state.onlineQuery || '极简 商务')}`);
      state.onlineTemplates = data.items || [];
      if (data.notice) toast(data.notice, 'info');
    } catch (err) {
      state.onlineTemplates = [];
      toast('在线模板搜索失败', 'error', err.message);
    } finally {
      state.onlineLoading = false;
      if (mode === 'pick') renderPickTemplate(); else renderLibrary();
    }
    void token;
  }

  function openTemplatePreview(t, { mode = 'pick' } = {}) {
    const custom = !!t.custom;
    const isSelected = state.template?.id === t.id;
    const useImage = state.template?.id === t.id ? state.templateUseImage : (t.suggest_image !== false);
    const cover = custom && t.thumb_url
      ? `<img src="${e(t.thumb_url)}" alt="${e(t.name)}">`
      : renderSlide({ type: 'cover', title: '想法，被看见。', subtitle: t.description, eyebrow: t.category }, t, 0, 1);
    const sampleA = renderSlide({ type: 'bullets', title: '把复杂的事，讲简单。', eyebrow: '01 / INSIGHT', bullets: ['先定义真正的问题', '找到少数关键变量', '从一个最小行动开始'] }, t, 3, 10);
    const sampleB = renderSlide({ type: 'stats', title: '用三个数字，盯住进展', eyebrow: 'MEASURE', stats: [{ value: '3', label: '关键动作', note: '先聚焦' }, { value: '90', label: '验证天数', note: '小步快跑' }, { value: '1', label: '反馈机制', note: '持续复盘' }] }, t, 8, 10);
    const host = openModal(`
      <div class="modal-head"><div><h2>${e(t.name)}</h2><p>${e(t.description || '')}</p></div><button class="modal-close" data-close-modal>${icon('close', 15)}</button></div>
      <div class="modal-body">
        <div class="tpl-preview-large">${cover}</div>
        <div class="tpl-preview-meta">
          <div><span class="kicker">${custom ? 'WEB INSPIRATION' : 'ORIGINAL THEME'}</span><h3 style="margin-top:8px">${e(t.english || 'QIMING THEME')}</h3><p>${custom ? '配色来自联网图片的自动提取，你可以只使用配色，也可以把图片作为封面背景。' : '原创排版系统，封面、章节、内容、数据、金句页全部适配。导出时不添加任何水印。'}</p><div class="tags" style="display:flex;gap:5px;flex-wrap:wrap;margin-top:11px">${(t.tags || []).slice(0, 4).map((tag) => `<span class="badge badge-muted">${e(tag)}</span>`).join('')}</div></div>
          <div><span class="kicker">PALETTE</span><div class="swatches" style="margin-top:10px">${swatches(t)}</div>
            ${custom ? `<label class="checkbox" style="margin-top:14px"><input type="checkbox" id="use-cover-image" ${useImage ? 'checked' : ''}><span>使用这张图片作为封面背景<br><small style="color:var(--muted-2)">关闭后只提取图片配色，生成完全原创的封面</small></span></label>${t.source_url ? `<button class="section-link" style="margin-top:12px" data-external="${e(t.source_url)}">${icon('external', 13)} 查看图片来源</button>` : ''}` : ''}
          </div>
        </div>
        <div class="tpl-sample-row" style="margin-top:14px"><div class="sample">${sampleA}</div><div class="sample">${sampleB}</div></div>
      </div>
      <div class="modal-foot"><div class="left"><span class="hint">${custom ? '在线灵感模板' : '内置原创模板'} · 16:9</span></div><button class="btn btn-ghost" data-close-modal>取消</button><button class="btn btn-primary" data-apply-template>${isSelected ? '保持这个选择' : '使用这个模板'} ${icon('arrowRight', 14)}</button></div>
    `, 'modal-xl tpl-preview-modal');

    host.querySelector('[data-external]')?.addEventListener('click', (event) => {
      event.preventDefault();
      openExternal(event.currentTarget.dataset.external);
    });
    host.querySelector('[data-apply-template]')?.addEventListener('click', () => {
      const keepImage = custom ? !!host.querySelector('#use-cover-image')?.checked : true;
      const chosen = { ...t };
      if (custom && !keepImage) chosen.image_url = '';
      state.template = chosen;
      state.templateUseImage = custom ? keepImage : true;
      saveDraft();
      closeModal();
      if (mode === 'library') {
        toast(keepImage ? '模板已选好' : '已提取模板配色', 'success', '接下来描述你想讲的内容');
        navigate('#/create');
      } else if (mode === 'dashboard') {
        toast('模板已选好', 'success');
        navigate(state.outline ? '#/pick-template' : '#/library');
      } else {
        renderPickTemplate();
        toast('模板已选好', 'success', '下一步设置动画、旁白与视频');
      }
    });
  }

  async function createProjectFromTemplate() {
    if (!state.template) { toast('请先选择一个模板', 'error'); return; }
    if (!state.outline) { navigate('#/create'); return; }
    const template = { ...state.template };
    if (template.custom && !state.templateUseImage) template.image_url = '';
    const baseOptions = state.project?.options || {
      animations: true, audio: false, video: false, auto_advance: false,
      animation_level: 'standard',
      voice_zh: 'zh-CN-XiaoxiaoNeural', voice_en: 'en-US-JennyNeural',
    };
    const options = {
      ...baseOptions,
      reference_ids: state.references.map((item) => item.id),
      use_reference_cover: state.references.some((item) => item.kind === 'image') && state.useReferenceCover,
      reading_text: state.readingText || '',
      reading_title: state.readingTitle || '',
    };
    const payload = {
      title: state.outline.title,
      prompt: state.create.prompt || state.outline.title,
      outline: state.outline,
      template_id: template.id,
      template,
      options,
    };
    const buttons = $$('[data-action="template-next"]');
    buttons.forEach((b) => { b.disabled = true; b.innerHTML = `<span class="spinner"></span> 正在创建…`; });
    try {
      let data;
      if (state.project?.id) {
        data = await api(`/api/projects/${state.project.id}`, { method: 'PATCH', body: payload });
        toast('项目已更新', 'success');
      } else {
        data = await api('/api/projects', { method: 'POST', body: payload });
        toast('项目已创建', 'success');
      }
      state.project = data.project;
      state.outline = data.project.outline || state.outline;
      state.template = data.project.template || state.template;
      saveDraft();
      navigate('#/generate');
    } catch (err) {
      toast('创建项目失败', 'error', err.message);
      buttons.forEach((b) => { b.disabled = false; b.innerHTML = `下一步：设置生成 ${icon('arrowRight', 14)}`; });
    }
  }

  /* ---------------------------------------------------------------- generate */
  function genOptionTile(key, iconName, title, desc, on, disabled = false) {
    return `<div class="option-tile ${on ? 'on' : ''} ${disabled ? 'is-disabled' : ''}" data-gen-option="${key}" style="${disabled ? 'opacity:.55' : ''}">
      <div class="ot-top"><span class="ot-icon">${icon(iconName, 15)}</span><label class="switch mini-switch"><input type="checkbox" ${on ? 'checked' : ''} ${disabled ? 'disabled' : ''}><span></span></label></div>
      <strong>${title}</strong><span class="ot-desc">${desc}</span>
    </div>`;
  }

  function voiceOptions(language, selected) {
    const items = (state.voices || []).filter((voice) => voice.language === language);
    if (!items.length) return '<option value="">声音加载中…</option>';
    return items.map((voice) => `<option value="${e(voice.id)}" ${voice.id === selected ? 'selected' : ''}>${e(voice.name)} · ${e(voice.role)}</option>`).join('');
  }

  async function previewVoice(language) {
    const select = document.getElementById(language === 'en' ? 'voice-en' : 'voice-zh');
    const audio = document.getElementById('voice-preview');
    if (!select?.value) { toast('声音还在加载，请稍后再试', 'info'); return; }
    const button = document.querySelector(`[data-preview-voice="${language}"]`);
    if (button) { button.disabled = true; button.textContent = '生成中'; }
    try {
      const response = await fetch('/api/voice/preview', {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json', Accept: 'audio/*' },
        body: JSON.stringify({ voice: select.value }),
      });
      if (!response.ok) {
        let message = '试听生成失败';
        try { message = (await response.json()).error || message; } catch (_) {}
        throw new Error(message);
      }
      const url = URL.createObjectURL(await response.blob());
      if (audio) {
        if (audio.dataset.url) URL.revokeObjectURL(audio.dataset.url);
        audio.dataset.url = url;
        audio.src = url;
        audio.style.display = 'block';
        await audio.play();
      }
      toast('正在试听声音', 'success', select.options[select.selectedIndex]?.textContent || '');
    } catch (err) {
      toast('试听失败', 'error', err.message);
    } finally {
      if (button) { button.disabled = false; button.textContent = '试听'; }
    }
  }

  async function renderGenerate(token) {
    if (!state.project?.id) {
      renderShell({ title: '生成演示', active: 'create', content: `<div class="empty"><div class="empty-icon">${icon('sparkles', 25)}</div><h3>还没有准备生成的项目</h3><p>先完成大纲和模板选择，再回到这里设置动画、旁白与视频。</p><button class="btn btn-primary" data-nav="#/create" style="margin-top:18px">开始创作</button></div>` });
      return;
    }
    let project = state.project;
    try {
      const data = await api(`/api/projects/${project.id}`);
      if (token !== state.viewToken) return;
      project = data.project;
    } catch (err) {
      if (token !== state.viewToken) return;
      renderShell({ title: '生成演示', active: 'create', content: `<div class="empty"><div class="empty-icon">${icon('alert', 24)}</div><h3>无法读取项目</h3><p>${e(err.message)}</p></div>` });
      return;
    }
    state.project = project;
    state.outline = project.outline || state.outline;
    state.template = project.template || state.template;
    if (project.references?.length) state.references = project.references;
    if (!state.voices.length) {
      try { state.voices = (await api('/api/voices')).items || []; } catch (_) { state.voices = []; }
    }
    if (state.optionsProjectId !== project.id) {
      state.optionsProjectId = project.id;
      state.optionsDirty = false;
    }
    const options = { ...{
      animations: true, audio: false, video: false, auto_advance: true, animation_level: 'standard',
      voice_zh: 'zh-CN-XiaoxiaoNeural', voice_en: 'en-US-JennyNeural',
    }, ...(project.options || {}) };
    project.options = options;
    const status = project.status || 'draft';
    const isWorking = ['generating', 'running', 'queued'].includes(status);
    const isReady = status === 'ready';
    const isFailed = status === 'failed';
    const slides = state.outline?.slides || [];
    const cover = slides[0] || { type: 'cover', title: project.title, eyebrow: 'PRESENTATION' };
    const selectedOptions = [options.animations, options.audio, options.video].filter(Boolean).length;
    const autoDisabled = !options.audio;
    const warnings = project.warnings || [];
    const dirtyNote = state.optionsDirty ? `<div class="gs-warning">设置已修改，点击下方按钮重新生成后生效。</div>` : '';

    const content = `
      <div class="outline-top">
        <div class="title-wrap"><span class="eyebrow">STEP 04 · MAKE IT MOVE</span><h1 class="page-title" style="font-size:32px;margin-top:6px">${e(project.title || '未命名演示')}</h1><p class="page-sub" style="margin-top:7px">${slides.length} 页 · ${e(project.template?.name || '主题模板')} · 所有设置都可以在生成前调整。</p></div>
        <div class="page-actions"><button class="btn btn-outline" data-nav="#/outline">${icon('edit', 15)} 编辑大纲</button><button class="btn btn-outline" data-nav="#/pick-template">${icon('palette', 15)} 换模板</button></div>
      </div>
      ${flowSteps(4)}
      ${isWorking ? `<div class="project-status-banner" id="generation-banner">${icon('sparkles', 17)}<div style="flex:1"><strong id="generation-message">${e(project.message || '正在生成…')}</strong><br><span style="font-size:9.5px;opacity:.72">可以先去忙别的，生成完成后会自动刷新。不要关闭软件。</span><div class="progress-track" style="margin-top:9px;background:rgba(120,86,0,.14)"><div class="progress-fill" id="banner-progress" style="width:${project.progress || 2}%"></div></div></div><strong id="banner-percent" style="font-family:var(--mono);font-size:13px">${project.progress || 0}%</strong></div>` : ''}
      ${isFailed ? `<div class="project-status-banner failed">${icon('alert', 17)}<div style="flex:1"><strong>上一次生成没有完成</strong><br>${e(project.error || '未知错误')}</div><button class="btn btn-sm btn-outline" data-action="generate-now">重试</button></div>` : ''}
      ${isReady ? `<div class="gen-success" style="margin-bottom:16px">
        <div class="success-head"><span class="success-icon">${icon('check', 24)}</span><div style="flex:1"><h3>你的演示已经准备好了</h3><p>${slides.length} 页 · ${e(project.template?.name || '原创模板')} · ${project.file_size_human || ''} · 文件里没有水印。</p></div>${state.optionsDirty ? '<span class="badge badge-amber">设置有更新</span>' : '<span class="badge badge-mint">已就绪</span>'}</div>
        <div class="download-grid">
          <a class="download-card" href="${e(project.download_url || `/api/projects/${project.id}/download?format=pptx`)}" download> <span class="dc-ic">${icon('ppt', 16)}</span><div><strong>下载 PPTX</strong><span>可继续在 PowerPoint 中编辑</span></div></a>
          <button class="download-card" data-action="download-pdf" data-url="${e(project.pdf_url || `/api/projects/${project.id}/download?format=pdf`)}"><span class="dc-ic">${icon('file', 16)}</span><div><strong>下载 PDF</strong><span>适合直接分享与打印</span></div></button>
        </div>
        ${warnings.length ? `<div class="warn-list">${warnings.map((w) => `<div class="warn-item">${icon('info', 12)}<span>${e(w)}</span></div>`).join('')}</div>` : ''}
        <div style="display:flex;gap:8px;margin-top:14px;flex-wrap:wrap"><button class="btn btn-sm btn-outline" data-action="preview-ready">${icon('play', 13)} 放映预览</button><button class="btn btn-sm btn-ghost" data-action="open-output-folder">${icon('folder', 13)} 打开文件夹</button><button class="btn btn-sm btn-ghost" data-nav="#/projects">${icon('slides', 13)} 返回项目列表</button></div>
      </div>` : ''}
      <div class="gen-grid">
        <div class="gen-main">
          <section class="gen-card">
            <h3>${icon('zap', 16)} 这场演示会怎么动</h3>
            <p>动画会自动应用到每一页。开启旁白后，PPT 会按讲解节奏自动翻页。</p>
            <div class="option-grid">
              ${genOptionTile('animations', 'zap', '元素动画', '标题、卡片、图片依次入场；翻页也带转场。', options.animations)}
              ${genOptionTile('audio', 'audio', '逐页旁白', '使用本机中文语音合成旁白，自动播放。', options.audio)}
              ${genOptionTile('video', 'video', '动态封面视频', '生成一段抽象动态背景，循环播放。', options.video)}
              ${genOptionTile('auto_advance', 'clock', '自动翻页', autoDisabled ? '开启旁白后可用，按每页旁白时长前进。' : '按旁白时长自动前进，也保留点击翻页。', options.auto_advance, autoDisabled)}
            </div>
            <div class="voice-panel">
              <h4>${icon('audio', 13)} 旁白声音 <span class="badge badge-muted">可试听</span></h4>
              <p>中文和英文各选一个。英文课文会自动切换英文声音；不联网时自动回退到本机语音。</p>
              <div class="voice-row"><select class="select" id="voice-zh">${voiceOptions('zh', options.voice_zh)}</select><button class="btn btn-outline voice-preview-btn" type="button" data-preview-voice="zh">试听</button></div>
              <div class="voice-row"><select class="select" id="voice-en">${voiceOptions('en', options.voice_en)}</select><button class="btn btn-outline voice-preview-btn" type="button" data-preview-voice="en">试听</button></div>
              <audio id="voice-preview" controls style="width:100%;height:30px;margin-top:9px;display:none"></audio>
            </div>
            <div class="setting-block" style="border-top:1px solid var(--line);margin-top:15px;padding-bottom:0">
              <div class="sb-head"><label for="animation-level">动画强度</label><span class="value" style="color:var(--muted-2);font-family:var(--font);font-size:10px">动画开启时生效</span></div>
              <select class="select" id="animation-level" ${options.animations ? '' : 'disabled'}>
                <option value="subtle" ${options.animation_level === 'subtle' ? 'selected' : ''}>克制 · 以淡入为主</option>
                <option value="standard" ${options.animation_level === 'standard' ? 'selected' : ''}>标准 · 淡入 + 飞入 + 擦除</option>
                <option value="dynamic" ${options.animation_level === 'dynamic' ? 'selected' : ''}>动感 · 更多缩放与飞入</option>
              </select>
            </div>
          </section>
          <section class="gen-card">
            <h3>${icon('info', 16)} 生成前，最后确认</h3>
            <div class="meta-list" style="margin-top:13px">
              <div class="meta-row"><span>页面数量</span><strong>${slides.length} 页</strong></div>
              <div class="meta-row"><span>视觉模板</span><strong>${e(project.template?.name || '原创模板')}</strong></div>
              <div class="meta-row"><span>AI 来源</span><strong>${e(providerLabel(state.outline?.provider_used || project.provider_used))}</strong></div>
              <div class="meta-row"><span>参考素材</span><strong>${(project.references || []).length ? `${(project.references || []).length} 个${options.use_reference_cover ? ' · 图片作封面' : ''}` : '未使用'}</strong></div>
              <div class="meta-row"><span>导出文件</span><strong>PPTX · 无水印</strong></div>
            </div>
            <div class="hint" style="margin-top:13px">${options.audio ? '旁白会逐页合成，生成时间会比纯 PPT 稍长。' : '纯 PPT 生成通常在十几秒内完成。'} 如果本机缺少语音或视频组件，软件会自动跳过对应素材，不影响 PPT 导出。</div>
          </section>
        </div>
        <aside class="gen-summary">
          <div class="gs-kicker">${isReady ? 'READY TO PRESENT' : 'READY TO BUILD'}</div>
          <div class="gs-title">${e(project.title || state.outline?.title || '未命名演示')}</div>
          <div class="gs-cover">${renderSlide(cover, project.template, 0, slides.length)}</div>
          <div class="gs-list">
            <div class="gs-row"><span>模板</span><strong style="max-width:60%;text-align:right">${e(project.template?.name || '原创模板')}</strong></div>
            <div class="gs-row"><span>页数</span><strong>${slides.length} 页</strong></div>
            <div class="gs-row"><span>已开启</span><strong id="summary-options">${selectedOptions} 项动态能力</strong></div>
            <div class="gs-row"><span>参考素材</span><strong>${(project.references || []).length ? `${(project.references || []).length} 个` : '未使用'}</strong></div>
            <div class="gs-row"><span>翻页</span><strong>${options.auto_advance && options.audio ? '按旁白自动' : '手动点击'}</strong></div>
          </div>
          ${dirtyNote}
          ${isWorking ? `<div class="progress-box"><div class="progress-track"><div class="progress-fill" id="summary-progress" style="width:${project.progress || 2}%"></div></div><div class="progress-meta"><span id="summary-message">${e(project.message || '正在生成…')}</span><strong id="summary-percent">${project.progress || 0}%</strong></div></div><button class="btn btn-outline btn-block" style="margin-top:14px;border-color:rgba(255,255,255,.15);color:#f8f3e8" data-nav="#/dashboard">后台生成，回到总览</button>` : `
            <button class="btn btn-primary btn-lg btn-block" style="margin-top:16px" data-action="generate-now" ${state.optionsDirty ? '' : ''}>${icon('sparkles', 17)} ${isReady ? (state.optionsDirty ? '应用新设置并重新生成' : '重新生成') : '开始生成 PPT'}</button>
            <div class="hint" style="text-align:center;margin-top:9px;color:rgba(248,243,232,.32)">${isReady ? '旧文件仍可继续下载，重新生成后才会替换。' : '生成过程不会上传你的内容。'}</div>
          `}
        </aside>
      </div>`;
    renderShell({ title: '生成演示', active: 'create', content });
    bindGenerate(project);
    if (isWorking) startGenerationPolling(project.id, token);
  }

  function bindGenerate(project) {
    const options = project.options;
    const saveOptions = () => { state.optionsDirty = true; };
    $$('[data-gen-option]').forEach((tile) => {
      const key = tile.dataset.genOption;
      tile.addEventListener('click', (event) => {
        if (key === 'auto_advance' && !options.audio) { toast('先开启逐页旁白，才能按旁白自动翻页', 'info'); return; }
        if (event.target.closest('.switch')) return;
        toggleOption(key);
      });
      tile.querySelector('input[type="checkbox"]')?.addEventListener('change', (event) => {
        event.stopPropagation();
        if (key === 'auto_advance' && !options.audio) { event.target.checked = false; return; }
        options[key] = event.target.checked;
        if (key === 'audio' && !options[key]) options.auto_advance = false;
        applyOptionUI();
        saveOptions();
      });
    });
    const applyOptionUI = () => {
      $$('[data-gen-option]').forEach((tile) => {
        const key = tile.dataset.genOption;
        tile.classList.toggle('on', !!options[key]);
        const input = tile.querySelector('input[type="checkbox"]');
        if (input) input.checked = !!options[key];
        if (key === 'auto_advance') {
          const disabled = !options.audio;
          tile.style.opacity = disabled ? '.55' : '1';
          if (input) input.disabled = disabled;
          tile.querySelector('.ot-desc')?.replaceChildren(document.createTextNode(disabled ? '开启旁白后可用，按每页旁白时长前进。' : '按旁白时长自动前进，也保留点击翻页。'));
        }
      });
      const selected = [options.animations, options.audio, options.video].filter(Boolean).length;
      const count = document.getElementById('summary-options');
      if (count) count.textContent = `${selected} 项动态能力`;
      const level = document.getElementById('animation-level');
      if (level) level.disabled = !options.animations;
    };
    const toggleOption = (key) => {
      if (key === 'auto_advance' && !options.audio) return;
      options[key] = !options[key];
      if (key === 'audio' && !options.audio) options.auto_advance = false;
      applyOptionUI();
      saveOptions();
    };
    document.getElementById('animation-level')?.addEventListener('change', (event) => {
      options.animation_level = event.target.value;
      saveOptions();
    });
    document.getElementById('voice-zh')?.addEventListener('change', (event) => { options.voice_zh = event.target.value; saveOptions(); });
    document.getElementById('voice-en')?.addEventListener('change', (event) => { options.voice_en = event.target.value; saveOptions(); });
    $$('[data-preview-voice]').forEach((btn) => btn.addEventListener('click', () => previewVoice(btn.dataset.previewVoice)));
    $$('[data-action="generate-now"]').forEach((btn) => btn.addEventListener('click', () => startGeneration(project)));
    $('[data-action="download-pdf"]')?.addEventListener('click', (event) => {
      const url = event.currentTarget.dataset.url;
      toast('正在准备 PDF，首次转换可能需要几秒', 'info');
      downloadUrl(url);
    });
    $('[data-action="preview-ready"]')?.addEventListener('click', () => openPlayer(state.outline, project.template, options));
    $('[data-action="open-output-folder"]')?.addEventListener('click', () => {
      if (window.pywebview?.api?.open_data_folder) window.pywebview.api.open_data_folder();
      else toast('文件已下载到浏览器的默认下载目录', 'info');
    });
  }

  async function startGeneration(project) {
    const button = $('[data-action="generate-now"]');
    if (button) { button.disabled = true; button.innerHTML = `<span class="spinner"></span> 正在启动…`; }
    try {
      await api(`/api/projects/${project.id}`, { method: 'PATCH', body: { options: project.options } });
      state.optionsDirty = false;
      await api(`/api/projects/${project.id}/generate`, { method: 'POST' });
      state.project.status = 'queued';
      state.project.progress = 1;
      toast('开始生成，正在搭建你的演示', 'success');
      await renderGenerate(state.viewToken);
    } catch (err) {
      toast('无法开始生成', 'error', err.message);
      if (button) { button.disabled = false; button.innerHTML = `${icon('sparkles', 17)} 开始生成 PPT`; }
    }
  }

  function startGenerationPolling(projectId, token) {
    if (state.generationTimer) clearInterval(state.generationTimer);
    const tick = async () => {
      if (token !== state.viewToken) { clearInterval(state.generationTimer); return; }
      try {
        const data = await api(`/api/projects/${projectId}/status`);
        const percent = Math.max(0, Math.min(100, Number(data.progress || 0)));
        const fill = document.getElementById('summary-progress');
        const bannerFill = document.getElementById('banner-progress');
        if (fill) fill.style.width = `${percent}%`;
        if (bannerFill) bannerFill.style.width = `${percent}%`;
        const msg = document.getElementById('summary-message');
        const pct = document.getElementById('summary-percent');
        const bmsg = document.getElementById('generation-message');
        const bpct = document.getElementById('banner-percent');
        if (msg) msg.textContent = data.message || '正在生成…';
        if (bmsg) bmsg.textContent = data.message || '正在生成…';
        if (pct) pct.textContent = `${percent}%`;
        if (bpct) bpct.textContent = `${percent}%`;
        if (data.status === 'ready') {
          clearInterval(state.generationTimer);
          state.generationTimer = null;
          try {
            const detail = await api(`/api/projects/${projectId}`);
            if (token !== state.viewToken) return;
            state.project = detail.project;
            state.outline = detail.project.outline || state.outline;
            state.template = detail.project.template || state.template;
            toast('演示生成完成，可以下载了', 'success');
            await renderGenerate(token);
          } catch (_) { await renderGenerate(token); }
        } else if (data.status === 'failed') {
          clearInterval(state.generationTimer);
          state.generationTimer = null;
          toast('生成失败', 'error', data.error || '请重试');
          state.project.status = 'failed';
          state.project.error = data.error || '';
          await renderGenerate(token);
        }
      } catch (err) {
        // Keep polling through transient local errors.
        console.warn('generation poll failed', err);
      }
    };
    state.generationTimer = setInterval(tick, 1300);
    tick();
  }

  /* ----------------------------------------------------------- project detail */
  async function renderProjectDetail(projectId, token) {
    if (!projectId) { navigate('#/projects'); return; }
    renderShell({ title: '项目详情', active: 'projects', content: `<div class="skeleton" style="height:400px;border-radius:22px"></div>` });
    let data;
    try { data = await api(`/api/projects/${projectId}`); }
    catch (err) {
      if (token !== state.viewToken) return;
      renderShell({ title: '项目详情', active: 'projects', content: `<div class="empty"><div class="empty-icon">${icon('alert', 24)}</div><h3>项目不存在</h3><p>${e(err.message)}</p><button class="btn btn-primary" data-nav="#/projects" style="margin-top:16px">返回项目列表</button></div>` });
      return;
    }
    if (token !== state.viewToken) return;
    const project = data.project;
    state.project = project;
    state.outline = project.outline || state.outline;
    state.template = project.template || state.template;
    if (project.references?.length) state.references = project.references;
    if (state.lastProjectId !== project.id) {
      state.lastProjectId = project.id;
      state.projectSlideIndex = 0;
    }
    if (typeof state.projectSlideIndex !== 'number') state.projectSlideIndex = 0;
    const slides = state.outline?.slides || [];
    state.projectSlideIndex = Math.min(state.projectSlideIndex, Math.max(0, slides.length - 1));
    const status = project.status || 'draft';
    const isWorking = ['generating', 'running', 'queued'].includes(status);
    const isReady = status === 'ready';
    const isFailed = status === 'failed';
    const options = project.options || {};
    const currentIndex = state.projectSlideIndex;
    const theme = themeOf(project.template);
    const sources = state.outline?.sources || [];
    const references = project.references || [];
    const banner = isWorking ? `<div class="project-status-banner">${icon('sparkles', 17)}<div style="flex:1"><strong>正在生成「${e(project.title)}」</strong><br>${e(project.message || '正在搭建页面…')}</div><span class="mono" style="font-size:12px">${project.progress || 0}%</span></div>`
      : isReady ? `<div class="project-status-banner ready">${icon('check', 17)}<div style="flex:1"><strong>已完成 · ${project.file_size_human || ''}</strong><br>${project.download_count || 0} 次下载 · ${project.slide_count || slides.length} 页 · 无水印</div><div class="banner-actions"><button class="btn btn-sm btn-outline" data-action="preview-ready">${icon('play', 12)} 放映</button></div></div>`
      : isFailed ? `<div class="project-status-banner failed">${icon('alert', 17)}<div style="flex:1"><strong>生成失败</strong><br>${e(project.error || '请重试')}</div><button class="btn btn-sm btn-outline" data-action="go-generate">重试</button></div>`
      : `<div class="project-status-banner">${icon('info', 17)}<div style="flex:1"><strong>这是一份草稿</strong><br>完善大纲和模板后，设置动画并生成 PPT。</div><div class="banner-actions"><button class="btn btn-sm btn-primary" data-action="go-generate">去生成</button></div></div>`;

    const content = `
      <div class="project-head">
        <div><span class="eyebrow">PROJECT · ${String(project.id).padStart(4, '0')}</span><h1 class="ph-title">${e(project.title)}</h1><div class="ph-meta"><span class="badge ${isReady ? 'badge-mint' : isFailed ? 'badge-coral' : 'badge-muted'}">${statusLabel(status)}</span><span class="badge badge-outline">${slides.length} 页</span><span class="badge badge-outline">${e(project.template?.name || '模板')}</span><span class="hint">更新于 ${formatDate(project.updated_at)}</span></div></div>
        <div class="ph-actions">
          ${isReady ? `<a class="btn btn-primary" href="${e(project.download_url)}" download>${icon('download', 15)} 下载 PPTX</a>` : ''}
          <button class="btn btn-outline" data-action="edit-outline">${icon('edit', 15)} 编辑大纲</button>
          <button class="btn btn-outline" data-action="go-generate">${icon('zap', 15)} ${isReady ? '重新生成' : '生成'}</button>
          <button class="btn btn-icon btn-outline" data-action="duplicate-project" title="创建副本">${icon('copy', 16)}</button>
          <button class="btn btn-icon btn-outline" data-action="delete-project" title="删除项目" style="color:var(--danger)">${icon('trash', 16)}</button>
        </div>
      </div>
      ${banner}
      <div class="detail-grid">
        <div class="detail-main">
          <div class="preview-panel">
            <div class="pp-bar"><span class="pp-title">DECK PREVIEW · ${String(currentIndex + 1).padStart(2, '0')} / ${String(slides.length).padStart(2, '0')}</span><div class="pp-actions"><button class="btn btn-sm btn-outline" data-action="preview-ready">${icon('play', 12)} 放映预览</button></div></div>
            <div class="deck-carousel" id="deck-carousel">
              ${slides.map((slide, i) => `<div class="pv-wrap ${i === currentIndex ? 'active' : ''}" data-slide-wrap="${i}" style="position:absolute;inset:0;opacity:${i === currentIndex ? 1 : 0};transition:opacity .4s">${renderSlide(slide, theme, i, slides.length)}</div>`).join('')}
              <button class="carousel-nav prev" data-carousel="-1" aria-label="上一页">${icon('chevronLeft', 16)}</button>
              <button class="carousel-nav next" data-carousel="1" aria-label="下一页">${icon('chevronRight', 16)}</button>
            </div>
            <div class="carousel-dots" id="carousel-dots">${slides.map((_, i) => `<button class="carousel-dot ${i === currentIndex ? 'active' : ''}" data-carousel-dot="${i}" aria-label="第 ${i + 1} 页"></button>`).join('')}</div>
          </div>
          ${isReady ? `<div class="download-grid" style="margin-top:14px"><a class="download-card" href="${e(project.download_url)}" download><span class="dc-ic">${icon('ppt', 16)}</span><div><strong>下载 PPTX</strong><span>${project.file_size_human || ''} · 无水印</span></div></a><button class="download-card" data-action="download-pdf" data-url="${e(project.pdf_url)}"><span class="dc-ic">${icon('file', 16)}</span><div><strong>下载 PDF</strong><span>适合分享与打印</span></div></button></div>` : ''}
        </div>
        <aside class="detail-side">
          <div class="side-card"><h3>${icon('info', 14)} 项目信息</h3><div class="meta-list">
            <div class="meta-row"><span>视觉主题</span><strong>${e(project.template?.name || '原创模板')}</strong></div>
            <div class="meta-row"><span>页面数量</span><strong>${slides.length} 页</strong></div>
            <div class="meta-row"><span>AI 来源</span><strong>${e(providerLabel(project.provider_used || state.outline?.provider_used))}</strong></div>
            <div class="meta-row"><span>生成时间</span><strong>${formatDate(project.generated_at) || '—'}</strong></div>
            <div class="meta-row"><span>下载次数</span><strong>${project.download_count || 0} 次</strong></div>
          </div></div>
          <div class="side-card"><h3>${icon('zap', 14)} 动态能力</h3><div class="option-pills">
            <span class="option-pill ${options.animations ? 'on' : ''}">${icon('zap', 10)} 动画</span>
            <span class="option-pill ${options.audio ? 'on' : ''}">${icon('audio', 10)} 旁白</span>
            <span class="option-pill ${options.video ? 'on' : ''}">${icon('video', 10)} 视频</span>
            <span class="option-pill ${options.auto_advance && options.audio ? 'on' : ''}">${icon('clock', 10)} 自动翻页</span>
          </div><button class="btn btn-sm btn-outline btn-block" data-action="go-generate" style="margin-top:12px">${icon('settings', 13)} 调整生成设置</button></div>
          <div class="side-card"><h3>${icon('slides', 14)} 页面目录 <span>${slides.length}</span></h3><div class="side-outline">${slides.map((slide, i) => `<button class="${i === currentIndex ? 'active' : ''}" data-side-slide="${i}"><span class="n">${String(i + 1).padStart(2, '0')}</span><span class="t">${e(slide.title || '未命名页面')}</span></button>`).join('')}</div></div>
          ${references.length ? `<div class="side-card"><h3>${icon('paperclip', 14)} 参考素材 <span>${references.length}</span></h3><div class="ref-mini-list">${references.map((item) => `<div class="ref-mini">${item.thumb_url ? `<img src="${e(item.thumb_url)}" alt="">` : `<span class="ref-mini-file">${icon('file', 15)}</span>`}<div><strong>${e(item.filename)}</strong><span>${e(item.type_label)} · ${item.kind === 'image' ? `${item.width}×${item.height}` : `${item.char_count} 字`}</span></div></div>`).join('')}</div></div>` : ''}
          ${sources.length ? `<div class="side-card"><h3>${icon('globe', 14)} 参考来源 <span>${sources.length}</span></h3><div class="sources-list">${sources.map((s) => `<a class="source-row" href="${e(s.url)}" target="_blank" rel="noopener noreferrer" data-external="${e(s.url)}">${e(s.title || '网页资料')}</a>`).join('')}</div></div>` : ''}
        </aside>
      </div>`;
    renderShell({ title: '项目详情', active: 'projects', content });
    bindProjectDetail(project, token);
    if (isWorking) startProjectStatusPolling(project.id, token);
  }

  function bindProjectDetail(project, token) {
    const slides = state.outline?.slides || [];
    let current = state.projectSlideIndex || 0;
    const show = (index) => {
      current = (index + slides.length) % slides.length;
      state.projectSlideIndex = current;
      $$('[data-slide-wrap]').forEach((node) => { node.style.opacity = Number(node.dataset.slideWrap) === current ? '1' : '0'; });
      $$('[data-carousel-dot]').forEach((node, i) => node.classList.toggle('active', i === current));
      $$('[data-side-slide]').forEach((node, i) => node.classList.toggle('active', i === current));
      const label = document.querySelector('.pp-title');
      if (label) label.textContent = `DECK PREVIEW · ${String(current + 1).padStart(2, '0')} / ${String(slides.length).padStart(2, '0')}`;
    };
    $$('[data-carousel]').forEach((btn) => btn.addEventListener('click', () => show(current + Number(btn.dataset.carousel))));
    $$('[data-carousel-dot]').forEach((dot) => dot.addEventListener('click', () => show(Number(dot.dataset.carouselDot))));
    $$('[data-side-slide]').forEach((btn) => btn.addEventListener('click', () => show(Number(btn.dataset.sideSlide))));
    $('[data-action="edit-outline"]')?.addEventListener('click', () => { state.selectedSlide = 0; navigate('#/outline'); });
    $('[data-action="go-generate"]')?.addEventListener('click', () => navigate('#/generate'));
    $('[data-action="preview-ready"]')?.addEventListener('click', () => openPlayer(state.outline, project.template, project.options || {}));
    $('[data-action="download-pdf"]')?.addEventListener('click', (event) => {
      toast('正在准备 PDF，首次转换可能需要几秒', 'info');
      downloadUrl(event.currentTarget.dataset.url);
    });
    $('[data-action="duplicate-project"]')?.addEventListener('click', async () => {
      try {
        const data = await api(`/api/projects/${project.id}/duplicate`, { method: 'POST' });
        toast('已创建副本', 'success');
        navigate(`#/project/${data.project.id}`);
      } catch (err) { toast('复制失败', 'error', err.message); }
    });
    $('[data-action="delete-project"]')?.addEventListener('click', async () => {
      const yes = await confirmDialog({ title: '删除这份演示？', message: `「${project.title}」及其生成文件会从本机删除，无法恢复。`, confirmText: '删除项目', danger: true });
      if (!yes) return;
      try {
        await api(`/api/projects/${project.id}`, { method: 'DELETE' });
        clearDraft();
        toast('项目已删除', 'success');
        navigate('#/projects');
      } catch (err) { toast('删除失败', 'error', err.message); }
    });
    $$('[data-external]').forEach((link) => link.addEventListener('click', (event) => {
      event.preventDefault();
      openExternal(link.dataset.external);
    }));
    void token;
  }

  function startProjectStatusPolling(projectId, token) {
    if (state.projectTimer) clearInterval(state.projectTimer);
    state.projectTimer = setInterval(async () => {
      if (token !== state.viewToken) { clearInterval(state.projectTimer); return; }
      try {
        const data = await api(`/api/projects/${projectId}/status`);
        if (data.status === 'ready' || data.status === 'failed') {
          clearInterval(state.projectTimer);
          state.projectTimer = null;
          await renderProjectDetail(projectId, token);
          if (data.status === 'ready') toast('生成完成', 'success');
        }
      } catch (_) {}
    }, 1600);
  }

  /* ---------------------------------------------------------------- settings */
  const SETTINGS_TABS = [
    ['ai', 'AI 模型', 'sparkles'],
    ['account', '账户资料', 'user'],
    ['security', '登录安全', 'lock'],
    ['about', '数据与关于', 'database'],
  ];

  async function renderSettings(token) {
    renderShell({ title: 'AI 与账户', active: 'settings', content: `<div class="settings-layout"><div class="skeleton" style="height:320px;border-radius:18px"></div><div class="skeleton" style="height:520px;border-radius:18px"></div></div>` });
    let settings;
    let sessions = [];
    try {
      const [aiData, sessionData, meData] = await Promise.all([
        api('/api/ai/settings'),
        api('/api/auth/sessions'),
        api('/api/auth/me'),
      ]);
      settings = aiData.settings;
      sessions = sessionData.sessions || [];
      if (meData.user) { state.user = meData.user; state.meta.user = meData.user; }
    } catch (err) {
      if (token !== state.viewToken) return;
      renderShell({ title: 'AI 与账户', active: 'settings', content: `<div class="empty"><div class="empty-icon">${icon('alert', 24)}</div><h3>读取设置失败</h3><p>${e(err.message)}</p></div>` });
      return;
    }
    if (token !== state.viewToken) return;
    state.aiSettings = settings;
    state.sessions = sessions;
    const tab = state.settingsTab;
    const content = `
      ${pageHead('AI 与账户', '管理你的模型密钥、个人资料与登录设备。所有密钥只保存在这台电脑。', `<span class="badge badge-mint">${icon('shield', 11)} 本地存储</span>`)}
      <div class="settings-layout">
        <nav class="settings-nav">${SETTINGS_TABS.map(([key, label, ic]) => `<button class="${tab === key ? 'active' : ''}" data-settings-tab="${key}">${icon(ic, 15)} ${label}</button>`).join('')}</nav>
        <div class="settings-panel">${settingsTabContent(tab, settings, sessions)}</div>
      </div>`;
    renderShell({ title: 'AI 与账户', active: 'settings', content });
    bindSettings(settings, sessions);
  }

  function settingsTabContent(tab, settings, sessions) {
    if (tab === 'account') return accountSettings(settings);
    if (tab === 'security') return securitySettings(sessions);
    if (tab === 'about') return aboutSettings(settings);
    return aiSettingsPanel(settings);
  }

  function aiSettingsPanel(settings) {
    const provider = settings.provider || 'auto';
    const active = settings.active_provider;
    const allow = settings.allow_user_keys;
    const providerCards = [
      ['auto', '自动选择', '有云模型密钥时优先使用云模型，否则使用内置 AI。'],
      ['deepseek', 'DeepSeek', settings.global_ready?.deepseek ? '管理员已配置' : '深度推理 · 需 API Key'],
      ['doubao', '豆包', settings.global_ready?.doubao ? '管理员已配置' : '火山方舟 · 需 Endpoint'],
      ['custom', '自定义模型', settings.global_ready?.custom ? '管理员已配置' : '任意 OpenAI 兼容接口'],
      ['local', '启明内置 AI', '无需密钥 · 离线可用 · 结构化叙事'],
    ];
    return `
      ${allow ? '' : `<div class="admin-note">${icon('info', 13)}<span>管理员已关闭个人模型密钥配置。你仍可使用管理员配置的全局模型，或使用内置 AI。</span></div>`}
      <section class="settings-block">
        <h3>${icon('sparkles', 16)} 选择 AI 引擎</h3>
        <p class="block-sub">当前生效：<strong>${e(providerLabel(active))}</strong>。选择「自动」时，系统会按 DeepSeek → 豆包 → 自定义 → 内置 的顺序寻找可用模型。</p>
        <div class="provider-grid">
          ${providerCards.map(([key, name, desc]) => `<button class="provider-card ${provider === key ? 'active' : ''}" data-ai-provider="${key}" ${allow ? '' : 'disabled'}><div class="pc-top"><span class="pc-name">${key === active ? `<span class="pc-status ready"></span>` : `<span class="pc-status"></span>`} ${name}</span>${key === active ? '<span class="pc-badge">使用中</span>' : ''}</div><p>${desc}</p></button>`).join('')}
        </div>
        ${allow ? '' : '<div class="hint">个人密钥功能已被管理员关闭，下面的输入框不可编辑。</div>'}
      </section>
      <section class="settings-block">
        <h3>${icon('key', 16)} 个人模型密钥</h3>
        <p class="block-sub">这里的密钥会覆盖管理员的全局配置，只保存在本机数据库中，不会上传。模型调用会直接发生在这台电脑与模型服务之间。</p>
        ${apiKeyBlock('deepseek', 'DeepSeek', settings.deepseek, allow, 'https://api.deepseek.com', 'deepseek-chat')}
        ${apiKeyBlock('doubao', '豆包 / 火山方舟', settings.doubao, allow, 'https://ark.cn-beijing.volces.com/api/v3', '填入方舟 Endpoint ID')}
        ${apiKeyBlock('custom', '自定义 OpenAI 兼容接口', settings.custom, allow, 'https://your-api.com/v1', '模型名称')}
        <div class="key-actions">
          ${allow ? `<button class="btn btn-primary" data-action="save-ai">${icon('check', 14)} 保存模型设置</button>` : ''}
          <button class="btn btn-outline" data-action="test-ai">${icon('zap', 14)} 测试当前引擎</button>
          <span class="hint">测试会先使用已经保存的配置</span>
        </div>
        <div id="ai-test-result" class="hint" style="margin-top:10px"></div>
      </section>
      <section class="settings-block">
        <h3>${icon('info', 16)} 密钥从哪里来？</h3>
        <div class="meta-list">
          <div class="meta-row"><span>DeepSeek</span><strong>platform.deepseek.com → API Keys</strong></div>
          <div class="meta-row"><span>豆包</span><strong>火山方舟控制台 → 推理接入点</strong></div>
          <div class="meta-row"><span>自定义</span><strong>任何兼容 /chat/completions 的服务</strong></div>
        </div>
        <div class="hint" style="margin-top:12px">不配置任何密钥也能使用：内置 AI 会结合领域知识与联网检索，生成结构完整的大纲。</div>
      </section>`;
  }

  function apiKeyBlock(key, label, block, allow, basePlaceholder, modelPlaceholder) {
    return `<div class="api-key-block">
      <div class="ak-head"><span class="ak-title">${label} ${block.has_key ? '<span class="badge badge-mint">已配置</span>' : '<span class="badge badge-muted">未配置</span>'}</span><span class="hint">${block.key_masked || ''}</span></div>
      <div class="ak-grid">
        <div class="field"><label class="field-label">API Key</label><div class="input-wrap">${icon('key', 15)}<input class="input" type="password" data-ai-key="${key}" placeholder="${block.has_key ? '已保存，留空保持不变' : '粘贴 API Key'}" ${allow ? '' : 'disabled'} autocomplete="off"></div></div>
        <div class="field"><label class="field-label">模型</label><input class="input" data-ai-model="${key}" value="${e(block.model || '')}" placeholder="${e(modelPlaceholder)}" ${allow ? '' : 'disabled'}></div>
      </div>
      <div class="field" style="margin-top:8px"><label class="field-label">Base URL</label><input class="input" data-ai-base="${key}" value="${e(block.base_url || '')}" placeholder="${e(basePlaceholder)}" ${allow ? '' : 'disabled'}></div>
      ${block.has_key ? `<div class="key-actions"><button class="section-link" data-clear-key="${key}" style="color:var(--muted-2)">${icon('trash', 12)} 移除已保存的密钥</button></div>` : ''}
    </div>`;
  }

  function accountSettings() {
    const user = state.user || {};
    return `
      <section class="settings-block">
        <h3>${icon('user', 16)} 个人资料</h3>
        <p class="block-sub">这些信息会显示在工作台和导出的文档属性中。</p>
        <div class="account-avatar-row">${avatar(user, 'lg')}<div class="who"><strong>${e(user.display_name || user.username)}</strong><span>@${e(user.username)} · ${user.role === 'admin' ? '管理员' : '创作者'}</span></div></div>
        <form id="profile-form" class="form-stack" novalidate>
          <div class="form-row"><div class="field"><label class="field-label">用户名</label><input class="input" value="${e(user.username)}" disabled></div><div class="field"><label class="field-label">昵称</label><input class="input" id="profile-display-name" value="${e(user.display_name)}" maxlength="30"></div></div>
          <div class="field"><label class="field-label">邮箱 <small>选填</small></label><input class="input" id="profile-email" type="email" value="${e(user.email || '')}" placeholder="用于找回账号"></div>
          <div style="display:flex;gap:8px"><button class="btn btn-primary" type="submit">${icon('check', 14)} 保存资料</button><span class="hint" style="align-self:center">注册时间：${formatDate(user.created_at)}</span></div>
        </form>
      </section>
      <section class="settings-block">
        <h3>${icon('lock', 16)} 修改密码</h3>
        <p class="block-sub">修改后，其他设备上的登录会自动失效。</p>
        <form id="password-form" class="form-stack" novalidate>
          <div class="form-row"><div class="field"><label class="field-label">当前密码</label><input class="input" id="current-password" type="password" autocomplete="current-password"></div><div class="field"><label class="field-label">新密码</label><input class="input" id="new-password" type="password" autocomplete="new-password" placeholder="至少 6 位"></div></div>
          <div class="field"><label class="field-label">确认新密码</label><input class="input" id="confirm-password" type="password" autocomplete="new-password"></div>
          <div><button class="btn btn-primary" type="submit">${icon('check', 14)} 更新密码</button></div>
        </form>
      </section>`;
  }

  function securitySettings(sessions) {
    return `
      <section class="settings-block">
        <h3>${icon('shield', 16)} 登录设备</h3>
        <p class="block-sub">如果发现不是你的设备，可以立即让其他设备退出。</p>
        <div class="session-list">${(sessions || []).map((s) => `<div class="session-row"><span class="sr-ic">${icon(s.current ? 'user' : 'server', 14)}</span><div class="sr-body"><strong>${s.current ? '当前设备' : e(s.device || '其他设备')}</strong><span>${formatDate(s.last_seen)} · IP ${e(s.ip || '本地')}</span></div>${s.current ? '<span class="badge badge-mint">当前</span>' : ''}</div>`).join('') || '<div class="admin-empty">暂无登录记录</div>'}</div>
        <button class="btn btn-outline" style="margin-top:14px" data-action="revoke-sessions">${icon('logout', 14)} 让其他设备退出</button>
      </section>
      <section class="settings-block">
        <h3>${icon('lock', 16)} 安全建议</h3>
        <div class="meta-list"><div class="meta-row"><span>密码长度</span><strong>至少 6 位，建议 12 位以上</strong></div><div class="meta-row"><span>邀请码</span><strong>仅管理员掌握</strong></div><div class="meta-row"><span>会话有效期</span><strong>30 天</strong></div></div>
      </section>`;
  }

  function aboutSettings(settings) {
    const user = state.user || {};
    return `
      <section class="settings-block">
        <h3>${icon('database', 16)} 本机数据</h3>
        <p class="block-sub">启明 PPT 是本地优先的桌面软件。账号、项目、大纲与生成文件都保存在你的电脑上。</p>
        <div class="meta-list">
          <div class="meta-row"><span>数据位置</span><strong>本机应用数据目录</strong></div>
          <div class="meta-row"><span>模型密钥</span><strong>仅保存在本地数据库</strong></div>
          <div class="meta-row"><span>遥测 / 上传</span><strong>无</strong></div>
          <div class="meta-row"><span>导出水印</span><strong>无</strong></div>
        </div>
        <div style="display:flex;gap:8px;margin-top:15px;flex-wrap:wrap"><button class="btn btn-outline" data-action="open-data-folder">${icon('folder', 14)} 打开数据目录</button>${user.role === 'admin' ? `<button class="btn btn-outline" data-action="go-admin">${icon('shield', 14)} 进入管理后台</button>` : ''}</div>
      </section>
      <section class="settings-block">
        <h3>${icon('sparkles', 16)} 关于启明 PPT</h3>
        <p class="block-sub">把想法，讲成一场好戏。软件完全免费，导出无水印。</p>
        <div class="meta-list">
          <div class="meta-row"><span>版本</span><strong>${e(state.meta?.app?.version || '1.5.0')}</strong></div>
          <div class="meta-row"><span>可用模板</span><strong>${state.templates.length} 套内置 + 联网灵感</strong></div>
          <div class="meta-row"><span>当前 AI</span><strong>${e(providerLabel(settings?.active_provider))}</strong></div>
          <div class="meta-row"><span>开源致谢</span><strong>python-pptx · Flask · Pillow · Lucide 风格图标</strong></div>
        </div>
        <div class="hint" style="margin-top:13px">本软件不会在导出的 PPT 中添加任何品牌水印或广告。动画使用 PowerPoint 原生时间轴，可在 PowerPoint 中继续编辑。</div>
      </section>`;
  }

  function bindSettings(settings, sessions) {
    $$('[data-settings-tab]').forEach((btn) => btn.addEventListener('click', () => {
      state.settingsTab = btn.dataset.settingsTab;
      renderSettings(state.viewToken);
    }));
    let selectedProvider = settings.provider || 'auto';
    $$('[data-ai-provider]').forEach((btn) => {
      btn.addEventListener('click', () => {
        selectedProvider = btn.dataset.aiProvider;
        $$('[data-ai-provider]').forEach((node) => node.classList.toggle('active', node === btn));
      });
    });
    $('[data-action="save-ai"]')?.addEventListener('click', async () => {
      const payload = { provider: selectedProvider };
      ['deepseek', 'doubao', 'custom'].forEach((key) => {
        payload[`${key}_api_key`] = $(`[data-ai-key="${key}"]`)?.value || '';
        payload[`${key}_model`] = $(`[data-ai-model="${key}"]`)?.value || '';
        payload[`${key}_base_url`] = $(`[data-ai-base="${key}"]`)?.value || '';
      });
      const button = $('[data-action="save-ai"]');
      if (button) { button.disabled = true; button.innerHTML = '<span class="spinner"></span> 保存中'; }
      try {
        const data = await api('/api/ai/settings', { method: 'PUT', body: payload });
        state.aiSettings = data.settings;
        toast('模型设置已保存', 'success');
        await renderSettings(state.viewToken);
      } catch (err) {
        toast('保存失败', 'error', err.message);
        if (button) { button.disabled = false; button.innerHTML = `${icon('check', 14)} 保存模型设置`; }
      }
    });
    $('[data-action="test-ai"]')?.addEventListener('click', async () => {
      const box = document.getElementById('ai-test-result');
      if (box) box.innerHTML = `<span class="loading-inline"><span class="spinner dark"></span> 正在连接模型服务…</span>`;
      try {
        const data = await api('/api/ai/test', { method: 'POST', body: { provider: selectedProvider } });
        if (box) box.innerHTML = `<span class="badge ${data.result.ok ? 'badge-mint' : 'badge-coral'}">${data.result.ok ? '连接成功' : '连接失败'}</span> <span style="margin-left:6px">${e(data.result.message || '')}${data.result.latency_ms ? ` · ${data.result.latency_ms} ms` : ''}</span>`;
      } catch (err) {
        if (box) box.textContent = err.message;
      }
    });
    $$('[data-clear-key]').forEach((btn) => btn.addEventListener('click', async () => {
      const key = btn.dataset.clearKey;
      const yes = await confirmDialog({ title: '移除这个密钥？', message: '移除后，如果管理员没有配置全局密钥，将自动回退到内置 AI。', confirmText: '移除密钥', danger: true });
      if (!yes) return;
      try {
        await api('/api/ai/settings', { method: 'PUT', body: { provider: selectedProvider, [`${key}_api_key`]: 'CLEAR' } });
        toast('密钥已移除', 'success');
        await renderSettings(state.viewToken);
      } catch (err) { toast('移除失败', 'error', err.message); }
    }));
    $('#profile-form')?.addEventListener('submit', async (event) => {
      event.preventDefault();
      try {
        const data = await api('/api/auth/profile', {
          method: 'PATCH',
          body: {
            display_name: document.getElementById('profile-display-name')?.value || '',
            email: document.getElementById('profile-email')?.value || '',
          },
        });
        state.user = data.user;
        state.meta.user = data.user;
        toast('资料已保存', 'success');
        await renderSettings(state.viewToken);
      } catch (err) { toast('保存失败', 'error', err.message); }
    });
    $('#password-form')?.addEventListener('submit', async (event) => {
      event.preventDefault();
      const current = document.getElementById('current-password')?.value || '';
      const next = document.getElementById('new-password')?.value || '';
      const confirm = document.getElementById('confirm-password')?.value || '';
      if (next !== confirm) { toast('两次输入的新密码不一致', 'error'); return; }
      try {
        await api('/api/auth/password', { method: 'POST', body: { current_password: current, new_password: next } });
        toast('密码已更新', 'success', '其他设备上的登录已失效');
        event.target.reset();
      } catch (err) { toast('修改失败', 'error', err.message); }
    });
    $('[data-action="revoke-sessions"]')?.addEventListener('click', async () => {
      const yes = await confirmDialog({ title: '让其他设备退出？', message: '当前设备会保持登录，其他所有设备都需要重新登录。', confirmText: '退出其他设备' });
      if (!yes) return;
      try {
        await api('/api/auth/sessions/revoke', { method: 'POST' });
        toast('其他设备已退出', 'success');
        await renderSettings(state.viewToken);
      } catch (err) { toast('操作失败', 'error', err.message); }
    });
    $('[data-action="open-data-folder"]')?.addEventListener('click', () => {
      if (window.pywebview?.api?.open_data_folder) window.pywebview.api.open_data_folder();
      else toast('数据保存在本机应用数据目录中', 'info', '桌面版可直接打开文件夹');
    });
    $('[data-action="go-admin"]')?.addEventListener('click', () => { location.href = '/admin'; });
    void sessions;
  }

  /* ------------------------------------------------------------------ player */
  function openPlayer(outline, theme, options = {}) {
    const slides = outline?.slides || [];
    if (!slides.length) { toast('没有可以放映的页面', 'error'); return; }
    closePlayer();
    const frame = slides.map((slide, i) => `<div class="player-slide ${i === 0 ? 'active' : ''}">${renderSlide(slide, theme, i, slides.length)}</div>`).join('');
    const overlay = document.createElement('div');
    overlay.className = 'player-overlay';
    overlay.innerHTML = `
      <div class="player-top">
        <div><div class="pt-title">${e(outline.title || '演示预览')}</div><div class="pt-meta">${slides.length} 页 · 16:9 · 本地预览${options.audio ? ' · 旁白已开启' : ''}</div></div>
        <div class="pt-actions"><button class="btn btn-sm" data-player-close>${icon('close', 14)} 退出放映</button></div>
      </div>
      <div class="player-stage"><div class="player-frame" id="player-frame">${frame}</div></div>
      <div class="player-controls">
        <button class="pc-btn" data-player-prev aria-label="上一页">${icon('chevronLeft', 17)}</button>
        <button class="pc-btn pc-play" data-player-toggle aria-label="播放/暂停">${icon('pause', 18)}</button>
        <button class="pc-btn" data-player-next aria-label="下一页">${icon('chevronRight', 17)}</button>
        <span class="pc-page" id="player-page">01 / ${String(slides.length).padStart(2, '0')}</span>
        ${window.speechSynthesis ? `<button class="pc-btn" data-player-speak title="朗读当前页备注" aria-label="朗读">${icon('audio', 16)}</button>` : ''}
      </div>`;
    document.body.appendChild(overlay);
    document.body.classList.add('modal-open');
    state.player.index = 0;
    state.player.playing = true;
    state.player.slides = slides;
    state.player.options = options;

    const setIndex = (index) => {
      const total = slides.length;
      const next = (index + total) % total;
      state.player.index = next;
      $$('.player-slide', overlay).forEach((node, i) => node.classList.toggle('active', i === next));
      const label = document.getElementById('player-page');
      if (label) label.textContent = `${String(next + 1).padStart(2, '0')} / ${String(total).padStart(2, '0')}`;
      if (window.speechSynthesis) window.speechSynthesis.cancel();
      if (options.audio && state.player.playing) speakCurrent();
    };
    const schedule = () => {
      if (state.player.timer) clearInterval(state.player.timer);
      state.player.timer = setInterval(() => {
        if (!state.player.playing) return;
        setIndex(state.player.index + 1);
      }, options.audio ? 7000 : 5200);
    };
    window.__qimingPlayerNext = () => setIndex(state.player.index + 1);
    window.__qimingPlayerPrev = () => setIndex(state.player.index - 1);

    overlay.querySelector('[data-player-close]')?.addEventListener('click', closePlayer);
    overlay.querySelector('[data-player-prev]')?.addEventListener('click', () => setIndex(state.player.index - 1));
    overlay.querySelector('[data-player-next]')?.addEventListener('click', () => setIndex(state.player.index + 1));
    overlay.querySelector('[data-player-toggle]')?.addEventListener('click', (event) => {
      state.player.playing = !state.player.playing;
      event.currentTarget.innerHTML = icon(state.player.playing ? 'pause' : 'play', 18);
      if (!state.player.playing && window.speechSynthesis) window.speechSynthesis.cancel();
      if (state.player.playing && options.audio) speakCurrent();
    });
    overlay.querySelector('[data-player-speak]')?.addEventListener('click', speakCurrent);
    if (!options.audio) overlay.querySelector('[data-player-speak]')?.classList.add('hidden');
    setIndex(0);
    schedule();
  }

  function speakCurrent() {
    if (!window.speechSynthesis) return;
    const slides = state.player.slides || [];
    const slide = slides[state.player.index];
    const text = slide?.notes || slide?.title || '';
    if (!text) return;
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = 'zh-CN';
    utterance.rate = 0.96;
    utterance.pitch = 1;
    const voices = window.speechSynthesis.getVoices();
    const zh = voices.find((v) => /zh[-_]CN|Chinese|Huihui|Xiaoxiao/i.test(`${v.lang} ${v.name}`));
    if (zh) utterance.voice = zh;
    window.speechSynthesis.speak(utterance);
  }

  bootApp();
})();
