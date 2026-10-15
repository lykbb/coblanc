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
      finalReady: false
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
    if (getSession()) {
      studioOverlay.classList.add('open');
      document.body.style.overflow = 'hidden';
      renderStudio();
      return;
    }
    authOverlay.classList.add('open');
    document.body.style.overflow = 'hidden';
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
    if (code !== '123456') return void (error.textContent = '原型验证码为 123456');
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
        <img src="${item.image}" alt="${escapeHTML(item.value)}参考图">
        <span class="visual-option-copy"><b>${escapeHTML(item.value)}</b><small>${escapeHTML(item.copy)}</small></span>
      </button>`).join('')}</div></div>`;
  }

  function promptBox(label, path, placeholder) {
    return `<div class="prompt-box"><label>${label}</label><textarea data-text-path="${path}" placeholder="${escapeHTML(placeholder)}">${escapeHTML(getPath(path))}</textarea></div>`;
  }

  function uploadCard(role, title, subtitle) {
    const photos = project.uploads[role];
    return `<section class="upload-card">
      <div class="upload-card-head"><div><h3>${title}</h3><small>${subtitle}</small></div><span class="upload-count">${photos.length} / 5</span></div>
      <label class="upload-drop"><input type="file" accept="image/*" multiple data-upload="${role}"><b>＋ 选择照片</b><span>支持一次多选，至少 1 张、最多 5 张</span></label>
      <div class="thumbs">${photos.map((photo, index) => `<div class="thumb"><img src="${photo.url}" alt="${escapeHTML(title)}参考照 ${index + 1}"><button type="button" data-remove-upload="${role}" data-index="${index}" aria-label="移除照片">×</button></div>`).join('')}</div>
      <div class="stage-error">${escapeHTML(project.uploadError[role])}</div>
    </section>`;
  }

  function renderUpload() {
    return `${agent('Amie 正在建立双人档案', 'A')}<span class="prototype-badge">STEP 01 · IDENTITY REFERENCES</span><h2>先让我好好认识你们。</h2><p class="stage-desc">男女双方分别上传清晰近照。系统会在继续前检查数量，照片只用于本次原型预览，不会上传到服务器。</p><div class="upload-grid">${uploadCard('bride', '女生照片', '正脸清晰，可包含不同角度')}${uploadCard('groom', '男生照片', '正脸清晰，可包含不同角度')}</div><div class="upload-guidance">建议包含正脸、轻微侧脸和自然表情；避免多人合照、重度滤镜、墨镜或大面积遮挡。</div>${actions('稍后再说', '选择风格')}`;
  }

  function renderStyle() {
    const heightDiff = Number(project.groomHeight) - Number(project.brideHeight);
    return `${agent('Amie 与造型组正在判断比例', 'A', '身高信息会同步给服装师与摄影师')}<span class="prototype-badge">STEP 02 · STYLE & HEIGHT</span><h2>先选一个故事的方向。</h2><p class="stage-desc">这是首轮测试的四套方向，后续可以继续替换。婚纱与中式均保留为核心品类。</p>${visualGroup('婚纱照风格（4 选 1）', 'style', [
      { value: '晴日胶片婚纱', copy: '草坪、直闪与自然互动', image: 'assets/style-film.png' },
      { value: '东方中式喜嫁', copy: '中式礼服、东方色彩与礼序', image: 'assets/style-chinese.png' },
      { value: '法式庄园婚纱', copy: '古典建筑、优雅与松弛感', image: 'assets/style-french.png' },
      { value: '韩式极简婚纱', copy: '干净柔光、克制而耐看', image: 'assets/style-korean.png' }
    ], 'style-options')}<div class="height-grid"><div class="height-card"><label for="brideHeight">女生身高</label><div class="height-input"><input id="brideHeight" type="number" min="140" max="210" value="${escapeHTML(project.brideHeight)}" data-height="brideHeight"><span>cm</span></div></div><div class="height-card"><label for="groomHeight">男生身高</label><div class="height-input"><input id="groomHeight" type="number" min="140" max="210" value="${escapeHTML(project.groomHeight)}" data-height="groomHeight"><span>cm</span></div></div></div><div class="height-note">当前身高差约 ${Number.isFinite(heightDiff) ? Math.abs(heightDiff) : '--'} cm，摄影师会据此调整站位、镜头高度与服装比例。</div>${promptBox('补充你们喜欢或不喜欢的方向（可选）', 'styleNote', '例如喜欢自然互动，不想要过度摆拍；中式希望更现代一些')}${actions('返回照片', '请造型组为女生搭配')}`;
  }

  function renderBride() {
    return `${agent('造型组 · 妆造师与服装师', '造', 'Amie 已把风格与身高信息交给造型组')}<span class="prototype-badge">STEP 03 · BRIDE STYLING</span><h2>先为女生完成整套造型。</h2><p class="stage-desc">妆容、发型和服装各提供两个图像方向。三个维度可以自由组合，不必被整套模板限制。</p>${visualGroup('妆容（2 选 1）', 'bride.makeup', [
      { value: '清透原生妆', copy: '保留皮肤质感，轻柔提亮轮廓', image: 'assets/style-korean.png' },
      { value: '复古柔焦妆', copy: '强化眉眼与唇色，更有胶片张力', image: 'assets/style-french.png' }
    ])}${visualGroup('发型（2 选 1）', 'bride.hair', [
      { value: '松弛低盘发', copy: '露出颈肩线条，适配头纱', image: 'assets/coblanc-film-couple.png' },
      { value: '自然波纹披发', copy: '空气感更强，适合户外互动', image: 'assets/style-film.png' }
    ])}${visualGroup('服装（2 选 1）', 'bride.outfit', [
      { value: '缎面极简白纱', copy: '线条干净，适合近景与全身构图', image: 'assets/style-minimal.png' },
      { value: '东方礼服', copy: '适配中式喜嫁与现代东方场景', image: 'assets/style-chinese.png' }
    ])}${promptBox('补充女生造型偏好（可选）', 'bride.note', '例如保留单眼皮、不要大红唇、希望袖子遮住手臂')}${actions('返回风格', '继续男生造型')}`;
  }

  function renderGroom() {
    return `${agent('造型组 · 妆造师与服装师', '造', '女生方案已保存，现在单独处理男生')}<span class="prototype-badge">STEP 04 · GROOM STYLING</span><h2>再让男生自然地进入同一个画面。</h2><p class="stage-desc">男生不直接套用女生方案。造型组会单独处理肤色、发型和服装，再检查双人搭配关系。</p>${visualGroup('妆容（2 选 1）', 'groom.makeup', [
      { value: '自然控油修饰', copy: '弱化瑕疵与油光，保留本人轮廓', image: 'assets/style-minimal.png' },
      { value: '立体轮廓修饰', copy: '加强眉眼与下颌，更适合电影光线', image: 'assets/style-cinema.png' }
    ])}${visualGroup('发型（2 选 1）', 'groom.hair', [
      { value: '自然纹理短发', copy: '松弛年轻，适合户外胶片', image: 'assets/style-film.png' },
      { value: '利落侧分', copy: '轮廓明确，适配经典礼服', image: 'assets/style-korean.png' }
    ])}${visualGroup('服装（2 选 1）', 'groom.outfit', [
      { value: '经典黑色礼服', copy: '稳定耐看，与白纱形成清晰对比', image: 'assets/style-minimal.png' },
      { value: '东方立领礼服', copy: '与中式造型形成统一礼序', image: 'assets/style-chinese.png' }
    ])}${promptBox('补充男生造型偏好（可选）', 'groom.note', '例如不要背头、保留眼镜、肩膀希望更自然')}${actions('返回女生造型', '请摄影师选场景')}`;
  }

  function renderScene() {
    return `${agent('摄影师正在匹配户外场景', '摄', `Amie 已交接「${escapeHTML(project.style || '已选风格')}」与双方造型`)}<span class="prototype-badge">STEP 05 · LOCATION</span><h2>两个户外场景，选一个更像你们的。</h2><p class="stage-desc">摄影师只推荐与当前风格、服装和身高差匹配的场景，并提前规划远、中、近景与特写。</p>${visualGroup('户外场景（2 选 1）', 'scene', [
      { value: '晴日庄园草坪', copy: '开阔远景、自然行走与直闪近景', image: 'assets/coblanc-film-hero.png' },
      { value: '梧桐老街与洋房', copy: '纪实街景、建筑纵深与电影侧光', image: 'assets/style-french.png' }
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
    return project.style.includes('中式') ? 'assets/style-chinese.png' : project.scene.includes('庄园') ? 'assets/coblanc-film-hero.png' : 'assets/style-french.png';
  }

  function renderSample() {
    if (!project.sampleReady) {
      return `${agent('生图 Agent 与修图师已收到工单', '生', 'Amie 会在生成后陪你一起确认')}<span class="prototype-badge">STEP 07 · SAMPLE</span><h2>先生成一张，把方向看清楚。</h2><p class="stage-desc">本次只生成一张样片。确认后才进入九张成片，避免消耗在错误方向上。</p><div class="gen-card"><div class="gen-log" id="genLog">双方参考照数量校验通过<br>造型与场景工单已锁定<br>等待生成样片</div><div class="gen-track"><div class="gen-bar" id="genBar"></div></div><button class="solid-btn" id="generateSample" type="button">生成 1 张样片</button></div><div class="stage-actions"><button class="back" type="button" data-back>返回方案</button><span class="prototype-note">原型使用示意图模拟生成结果</span></div>`;
    }
    return `${agent('修图师已完成样片初检', '修', 'Amie 想先听你的真实感受')}<span class="prototype-badge">STEP 07 · SAMPLE REVIEW</span><h2>这张像你们，也像想要的婚纱照吗？</h2><div class="sample-layout"><div class="sample-image"><img src="${sampleImage()}" alt="COBLANC 婚纱照样片"></div><div><div class="score-row"><span class="score">双人辨识度 94</span><span class="score">手部结构 96</span><span class="score">服装完整度 95</span><span class="score">画面清晰度 97</span></div><p class="stage-desc">修图师建议通过。你仍然拥有最终决定权，不满意可以按问题准确退回。</p>${promptBox('告诉 Amie 哪里还不对（可选）', 'sampleNote', '例如女生发型不对、男生不像、场景太空、希望动作更自然')}<div class="review-actions"><button class="approve" id="approveSample" type="button">符合预期，生成 9 张成片 →</button><button id="toggleRework" type="button">不符合，我想调整</button></div><div class="rework-panel${project.showRework ? ' open' : ''}" id="reworkPanel"><div class="rework-grid"><button data-route="1">风格或身高不对</button><button data-route="2">女生妆造不对</button><button data-route="3">男生妆造不对</button><button data-route="4">场景或摄影感觉不对</button><button data-route="regen">方案没问题，重新生成</button></div></div></div></div><div class="stage-actions"><button class="back" type="button" data-back>返回方案</button><span class="prototype-note">不满意不会进入九张成片</span></div>`;
  }

  function renderFinal() {
    const labels = ['特写 01', '近景 01', '中景 01', '远景 01', '中景 02', '近景 02', '远景 02', '中景 03', '特写 02'];
    const sources = labels.map((_, index) => index % 3 === 1 ? 'assets/coblanc-film-couple.png' : sampleImage());
    if (!project.finalReady) {
      return `${agent('摄影师与修图师准备整套出片', '摄', '样片已确认，Amie 将陪你等待最终揭晓')}<span class="prototype-badge">STEP 08 · FINAL SET</span><h2>一张定方向，九张讲完整故事。</h2><p class="stage-desc">九张成片会保持同一套人物、造型与色调，同时覆盖不同规格和镜头距离。</p><div class="final-plan"><span>近景 × 2</span><span>中景 × 3</span><span>远景 × 2</span><span>特写 × 2</span></div><div class="gen-card"><div class="gen-log" id="genLog">样片方向已锁定<br>摄影师正在编排九张镜头<br>修图师将在生成后逐张验收</div><div class="gen-track"><div class="gen-bar" id="genBar"></div></div><button class="solid-btn" id="generateFinal" type="button">生成 9 张成片</button></div><div class="stage-actions"><button class="back" type="button" data-back>返回样片</button><span class="prototype-note">原型使用现有图像模拟九张交付结构</span></div>`;
    }
    return `${agent('Amie 为你们揭晓完整作品', 'A', '四位专家已经完成逐张验收')}<span class="prototype-badge">FINAL REVEAL · 9 FRAMES</span><h2>这是属于你们的九个瞬间。</h2><p class="stage-desc">镜头距离与画幅已经覆盖婚礼请帖、迎宾、社交发布和相册排版所需的基本场景。</p><div class="final-nine">${labels.map((label, index) => `<figure class="final-frame"><img src="${sources[index]}" alt="${label}"><span>0${index + 1} · ${label}</span></figure>`).join('')}</div><div class="stage-actions"><button class="back" type="button" data-back>返回样片</button><button class="next" id="saveProject" type="button">保存到我的作品</button></div>`;
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
    chatPanel.innerHTML = `<div class="chat-message-head"><span class="chat-avatar"><img src="assets/amie-portrait.png" alt="Amie"></span><b>AMIE 艾蜜</b><small>始终在线</small></div><div class="chat-message">${escapeHTML(message)}</div><div class="chat-thinking"><button type="button"><span>✦ 展开 Amie 的思考过程</span><b>${project.stage + 1} / ${stages.length}</b></button>${thinking.map(([label, state], index) => `<div class="thinking-step"><i>${index + 1}</i><span>${label}</span><em>${state}</em></div>`).join('')}</div><div class="chat-task-card"><b>${escapeHTML(task)}</b><span>${escapeHTML(status)}</span></div><div class="chat-status-row"><span>Amie 主理</span><span>${project.stage === 2 || project.stage === 3 ? '已请造型组加入' : project.stage === 4 ? '已请摄影师加入' : project.stage >= 6 ? '已请修图师加入' : '专家由 Amie 按需邀请'}</span></div>`;
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
    '晴日胶片婚纱': 'assets/style-film.png', '东方中式喜嫁': 'assets/style-chinese.png', '法式庄园婚纱': 'assets/style-french.png', '韩式极简婚纱': 'assets/style-korean.png',
    '清透原生妆': 'assets/style-korean.png', '复古柔焦妆': 'assets/style-french.png', '松弛低盘发': 'assets/coblanc-film-couple.png', '自然波纹披发': 'assets/style-film.png', '缎面极简白纱': 'assets/style-minimal.png', '东方礼服': 'assets/style-chinese.png',
    '自然控油修饰': 'assets/style-minimal.png', '立体轮廓修饰': 'assets/style-cinema.png', '自然纹理短发': 'assets/style-film.png', '利落侧分': 'assets/style-korean.png', '经典黑色礼服': 'assets/style-minimal.png', '东方立领礼服': 'assets/style-chinese.png',
    '晴日庄园草坪': 'assets/coblanc-film-hero.png', '梧桐老街与洋房': 'assets/style-french.png'
  };

  function resultVisual(src, label, kind = '') {
    return src ? `<figure class="result-visual ${kind}"><img src="${src}" alt="${escapeHTML(label)}"><figcaption>${escapeHTML(label)}</figcaption></figure>` : `<div class="result-placeholder ${kind}"><span>+</span>${escapeHTML(label)}</div>`;
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
    if (index === 6) return `<div class="node-result visual-result sample-result">${project.sampleReady ? resultVisual(sampleImage(), '当前样片', 'landscape') : resultVisual('', '等待生成样片', 'landscape')}<div class="result-facts"><span>${project.sampleReady ? '修图师已初检' : '尚未验收'}</span></div></div>`;
    const finalSources = Array.from({ length: 9 }, (_, photoIndex) => photoIndex % 3 === 1 ? 'assets/coblanc-film-couple.png' : sampleImage());
    return `<div class="node-result visual-result final-result">${project.finalReady ? finalSources.map((src, photoIndex) => resultVisual(src, `0${photoIndex + 1}`, 'final-thumb')).join('') : resultVisual('', '等待 9 张成片', 'landscape')}</div>`;
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
    stagePanel.innerHTML = renderers[project.stage]();
    bindStageEvents();
    const content = document.querySelector('.studio-content');
    const activeNode = document.querySelector('.graph-node.active');
    requestAnimationFrame(() => { content.scrollTop = Math.max(0, activeNode.offsetTop - 26); });
    document.querySelector('.chat-scroll').scrollTop = 0;
  }

  function validateStage() {
    if (project.stage === 0) {
      if (project.uploads.bride.length < 1 || project.uploads.groom.length < 1) return '请为女生和男生分别上传至少 1 张照片';
      if (project.uploads.bride.length > 5 || project.uploads.groom.length > 5) return '每个人最多上传 5 张照片';
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
    project.sampleReady = false;
    project.showRework = false;
    project.finalReady = false;
  }

  function bindStageEvents() {
    stagePanel.querySelectorAll('[data-upload]').forEach((input) => input.addEventListener('change', () => {
      const role = input.dataset.upload;
      const files = [...input.files].filter((file) => file.type.startsWith('image/'));
      const total = project.uploads[role].length + files.length;
      if (total > 5) {
        project.uploadError[role] = `当前已有 ${project.uploads[role].length} 张，本次最多还能添加 ${5 - project.uploads[role].length} 张`;
      } else {
        project.uploadError[role] = '';
        files.forEach((file) => project.uploads[role].push({ name: file.name, url: URL.createObjectURL(file) }));
      }
      resetGeneratedResults();
      renderStudio();
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
      project.stage = Math.min(stages.length - 1, project.stage + 1);
      renderStudio();
    });

    const back = stagePanel.querySelector('[data-back]');
    if (back) back.addEventListener('click', () => {
      if (project.stage === 0) return closeStudio();
      project.stage -= 1;
      renderStudio();
    });

    const generateSample = document.getElementById('generateSample');
    if (generateSample) generateSample.addEventListener('click', () => {
      generateSample.disabled = true;
      document.getElementById('genBar').classList.add('run');
      document.getElementById('genLog').innerHTML = '正在融合双方人物特征<br>正在应用造型与户外场景<br>修图师正在检查手部、比例与清晰度';
      setTimeout(() => { project.sampleReady = true; renderStudio(); }, 1800);
    });

    const approve = document.getElementById('approveSample');
    if (approve) approve.addEventListener('click', () => { project.stage = 7; project.showRework = false; renderStudio(); });
    const toggleRework = document.getElementById('toggleRework');
    if (toggleRework) toggleRework.addEventListener('click', () => { project.showRework = !project.showRework; renderStudio(); });
    stagePanel.querySelectorAll('[data-route]').forEach((button) => button.addEventListener('click', () => {
      if (button.dataset.route === 'regen') {
        project.sampleReady = false;
      } else {
        project.stage = Number(button.dataset.route);
        resetGeneratedResults();
      }
      renderStudio();
    }));

    const generateFinal = document.getElementById('generateFinal');
    if (generateFinal) generateFinal.addEventListener('click', () => {
      generateFinal.disabled = true;
      document.getElementById('genBar').classList.add('run');
      document.getElementById('genLog').innerHTML = '正在生成 2 张特写与 2 张近景<br>正在生成 3 张中景与 2 张远景<br>修图师正在逐张完成最终验收';
      setTimeout(() => { project.finalReady = true; renderStudio(); }, 2000);
    });

    const save = document.getElementById('saveProject');
    if (save) save.addEventListener('click', () => {
      save.textContent = '已保存到我的作品';
      save.disabled = true;
    });
  }

  updateSessionUI();
})();
