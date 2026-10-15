(() => {
  const authOverlay = document.getElementById('authOverlay');
  const studioOverlay = document.getElementById('studioOverlay');
  const stagePanel = document.getElementById('stagePanel');
  const stageList = document.getElementById('stageList');
  const progressBar = document.getElementById('progressBar');
  const chatPanel = document.getElementById('chatPanel');
  const nodeSpine = document.getElementById('nodeSpine');
  const workspaceTitle = document.getElementById('workspaceTitle');
  const sessionKey = 'coblanc_session_v3';
  const stages = ['上传双方照片', '风格与身高', '女生造型', '男生造型', '摄影场景', '方案确认', '样片验收', '九张成片'];
  const macroStages = ['上传照片', '选风格', '选妆造', '选场景', '样片确认', '批量出片'];
  const stageToMacro = [0, 1, 2, 2, 3, 4, 4, 5];
  let codeTimer = null;
  let project = freshProject();


  // ===== 真实接口（同源 /api，开发时由 Vite 代理到后端 8000）=====
  const API_BASE = '';
  const POLL_MS = 1500;
  const PAUSED = ['waiting_user', 'preview_ready', 'awaiting_payment', 'done', 'failed'];
  const SPEAKERS = { intake: '小囍（项目经理）', styling: '妆造师', framing: '摄影师' };
  const REDO_REASONS = [['face', '脸不像'], ['body', '身材比例不对'], ['hands', '手部有问题'], ['style', '不喜欢这个风格'], ['other', '其他']];
  let pollTimer = null;
  let lastKey = '';

  async function request(path, options = {}) {
    let res;
    try {
      res = await fetch(API_BASE + path, options);
    } catch (error) {
      throw new Error('连不上后端服务（' + path + '），请确认后端已启动');
    }
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      const error = new Error(data?.error?.message || data?.detail?.[0]?.msg || ('HTTP ' + res.status));
      error.code = data?.error?.code || ('HTTP_' + res.status);
      throw error;
    }
    return data;
  }
  function post(path, body) {
    return request(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  }
  const api = {
    upload(file) { const form = new FormData(); form.append('file', file); return request('/api/uploads', { method: 'POST', body: form }); },
    createTask(body) { return post('/api/tasks', body); },
    getTask(taskId) { return request(`/api/tasks/${taskId}`); },
    answers(taskId, answers) { return post(`/api/tasks/${taskId}/answers`, { answers }); },
    review(taskId, payload) { return post(`/api/tasks/${taskId}/review`, payload); },
    pay(taskId) { return post(`/api/tasks/${taskId}/pay`, { method: 'mock' }); }
  };

  function showApiError(error) {
    project.apiError = error.code ? `${error.code}：${error.message}` : error.message;
  }
  function stopPolling() { clearTimeout(pollTimer); pollTimer = null; }
  function startPolling() { stopPolling(); lastKey = ''; poll(); }
  async function poll() {
    if (!project.taskId) return;
    try {
      const data = await api.getTask(project.taskId);
      const key = JSON.stringify([data.status, data.step, data.step_text, (data.questions || []).map((q) => q.question_id), (data.previews || []).map((p) => p.image_id)]);
      if (key !== lastKey) {
        lastKey = key;
        applyTask(data);
        if (studioOverlay.classList.contains('open')) renderStudio();
      } else {
        project.task = data;
      }
      if (PAUSED.includes(data.status)) return stopPolling();
    } catch (error) {
      showApiError(error);
      if (error.code === 'TASK_NOT_FOUND') { dropTask(); renderStudio(); return; }
      renderStudio();
    }
    pollTimer = setTimeout(poll, POLL_MS);
  }
  function applyTask(data) {
    project.task = data;
    const previews = data.previews || [];
    if (data.status === 'waiting_user') {
      project.answers = {};
      (data.questions || []).forEach((q) => {
        if (q.type === 'multi_choice') project.answers[q.question_id] = Array.isArray(q.recommended) ? [...q.recommended] : [];
        else if (q.type === 'upload') project.answers[q.question_id] = [];
        else project.answers[q.question_id] = q.recommended ?? '';
      });
    }
    if (data.status === 'preview_ready') {
      project.selectedImage = (previews.find((p) => p.is_best) || previews[0])?.image_id || '';
      if (data.generation?.stage === 'set') { project.finalPreviews = previews; project.stage = 7; }
      else { project.sampleUrl = previews[0]?.url || ''; project.stage = 6; }
    }
    if (['awaiting_payment', 'delivering', 'done'].includes(data.status)) project.stage = 7;
    project.sampleReady = Boolean(project.sampleUrl);
    project.finalReady = data.status === 'done';
  }
  function dropTask() {
    stopPolling();
    Object.assign(project, { taskId: null, task: null, sampleUrl: '', finalPreviews: [], selectedImage: '', answers: {}, sampleReady: false, finalReady: false, showRework: false });
  }
  async function act(action) {
    if (project.busy) return;
    project.busy = true;
    project.apiError = '';
    renderStudio();
    try {
      await action();
      startPolling();
    } catch (error) {
      showApiError(error);
    } finally {
      project.busy = false;
      renderStudio();
    }
  }
  function fileIds(role) { return project.uploads[role].filter((photo) => photo.fileId).map((photo) => photo.fileId); }
  function buildDescription() {
    const b = project.bride, g = project.groom;
    return [
      `风格：${project.style}`,
      `身高：女生 ${project.brideHeight}cm / 男生 ${project.groomHeight}cm`,
      project.styleNote && `风格补充：${project.styleNote}`,
      `女生造型：妆容 ${b.makeup}，发型 ${b.hair}，服装 ${b.outfit}`,
      b.note && `女生补充：${b.note}`,
      `男生造型：妆容 ${g.makeup}，发型 ${g.hair}，服装 ${g.outfit}`,
      g.note && `男生补充：${g.note}`,
      `场景：${project.scene}`,
      project.sceneNote && `摄影补充：${project.sceneNote}`
    ].filter(Boolean).join('\n');
  }

  function freshProject() {
    return {
      stage: 0,
      uploads: { bride: [], groom: [] },
      uploadError: { bride: '', groom: '' },
      style: '',
      brideHeight: '165',
      groomHeight: '180',
      styleNote: '',
      bride: { makeup: '', hair: '', outfit: '', note: '' },
      groom: { makeup: '', hair: '', outfit: '', note: '' },
      scene: '',
      sceneNote: '',
      sampleReady: false,
      sampleNote: '',
      showRework: false,
      finalReady: false,
      taskId: null,
      task: null,
      busy: false,
      apiError: '',
      answers: {},
      sampleUrl: '',
      finalPreviews: [],
      selectedImage: ''
    };
  }

  function escapeHTML(value) {
    return String(value ?? '').replace(/[&<>'"]/g, (char) => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;'
    })[char]);
  }

  function getSession() {
    try {
      const session = JSON.parse(localStorage.getItem(sessionKey) || 'null');
      return session && session.phone ? session : null;
    } catch (error) {
      return null;
    }
  }

  function setSession(phone) {
    const session = { phone, loginAt: new Date().toISOString() };
    try { localStorage.setItem(sessionKey, JSON.stringify(session)); } catch (error) {}
    return session;
  }

  function clearSession() {
    try { localStorage.removeItem(sessionKey); } catch (error) {}
  }

  function maskPhone(phone) {
    return phone.slice(0, 3) + ' **** ' + phone.slice(-4);
  }

  function updateSessionUI() {
    const session = getSession();
    document.querySelectorAll('[data-open-studio]').forEach((button) => {
      if (button.classList.contains('nav-action')) button.textContent = session ? '继续我的项目' : '登录 / 我的项目';
    });
    document.getElementById('studioUser').textContent = session ? maskPhone(session.phone) : '未登录';
  }

  function openProject() {
    // 跳进新版 Vue 创作台，不再打开落地页里的旧工作室
    window.location.href = '/';
  }

  function closeAuth() {
    authOverlay.classList.remove('open');
    document.body.style.overflow = '';
  }

  function closeStudio() {
    studioOverlay.classList.remove('open');
    document.body.style.overflow = '';
  }

  document.querySelectorAll('[data-open-studio]').forEach((button) => button.addEventListener('click', openProject));
  document.querySelector('[data-close-auth]').addEventListener('click', closeAuth);
  document.getElementById('closeStudio').addEventListener('click', closeStudio);
  authOverlay.addEventListener('click', (event) => { if (event.target === authOverlay) closeAuth(); });

  document.getElementById('logoutUser').addEventListener('click', () => {
    clearSession();
    closeStudio();
    updateSessionUI();
  });

  document.getElementById('sendCode').addEventListener('click', () => {
    const phone = document.getElementById('phone').value.trim();
    const error = document.getElementById('authError');
    const button = document.getElementById('sendCode');
    if (!/^1\d{10}$/.test(phone)) {
      error.textContent = '请输入有效的 11 位手机号';
      return;
    }
    error.textContent = '';
    let seconds = 60;
    button.disabled = true;
    button.textContent = `${seconds}s 后重发`;
    clearInterval(codeTimer);
    codeTimer = setInterval(() => {
      seconds -= 1;
      button.textContent = seconds > 0 ? `${seconds}s 后重发` : '重新获取';
      if (seconds <= 0) {
        clearInterval(codeTimer);
        button.disabled = false;
      }
    }, 1000);
    document.getElementById('code').focus();
  });

  document.getElementById('authForm').addEventListener('submit', (event) => {
    event.preventDefault();
    const phone = document.getElementById('phone').value.trim();
    const code = document.getElementById('code').value.trim();
    const consent = document.getElementById('consent').checked;
    const error = document.getElementById('authError');
    if (!/^1\d{10}$/.test(phone)) return void (error.textContent = '请输入有效的 11 位手机号');
    if (code !== '123456') return void (error.textContent = '演示登录（未接登录后端）：验证码固定为 123456');
    if (!consent) return void (error.textContent = '请先同意用户协议与隐私说明');
    setSession(phone);
    error.textContent = '';
    authOverlay.classList.remove('open');
    studioOverlay.classList.add('open');
    document.body.style.overflow = 'hidden';
    updateSessionUI();
    renderStudio();
  });

  function getPath(path) {
    return path.split('.').reduce((value, key) => value?.[key], project);
  }

  function setPath(path, value) {
    const keys = path.split('.');
    let target = project;
    keys.slice(0, -1).forEach((key) => { target = target[key]; });
    target[keys.at(-1)] = value;
  }

  function agent(name, letter, note) {
    return `<div class="agent-chip"><span class="agent-avatar">${letter}</span><span>${name}</span></div>${note ? `<div class="expert-handoff"><b>Amie</b><span></span>${note}</div>` : ''}`;
  }

  function actions(backLabel, nextLabel) {
    return `<div class="stage-error" id="stageError" aria-live="polite"></div><div class="stage-actions"><button class="back" type="button" data-back>${backLabel || '返回上一步'}</button><button class="next" type="button" data-next>${nextLabel || '继续'} →</button></div>`;
  }

  function visualGroup(title, path, items, extraClass = '') {
    const current = getPath(path);
    return `<div class="option-group"><h3>${title}</h3><div class="visual-options ${extraClass}">${items.map((item) => `
      <button type="button" class="visual-option${current === item.value ? ' selected' : ''}" data-path="${path}" data-value="${escapeHTML(item.value)}">
        <img loading="lazy" decoding="async" src="${item.image}" alt="${escapeHTML(item.value)}参考图">
        <span class="visual-option-copy"><b>${escapeHTML(item.value)}</b><small>${escapeHTML(item.copy)}</small></span>
      </button>`).join('')}</div></div>`;
  }

  function promptBox(label, path, placeholder) {
    return `<div class="prompt-box"><label>${label}</label><textarea data-text-path="${path}" placeholder="${escapeHTML(placeholder)}">${escapeHTML(getPath(path))}</textarea></div>`;
  }

  function uploadCard(role, title, subtitle) {
    const photos = project.uploads[role];
    return `<section class="upload-card">
      <div class="upload-card-head"><div><h3>${title}</h3><small>${subtitle}</small></div><span class="upload-count">${photos.filter((photo) => photo.fileId).length} / 10</span></div>
      <label class="upload-drop"><input type="file" accept="image/*" multiple data-upload="${role}"><b>＋ 选择照片</b><span>支持一次多选，至少 1 张、最多 10 张</span></label>
      <div class="thumbs">${photos.map((photo, index) => `<div class="thumb"><img loading="lazy" decoding="async" src="${photo.url}" alt="${escapeHTML(title)}参考照 ${index + 1}">${photo.status === 'done' ? '' : `<small style="position:absolute;left:4px;bottom:4px;background:#fff;padding:0 4px">${photo.status === 'failed' ? '上传失败' : '上传中'}</small>`}<button type="button" data-remove-upload="${role}" data-index="${index}" aria-label="移除照片">×</button></div>`).join('')}</div>
      <div class="stage-error">${escapeHTML(project.uploadError[role])}</div>
    </section>`;
  }

  function renderUpload() {
    return `${agent('Amie 正在建立双人档案', 'A')}<span class="prototype-badge">STEP 01 · IDENTITY REFERENCES</span><h2>先让我好好认识你们。</h2><p class="stage-desc">男女双方分别上传清晰近照。系统会在继续前检查数量，照片会上传到小囍后端（POST /api/uploads），只用于本次生成。</p><div class="upload-grid">${uploadCard('bride', '女生照片', '正脸清晰，可包含不同角度')}${uploadCard('groom', '男生照片', '正脸清晰，可包含不同角度')}</div><div class="upload-guidance">建议包含正脸、轻微侧脸和自然表情；避免多人合照、重度滤镜、墨镜或大面积遮挡。</div>${actions('稍后再说', '选择风格')}`;
  }

  function renderStyle() {
    const heightDiff = Number(project.groomHeight) - Number(project.brideHeight);
    return `${agent('Amie 与造型组正在判断比例', 'A', '身高信息会同步给服装师与摄影师')}<span class="prototype-badge">STEP 02 · STYLE & HEIGHT</span><h2>先选一个故事的方向。</h2><p class="stage-desc">这是首轮测试的四套方向，后续可以继续替换。婚纱与中式均保留为核心品类。</p>${visualGroup('婚纱照风格（4 选 1）', 'style', [
      { value: '晴日胶片婚纱', copy: '草坪、直闪与自然互动', image: 'assets/style-film.webp' },
      { value: '东方中式喜嫁', copy: '中式礼服、东方色彩与礼序', image: 'assets/style-chinese.webp' },
      { value: '法式庄园婚纱', copy: '古典建筑、优雅与松弛感', image: 'assets/style-french.webp' },
      { value: '韩式极简婚纱', copy: '干净柔光、克制而耐看', image: 'assets/style-korean.webp' }
    ], 'style-options')}<div class="height-grid"><div class="height-card"><label for="brideHeight">女生身高</label><div class="height-input"><input id="brideHeight" type="number" min="140" max="210" value="${escapeHTML(project.brideHeight)}" data-height="brideHeight"><span>cm</span></div></div><div class="height-card"><label for="groomHeight">男生身高</label><div class="height-input"><input id="groomHeight" type="number" min="140" max="210" value="${escapeHTML(project.groomHeight)}" data-height="groomHeight"><span>cm</span></div></div></div><div class="height-note">当前身高差约 ${Number.isFinite(heightDiff) ? Math.abs(heightDiff) : '--'} cm，摄影师会据此调整站位、镜头高度与服装比例。</div>${promptBox('补充你们喜欢或不喜欢的方向（可选）', 'styleNote', '例如喜欢自然互动，不想要过度摆拍；中式希望更现代一些')}${actions('返回照片', '请造型组为女生搭配')}`;
  }

  function renderBride() {
    return `${agent('造型组 · 妆造师与服装师', '造', 'Amie 已把风格与身高信息交给造型组')}<span class="prototype-badge">STEP 03 · BRIDE STYLING</span><h2>先为女生完成整套造型。</h2><p class="stage-desc">妆容、发型和服装各提供两个图像方向。三个维度可以自由组合，不必被整套模板限制。</p>${visualGroup('妆容（2 选 1）', 'bride.makeup', [
      { value: '清透原生妆', copy: '保留皮肤质感，轻柔提亮轮廓', image: 'assets/style-korean.webp' },
      { value: '复古柔焦妆', copy: '强化眉眼与唇色，更有胶片张力', image: 'assets/style-french.webp' }
    ])}${visualGroup('发型（2 选 1）', 'bride.hair', [
      { value: '松弛低盘发', copy: '露出颈肩线条，适配头纱', image: 'assets/coblanc-film-couple.webp' },
      { value: '自然波纹披发', copy: '空气感更强，适合户外互动', image: 'assets/style-film.webp' }
    ])}${visualGroup('服装（2 选 1）', 'bride.outfit', [
      { value: '缎面极简白纱', copy: '线条干净，适合近景与全身构图', image: 'assets/style-minimal.webp' },
      { value: '东方礼服', copy: '适配中式喜嫁与现代东方场景', image: 'assets/style-chinese.webp' }
    ])}${promptBox('补充女生造型偏好（可选）', 'bride.note', '例如保留单眼皮、不要大红唇、希望袖子遮住手臂')}${actions('返回风格', '继续男生造型')}`;
  }

  function renderGroom() {
    return `${agent('造型组 · 妆造师与服装师', '造', '女生方案已保存，现在单独处理男生')}<span class="prototype-badge">STEP 04 · GROOM STYLING</span><h2>再让男生自然地进入同一个画面。</h2><p class="stage-desc">男生不直接套用女生方案。造型组会单独处理肤色、发型和服装，再检查双人搭配关系。</p>${visualGroup('妆容（2 选 1）', 'groom.makeup', [
      { value: '自然控油修饰', copy: '弱化瑕疵与油光，保留本人轮廓', image: 'assets/style-minimal.webp' },
      { value: '立体轮廓修饰', copy: '加强眉眼与下颌，更适合电影光线', image: 'assets/style-cinema.webp' }
    ])}${visualGroup('发型（2 选 1）', 'groom.hair', [
      { value: '自然纹理短发', copy: '松弛年轻，适合户外胶片', image: 'assets/style-film.webp' },
      { value: '利落侧分', copy: '轮廓明确，适配经典礼服', image: 'assets/style-korean.webp' }
    ])}${visualGroup('服装（2 选 1）', 'groom.outfit', [
      { value: '经典黑色礼服', copy: '稳定耐看，与白纱形成清晰对比', image: 'assets/style-minimal.webp' },
      { value: '东方立领礼服', copy: '与中式造型形成统一礼序', image: 'assets/style-chinese.webp' }
    ])}${promptBox('补充男生造型偏好（可选）', 'groom.note', '例如不要背头、保留眼镜、肩膀希望更自然')}${actions('返回女生造型', '请摄影师选场景')}`;
  }

  function renderScene() {
    return `${agent('摄影师正在匹配户外场景', '摄', `Amie 已交接「${escapeHTML(project.style || '已选风格')}」与双方造型`)}<span class="prototype-badge">STEP 05 · LOCATION</span><h2>两个户外场景，选一个更像你们的。</h2><p class="stage-desc">摄影师只推荐与当前风格、服装和身高差匹配的场景，并提前规划远、中、近景与特写。</p>${visualGroup('户外场景（2 选 1）', 'scene', [
      { value: '晴日庄园草坪', copy: '开阔远景、自然行走与直闪近景', image: 'assets/coblanc-film-hero.webp' },
      { value: '梧桐老街与洋房', copy: '纪实街景、建筑纵深与电影侧光', image: 'assets/style-french.webp' }
    ], 'scene-options')}${promptBox('补充摄影偏好（可选）', 'sceneNote', '例如希望多一些对视和行走，避开过度亲密动作，想要日落光线')}${actions('返回男生造型', '请 Amie 汇总')}`;
  }

  function renderSummary() {
    return `${agent('Amie 已整理完整创作工单', 'A', '四位专家只执行你已经确认的选择')}<span class="prototype-badge">STEP 06 · CREATIVE BRIEF</span><h2>确认以后，先只生成一张样片。</h2><p class="stage-desc">这样可以先验证人物、造型、场景和气质，避免方向不对时一次生成整套。</p><div class="summary-grid">
      <div class="summary-item"><small>参考照片</small><strong>女生 ${project.uploads.bride.length} 张 · 男生 ${project.uploads.groom.length} 张</strong></div>
      <div class="summary-item"><small>风格与身高</small><strong>${escapeHTML(project.style)} · ${escapeHTML(project.brideHeight)} / ${escapeHTML(project.groomHeight)} cm</strong></div>
      <div class="summary-item"><small>女生造型</small><strong>${escapeHTML(project.bride.makeup)} · ${escapeHTML(project.bride.hair)} · ${escapeHTML(project.bride.outfit)}</strong></div>
      <div class="summary-item"><small>男生造型</small><strong>${escapeHTML(project.groom.makeup)} · ${escapeHTML(project.groom.hair)} · ${escapeHTML(project.groom.outfit)}</strong></div>
      <div class="summary-item"><small>摄影场景</small><strong>${escapeHTML(project.scene)}</strong></div>
      <div class="summary-item"><small>最终镜头计划</small><strong>近景 2 · 中景 3 · 远景 2 · 特写 2</strong></div>
    </div>${actions('返回摄影师', '确认并生成 1 张样片')}`;
  }

  function sampleImage() {
    return project.sampleUrl;
  }

  function taskProgress(t) {
    return `<div class="gen-card"><div class="gen-log">${escapeHTML(t?.step_text || '已提交，等待后端处理')}<br><small>状态 ${escapeHTML(t?.status || '-')} · 步骤 ${escapeHTML(t?.step || '-')} · 任务 ${escapeHTML(project.taskId || '-')}</small></div><button class="solid-btn" type="button" data-refresh>刷新状态</button></div>`;
  }

  function taskFailed(t) {
    return `<h2>这次没做成</h2><p class="stage-desc">错误码：${escapeHTML(t.error?.code || '（无）')}<br>说明：${escapeHTML(t.error?.message || '出了点问题')}<br>停在：${escapeHTML(t.step || '（无）')}</p><div class="stage-actions"><button class="back" type="button" data-restart>重新开始</button></div>`;
  }

  function renderQuestions(questions) {
    return questions.map((q) => {
      const value = project.answers[q.question_id];
      let body = '';
      if (q.type === 'single_choice' || q.type === 'multi_choice') {
        body = `<div class="rework-grid">${(q.options || []).map((o) => {
          const on = q.type === 'multi_choice' ? (value || []).includes(o.value) : value === o.value;
          return `<button type="button" class="${on ? 'selected' : ''}" style="${on ? 'outline:2px solid currentColor' : ''}" data-q="${escapeHTML(q.question_id)}" data-qtype="${q.type}" data-v="${escapeHTML(o.value)}">${o.image ? `<img loading="lazy" decoding="async" src="${escapeHTML(o.image)}" alt="" style="width:100%;display:block">` : ''}${on ? '✓ ' : ''}${escapeHTML(o.label)}</button>`;
        }).join('')}</div>`;
      } else if (q.type === 'upload') {
        body = `<label class="upload-drop"><input type="file" accept="image/*" multiple data-qupload="${escapeHTML(q.question_id)}"><b>＋ 选择照片</b><span>已上传 ${(value || []).length} 张</span></label>`;
      } else {
        body = `<textarea data-qtext="${escapeHTML(q.question_id)}" placeholder="${escapeHTML(q.placeholder || '')}">${escapeHTML(value)}</textarea>`;
      }
      return `<div class="prompt-box"><label>${escapeHTML(q.title)}${q.allow_skip ? '（可跳过）' : '（必答）'}</label>${body}</div>`;
    }).join('');
  }

  function reworkPanel() {
    return `<div class="rework-panel${project.showRework ? ' open' : ''}"><p class="stage-desc">选一个原因，后端会重新生成（POST review action=redo）。备注写在上面的输入框里。</p><div class="rework-grid">${REDO_REASONS.map(([value, label]) => `<button type="button" data-redo="${value}">${label}</button>`).join('')}</div></div>`;
  }

  function renderSample() {
    const t = project.task;
    const head = `${agent('生图 Agent 与修图师', '生', 'Amie 会在生成后陪你一起确认')}<span class="prototype-badge">STEP 07 · SAMPLE</span>`;
    const busy = project.busy ? 'disabled' : '';
    if (!t) return `${head}<h2>还没有提交任务</h2><p class="stage-desc">请回到方案汇总页点「确认并生成 1 张样片」。</p><div class="stage-actions"><button class="back" type="button" data-back>返回方案</button></div>`;
    if (t.status === 'failed') return head + taskFailed(t);
    if (t.status === 'waiting_user') {
      return `${head}<h2>${escapeHTML(SPEAKERS[t.step] || '小囍')}想再确认几件事</h2><p class="stage-desc">${escapeHTML(t.step_text || '')}</p>${renderQuestions(t.questions || [])}<div class="stage-error" id="stageError" aria-live="polite"></div><div class="stage-actions"><button class="back" type="button" data-back>返回方案</button><button class="next" id="submitAnswers" type="button" ${busy}>提交回答 →</button></div>`;
    }
    if (t.status === 'preview_ready' && t.generation?.stage !== 'set') {
      const gen = t.generation || {};
      return `${head}<h2>这张像你们，也像想要的婚纱照吗？</h2><div class="sample-layout"><div class="sample-image"><img loading="lazy" decoding="async" src="${escapeHTML(project.sampleUrl)}" alt="样片"></div><div><div class="score-row"><span class="score">引擎 ${escapeHTML(gen.engine || '-')}</span><span class="score">耗时 ${escapeHTML(gen.seconds ?? '-')}s</span><span class="score">累计 ${escapeHTML(gen.total_images ?? '-')} 张</span></div>${promptBox('告诉 Amie 哪里还不对（重做时作为备注）', 'sampleNote', '例如女生发型不对、男生不像、希望动作更自然')}<div class="review-actions"><button class="approve" id="approveSample" type="button" ${busy}>符合预期，生成 9 张成片 →</button><button id="sampleOnly" type="button" ${busy}>只要这一张，直接交付</button><button id="toggleRework" type="button" ${busy}>不符合，重新生成</button></div>${reworkPanel()}</div></div><div class="stage-actions"><button class="back" type="button" data-back>返回方案</button></div>`;
    }
    return `${head}<h2>正在制作中…</h2><p class="stage-desc">每 ${POLL_MS / 1000} 秒查询一次 GET /api/tasks/{id}。</p>${taskProgress(t)}<div class="stage-actions"><button class="back" type="button" data-back>返回方案</button></div>`;
  }

  function renderFinal() {
    const t = project.task;
    const head = `${agent('摄影师与修图师', '摄', '样片已确认')}<span class="prototype-badge">STEP 08 · FINAL SET</span>`;
    const busy = project.busy ? 'disabled' : '';
    if (!t) return `${head}<h2>还没有任务</h2><div class="stage-actions"><button class="back" type="button" data-back>返回样片</button></div>`;
    if (t.status === 'failed') return head + taskFailed(t);
    if (t.status === 'preview_ready' && t.generation?.stage === 'set') {
      return `${head}<h2>九张成片已生成，点一张作为主图。</h2><div class="final-nine">${project.finalPreviews.map((p, index) => `<figure class="final-frame" data-pick="${escapeHTML(p.image_id)}" style="cursor:pointer;${p.image_id === project.selectedImage ? 'outline:3px solid currentColor' : ''}"><img loading="lazy" decoding="async" src="${escapeHTML(p.url)}" alt="成片 ${index + 1}"><span>0${index + 1}${p.is_best ? ' · 推荐' : ''}${p.image_id === project.selectedImage ? ' · 已选' : ''}</span></figure>`).join('')}</div>${promptBox('不满意的地方（重做时作为备注）', 'sampleNote', '例如第 3 张手部不对')}<div class="review-actions"><button class="approve" id="confirmSet" type="button" ${busy}>满意，去支付 →</button><button id="toggleRework" type="button" ${busy}>不满意，重新生成</button></div>${reworkPanel()}`;
    }
    if (t.status === 'awaiting_payment') {
      return `${head}<h2>确认完成，去支付</h2><p class="stage-desc">演示支付（method=mock），不会真实扣款。</p><div class="stage-actions"><button class="back" type="button" data-back>返回样片</button><button class="next" id="payTask" type="button" ${busy}>模拟支付 →</button></div>`;
    }
    if (t.status === 'done') {
      const d = t.deliverables || {};
      const photos = d.photos?.length ? d.photos : (d.photo ? [d.photo] : []);
      const materials = Object.entries(d).filter(([key]) => key !== 'photos' && key !== 'photo');
      return `${agent('Amie 为你们揭晓完整作品', 'A')}<span class="prototype-badge">FINAL REVEAL · ${photos.length} FRAMES</span><h2>这是属于你们的${photos.length > 1 ? '九个瞬间' : '那一张'}。</h2>${t.message ? `<p class="stage-desc">${escapeHTML(t.message)}</p>` : ''}<div class="final-nine">${photos.map((url, index) => `<figure class="final-frame"><a href="${escapeHTML(url)}" target="_blank" download><img loading="lazy" decoding="async" src="${escapeHTML(url)}" alt="成片 ${index + 1}"></a><span>0${index + 1} · 点击下载</span></figure>`).join('')}</div>${materials.length ? `<div class="summary-grid">${materials.map(([key, url]) => `<div class="summary-item"><small>${escapeHTML(key)}</small><strong><a href="${escapeHTML(url)}" target="_blank" download>下载</a></strong></div>`).join('')}</div>` : ''}<div class="stage-actions"><button class="back" type="button" data-restart>再做一套</button></div>`;
    }
    return `${head}<h2>正在制作中…</h2>${taskProgress(t)}`;
  }

  function renderChat() {
    const messages = [
      ['先上传你们两个人的照片吧。每人至少 1 张、最多 5 张，我会从中提取最自然的面部特征。', '照片检查', '正脸清晰 · 单人照片 · 不超过 5 张'],
      ['照片收到了。接下来选一套想尝试的婚纱照风格，再告诉我你们的身高，摄影师会据此调整站位与比例。', '风格与身高', project.style || '等待选择 4 套风格之一'],
      ['造型组先为女生准备妆容、发型和服装。每一项都可以单独选择，也可以继续告诉我你的偏好。', '女生造型', project.bride.makeup || '等待选择妆容、发型与服装'],
      ['女生方案已经保存。现在单独处理男生，让两个人的造型既协调，又都保留本人特征。', '男生造型', project.groom.makeup || '等待选择妆容、发型与服装'],
      ['摄影师结合你们的风格和造型推荐了两个户外场景。你只需要选择更有感觉的一个。', '摄影场景', project.scene || '等待选择 2 个户外场景之一'],
      ['我已经把双方照片、身高、造型和摄影方案整理成一张工单。确认后我们先只生成 1 张样片。', '方案汇总', '先看 1 张 · 确认后再生成 9 张'],
      ['样片已经交给修图师检查。你可以确认，也可以准确退回风格、女生造型、男生造型、摄影场景或重新生成。', '样片确认', project.sampleReady ? '等待你的确认' : '正在准备 1 张样片'],
      ['样片方向已确认。摄影师正在编排九张镜头，修图师会逐张检查相似度、手部、比例与清晰度。', '批量出片', '近景 2 · 中景 3 · 远景 2 · 特写 2']
    ];
    const [message, task, status] = messages[project.stage];
    const thinking = [
      ['读取当前选择', '已完成'],
      ['交给对应专家', project.stage < 2 ? '等待中' : '已同步'],
      ['记录可返工节点', project.stage < 5 ? '持续记录' : '已建立']
    ];
    chatPanel.innerHTML = `<div class="chat-message-head"><span class="chat-avatar"><img loading="lazy" decoding="async" src="assets/amie-portrait.webp" alt="Amie"></span><b>AMIE 艾蜜</b><small>始终在线</small></div><div class="chat-message">${escapeHTML(message)}</div><div class="chat-thinking"><button type="button"><span>✦ 展开 Amie 的思考过程</span><b>${project.stage + 1} / ${stages.length}</b></button>${thinking.map(([label, state], index) => `<div class="thinking-step"><i>${index + 1}</i><span>${label}</span><em>${state}</em></div>`).join('')}</div><div class="chat-task-card"><b>${escapeHTML(task)}</b><span>${escapeHTML(status)}</span></div><div class="chat-status-row"><span>Amie 主理</span><span>${project.stage === 2 || project.stage === 3 ? '已请造型组加入' : project.stage === 4 ? '已请摄影师加入' : project.stage >= 6 ? '已请修图师加入' : '专家由 Amie 按需邀请'}</span></div>`;
  }

  function nodeSummary(index) {
    const summaries = [
      `${project.uploads.bride.length + project.uploads.groom.length} 张参考照`,
      project.style || '待选择',
      project.bride.makeup || '待搭配',
      project.groom.makeup || '待搭配',
      project.scene || '待选择',
      project.stage > 5 ? '已锁定' : '待确认',
      project.sampleReady ? '已出样片' : '待生成',
      project.finalReady ? '9 张已完成' : '待出片'
    ];
    return summaries[index];
  }

  const stageRoles = [
    [['Amie', '接单与档案', 'A']],
    [['Amie', '风格理解', 'A'], ['服装师', '比例建议', '服']],
    [['妆造师', '妆容与发型', '妆'], ['服装师', '女生礼服', '服']],
    [['妆造师', '男生修饰', '妆'], ['服装师', '双人搭配', '服']],
    [['摄影师', '场景与光线', '摄'], ['分镜师', '远中近景', '镜']],
    [['Amie', '汇总工单', 'A'], ['提示词师', '生成指令', '词']],
    [['生图 Agent', '生成样片', '生'], ['修图师', '质量验收', '修']],
    [['分镜师', '9 张镜头编排', '镜'], ['生图 Agent', '批量生成', '生'], ['修图师', '逐张验收', '修']]
  ];

  function renderRoleNodes(index, state) {
    return `<div class="node-agents">${stageRoles[index].map(([name, task, icon]) => `<div class="role-node ${state}"><span>${icon}</span><div><b>${name}</b><small>${task}</small></div><em>${state === 'done' ? '已完成' : state === 'active' ? '已加入' : '待唤醒'}</em></div>`).join('')}</div>`;
  }

  const selectionAssets = {
    '晴日胶片婚纱': 'assets/style-film.webp', '东方中式喜嫁': 'assets/style-chinese.webp', '法式庄园婚纱': 'assets/style-french.webp', '韩式极简婚纱': 'assets/style-korean.webp',
    '清透原生妆': 'assets/style-korean.webp', '复古柔焦妆': 'assets/style-french.webp', '松弛低盘发': 'assets/coblanc-film-couple.webp', '自然波纹披发': 'assets/style-film.webp', '缎面极简白纱': 'assets/style-minimal.webp', '东方礼服': 'assets/style-chinese.webp',
    '自然控油修饰': 'assets/style-minimal.webp', '立体轮廓修饰': 'assets/style-cinema.webp', '自然纹理短发': 'assets/style-film.webp', '利落侧分': 'assets/style-korean.webp', '经典黑色礼服': 'assets/style-minimal.webp', '东方立领礼服': 'assets/style-chinese.webp',
    '晴日庄园草坪': 'assets/coblanc-film-hero.webp', '梧桐老街与洋房': 'assets/style-french.webp'
  };

  function resultVisual(src, label, kind = '') {
    return src ? `<figure class="result-visual ${kind}"><img loading="lazy" decoding="async" src="${src}" alt="${escapeHTML(label)}"><figcaption>${escapeHTML(label)}</figcaption></figure>` : `<div class="result-placeholder ${kind}"><span>+</span>${escapeHTML(label)}</div>`;
  }

  function renderNodeResult(index, state) {
    if (index === 0) {
      const bride = project.uploads.bride.map((photo, photoIndex) => resultVisual(photo.url, `女生 ${photoIndex + 1}`, 'portrait')).join('');
      const groom = project.uploads.groom.map((photo, photoIndex) => resultVisual(photo.url, `男生 ${photoIndex + 1}`, 'portrait')).join('');
      return `<div class="node-result visual-result"><div class="result-group"><b>女生参考照 <em>${project.uploads.bride.length}/5</em></b><div class="result-gallery">${bride || resultVisual('', '待上传', 'portrait')}</div></div><div class="result-group"><b>男生参考照 <em>${project.uploads.groom.length}/5</em></b><div class="result-gallery">${groom || resultVisual('', '待上传', 'portrait')}</div></div></div>`;
    }
    if (index === 1) return `<div class="node-result visual-result single-result">${resultVisual(selectionAssets[project.style], project.style || '等待风格选择', 'landscape')}<div class="result-facts"><span>女生 ${escapeHTML(project.brideHeight)} cm</span><span>男生 ${escapeHTML(project.groomHeight)} cm</span></div></div>`;
    if (index === 2 || index === 3) {
      const person = index === 2 ? project.bride : project.groom;
      return `<div class="node-result visual-result styling-result">${resultVisual(selectionAssets[person.makeup], person.makeup || '等待妆容')} ${resultVisual(selectionAssets[person.hair], person.hair || '等待发型')} ${resultVisual(selectionAssets[person.outfit], person.outfit || '等待服装')}</div>`;
    }
    if (index === 4) return `<div class="node-result visual-result single-result">${resultVisual(selectionAssets[project.scene], project.scene || '等待场景选择', 'landscape')}<div class="result-facts"><span>特写</span><span>近景</span><span>中景</span><span>远景</span></div></div>`;
    if (index === 5) return `<div class="node-result result-brief"><span>${escapeHTML(project.style || '风格待确认')}</span><span>${escapeHTML(project.scene || '场景待确认')}</span><span>${state === 'done' ? '工单已锁定' : '等待 Amie 汇总'}</span></div>`;
    if (index === 6) return `<div class="node-result visual-result sample-result">${project.sampleReady ? resultVisual(project.sampleUrl, '当前样片', 'landscape') : resultVisual('', '等待生成样片', 'landscape')}<div class="result-facts"><span>${project.sampleReady ? '修图师已初检' : '尚未验收'}</span></div></div>`;
    const finalSources = project.finalPreviews.map((p) => p.url);
    return `<div class="node-result visual-result final-result">${finalSources.length ? finalSources.map((src, photoIndex) => resultVisual(src, `0${photoIndex + 1}`, 'final-thumb')).join('') : resultVisual('', '等待 9 张成片', 'landscape')}</div>`;
  }

  function renderNodeFlow() {
    nodeSpine.innerHTML = stages.map((name, index) => {
      const state = index < project.stage ? 'done' : index === project.stage ? 'active' : 'waiting';
      const accessible = index <= project.stage;
      const nodeHead = `<button type="button" class="flow-node ${state}" data-flow-stage="${index}" ${accessible ? '' : 'disabled'}><span class="flow-node-index">${index < project.stage ? '✓' : String(index + 1).padStart(2, '0')}</span><span class="flow-node-copy"><b>${name}</b><small>${escapeHTML(nodeSummary(index))}</small></span><em>${state === 'active' ? '进行中' : state === 'done' ? '已完成' : '等待'}</em></button>`;
      return `<section class="graph-node ${state}" data-graph-stage="${index}">${nodeHead}${renderNodeResult(index, state)}${renderRoleNodes(index, state)}<span class="graph-port" aria-hidden="true"></span></section>`;
    }).join('');
    nodeSpine.querySelectorAll('[data-flow-stage]:not([disabled])').forEach((button) => button.addEventListener('click', () => {
      project.stage = Number(button.dataset.flowStage);
      renderStudio();
    }));
  }

  function renderExpertPipeline() {
    const states = {
      styling: project.stage < 2 ? 'waiting' : project.stage <= 3 ? 'active' : 'done',
      photo: project.stage < 4 ? 'waiting' : project.stage === 4 ? 'active' : 'done',
      retouch: project.stage < 6 ? 'waiting' : 'active'
    };
    document.querySelectorAll('[data-expert]').forEach((item) => {
      const state = states[item.dataset.expert];
      item.classList.toggle('active', state === 'active');
      item.classList.toggle('done', state === 'done');
      const status = item.querySelector('[data-expert-status]');
      if (status) status.textContent = state === 'active' ? '已由 Amie 邀请加入' : state === 'done' ? '本阶段已完成' : '等待 Amie 交接';
    });
  }

  function renderStudio() {
    updateSessionUI();
    const macroStage = stageToMacro[project.stage];
    progressBar.innerHTML = macroStages.map((_, index) => `<span class="progress-dot ${index < macroStage ? 'done' : index === macroStage ? 'active' : ''}"></span>`).join('');
    stageList.innerHTML = macroStages.map((name, index) => `<li class="${index < macroStage ? 'done' : index === macroStage ? 'active' : ''}">${name}</li>`).join('');
    workspaceTitle.textContent = macroStages[macroStage];
    renderChat();
    renderExpertPipeline();
    renderNodeFlow();
    const renderers = [renderUpload, renderStyle, renderBride, renderGroom, renderScene, renderSummary, renderSample, renderFinal];
    const banner = project.apiError ? `<div role="alert" style="border:1px solid #c0392b;color:#c0392b;padding:8px 12px;margin-bottom:12px">接口出错：${escapeHTML(project.apiError)}</div>` : '';
    stagePanel.innerHTML = banner + renderers[project.stage]();
    bindStageEvents();
    const content = document.querySelector('.studio-content');
    const activeNode = document.querySelector('.graph-node.active');
    requestAnimationFrame(() => { content.scrollTop = Math.max(0, (activeNode ? activeNode.offsetTop : 0) - 26); });
    document.querySelector('.chat-scroll').scrollTop = 0;
  }

  function validateStage() {
    if (project.stage === 0) {
      const all = [...project.uploads.bride, ...project.uploads.groom];
      if (all.some((photo) => photo.status === 'uploading')) return '照片还在上传，请稍等';
      if (all.some((photo) => photo.status === 'failed')) return '有照片上传失败，请删掉后重新上传';
      if (fileIds('bride').length < 1 || fileIds('groom').length < 1) return '请为女生和男生分别上传至少 1 张照片';
      if (fileIds('bride').length > 10 || fileIds('groom').length > 10) return '每个人最多上传 10 张照片';
    }
    if (project.stage === 1) {
      const heights = [Number(project.brideHeight), Number(project.groomHeight)];
      if (!project.style) return '请选择一套婚纱照风格';
      if (heights.some((value) => value < 140 || value > 210)) return '请输入 140–210 cm 之间的身高';
    }
    if (project.stage === 2 && (!project.bride.makeup || !project.bride.hair || !project.bride.outfit)) return '请完成女生的妆容、发型和服装选择';
    if (project.stage === 3 && (!project.groom.makeup || !project.groom.hair || !project.groom.outfit)) return '请完成男生的妆容、发型和服装选择';
    if (project.stage === 4 && !project.scene) return '请选择一个户外场景';
    return '';
  }

  function resetGeneratedResults() {
    dropTask();
  }

  function bindStageEvents() {
    stagePanel.querySelectorAll('[data-upload]').forEach((input) => input.addEventListener('change', async () => {
      const role = input.dataset.upload;
      const files = [...input.files].filter((file) => file.type.startsWith('image/'));
      const total = project.uploads[role].length + files.length;
      if (total > 10) {
        project.uploadError[role] = `当前已有 ${project.uploads[role].length} 张，本次最多还能添加 ${10 - project.uploads[role].length} 张`;
        return renderStudio();
      }
      project.uploadError[role] = '';
      resetGeneratedResults();
      const items = files.map((file) => ({ name: file.name, url: URL.createObjectURL(file), status: 'uploading', fileId: null, file }));
      project.uploads[role].push(...items);
      renderStudio();
      for (const item of items) {
        try {
          const result = await api.upload(item.file);
          item.fileId = result.file_id;
          item.status = 'done';
        } catch (error) {
          item.status = 'failed';
          project.uploadError[role] = `${item.name} 上传失败：${error.message}`;
        }
        renderStudio();
      }
    }));

    stagePanel.querySelectorAll('[data-remove-upload]').forEach((button) => button.addEventListener('click', () => {
      const role = button.dataset.removeUpload;
      const index = Number(button.dataset.index);
      const [removed] = project.uploads[role].splice(index, 1);
      if (removed?.url) URL.revokeObjectURL(removed.url);
      project.uploadError[role] = '';
      resetGeneratedResults();
      renderStudio();
    }));

    stagePanel.querySelectorAll('[data-path]').forEach((button) => button.addEventListener('click', () => {
      setPath(button.dataset.path, button.dataset.value);
      resetGeneratedResults();
      renderStudio();
    }));

    stagePanel.querySelectorAll('[data-text-path]').forEach((input) => input.addEventListener('input', () => { setPath(input.dataset.textPath, input.value); renderNodeFlow(); }));
    stagePanel.querySelectorAll('[data-height]').forEach((input) => input.addEventListener('input', () => { project[input.dataset.height] = input.value; resetGeneratedResults(); renderNodeFlow(); }));

    const next = stagePanel.querySelector('[data-next]');
    if (next && !next.id) next.addEventListener('click', () => {
      const errorMessage = validateStage();
      if (errorMessage) {
        const error = document.getElementById('stageError');
        if (error) error.textContent = errorMessage;
        return;
      }
      if (project.stage === 5) {
        if (project.taskId) { project.stage = 6; renderStudio(); return startPolling(); }
        return act(async () => {
          const created = await api.createTask({ groom_photo_file_ids: fileIds('groom'), bride_photo_file_ids: fileIds('bride'), description: buildDescription() });
          project.taskId = created.task_id;
          project.task = { status: created.status };
          project.stage = 6;
        });
      }
      project.stage = Math.min(stages.length - 1, project.stage + 1);
      renderStudio();
    });

    const back = stagePanel.querySelector('[data-back]');
    if (back) back.addEventListener('click', () => {
      if (project.stage === 0) return closeStudio();
      project.stage -= 1;
      renderStudio();
    });

    const byId = (id) => document.getElementById(id);
    const note = () => (project.sampleNote || '').trim() || null;
    stagePanel.querySelectorAll('[data-refresh]').forEach((button) => button.addEventListener('click', startPolling));
    stagePanel.querySelectorAll('[data-restart]').forEach((button) => button.addEventListener('click', () => { dropTask(); project.apiError = ''; project.stage = 0; renderStudio(); }));

    stagePanel.querySelectorAll('[data-q]').forEach((button) => button.addEventListener('click', () => {
      const id = button.dataset.q;
      const value = button.dataset.v;
      if (button.dataset.qtype === 'multi_choice') {
        const list = project.answers[id] || [];
        project.answers[id] = list.includes(value) ? list.filter((item) => item !== value) : [...list, value];
      } else {
        project.answers[id] = value;
      }
      renderStudio();
    }));
    stagePanel.querySelectorAll('[data-qtext]').forEach((input) => input.addEventListener('input', () => { project.answers[input.dataset.qtext] = input.value; }));
    stagePanel.querySelectorAll('[data-qupload]').forEach((input) => input.addEventListener('change', async () => {
      const id = input.dataset.qupload;
      for (const file of [...input.files]) {
        try {
          const result = await api.upload(file);
          project.answers[id] = [...(project.answers[id] || []), result.file_id];
        } catch (error) {
          showApiError(error);
        }
      }
      renderStudio();
    }));

    const submitAnswers = byId('submitAnswers');
    if (submitAnswers) submitAnswers.addEventListener('click', () => {
      const questions = project.task?.questions || [];
      const empty = (value) => value === '' || value == null || (Array.isArray(value) && value.length === 0);
      const answers = questions.map((q) => {
        const value = project.answers[q.question_id];
        return empty(value) ? { question_id: q.question_id, skipped: true } : { question_id: q.question_id, value };
      });
      const missing = questions.find((q, index) => !q.allow_skip && answers[index].skipped);
      if (missing) { byId('stageError').textContent = `这题必须回答：${missing.title}`; return; }
      act(() => api.answers(project.taskId, answers));
    });

    const approve = byId('approveSample');
    if (approve) approve.addEventListener('click', () => act(() => api.review(project.taskId, { action: 'confirm', image_id: project.selectedImage })));
    const sampleOnly = byId('sampleOnly');
    if (sampleOnly) sampleOnly.addEventListener('click', () => act(() => api.review(project.taskId, { action: 'sample_only', image_id: project.selectedImage })));
    const confirmSet = byId('confirmSet');
    if (confirmSet) confirmSet.addEventListener('click', () => act(() => api.review(project.taskId, { action: 'confirm', image_id: project.selectedImage })));
    const toggleRework = byId('toggleRework');
    if (toggleRework) toggleRework.addEventListener('click', () => { project.showRework = !project.showRework; renderStudio(); });
    stagePanel.querySelectorAll('[data-redo]').forEach((button) => button.addEventListener('click', () => {
      project.showRework = false;
      act(() => api.review(project.taskId, { action: 'redo', image_id: project.selectedImage, reason: button.dataset.redo, note: note() }));
    }));
    stagePanel.querySelectorAll('[data-pick]').forEach((figure) => figure.addEventListener('click', () => { project.selectedImage = figure.dataset.pick; renderStudio(); }));
    const payTask = byId('payTask');
    if (payTask) payTask.addEventListener('click', () => act(() => api.pay(project.taskId)));
  }

  updateSessionUI();
})();
