/* 启明 PPT — local administration console. */
(() => {
  'use strict';
  const { icon, logoMark } = window.QmIcons;
  const root = document.getElementById('admin-app');
  const modalRoot = document.getElementById('modal-root');
  const toastRoot = document.getElementById('toast-root');
  const state = {
    meta: null,
    user: null,
    view: 'overview',
    overview: null,
    users: [],
    projects: [],
    invites: [],
    events: [],
    settings: null,
    userQuery: '',
    projectQuery: '',
    toastId: 0,
  };
  const TITLES = {
    overview: ['系统总览', '看一下今天的工作台'],
    users: ['用户管理', '注册信息、状态与密码管理'],
    projects: ['项目记录', '所有用户生成的演示与文件'],
    invites: ['邀请码', '唯一的注册入口'],
    settings: ['系统设置', '模型、开关与运行环境'],
    events: ['操作日志', '登录、生成与管理动作'],
  };

  const $ = (s, scope = document) => scope.querySelector(s);
  const $$ = (s, scope = document) => Array.from(scope.querySelectorAll(s));
  function e(value) {
    return String(value ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#039;');
  }
  function formatDate(value) {
    if (!value) return '—';
    try {
      const d = new Date(value);
      if (Number.isNaN(d.getTime())) return String(value).slice(0, 16);
      return new Intl.DateTimeFormat('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }).format(d);
    } catch (_) { return String(value).slice(0, 16); }
  }
  function providerLabel(p) {
    return { auto: '自动', deepseek: 'DeepSeek', doubao: '豆包', custom: '自定义', local: '内置 AI' }[p] || p || '内置 AI';
  }
  function statusLabel(s) {
    return { draft: '草稿', ready: '已完成', failed: '失败', generating: '生成中', queued: '排队', running: '生成中' }[s] || s || '草稿';
  }
  function initials(name) { return String(name || '管').slice(0, 1).toUpperCase(); }
  function avatar(user) {
    return `<span class="avatar" style="--hue:${Number(user?.avatar_hue || 350)}">${e(initials(user?.display_name || user?.username))}</span>`;
  }
  function toast(message, type = 'info', detail = '') {
    const node = document.createElement('div');
    node.className = `toast ${type}`;
    node.innerHTML = `<span class="t-ic">${icon(type === 'success' ? 'check' : type === 'error' ? 'alert' : 'info', 13)}</span><div class="t-body"><strong>${e(message)}</strong>${detail ? `<span>${e(detail)}</span>` : ''}</div>`;
    toastRoot.appendChild(node);
    setTimeout(() => { node.classList.add('out'); setTimeout(() => node.remove(), 260); }, type === 'error' ? 5200 : 3800);
  }
  function closeModal() { modalRoot.innerHTML = ''; document.body.classList.remove('modal-open'); }
  function openModal(html, cls = '') {
    modalRoot.innerHTML = `<div class="modal-backdrop" data-modal-backdrop><div class="modal ${cls}" role="dialog" aria-modal="true">${html}</div></div>`;
    document.body.classList.add('modal-open');
    $$('[data-close-modal]').forEach((b) => b.addEventListener('click', closeModal));
    $('[data-modal-backdrop]')?.addEventListener('mousedown', (ev) => { if (ev.target === ev.currentTarget) closeModal(); });
    return modalRoot;
  }
  function confirmDialog({ title, message, confirmText = '确认', danger = false }) {
    return new Promise((resolve) => {
      const host = openModal(`<div class="modal-head"><div><h2>${e(title)}</h2><p>${e(message)}</p></div><button class="modal-close" data-close-modal>${icon('close', 15)}</button></div><div class="modal-foot" style="padding-top:18px"><button class="btn btn-ghost" data-no>取消</button><button class="btn ${danger ? 'btn-danger' : 'btn-primary'}" data-yes>${e(confirmText)}</button></div>`);
      let settled = false;
      const finish = (v) => { if (settled) return; settled = true; closeModal(); resolve(v); };
      host.querySelector('[data-no]')?.addEventListener('click', () => finish(false));
      host.querySelector('[data-yes]')?.addEventListener('click', () => finish(true));
      host.querySelector('.modal-close')?.addEventListener('click', () => finish(false));
      host.querySelector('[data-modal-backdrop]')?.addEventListener('mousedown', (ev) => { if (ev.target === ev.currentTarget) finish(false); });
    });
  }

  class ApiError extends Error {}
  async function api(path, options = {}) {
    const { method = 'GET', body } = options;
    const headers = { Accept: 'application/json' };
    const init = { method, credentials: 'same-origin', headers };
    if (body !== undefined) { headers['Content-Type'] = 'application/json'; init.body = JSON.stringify(body); }
    let response;
    try { response = await fetch(path, init); }
    catch (_) { throw new ApiError('无法连接本地服务'); }
    let data = {};
    const text = await response.text();
    if (text) { try { data = JSON.parse(text); } catch (_) { data = { error: text.slice(0, 120) }; } }
    if (!response.ok || data.ok === false) throw new ApiError(data.error || `请求失败（${response.status}）`);
    return data;
  }

  /* ------------------------------------------------------------------- login */
  function renderLogin() {
    root.innerHTML = `<div class="admin-auth">
      <div class="admin-login-card">
        <div class="al-brand">${logoMark(40)}<div><div class="t">启明 PPT</div><div class="s">ADMIN CONSOLE</div></div></div>
        <h1>管理后台</h1>
        <p class="desc">仅管理员可访问。使用管理员账号登录，查看用户、项目与系统设置。</p>
        <form id="admin-login-form" class="form-stack">
          <div class="field"><label class="field-label">管理员账号</label><div class="input-wrap">${icon('user', 16)}<input class="input" id="admin-username" autocomplete="username" placeholder="admin" autofocus></div></div>
          <div class="field"><label class="field-label">密码</label><div class="input-wrap">${icon('lock', 16)}<input class="input" id="admin-password" type="password" autocomplete="current-password" placeholder="管理员密码"></div></div>
          <div class="admin-error" id="admin-login-error"></div>
          <button class="btn btn-primary btn-lg" type="submit" id="admin-login-btn">${icon('shield', 16)} 进入后台</button>
        </form>
        <div class="al-foot">初始密码见软件数据目录中的「管理员初始账号.txt」<br>首次登录后请在设置中修改密码</div>
        <div class="back-link"><a href="/">← 返回用户端</a></div>
      </div>
    </div>`;
    $('#admin-login-form')?.addEventListener('submit', adminLogin);
  }

  async function adminLogin(event) {
    event.preventDefault();
    const username = $('#admin-username')?.value.trim() || '';
    const password = $('#admin-password')?.value || '';
    const error = $('#admin-login-error');
    const btn = $('#admin-login-btn');
    error.classList.remove('show');
    if (!username || !password) { error.textContent = '请输入账号和密码'; error.classList.add('show'); return; }
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner"></span> 正在验证';
    try {
      const data = await api('/api/auth/login', { method: 'POST', body: { username, password } });
      if (data.user.role !== 'admin') {
        await api('/api/auth/logout', { method: 'POST' });
        throw new ApiError('这个账号不是管理员');
      }
      state.user = data.user;
      toast('管理员登录成功', 'success');
      await bootAdmin();
    } catch (err) {
      error.textContent = err.message;
      error.classList.add('show');
      btn.disabled = false;
      btn.innerHTML = `${icon('shield', 16)} 进入后台`;
    }
  }

  function renderDenied() {
    root.innerHTML = `<div class="admin-auth"><div class="admin-login-card">
      <div class="al-brand">${logoMark(40)}<div><div class="t">启明 PPT</div><div class="s">ADMIN CONSOLE</div></div></div>
      <h1>没有管理员权限</h1>
      <p class="desc">当前登录账号是普通用户。请退出后使用管理员账号登录。</p>
      <div style="display:flex;gap:8px"><button class="btn btn-primary" data-denied-logout>退出并切换账号</button><a class="btn" href="/" style="border-color:rgba(255,255,255,.15);color:#f8f3e8">返回用户端</a></div>
    </div></div>`;
    $('[data-denied-logout]')?.addEventListener('click', async () => {
      try { await api('/api/auth/logout', { method: 'POST' }); } catch (_) {}
      state.user = null; renderLogin();
    });
  }

  /* ------------------------------------------------------------------- shell */
  const NAV = [
    ['overview', '总览', 'dashboard'],
    ['users', '用户管理', 'users'],
    ['projects', '项目记录', 'folder'],
    ['invites', '邀请码', 'key'],
    ['settings', '系统设置', 'settings'],
    ['events', '操作日志', 'file'],
  ];

  function renderShell(content, active) {
    const [title] = TITLES[active] || ['管理后台', ''];
    root.innerHTML = `<div class="admin-shell">
      <aside class="admin-sidebar" id="admin-sidebar">
        <div class="admin-brand">${logoMark(34)}<div><div class="t">启明 PPT</div><div class="s">ADMIN CONSOLE</div></div></div>
        <nav class="admin-nav">${NAV.map(([key, label, ic]) => `<button class="${active === key ? 'active' : ''}" data-admin-nav="${key}">${icon(ic, 15)} ${label}</button>`).join('')}</nav>
        <div class="as-bottom">
          <div class="side-user" style="margin-bottom:10px">${avatar(state.user)}<div class="who"><strong>${e(state.user?.display_name || '管理员')}</strong><span>管理员 · ${e(state.user?.username || '')}</span></div></div>
          <a class="admin-back" href="/">${icon('arrowLeft', 14)} 返回用户端</a>
        </div>
      </aside>
      <div class="admin-main">
        <header class="admin-topbar">
          <button class="btn btn-icon btn-ghost admin-mobile-menu" data-admin-menu>${icon('menu', 18)}</button>
          <h2>${e(title)}</h2>
          <div class="at-right"><span class="free-pill"><span class="dot"></span>本地运行</span><button class="btn btn-sm btn-ghost" data-admin-logout>${icon('logout', 14)} 退出</button></div>
        </header>
        <main class="admin-page">${content}</main>
      </div>
    </div>`;
    $('[data-admin-logout]')?.addEventListener('click', adminLogout);
    $('[data-admin-menu]')?.addEventListener('click', () => $('#admin-sidebar')?.classList.toggle('open'));
  }

  async function adminLogout() {
    try { await api('/api/auth/logout', { method: 'POST' }); } catch (_) {}
    state.user = null;
    renderLogin();
  }

  function navigateAdmin(view) {
    location.hash = `#/${view}`;
  }

  async function handleRoute() {
    if (!state.user) return renderLogin();
    if (state.user.role !== 'admin') return renderDenied();
    const view = (location.hash.replace(/^#\/?/, '') || 'overview').split('/')[0];
    state.view = view;
    $('#admin-sidebar')?.classList.remove('open');
    if (!TITLES[view]) return navigateAdmin('overview');
    if (view === 'overview') return loadOverview();
    if (view === 'users') return loadUsers();
    if (view === 'projects') return loadProjects();
    if (view === 'invites') return loadInvites();
    if (view === 'settings') return loadSettings();
    if (view === 'events') return loadEvents();
  }

  window.addEventListener('hashchange', () => { if (state.user) handleRoute(); });

  function skeletonPage(title) {
    renderShell(`<div class="admin-hero"><div><h1>${title}</h1><p class="page-desc">正在加载数据…</p></div></div><div class="skeleton" style="height:260px;border-radius:16px"></div>`, state.view);
  }

  /* ---------------------------------------------------------------- overview */
  async function loadOverview() {
    skeletonPage('系统总览');
    try {
      const data = await api('/api/admin/overview');
      state.overview = data;
      const stats = data.stats;
      const chart = stats.chart || {};
      const max = Math.max(1, ...(chart.registrations || [0]), ...(chart.generations || [0]));
      const chartHtml = (chart.labels || []).map((label, i) => {
        const reg = chart.registrations?.[i] || 0;
        const gen = chart.generations?.[i] || 0;
        return `<div class="chart-col"><div class="chart-bars"><div class="chart-bar" data-v="注册 ${reg}" style="height:${Math.max(3, (reg / max) * 100)}%"></div><div class="chart-bar alt" data-v="项目 ${gen}" style="height:${Math.max(3, (gen / max) * 100)}%"></div></div><span class="chart-label">${e(label)}</span></div>`;
      }).join('');
      const recentUsers = (stats.recent_users || []).map((u) => `<tr><td><span class="strong">${e(u.display_name || u.username)}</span><br><span style="font-size:8px">@${e(u.username)}</span></td><td>${formatDate(u.created_at)}</td><td><span class="status-pill ${u.is_active ? 'ready' : 'failed'}">${u.is_active ? '正常' : '停用'}</span></td></tr>`).join('') || '<tr><td colspan="3" class="admin-empty">暂无用户</td></tr>';
      const events = (data.recent_events || []).slice(0, 7).map((ev) => `<div class="event-row"><span class="event-dot"></span><div><strong>${e(ev.kind)}</strong><span>${e(ev.detail || '')}</span></div><time>${formatDate(ev.created_at)}</time></div>`).join('') || '<div class="admin-empty">暂无日志</div>';
      const content = `
        <div class="admin-hero"><div><h1>系统总览</h1><p class="page-desc">这里只属于你。查看注册、项目与系统运行情况。</p></div><div class="admin-hero-actions"><button class="btn btn-sm btn-outline" data-refresh>${icon('refresh', 13)} 刷新</button><a class="btn btn-sm btn-outline" href="/api/admin/export/users.csv">${icon('download', 13)} 导出用户</a><a class="btn btn-sm btn-primary" href="/" target="_blank">${icon('external', 13)} 打开用户端</a></div></div>
        <div class="admin-stat-grid">
          <div class="admin-stat"><div class="as-label">${icon('users', 13)} 总用户</div><div class="as-value">${stats.total_users}<small>人</small></div><div class="as-foot">${stats.active_users} 个账号正常</div></div>
          <div class="admin-stat"><div class="as-label">${icon('plus', 13)} 今日新增</div><div class="as-value">${stats.today_users}<small>人</small></div><div class="as-foot">邀请码累计使用 ${stats.invite_uses} 次</div></div>
          <div class="admin-stat"><div class="as-label">${icon('slides', 13)} 项目总数</div><div class="as-value">${stats.total_projects}<small>份</small></div><div class="as-foot">${stats.today_projects} 份创建于今天</div></div>
          <div class="admin-stat"><div class="as-label">${icon('download', 13)} 累计下载</div><div class="as-value">${stats.total_downloads}<small>次</small></div><div class="as-foot">已生成 ${stats.ready_projects} 份 · ${Math.round((stats.total_bytes || 0) / 1024 / 1024)} MB</div></div>
        </div>
        <div class="admin-col-2" style="margin-bottom:16px">
          <section class="admin-card"><h3>${icon('chart', 14)} 最近 7 天 <span class="hint">注册 / 新建项目</span></h3><div class="chart-legend" style="margin-bottom:4px"><span><i style="background:var(--coral)"></i>注册</span><span><i style="background:var(--cobalt);opacity:.6"></i>项目</span></div><div class="bar-chart">${chartHtml}</div></section>
          <section class="invite-card"><div class="ic-kicker">MASTER INVITE CODE</div><div class="ic-code">${e(data.invite.code)}</div><div class="ic-meta"><span>唯一有效邀请码</span><span>·</span><span>已被使用 ${data.invite.uses} 次</span></div><div class="ic-actions"><button class="btn" data-copy-invite="${e(data.invite.code)}">${icon('copy', 13)} 复制邀请码</button><button class="btn" data-admin-nav="invites">${icon('key', 13)} 查看记录</button></div></section>
        </div>
        <div class="admin-col-2">
          <section class="admin-card"><h3>${icon('users', 14)} 最近注册 <span class="hint">最新 6 位</span></h3><div class="table-wrap"><table class="data-table"><thead><tr><th>用户</th><th>注册时间</th><th>状态</th></tr></thead><tbody>${recentUsers}</tbody></table></div></section>
          <section class="admin-card"><h3>${icon('file', 14)} 最近操作</h3><div class="event-list">${events}</div></section>
        </div>
        <div class="admin-col-2" style="margin-top:16px">
          <section class="admin-card"><h3>${icon('sparkles', 14)} AI 引擎状态</h3><div class="meta-list">
            <div class="meta-row"><span>当前模式</span><strong>${e(providerLabel(data.providers.active))}</strong></div>
            <div class="meta-row"><span>DeepSeek</span><strong>${data.providers.deepseek ? '已配置' : '未配置'}</strong></div>
            <div class="meta-row"><span>豆包</span><strong>${data.providers.doubao ? '已配置' : '未配置'}</strong></div>
            <div class="meta-row"><span>联网检索</span><strong>${data.providers.online_search ? '开启' : '关闭'}</strong></div>
            <div class="meta-row"><span>在线模板</span><strong>${data.providers.online_templates ? '开启' : '关闭'}</strong></div>
            <div class="meta-row"><span>邮箱验证码</span><strong>${data.providers.email_verification ? (data.providers.smtp_ready ? '开启' : '开启 · SMTP未就绪') : '关闭'}</strong></div>
          </div><button class="btn btn-sm btn-outline btn-block" data-admin-nav="settings" style="margin-top:12px">${icon('settings', 13)} 去配置</button></section>
          <section class="admin-card"><h3>${icon('database', 14)} 运行环境</h3><div class="meta-list"><div class="meta-row"><span>版本</span><strong>${e(data.app.version)}</strong></div><div class="meta-row"><span>数据目录</span><strong style="max-width:65%;overflow:hidden;text-overflow:ellipsis">${e(data.app.data_dir)}</strong></div><div class="meta-row"><span>许可</span><strong>完全免费</strong></div></div><button class="btn btn-sm btn-outline btn-block" data-admin-nav="events" style="margin-top:12px">${icon('file', 13)} 查看完整日志</button></section>
        </div>`;
      renderShell(content, 'overview');
      $('[data-refresh]')?.addEventListener('click', loadOverview);
      $$('[data-copy-invite]').forEach((btn) => btn.addEventListener('click', () => copyText(btn.dataset.copyInvite)));
    } catch (err) {
      renderShell(`<div class="empty"><div class="empty-icon">${icon('alert', 24)}</div><h3>加载失败</h3><p>${e(err.message)}</p></div>`, 'overview');
    }
  }

  async function copyText(text) {
    try { await navigator.clipboard.writeText(text); toast('已复制', 'success'); }
    catch (_) {
      const input = document.createElement('textarea');
      input.value = text; document.body.appendChild(input); input.select();
      try { document.execCommand('copy'); toast('已复制', 'success'); } catch (e2) { toast('复制失败', 'error'); }
      input.remove();
    }
  }

  /* ------------------------------------------------------------------- users */
  async function loadUsers() {
    skeletonPage('用户管理');
    try {
      const data = await api(`/api/admin/users?q=${encodeURIComponent(state.userQuery)}&limit=200`);
      state.users = data.items || [];
      const content = `
        <div class="admin-hero"><div><h1>用户管理</h1><p class="page-desc">${state.users.length} 条记录 · 可停用账号或重置密码。</p></div><div class="admin-hero-actions"><a class="btn btn-sm btn-outline" href="/api/admin/export/users.csv">${icon('download', 13)} 导出 CSV</a></div></div>
        <div class="admin-note">${icon('shield', 13)}<span>密码以 PBKDF2 哈希保存，后台也无法查看明文。重置后请让用户使用新密码登录。</span></div>
        <div class="admin-toolbar"><div class="search-box">${icon('search', 14)}<input id="user-search" value="${e(state.userQuery)}" placeholder="搜索用户名、昵称或邮箱"></div><button class="btn btn-sm btn-primary" data-user-search>${icon('search', 13)} 搜索</button><button class="btn btn-sm btn-outline" data-user-refresh>${icon('refresh', 13)} 刷新</button></div>
        <div class="table-wrap"><table class="data-table"><thead><tr><th>ID</th><th>用户</th><th>邮箱</th><th>注册时间</th><th>最后登录</th><th>项目</th><th>状态</th><th>操作</th></tr></thead><tbody>
          ${state.users.map((u) => `<tr>
            <td class="mono">${u.id}</td>
            <td><span class="strong">${e(u.display_name || u.username)}</span><br><span style="font-size:8px">@${e(u.username)}${u.role === 'admin' ? ' · 管理员' : ''}</span></td>
            <td>${e(u.email || '—')}</td>
            <td>${formatDate(u.created_at)}</td>
            <td>${formatDate(u.last_login)}</td>
            <td>${u.project_count}</td>
            <td><span class="status-pill ${u.is_active ? 'ready' : 'failed'}">${u.is_active ? '正常' : '停用'}</span>${u.must_change_password ? '<br><span class="status-pill" style="margin-top:3px">待改密</span>' : ''}</td>
            <td><div class="actions"><button class="btn btn-sm btn-outline" data-reset-user="${u.id}">${icon('key', 12)} 重置</button>${u.role === 'admin' ? '' : `<button class="btn btn-sm ${u.is_active ? 'btn-danger' : 'btn-outline'}" data-toggle-user="${u.id}" data-active="${u.is_active ? '1' : '0'}">${u.is_active ? '停用' : '启用'}</button>`}</div></td>
          </tr>`).join('') || '<tr><td colspan="8" class="admin-empty">没有匹配的用户</td></tr>'}
        </tbody></table></div>`;
      renderShell(content, 'users');
      const search = $('#user-search');
      search?.addEventListener('keydown', (event) => { if (event.key === 'Enter') { state.userQuery = search.value; loadUsers(); } });
      $('[data-user-search]')?.addEventListener('click', () => { state.userQuery = search?.value || ''; loadUsers(); });
      $('[data-user-refresh]')?.addEventListener('click', loadUsers);
      $$('[data-reset-user]').forEach((btn) => btn.addEventListener('click', () => resetUser(Number(btn.dataset.resetUser))));
      $$('[data-toggle-user]').forEach((btn) => btn.addEventListener('click', () => toggleUser(Number(btn.dataset.toggleUser), btn.dataset.active === '1')));
    } catch (err) {
      renderShell(`<div class="empty"><div class="empty-icon">${icon('alert', 24)}</div><h3>加载失败</h3><p>${e(err.message)}</p></div>`, 'users');
    }
  }

  function debounce(fn, wait) {
    let t = null;
    return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), wait); };
  }

  async function toggleUser(id, active) {
    const yes = await confirmDialog({ title: active ? '停用这个账号？' : '重新启用账号？', message: active ? '停用后该用户的全部登录会话会立即失效，项目数据仍会保留。' : '启用后，该用户可以重新登录并继续使用。', confirmText: active ? '停用账号' : '启用账号', danger: active });
    if (!yes) return;
    try {
      await api(`/api/admin/users/${id}`, { method: 'PATCH', body: { is_active: !active } });
      toast(active ? '账号已停用' : '账号已启用', 'success');
      loadUsers();
    } catch (err) { toast('操作失败', 'error', err.message); }
  }

  function resetUser(id) {
    const host = openModal(`<div class="modal-head"><div><h2>重置用户密码</h2><p>可以设置一个临时密码，或让系统自动生成。</p></div><button class="modal-close" data-close-modal>${icon('close', 15)}</button></div>
      <div class="modal-body"><div class="field"><label class="field-label">新密码</label><input class="input" id="reset-password-input" placeholder="留空则自动生成 12 位密码" autocomplete="new-password"></div><div class="hint" style="margin-top:8px">用户下次登录后会看到修改密码提示。</div></div>
      <div class="modal-foot"><button class="btn btn-ghost" data-close-modal>取消</button><button class="btn btn-primary" data-reset-submit>确认重置</button></div>`);
    host.querySelector('[data-reset-submit]')?.addEventListener('click', async () => {
      const value = $('#reset-password-input')?.value || 'AUTO';
      try {
        const data = await api(`/api/admin/users/${id}`, { method: 'PATCH', body: { reset_password: value } });
        closeModal();
        if (data.generated_password) {
          const result = openModal(`<div class="modal-head"><div><h2>密码已重置</h2><p>请把下面的临时密码发给用户，关闭后不再显示。</p></div><button class="modal-close" data-close-modal>${icon('close', 15)}</button></div><div class="modal-body"><div class="invite-card"><div class="ic-kicker">TEMPORARY PASSWORD</div><div class="ic-code" style="font-size:24px">${e(data.generated_password)}</div><div class="ic-actions"><button class="btn" data-copy-temp="${e(data.generated_password)}">${icon('copy', 13)} 复制密码</button></div></div></div><div class="modal-foot"><button class="btn btn-primary" data-close-modal>完成</button></div>`);
          result.querySelector('[data-copy-temp]')?.addEventListener('click', () => copyText(data.generated_password));
        } else {
          toast('密码已重置', 'success');
        }
        loadUsers();
      } catch (err) { toast('重置失败', 'error', err.message); }
    });
  }

  /* ---------------------------------------------------------------- projects */
  async function loadProjects() {
    skeletonPage('项目记录');
    try {
      const data = await api(`/api/admin/projects?q=${encodeURIComponent(state.projectQuery)}&limit=200`);
      state.projects = data.items || [];
      const content = `
        <div class="admin-hero"><div><h1>项目记录</h1><p class="page-desc">${state.projects.length} 条生成记录 · 可下载或删除文件。</p></div><div class="admin-hero-actions"><a class="btn btn-sm btn-outline" href="/api/admin/export/projects.csv">${icon('download', 13)} 导出 CSV</a></div></div>
        <div class="admin-toolbar"><div class="search-box">${icon('search', 14)}<input id="project-search" value="${e(state.projectQuery)}" placeholder="搜索项目标题、用户或需求"></div><button class="btn btn-sm btn-primary" data-project-search>${icon('search', 13)} 搜索</button><button class="btn btn-sm btn-outline" data-project-refresh>${icon('refresh', 13)} 刷新</button></div>
        <div class="table-wrap"><table class="data-table"><thead><tr><th>ID</th><th>项目</th><th>用户</th><th>模板</th><th>状态</th><th>页数</th><th>大小</th><th>下载</th><th>创建时间</th><th>操作</th></tr></thead><tbody>
          ${state.projects.map((p) => `<tr>
            <td class="mono">${p.id}</td>
            <td><span class="strong">${e(p.title)}</span><br><span style="font-size:8px">${e(providerLabel(p.provider_used))}</span></td>
            <td>${e(p.display_name || p.username)}<br><span style="font-size:8px">@${e(p.username)}</span></td>
            <td>${e(p.template_id)}</td>
            <td><span class="status-pill ${e(p.status)}">${statusLabel(p.status)}</span></td>
            <td>${p.slide_count || 0}</td>
            <td>${p.file_size_human || '—'}</td>
            <td>${p.download_count || 0}</td>
            <td>${formatDate(p.created_at)}</td>
            <td><div class="actions">${p.status === 'ready' ? `<a class="btn btn-sm btn-outline" href="/api/projects/${p.id}/download?format=pptx">${icon('download', 12)}</a>` : ''}<button class="btn btn-sm btn-ghost" data-delete-project="${p.id}" title="删除">${icon('trash', 13)}</button></div></td>
          </tr>`).join('') || '<tr><td colspan="10" class="admin-empty">没有匹配的项目</td></tr>'}
        </tbody></table></div>`;
      renderShell(content, 'projects');
      const search = $('#project-search');
      search?.addEventListener('keydown', (event) => { if (event.key === 'Enter') { state.projectQuery = search.value; loadProjects(); } });
      $('[data-project-search]')?.addEventListener('click', () => { state.projectQuery = search?.value || ''; loadProjects(); });
      $('[data-project-refresh]')?.addEventListener('click', loadProjects);
      $$('[data-delete-project]').forEach((btn) => btn.addEventListener('click', () => deleteAdminProject(Number(btn.dataset.deleteProject))));
    } catch (err) {
      renderShell(`<div class="empty"><div class="empty-icon">${icon('alert', 24)}</div><h3>加载失败</h3><p>${e(err.message)}</p></div>`, 'projects');
    }
  }

  async function deleteAdminProject(id) {
    const yes = await confirmDialog({ title: '删除这个项目？', message: '项目的 PPTX 文件、图片与音频会一并从本机删除，无法恢复。', confirmText: '删除项目', danger: true });
    if (!yes) return;
    try { await api(`/api/admin/projects/${id}`, { method: 'DELETE' }); toast('项目已删除', 'success'); loadProjects(); }
    catch (err) { toast('删除失败', 'error', err.message); }
  }

  /* ----------------------------------------------------------------- invites */
  async function loadInvites() {
    skeletonPage('邀请码');
    try {
      const data = await api('/api/admin/invites');
      const content = `
        <div class="admin-hero"><div><h1>邀请码</h1><p class="page-desc">系统只接受一个主邀请码，确保注册入口可控。</p></div></div>
        <div class="invite-card" style="margin-bottom:16px"><div class="ic-kicker">MASTER INVITE CODE</div><div class="ic-code">${e(data.code)}</div><div class="ic-meta"><span>唯一有效邀请码</span><span>·</span><span>已使用 ${data.uses} 次</span><span>·</span><span>区分大小写</span></div><div class="ic-actions"><button class="btn" data-copy-invite="${e(data.code)}">${icon('copy', 13)} 复制邀请码</button><button class="btn" data-admin-nav="settings">${icon('settings', 13)} 注册开关</button></div></div>
        <div class="admin-note">${icon('shield', 13)}<span>注册时必须输入上面的邀请码。邀请码不能通过后台修改，如需更换请联系开发者。每次成功注册都会记录在这里。</span></div>
        <section class="admin-card"><h3>${icon('users', 14)} 使用记录 <span class="hint">${data.items.length} 条</span></h3><div class="table-wrap"><table class="data-table"><thead><tr><th>ID</th><th>用户</th><th>邀请码</th><th>IP</th><th>注册时间</th></tr></thead><tbody>
          ${(data.items || []).map((row) => `<tr><td class="mono">${row.id}</td><td><span class="strong">${e(row.display_name || row.username)}</span><br><span style="font-size:8px">@${e(row.username)}</span></td><td class="mono">${e(row.code)}</td><td class="mono">${e(row.ip || '—')}</td><td>${formatDate(row.created_at)}</td></tr>`).join('') || '<tr><td colspan="5" class="admin-empty">还没有人使用邀请码注册</td></tr>'}
        </tbody></table></div></section>`;
      renderShell(content, 'invites');
      $$('[data-copy-invite]').forEach((btn) => btn.addEventListener('click', () => copyText(btn.dataset.copyInvite)));
    } catch (err) {
      renderShell(`<div class="empty"><div class="empty-icon">${icon('alert', 24)}</div><h3>加载失败</h3><p>${e(err.message)}</p></div>`, 'invites');
    }
  }

  /* ---------------------------------------------------------------- settings */
  async function loadSettings() {
    skeletonPage('系统设置');
    try {
      const data = await api('/api/admin/settings');
      state.settings = data.settings;
      const s = data.settings;
      const content = `
        <div class="admin-hero"><div><h1>系统设置</h1><p class="page-desc">全局模型与功能开关。这些设置会立即影响所有用户。</p></div><div class="admin-hero-actions"><button class="btn btn-sm btn-primary" data-save-settings>${icon('check', 13)} 保存设置</button></div></div>
        ${state.user?.must_change_password ? `<div class="admin-note">${icon('lock', 13)}<span>当前管理员仍在使用初始密码，请在本页底部修改密码。</span></div>` : ''}
        <div class="admin-col-2">
          <div>
            <section class="admin-card" style="margin-bottom:16px"><h3>${icon('sparkles', 14)} 全局 AI 引擎</h3>
              <div class="field" style="margin-bottom:14px"><label class="field-label">默认策略</label><select class="select" id="global-provider"><option value="auto" ${s.ai_provider === 'auto' ? 'selected' : ''}>自动：有云模型则优先云模型</option><option value="local" ${s.ai_provider === 'local' ? 'selected' : ''}>仅内置 AI（离线）</option><option value="deepseek" ${s.ai_provider === 'deepseek' ? 'selected' : ''}>DeepSeek</option><option value="doubao" ${s.ai_provider === 'doubao' ? 'selected' : ''}>豆包</option><option value="custom" ${s.ai_provider === 'custom' ? 'selected' : ''}>自定义</option></select></div>
              ${adminKeyBlock('deepseek', 'DeepSeek', s.deepseek, 'https://api.deepseek.com', 'deepseek-chat')}
              ${adminKeyBlock('doubao', '豆包 / 火山方舟', s.doubao, 'https://ark.cn-beijing.volces.com/api/v3', 'Endpoint ID')}
              ${adminKeyBlock('custom', '自定义 OpenAI 兼容', s.custom, 'https://your-api.com/v1', '模型名称')}
              <div class="key-actions"><button class="btn btn-primary btn-sm" data-save-settings>${icon('check', 13)} 保存</button><button class="btn btn-outline btn-sm" data-test-provider="deepseek">${icon('zap', 13)} 测 DeepSeek</button><button class="btn btn-outline btn-sm" data-test-provider="doubao">测豆包</button><button class="btn btn-outline btn-sm" data-test-provider="custom">测自定义</button></div>
              <div class="hint" id="provider-test-result" style="margin-top:9px"></div>
            </section>
            <section class="admin-card" style="margin-bottom:16px"><h3>${icon('mail', 14)} 注册邮箱验证码 <span class="hint">SMTP</span></h3>
              <div class="admin-note">${icon('info', 13)}<span>开启后，新用户注册需要「邀请码 + 邮箱验证码」。请先填写 SMTP 并保存，再发送测试邮件确认。</span></div>
              <div class="admin-toggle-row"><div class="at-text"><strong>开启邮箱验证码</strong><span>关闭时保持仅邀请码注册</span></div><label class="switch"><input type="checkbox" id="set-email-verification" ${s.email_verification_enabled ? 'checked' : ''}><span></span></label></div>
              <div class="form-row" style="margin-top:12px">
                <div class="field"><label class="field-label">SMTP 服务器</label><input class="input" id="smtp-host" value="${e(s.smtp.host)}" placeholder="smtp.qq.com"></div>
                <div class="field"><label class="field-label">端口</label><input class="input" id="smtp-port" type="number" value="${e(s.smtp.port)}" placeholder="465"></div>
              </div>
              <div class="field" style="margin-top:9px"><label class="field-label">加密方式</label><select class="select" id="smtp-security"><option value="ssl" ${s.smtp.security === 'ssl' ? 'selected' : ''}>SSL（常用 465）</option><option value="starttls" ${s.smtp.security === 'starttls' ? 'selected' : ''}>STARTTLS（常用 587）</option><option value="none" ${s.smtp.security === 'none' ? 'selected' : ''}>不加密（不推荐）</option></select></div>
              <div class="form-row" style="margin-top:9px">
                <div class="field"><label class="field-label">SMTP 用户名</label><input class="input" id="smtp-username" value="${e(s.smtp.username)}" placeholder="通常是完整邮箱地址" autocomplete="off"></div>
                <div class="field"><label class="field-label">密码 / 授权码</label><input class="input" id="smtp-password" type="password" placeholder="${s.smtp.has_password ? '已保存，留空保持不变' : '邮箱授权码，不是登录密码'}" autocomplete="new-password"></div>
              </div>
              <div class="form-row" style="margin-top:9px">
                <div class="field"><label class="field-label">发件邮箱</label><input class="input" id="smtp-from" value="${e(s.smtp.from_addr)}" placeholder="noreply@example.com"></div>
                <div class="field"><label class="field-label">发件人名称</label><input class="input" id="smtp-from-name" value="${e(s.smtp.from_name)}" maxlength="40" placeholder="启明 PPT"></div>
              </div>
              ${s.smtp.has_password ? `<div class="key-actions"><button class="section-link" data-clear-smtp style="color:var(--muted-2)">${icon('trash', 12)} 清除已保存的 SMTP 密码</button></div>` : ''}
              <div style="display:flex;gap:7px;margin-top:14px;flex-wrap:wrap"><input class="input" id="test-email-to" style="flex:1;min-width:160px" placeholder="测试收件邮箱" value="${e(s.smtp.from_addr)}"><button class="btn btn-outline btn-sm" data-test-email>${icon('send', 13)} 发送测试邮件</button></div>
              <div class="hint" id="email-test-result" style="margin-top:9px">${s.email_verification_ready ? 'SMTP 配置完整，可以测试发送。' : '尚未填写 SMTP 服务器或发件邮箱。'}</div>
            </section>
            <section class="admin-card"><h3>${icon('settings', 14)} 功能开关</h3>
              <div class="admin-toggle-row"><div class="at-text"><strong>联网检索</strong><span>允许 AI 生成前搜索公开网页补充资料</span></div><label class="switch"><input type="checkbox" id="set-online-search" ${s.online_search_enabled ? 'checked' : ''}><span></span></label></div>
              <div class="admin-toggle-row"><div class="at-text"><strong>在线模板搜索</strong><span>允许用户从百度 / Bing 图片提取在线灵感配色</span></div><label class="switch"><input type="checkbox" id="set-online-templates" ${s.online_templates_enabled ? 'checked' : ''}><span></span></label></div>
              <div class="admin-toggle-row"><div class="at-text"><strong>允许个人密钥</strong><span>用户可以用自己的 DeepSeek / 豆包密钥覆盖全局配置</span></div><label class="switch"><input type="checkbox" id="set-allow-user-keys" ${s.allow_user_keys ? 'checked' : ''}><span></span></label></div>
              <div class="admin-toggle-row"><div class="at-text"><strong>开放注册</strong><span>关闭后即使有邀请码也不能创建新账号</span></div><label class="switch"><input type="checkbox" id="set-registration" ${s.registration_enabled ? 'checked' : ''}><span></span></label></div>
            </section>
          </div>
          <div>
            <section class="admin-card" style="margin-bottom:16px"><h3>${icon('zap', 14)} 新项目默认设置</h3>
              <div class="admin-toggle-row"><div class="at-text"><strong>默认开启动画</strong><span>每页元素入场与翻页转场</span></div><label class="switch"><input type="checkbox" id="set-default-anim" ${s.default_animations ? 'checked' : ''}><span></span></label></div>
              <div class="admin-toggle-row"><div class="at-text"><strong>默认开启旁白</strong><span>会明显增加生成时间</span></div><label class="switch"><input type="checkbox" id="set-default-audio" ${s.default_audio ? 'checked' : ''}><span></span></label></div>
              <div class="admin-toggle-row"><div class="at-text"><strong>默认开启视频</strong><span>生成动态封面背景</span></div><label class="switch"><input type="checkbox" id="set-default-video" ${s.default_video ? 'checked' : ''}><span></span></label></div>
              <div class="field" style="margin-top:13px"><label class="field-label">品牌标语</label><input class="input" id="set-tagline" value="${e(s.brand_tagline)}" maxlength="60"></div>
            </section>
            <section class="admin-card" style="margin-bottom:16px"><h3>${icon('server', 14)} 环境诊断</h3>
              <div class="meta-list"><div class="meta-row"><span>数据目录</span><strong style="max-width:64%;overflow:hidden;text-overflow:ellipsis">${e(state.overview?.app?.data_dir || '本机')}</strong></div><div class="meta-row"><span>PPT 生成</span><strong>python-pptx</strong></div><div class="meta-row"><span>视频编码</span><strong>ffmpeg</strong></div><div class="meta-row"><span>PDF 转换</span><strong>LibreOffice</strong></div><div class="meta-row"><span>语音合成</span><strong>Windows SAPI</strong></div></div>
              <button class="btn btn-outline btn-sm btn-block" data-diagnostics style="margin-top:12px">${icon('zap', 13)} 运行一次诊断</button>
              <div class="hint" id="diagnostics-result" style="margin-top:9px"></div>
            </section>
            <section class="admin-card danger-zone"><h3>${icon('lock', 14)} 修改管理员密码</h3>
              <form id="admin-password-form" class="form-stack">
                <div class="field"><label class="field-label">当前密码</label><input class="input" id="admin-current-password" type="password" autocomplete="current-password"></div>
                <div class="field"><label class="field-label">新密码</label><input class="input" id="admin-new-password" type="password" autocomplete="new-password" placeholder="至少 6 位"></div>
                <button class="btn btn-danger" type="submit">${icon('check', 13)} 更新管理员密码</button>
              </form>
            </section>
          </div>
        </div>`;
      renderShell(content, 'settings');
      $('#global-provider')?.addEventListener('change', () => {});
      $('[data-save-settings]')?.addEventListener('click', saveGlobalSettings);
      $$('[data-test-provider]').forEach((btn) => btn.addEventListener('click', () => testProvider(btn.dataset.testProvider)));
      $$('[data-clear-global]').forEach((btn) => btn.addEventListener('click', () => clearGlobalKey(btn.dataset.clearGlobal)));
      $('[data-test-email]')?.addEventListener('click', testEmail);
      $('[data-clear-smtp]')?.addEventListener('click', clearSmtpPassword);
      $('[data-diagnostics]')?.addEventListener('click', runDiagnostics);
      $('#admin-password-form')?.addEventListener('submit', changeAdminPassword);
    } catch (err) {
      renderShell(`<div class="empty"><div class="empty-icon">${icon('alert', 24)}</div><h3>加载失败</h3><p>${e(err.message)}</p></div>`, 'settings');
    }
  }

  function adminKeyBlock(key, label, block, basePlaceholder, modelPlaceholder) {
    return `<div class="api-key-block"><div class="ak-head"><span class="ak-title">${label} ${block.has_key ? '<span class="badge badge-mint">已配置</span>' : '<span class="badge badge-muted">未配置</span>'}</span><span class="hint">${e(block.key_masked || '')}</span></div>
      <div class="ak-grid"><div class="field"><label class="field-label">API Key</label><input class="input" type="password" data-global-key="${key}" placeholder="${block.has_key ? '留空保持不变' : '粘贴 API Key'}" autocomplete="off"></div><div class="field"><label class="field-label">模型</label><input class="input" data-global-model="${key}" value="${e(block.model || '')}" placeholder="${e(modelPlaceholder)}"></div></div>
      <div class="field" style="margin-top:8px"><label class="field-label">Base URL</label><input class="input" data-global-base="${key}" value="${e(block.base_url || '')}" placeholder="${e(basePlaceholder)}"></div>
      ${block.has_key ? `<div class="key-actions"><button class="section-link" data-clear-global="${key}" style="color:var(--muted-2)">${icon('trash', 12)} 清除密钥</button></div>` : ''}
    </div>`;
  }

  async function saveGlobalSettings() {
    const button = $('[data-save-settings]');
    if (button) { button.disabled = true; button.innerHTML = '<span class="spinner"></span> 保存中'; }
    const provider = $('#global-provider')?.value || 'auto';
    const payload = {
      ai_provider: provider,
      deepseek: { api_key: $('[data-global-key="deepseek"]')?.value || '', model: $('[data-global-model="deepseek"]')?.value || '', base_url: $('[data-global-base="deepseek"]')?.value || '' },
      doubao: { api_key: $('[data-global-key="doubao"]')?.value || '', model: $('[data-global-model="doubao"]')?.value || '', base_url: $('[data-global-base="doubao"]')?.value || '' },
      custom: { api_key: $('[data-global-key="custom"]')?.value || '', model: $('[data-global-model="custom"]')?.value || '', base_url: $('[data-global-base="custom"]')?.value || '' },
      online_search_enabled: $('#set-online-search')?.checked,
      online_templates_enabled: $('#set-online-templates')?.checked,
      allow_user_keys: $('#set-allow-user-keys')?.checked,
      registration_enabled: $('#set-registration')?.checked,
      email_verification_enabled: $('#set-email-verification')?.checked,
      smtp: {
        host: $('#smtp-host')?.value || '',
        port: $('#smtp-port')?.value || '',
        security: $('#smtp-security')?.value || 'ssl',
        username: $('#smtp-username')?.value || '',
        password: $('#smtp-password')?.value || '',
        from_addr: $('#smtp-from')?.value || '',
        from_name: $('#smtp-from-name')?.value || '',
      },
      default_animations: $('#set-default-anim')?.checked,
      default_audio: $('#set-default-audio')?.checked,
      default_video: $('#set-default-video')?.checked,
      brand_tagline: $('#set-tagline')?.value || '',
    };
    try {
      await api('/api/admin/settings', { method: 'PUT', body: payload });
      toast('系统设置已保存', 'success');
      loadSettings();
    } catch (err) {
      toast('保存失败', 'error', err.message);
      if (button) { button.disabled = false; button.innerHTML = `${icon('check', 13)} 保存设置`; }
    }
  }

  async function clearGlobalKey(key) {
    const yes = await confirmDialog({ title: '清除这个全局密钥？', message: '清除后，如果默认策略指向这个模型，系统会自动回退到其他可用模型或内置 AI。', confirmText: '清除密钥', danger: true });
    if (!yes) return;
    try {
      await api('/api/admin/settings', { method: 'PUT', body: { ai_provider: $('#global-provider')?.value || 'auto', [key]: { api_key: 'CLEAR' } } });
      toast('全局密钥已清除', 'success');
      loadSettings();
    } catch (err) { toast('清除失败', 'error', err.message); }
  }

  async function testProvider(provider) {
    const box = document.getElementById('provider-test-result');
    if (box) box.innerHTML = `<span class="loading-inline"><span class="spinner dark"></span> 正在测试 ${e(providerLabel(provider))}…</span>`;
    try {
      const data = await api('/api/admin/settings/test', { method: 'POST', body: { provider } });
      if (box) box.innerHTML = `<span class="badge ${data.result.ok ? 'badge-mint' : 'badge-coral'}">${data.result.ok ? '连接成功' : '连接失败'}</span> ${e(data.result.message || '')}${data.result.latency_ms ? ` · ${data.result.latency_ms}ms` : ''}`;
    } catch (err) { if (box) box.textContent = err.message; }
  }

  async function testEmail() {
    const box = document.getElementById('email-test-result');
    const button = $('[data-test-email]');
    const to = ($('#test-email-to')?.value || $('#smtp-from')?.value || '').trim();
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(to)) {
      toast('请先填写测试收件邮箱', 'error');
      return;
    }
    if (button) { button.disabled = true; button.innerHTML = '<span class="spinner dark"></span> 发送中'; }
    if (box) box.innerHTML = `<span class="loading-inline"><span class="spinner dark"></span> 正在连接 SMTP 并发送测试邮件…</span>`;
    try {
      const data = await api('/api/admin/email/test', { method: 'POST', body: { to } });
      if (box) box.innerHTML = `<span class="badge badge-mint">发送成功</span> 请检查 ${e(to)} 的收件箱。`;
      toast('测试邮件已发送', 'success');
    } catch (err) {
      if (box) box.innerHTML = `<span class="badge badge-coral">发送失败</span> ${e(err.message)}`;
      toast('测试邮件发送失败', 'error', err.message);
    } finally {
      if (button) { button.disabled = false; button.innerHTML = `${icon('send', 13)} 发送测试邮件`; }
    }
  }

  async function clearSmtpPassword() {
    const yes = await confirmDialog({ title: '清除 SMTP 密码？', message: '清除后邮件验证码将自动关闭，直到重新填写授权码并再次开启。', confirmText: '清除并关闭', danger: true });
    if (!yes) return;
    try {
      await api('/api/admin/settings', { method: 'PUT', body: { email_verification_enabled: false, smtp: { password: 'CLEAR' } } });
      toast('SMTP 密码已清除，邮箱验证已关闭', 'success');
      loadSettings();
    } catch (err) { toast('清除失败', 'error', err.message); }
  }

  async function runDiagnostics() {
    const box = document.getElementById('diagnostics-result');
    if (box) box.innerHTML = `<span class="loading-inline"><span class="spinner dark"></span> 正在检查本机组件，可能需要几十秒…</span>`;
    try {
      const data = await api('/api/admin/test-generate', { method: 'POST' });
      box.innerHTML = `<div style="display:flex;flex-direction:column;gap:4px"><span>${data.libreoffice ? '✅' : '⚠️'} LibreOffice：${data.libreoffice ? '可用' : '未安装（PDF 导出不可用）'}</span><span>${data.ffmpeg ? '✅' : '⚠️'} 视频编码：${data.ffmpeg ? '可用' : '不可用'}</span><span>${data.tts ? '✅' : '⚠️'} 中文语音：${data.tts ? '可用' : '不可用'}</span><span>Python ${e(data.python_version)}</span></div>`;
    } catch (err) { if (box) box.textContent = err.message; }
  }

  async function changeAdminPassword(event) {
    event.preventDefault();
    const current = $('#admin-current-password')?.value || '';
    const next = $('#admin-new-password')?.value || '';
    if (next.length < 6) { toast('新密码至少 6 位', 'error'); return; }
    try {
      await api('/api/admin/password', { method: 'POST', body: { current_password: current, new_password: next } });
      toast('管理员密码已更新', 'success');
      state.user.must_change_password = false;
      event.target.reset();
      loadSettings();
    } catch (err) { toast('修改失败', 'error', err.message); }
  }

  /* ------------------------------------------------------------------ events */
  async function loadEvents() {
    skeletonPage('操作日志');
    try {
      const data = await api('/api/admin/events');
      const content = `<div class="admin-hero"><div><h1>操作日志</h1><p class="page-desc">最近 ${data.items.length} 条系统事件。</p></div><div class="admin-hero-actions"><button class="btn btn-sm btn-outline" data-refresh-events>${icon('refresh', 13)} 刷新</button></div></div>
        <div class="table-wrap"><table class="data-table"><thead><tr><th>ID</th><th>类型</th><th>用户</th><th>详情</th><th>IP</th><th>时间</th></tr></thead><tbody>
          ${(data.items || []).map((ev) => `<tr><td class="mono">${ev.id}</td><td><span class="status-pill ${/failed|denied/.test(ev.kind) ? 'failed' : /login|register|generate|download/.test(ev.kind) ? 'ready' : ''}">${e(ev.kind)}</span></td><td>${e(ev.username || '—')}</td><td>${e(ev.detail || '')}</td><td class="mono">${e(ev.ip || '—')}</td><td>${formatDate(ev.created_at)}</td></tr>`).join('') || '<tr><td colspan="6" class="admin-empty">暂无日志</td></tr>'}
        </tbody></table></div>`;
      renderShell(content, 'events');
      $('[data-refresh-events]')?.addEventListener('click', loadEvents);
    } catch (err) {
      renderShell(`<div class="empty"><div class="empty-icon">${icon('alert', 24)}</div><h3>加载失败</h3><p>${e(err.message)}</p></div>`, 'events');
    }
  }

  /* -------------------------------------------------------------------- boot */
  async function bootAdmin() {
    try {
      const meta = await api('/api/meta');
      state.meta = meta;
      state.user = meta.user;
      if (!state.user) { renderLogin(); return; }
      if (state.user.role !== 'admin') { renderDenied(); return; }
      try { state.overview = await api('/api/admin/overview'); } catch (_) {}
      if (!location.hash) history.replaceState(null, '', '#/overview');
      await handleRoute();
    } catch (err) {
      renderLogin();
      setTimeout(() => toast('无法连接本地服务', 'error', err.message), 300);
    }
  }

  // Add event rows styles dynamically with the shared icons.
  document.addEventListener('click', (event) => {
    const nav = event.target.closest('[data-admin-nav]');
    if (nav) { event.preventDefault(); navigateAdmin(nav.dataset.adminNav); }
  });
  document.addEventListener('keydown', (event) => { if (event.key === 'Escape') closeModal(); });
  bootAdmin();
})();
