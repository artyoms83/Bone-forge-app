/* ===================================================================
   BONEFORGE APP — Dashboard Logic v2
   =================================================================== */

var generatedData = null;
var fixedScript = null;
var isEditing = false;
var currentFormula = 'a';
var currentCharMode = 'library';
var currentCharacterKey = 'base';
var regenerationsLeft = 3;

// ---------------------------------------------------------------------------
// FORMULA TOGGLE
// ---------------------------------------------------------------------------
function setFormula(f) {
  currentFormula = f;
  var btnA = document.getElementById('btnFormulaA');
  var btnB = document.getElementById('btnFormulaB');
  var figureWrap = document.getElementById('figureSelectWrap');
  var conceptInput = document.getElementById('conceptInput');

  btnA.classList.toggle('formula-btn-active', f === 'a');
  btnB.classList.toggle('formula-btn-active', f === 'b');

  if (figureWrap) figureWrap.style.display = f === 'a' ? '' : 'none';

  if (f === 'a') {
    conceptInput.placeholder = 'What if you brought McDonald\'s to ancient Egypt...';
  } else {
    conceptInput.placeholder = 'A skeleton finds a dirt bike in 1803...';
  }
}

// ---------------------------------------------------------------------------
// CHARACTER MODE
// ---------------------------------------------------------------------------
function setCharMode(mode) {
  currentCharMode = mode;
  ['library', 'profession', 'custom'].forEach(function(m) {
    var btn = document.getElementById('btnMode' + m.charAt(0).toUpperCase() + m.slice(1));
    if (btn) btn.classList.toggle('char-mode-btn-active', m === mode);
  });
  document.getElementById('librarySelectWrap').style.display = mode === 'library' ? '' : 'none';
  document.getElementById('professionWrap').style.display = mode === 'profession' ? '' : 'none';
  document.getElementById('customWrap').style.display = mode === 'custom' ? '' : 'none';
}

// ---------------------------------------------------------------------------
// USAGE COUNTER
// ---------------------------------------------------------------------------
function loadUsage() {
  fetch('/usage').then(function(r) { return r.json(); }).then(function(data) {
    if (typeof data.videos_generated === 'undefined') return;
    var text = document.getElementById('usageText');
    var fill = document.getElementById('usageFill');
    if (text) text.textContent = data.videos_generated + ' / ' + data.video_cap + ' videos this month';
    if (fill) fill.style.width = Math.min(100, (data.videos_generated / data.video_cap) * 100) + '%';
  }).catch(function() {});
}
loadUsage();

// ---------------------------------------------------------------------------
// FORGE TIPS — shown during loading like a game
// ---------------------------------------------------------------------------
var FORGE_TIPS = [
  "The best content doesn't feel like content. It feels like a story you accidentally watched twice.",
  "Second person pulls the viewer in. Third person leaves them watching from the outside.",
  "The first 2 seconds decide everything. If the opener doesn't hook, nothing else matters.",
  "Short sentences hit harder at key moments. Use them like punctuation for impact.",
  "Sensory detail makes fiction feel real. Smell, sound, and texture beat description every time.",
  "The quiet closer lands harder than the hype closer. Understatement is a superpower.",
  "Escalating stakes keep people watching. Every scene should raise the ceiling.",
  "Foul language used once lands harder than foul language used ten times.",
  "The recurring character is your brand signature. Consistency builds audience memory.",
  "Deadpan delivery never explains the joke. Trust your audience to find it.",
  "Every shot is a reason to keep watching. Make each scene earn its place.",
  "The best video scripts read like they were easy to write. They never were.",
  "If the concept works as a one-sentence pitch, it works as a video.",
  "Profession-appropriate visuals make AI characters feel real, not random.",
  "The image prompt is half the video. Weak prompts produce weak scenes.",
  "Your thumbnail is a billboard. If it doesn't stop the scroll, nothing else gets a chance.",
  "Consistency beats virality. One video a day compounds faster than one viral video a month.",
  "The algorithm rewards watch time. Your script's only job is to earn the next second.",
  "Great content makes people feel something. Even confusion counts.",
  "Every format has a ceiling. The creators who win are the ones who find it first.",
];

// ---------------------------------------------------------------------------
// LOADER ICONS — cycle during generation
// ---------------------------------------------------------------------------
var LOADER_ICONS = ['iconAnvil', 'iconFlame', 'iconChain'];
var loaderIdx = 0;
var loaderInterval = null;

function cycleLoader() {
  var icons = LOADER_ICONS;
  icons.forEach(function(id) {
    var el = document.getElementById(id);
    if (el) el.classList.add('forge-loader-hidden');
  });
  loaderIdx = (loaderIdx + 1) % icons.length;
  var next = document.getElementById(icons[loaderIdx]);
  if (next) next.classList.remove('forge-loader-hidden');
}

function startLoader() {
  loaderIdx = 0;
  LOADER_ICONS.forEach(function(id, i) {
    var el = document.getElementById(id);
    if (el) el.classList.toggle('forge-loader-hidden', i !== 0);
  });
  loaderInterval = setInterval(cycleLoader, 2000);
}

function stopLoader() {
  if (loaderInterval) clearInterval(loaderInterval);
}

// ---------------------------------------------------------------------------
// TIPS rotation
// ---------------------------------------------------------------------------
var tipIdx = 0;
var tipInterval = null;

function startTips() {
  tipIdx = Math.floor(Math.random() * FORGE_TIPS.length);
  setTip(FORGE_TIPS[tipIdx]);
  tipInterval = setInterval(function() {
    tipIdx = (tipIdx + 1) % FORGE_TIPS.length;
    var el = document.getElementById('loadingTip');
    if (el) {
      el.style.opacity = '0';
      setTimeout(function() {
        setTip(FORGE_TIPS[tipIdx]);
        el.style.opacity = '1';
      }, 300);
    }
  }, 4000);
}

function stopTips() {
  if (tipInterval) clearInterval(tipInterval);
}

function setTip(text) {
  var el = document.getElementById('loadingTipText');
  if (el) el.textContent = text;
}

// ---------------------------------------------------------------------------
// EMBERS
// ---------------------------------------------------------------------------
(function () {
  var c = document.getElementById('dashEmbers');
  if (!c) return;
  for (var i = 0; i < 18; i++) {
    var e = document.createElement('div');
    e.classList.add('dash-ember');
    var sz = 1.5 + Math.random() * 2.5;
    var dr = (Math.random() - 0.5) * 50;
    var r = Math.random();
    e.style.cssText =
      'left:' + (Math.random() * 90 + 5) + '%;' +
      'bottom:' + (Math.random() * 15 - 5) + '%;' +
      'width:' + sz + 'px;height:' + sz + 'px;' +
      'background:' + (r > 0.6 ? '#ff8c3a' : r > 0.3 ? '#e06b18' : '#d4580a') + ';' +
      'box-shadow:0 0 ' + (3 + sz * 2) + 'px ' + (1 + sz) + 'px rgba(212,88,10,0.35);' +
      'animation:dash-ember-rise ' + (8 + Math.random() * 14) + 's linear ' + (Math.random() * 12) + 's infinite';
    e.style.setProperty('--drift', dr + 'px');
    c.appendChild(e);
  }
})();

// ---------------------------------------------------------------------------
// START GENERATION
// ---------------------------------------------------------------------------
function startGeneration() {
  var concept = document.getElementById('conceptInput').value.trim();
  if (!concept) { document.getElementById('conceptInput').focus(); return; }

  var character = document.getElementById('characterSelect').value;
  currentCharacterKey = character;

  document.getElementById('stepInput').classList.add('gen-step-hidden');
  document.getElementById('stepGeneration').classList.remove('gen-step-hidden');
  document.getElementById('stepGeneration').style.display = '';

  document.getElementById('genLoading').style.display = '';
  document.getElementById('genResults').style.display = 'none';
  document.getElementById('genError').style.display = 'none';
  var ips = document.getElementById('imagePreviewSection');
  if (ips) ips.style.display = 'none';
  document.getElementById('newVideoBtn').style.display = 'none';

  hideAllCards();
  setProgress(0, 'script');
  setLoadingText('Heating the forge...');

  startLoader();
  startTips();

  var loadingSteps = [
    { text: 'Writing your script...', stage: 'script', pct: 20 },
    { text: 'Generating image scenes...', stage: 'images', pct: 50 },
    { text: 'Building animation directives...', stage: 'anim', pct: 75 },
    { text: 'Finishing touches...', stage: 'done', pct: 90 },
  ];
  var ltIdx = 0;
  var loadingInterval = setInterval(function () {
    if (ltIdx < loadingSteps.length) {
      var step = loadingSteps[ltIdx];
      setLoadingText(step.text);
      setProgress(step.pct, step.stage);
      ltIdx++;
    }
  }, 4000);

  fetch('/generate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      concept: concept,
      character_mode: currentCharMode,
      character_preset: document.getElementById('characterSelect').value,
      formula: currentFormula,
      recurring_figure: document.getElementById('figureSelect').value,
      word_count: parseInt(document.getElementById('wordCountSlider').value, 10)
    })
  })
    .then(function (r) { return r.json(); })
    .then(function (data) {
      clearInterval(loadingInterval);
      stopLoader();
      stopTips();
      if (data.error) { showError(data.error); return; }
      generatedData = data;
      showResults(data);
      loadUsage();
    })
    .catch(function () {
      clearInterval(loadingInterval);
      stopLoader();
      stopTips();
      showError('Network error. Check your connection and try again.');
    });
}

// ---------------------------------------------------------------------------
// SHOW RESULTS
// ---------------------------------------------------------------------------
function showResults(data) {
  document.getElementById('genLoading').style.display = 'none';
  document.getElementById('genResults').style.display = '';
  document.getElementById('quickNav').style.display = 'flex';
  setProgress(100, 'done');

  // Script card
  setTimeout(function () {
    var card = document.getElementById('cardScript');
    card.classList.remove('result-card-hidden');
    card.style.display = '';
    var body = document.getElementById('scriptBody');
    var text = data.script || '';
    var wordCount = text.split(/\s+/).filter(Boolean).length;
    document.getElementById('scriptMeta').textContent = wordCount + ' words';
    document.getElementById('editScriptBtn').style.display = '';
    typewriter(body, text, 12, function() {
      setTimeout(gradeScript, 500);
    });
    // Show outfit pill if present
    var outfitPill = document.getElementById('outfitPill');
    var outfitText = document.getElementById('outfitText');
    if (data.character_outfit && outfitPill && outfitText) {
      outfitText.textContent = 'Character Outfit: ' + data.character_outfit;
      outfitPill.style.display = '';
    } else if (outfitPill) {
      outfitPill.style.display = 'none';
    }
  }, 200);

  // Score card
  setTimeout(function () {
    var card = document.getElementById('cardScore');
    if (card) {
      card.classList.remove('result-card-hidden');
      card.style.display = '';
    }
  }, 400);

  // Image prompts
  setTimeout(function () {
    var card = document.getElementById('cardPrompts');
    card.classList.remove('result-card-hidden');
    card.style.display = '';
    var prompts = data.image_prompts || [];
    var countEl = document.getElementById('promptCount');
    if (countEl) countEl.textContent = '(' + prompts.length + ')';
    var body = document.getElementById('promptsBody');
    body.innerHTML = '';
    prompts.forEach(function (p, i) {
      setTimeout(function () {
        var item = document.createElement('div');
        item.className = 'prompt-item';
        item.innerHTML = '<span class="prompt-num">' + String(i + 1).padStart(2, '0') + '</span><span class="prompt-text">' + escapeHtml(p) + '</span>' +
          '<button class="prompt-copy-btn" onclick="copyPromptItem(this)" title="Copy prompt">' +
            '<svg width="12" height="12" viewBox="0 0 14 14" fill="none"><rect x="4" y="4" width="8" height="8" rx="1.5" stroke="currentColor" stroke-width="1.2"/><path d="M10 4V3a1.5 1.5 0 0 0-1.5-1.5h-5A1.5 1.5 0 0 0 2 3v5A1.5 1.5 0 0 0 3.5 9.5H4" stroke="currentColor" stroke-width="1.2"/></svg>' +
          '</button>';
        body.appendChild(item);
      }, i * 55);
    });
  }, 1000);

  // Animation directives
  setTimeout(function () {
    var card = document.getElementById('cardDirectives');
    card.classList.remove('result-card-hidden');
    card.style.display = '';
    var body = document.getElementById('directivesBody');
    body.innerHTML = '';
    var directives = data.animation_directives || [];
    directives.forEach(function (d, i) {
      setTimeout(function () {
        var item = document.createElement('div');
        item.className = 'prompt-item';
        item.innerHTML = '<span class="prompt-num">' + String(i + 1).padStart(2, '0') + '</span><span class="prompt-text">' + escapeHtml(d) + '</span>' +
          '<button class="prompt-copy-btn" onclick="copyPromptItem(this)" title="Copy directive">' +
            '<svg width="12" height="12" viewBox="0 0 14 14" fill="none"><rect x="4" y="4" width="8" height="8" rx="1.5" stroke="currentColor" stroke-width="1.2"/><path d="M10 4V3a1.5 1.5 0 0 0-1.5-1.5h-5A1.5 1.5 0 0 0 2 3v5A1.5 1.5 0 0 0 3.5 9.5H4" stroke="currentColor" stroke-width="1.2"/></svg>' +
          '</button>';
        body.appendChild(item);
      }, i * 55);
    });
  }, 1800);

  // Image preview card (inside grid) — owner only
  setTimeout(function () {
    var previewCard = document.getElementById('cardPreview');
    if (previewCard) {
      previewCard.classList.remove('result-card-hidden');
      previewCard.style.display = '';
      var previewInner = document.getElementById('imagePreviewSection');
      if (previewInner) previewInner.style.display = '';
      if (data.image_prompts && data.image_prompts.length > 0) {
        showImagePreview(data.image_prompts[0]);
        var btn = document.getElementById('generateAllBtn');
        if (btn) btn.querySelector('#generateAllCount').textContent = data.image_prompts.length;
      }
    }
    document.getElementById('newVideoBtn').style.display = '';
  }, 2600);

  // Show regen counter
  var regenCounter = document.getElementById('regenCounter');
  if (regenCounter) regenCounter.style.display = 'flex';
  updateRegenCounter();
}

// ---------------------------------------------------------------------------
// SCORE GRADER
// ---------------------------------------------------------------------------
function gradeScript() {
  var scriptText = document.getElementById('scriptBody').textContent.trim();
  if (!scriptText) return;

  document.getElementById('gradeBtn').style.display = 'none';
  document.getElementById('gradeLoading').style.display = 'flex';
  document.getElementById('gradeResults').style.display = 'none';
  document.getElementById('scriptEditWrap').style.display = 'none';

  fetch('/grade-script', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ script: scriptText, formula: currentFormula })
  })
    .then(function (r) { return r.json(); })
    .then(function (data) {
      document.getElementById('gradeLoading').style.display = 'none';
      if (data.error) {
        document.getElementById('gradeBtn').style.display = '';
        return;
      }
      fixedScript = data.fixed_script || null;
      renderGradeResults(data);
    })
    .catch(function () {
      document.getElementById('gradeLoading').style.display = 'none';
      document.getElementById('gradeBtn').style.display = '';
    });
}

function renderGradeResults(data) {
  document.getElementById('gradeResults').style.display = 'block';

  var score = data.overall_score || 0;
  var grade = data.grade || '--';
  var issues = data.issues || [];

  // Score circle color
  var circleEl = document.getElementById('gradeCircle');
  var color = score >= 85 ? '#2dd4a0' : score >= 70 ? '#e8a040' : '#e84040';
  circleEl.style.borderColor = color;
  document.getElementById('gradeScoreNum').textContent = score;
  document.getElementById('gradeScoreNum').style.color = color;

  var letterEl = document.getElementById('gradeLetter');
  letterEl.textContent = grade;
  letterEl.style.color = color;

  var issuesEl = document.getElementById('gradeIssuesCount');
  issuesEl.textContent = issues.length === 0 ? 'Perfect formula' : issues.length + ' issue' + (issues.length > 1 ? 's' : '') + ' found';
  issuesEl.style.color = issues.length === 0 ? '#2dd4a0' : '#b8b3ab';

  // Criteria breakdown
  var criteriaEl = document.getElementById('gradeCriteria');
  criteriaEl.innerHTML = '';
  var criteriaMap = currentFormula === 'a' ? {
    word_count: 'Word Count (280-380)',
    second_person: 'Second Person',
    time_progression: 'Time Progression',
    recurring_figure: 'Recurring Figure',
    quiet_closer: 'Quiet Closer',
    visceral_detail: 'Visceral Detail'
  } : {
    word_count: 'Word Count (130-140)',
    second_person: 'Second Person',
    named_object: 'Named by Sentence 2',
    head_fake: 'Head Fake (60-70%)',
    cta_format: 'Three-Option CTA',
    dry_tone: 'Dry Tone'
  };

  var scores = data.scores || {};
  Object.keys(criteriaMap).forEach(function (key) {
    var c = scores[key];
    if (!c) return;
    var item = document.createElement('div');
    item.className = 'grade-criterion';
    var passClass = c.pass ? 'criterion-pass' : 'criterion-fail';
    var icon = c.pass
      ? '<svg width="12" height="12" viewBox="0 0 12 12" fill="none"><path d="M2 6l3 3 5-5" stroke="#2dd4a0" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>'
      : '<svg width="12" height="12" viewBox="0 0 12 12" fill="none"><path d="M3 3l6 6M9 3l-6 6" stroke="#e84040" stroke-width="1.5" stroke-linecap="round"/></svg>';
    item.innerHTML =
      '<div class="criterion-left">' +
        '<div class="criterion-badge ' + passClass + '">' + icon + '</div>' +
        '<span class="criterion-name">' + criteriaMap[key] + '</span>' +
      '</div>' +
      '<div class="criterion-right">' +
        '<div class="criterion-bar-track"><div class="criterion-bar-fill" style="width:' + (c.score * 10) + '%;background:' + (c.pass ? '#2dd4a0' : '#e84040') + '"></div></div>' +
        '<span class="criterion-score">' + c.score + '/10</span>' +
      '</div>';
    if (c.detail) {
      var detail = document.createElement('div');
      detail.className = 'criterion-detail';
      detail.textContent = c.detail;
      item.appendChild(detail);
    }
    criteriaEl.appendChild(item);
  });

  // Show fix actions if issues exist
  var fixActions = document.getElementById('gradeFixActions');
  if (issues.length > 0 && fixedScript) {
    fixActions.style.display = 'flex';
  } else {
    fixActions.style.display = 'none';
  }
}

function applyFix() {
  if (!fixedScript) return;
  var body = document.getElementById('scriptBody');
  body.textContent = '';
  typewriter(body, fixedScript, 10, function() {
    setTimeout(gradeScript, 400);
  });

  // Update word count
  var wordCount = fixedScript.split(/\s+/).filter(Boolean).length;
  document.getElementById('scriptMeta').textContent = wordCount + ' words';

  // Update stored data
  if (generatedData) generatedData.script = fixedScript;

  document.getElementById('gradeFixActions').style.display = 'none';
  document.getElementById('gradeResults').style.display = 'none';
  document.getElementById('gradeBtn').style.display = '';
  document.getElementById('gradeBtn').textContent = 'Re-grade Script';
}

function toggleEditScript() {
  var wrap = document.getElementById('scriptEditWrap');
  var gradeResults = document.getElementById('gradeResults');
  var isHidden = wrap.style.display === 'none' || wrap.style.display === '';

  if (isHidden) {
    var currentText = document.getElementById('scriptBody').textContent;
    document.getElementById('scriptEditArea').value = currentText;
    wrap.style.display = 'block';
    gradeResults.style.display = 'none';
    document.getElementById('scriptEditArea').focus();
  } else {
    wrap.style.display = 'none';
  }
}

function saveManualEdit() {
  var newText = document.getElementById('scriptEditArea').value.trim();
  if (!newText) return;

  document.getElementById('scriptBody').textContent = newText;
  var wordCount = newText.split(/\s+/).filter(Boolean).length;
  document.getElementById('scriptMeta').textContent = wordCount + ' words';
  if (generatedData) generatedData.script = newText;

  document.getElementById('scriptEditWrap').style.display = 'none';
  document.getElementById('gradeResults').style.display = 'none';
  document.getElementById('gradeBtn').style.display = '';
  document.getElementById('gradeBtn').textContent = 'Re-grade Script';

  setTimeout(gradeScript, 400);
}

function cancelEdit() {
  document.getElementById('scriptEditWrap').style.display = 'none';
  document.getElementById('gradeResults').style.display = 'block';
}

// ---------------------------------------------------------------------------
// IMAGE PREVIEW
// ---------------------------------------------------------------------------
function showImagePreview(prompt) {
  var skeleton = document.getElementById('imageSkeleton');
  var img = document.getElementById('previewImage');

  skeleton.style.display = 'flex';
  img.style.display = 'none';
  document.getElementById('imagePromptText').textContent = prompt;

  fetch('/generate-image', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ prompt: prompt, character_key: currentCharacterKey })
  })
    .then(function(r) { return r.json(); })
    .then(function(data) {
      if (data.image) {
        try {
          var base64 = data.image.split(',')[1];
          var mime = data.image.split(';')[0].split(':')[1];
          var byteChars = atob(base64);
          var byteArr = new Uint8Array(byteChars.length);
          for (var i = 0; i < byteChars.length; i++) {
            byteArr[i] = byteChars.charCodeAt(i);
          }
          var blob = new Blob([byteArr], { type: mime });
          var blobUrl = URL.createObjectURL(blob);
          img.onload = function() {
            skeleton.style.display = 'none';
            img.style.display = 'block';
            img.style.opacity = '1';
          };
          img.onerror = function() {
            skeleton.style.display = 'flex';
            document.querySelector('.skeleton-text').textContent = 'Image failed to render';
            document.querySelector('.skeleton-shimmer').style.display = 'none';
          };
          img.style.opacity = '0';
          img.style.display = 'none';
          img.src = blobUrl;
        } catch(e) {
          skeleton.style.display = 'flex';
          document.querySelector('.skeleton-text').textContent = 'Failed to decode image';
          document.querySelector('.skeleton-shimmer').style.display = 'none';
        }
      } else {
        skeleton.style.display = 'flex';
        document.querySelector('.skeleton-text').textContent = data.error || 'Image generation unavailable';
        document.querySelector('.skeleton-shimmer').style.display = 'none';
      }
    })
    .catch(function() {
      skeleton.style.display = 'flex';
      document.querySelector('.skeleton-text').textContent = 'Image generation failed';
      document.querySelector('.skeleton-shimmer').style.display = 'none';
    });
}

// ---------------------------------------------------------------------------
// TYPEWRITER
// ---------------------------------------------------------------------------
function typewriter(el, text, speed, onComplete) {
  el.textContent = '';
  var i = 0;
  var interval = setInterval(function () {
    if (i < text.length) { el.textContent += text[i]; i++; }
    else { clearInterval(interval); if (onComplete) onComplete(); }
  }, speed);
}

// ---------------------------------------------------------------------------
// COPY
// ---------------------------------------------------------------------------
function copyContent(bodyId, btnId) {
  var body = document.getElementById(bodyId);
  var btn = document.getElementById(btnId);
  var text = '';
  if (bodyId === 'scriptBody') {
    text = body.textContent;
  } else {
    var items = body.querySelectorAll('.prompt-text');
    var arr = [];
    items.forEach(function (item, i) { arr.push((i + 1) + '. ' + item.textContent); });
    text = arr.join('\n\n');
  }
  navigator.clipboard.writeText(text).then(function () { showCopied(btn); }).catch(function () {
    var ta = document.createElement('textarea');
    ta.value = text; ta.style.position = 'fixed'; ta.style.left = '-9999px';
    document.body.appendChild(ta); ta.select(); document.execCommand('copy');
    document.body.removeChild(ta); showCopied(btn);
  });
}

function copyPromptItem(btn) {
  var text = btn.parentElement.querySelector('.prompt-text').textContent;
  navigator.clipboard.writeText(text).then(function() {
    btn.style.color = '#2dd4a0';
    setTimeout(function() { btn.style.color = ''; }, 1500);
  });
}

function copyItemText(btn) {
  var item = btn.closest('.prompt-item');
  var text = item.querySelector('.prompt-text').textContent;
  navigator.clipboard.writeText(text).then(function () { showCopied(btn); }).catch(function () {
    var ta = document.createElement('textarea');
    ta.value = text; ta.style.position = 'fixed'; ta.style.left = '-9999px';
    document.body.appendChild(ta); ta.select(); document.execCommand('copy');
    document.body.removeChild(ta); showCopied(btn);
  });
}

function copyAllPrompts() {
  if (!generatedData) return;
  var all = ['=== SCRIPT ===\n' + (generatedData.script || '')];
  all.push('\n\n=== IMAGE PROMPTS ===');
  (generatedData.image_prompts || []).forEach(function (p, i) { all.push((i + 1) + '. ' + p); });
  all.push('\n\n=== ANIMATION DIRECTIVES ===');
  (generatedData.animation_directives || []).forEach(function (d, i) { all.push((i + 1) + '. ' + d); });
  navigator.clipboard.writeText(all.join('\n')).then(function () {
    var btn = document.querySelector('.gen-action-copy');
    if (btn) showCopiedText(btn, 'Copied Everything!');
  });
}

function showCopied(btn) {
  var original = btn.innerHTML;
  btn.classList.add('copied');
  btn.innerHTML = '<svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M3 7l3 3 5-6" stroke="#2dd4a0" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg> Copied';
  setTimeout(function () { btn.classList.remove('copied'); btn.innerHTML = original; }, 2000);
}

function showCopiedText(btn, text) {
  var original = btn.innerHTML;
  btn.style.color = '#2dd4a0';
  btn.innerHTML = '<svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M3 7l3 3 5-6" stroke="#2dd4a0" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg> ' + text;
  setTimeout(function () { btn.style.color = ''; btn.innerHTML = original; }, 2500);
}

// ---------------------------------------------------------------------------
// PROGRESS
// ---------------------------------------------------------------------------
function setProgress(pct, stage) {
  document.getElementById('progressFill').style.width = pct + '%';
  var steps = ['script', 'grade', 'images', 'anim', 'done'];
  var ids = ['progScript', 'progGrade', 'progImages', 'progAnim', 'progDone'];
  var activeIdx = steps.indexOf(stage);
  ids.forEach(function (id, i) {
    var el = document.getElementById(id);
    if (!el) return;
    el.classList.remove('prog-active', 'prog-done');
    if (i < activeIdx) el.classList.add('prog-done');
    else if (i === activeIdx) el.classList.add('prog-active');
  });
}

function setLoadingText(text) {
  var el = document.getElementById('loadingText');
  if (el) el.textContent = text;
}

// ---------------------------------------------------------------------------
// ERROR
// ---------------------------------------------------------------------------
function showError(msg) {
  document.getElementById('genLoading').style.display = 'none';
  document.getElementById('genResults').style.display = 'none';
  document.getElementById('genError').style.display = '';
  document.getElementById('genErrorText').textContent = msg;
}

// ---------------------------------------------------------------------------
// RESET
// ---------------------------------------------------------------------------
function resetGenerator() {
  generatedData = null;
  fixedScript = null;
  regenerationsLeft = 3;
  stopLoader();
  stopTips();

  document.getElementById('quickNav').style.display = 'none';
  var regenCounter = document.getElementById('regenCounter');
  if (regenCounter) regenCounter.style.display = 'none';
  document.getElementById('stepInput').classList.remove('gen-step-hidden');
  document.getElementById('stepInput').style.display = '';
  document.getElementById('stepGeneration').classList.add('gen-step-hidden');
  document.getElementById('stepGeneration').style.display = 'none';
  document.getElementById('conceptInput').value = '';
  document.getElementById('conceptInput').focus();

  hideAllCards();
  setProgress(0, 'script');
  resetGrader();
}

function hideAllCards() {
  ['cardScript', 'cardScore', 'cardPrompts', 'cardDirectives', 'cardPreview'].forEach(function (id) {
    var el = document.getElementById(id);
    if (el) { el.classList.add('result-card-hidden'); el.style.display = 'none'; }
  });
}

function resetGrader() {
  document.getElementById('gradeBtn') && (document.getElementById('gradeBtn').style.display = '');
  document.getElementById('gradeBtn') && (document.getElementById('gradeBtn').textContent = '');
  document.getElementById('gradeBtn') && (document.getElementById('gradeBtn').innerHTML = '<svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M7 1l1.5 3.5L12 5l-2.5 2.5.5 3.5L7 9.5 4 11l.5-3.5L2 5l3.5-.5L7 1Z" stroke="currentColor" stroke-width="1.2" stroke-linejoin="round"/></svg> Grade This Script');
  document.getElementById('gradeLoading') && (document.getElementById('gradeLoading').style.display = 'none');
  document.getElementById('gradeResults') && (document.getElementById('gradeResults').style.display = 'none');
  document.getElementById('scriptEditWrap') && (document.getElementById('scriptEditWrap').style.display = 'none');
  document.getElementById('editScriptBtn') && (document.getElementById('editScriptBtn').style.display = 'none');
}

// ---------------------------------------------------------------------------
// REGENERATE SECTION
// ---------------------------------------------------------------------------
function updateRegenCounter() {
  var text = document.getElementById('regenCountText');
  if (text) text.textContent = regenerationsLeft + ' regeneration' + (regenerationsLeft !== 1 ? 's' : '') + ' left';
  var btns = document.querySelectorAll('.regen-btn');
  btns.forEach(function(btn) { btn.disabled = regenerationsLeft <= 0; });
}

function regenerateSection(section) {
  if (regenerationsLeft <= 0 || !generatedData) return;

  var concept = document.getElementById('conceptInput').value.trim();
  if (!concept) concept = 'regenerate';

  var btnId = section === 'script' ? 'regenScript' : section === 'image_prompts' ? 'regenPrompts' : 'regenDirectives';
  var btn = document.getElementById(btnId);
  if (btn) { btn.disabled = true; btn.classList.add('regen-spinning'); }

  fetch('/generate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      concept: concept,
      character_mode: currentCharMode,
      character_preset: document.getElementById('characterSelect').value,
      formula: currentFormula,
      recurring_figure: document.getElementById('figureSelect').value,
      word_count: parseInt(document.getElementById('wordCountSlider').value, 10)
    })
  })
  .then(function(r) { return r.json(); })
  .then(function(data) {
    if (btn) btn.classList.remove('regen-spinning');
    if (data.error) { if (btn) btn.disabled = false; return; }

    regenerationsLeft--;
    updateRegenCounter();

    if (section === 'script') {
      generatedData.script = data.script;
      generatedData.character_outfit = data.character_outfit;
      var body = document.getElementById('scriptBody');
      body.textContent = '';
      typewriter(body, data.script, 12, function() { setTimeout(gradeScript, 500); });
      var wc = data.script.split(/\s+/).filter(Boolean).length;
      document.getElementById('scriptMeta').textContent = wc + ' words';
      var outfitPill = document.getElementById('outfitPill');
      var outfitText = document.getElementById('outfitText');
      if (data.character_outfit && outfitPill && outfitText) {
        outfitText.textContent = 'Character Outfit: ' + data.character_outfit;
        outfitPill.style.display = '';
      }
    } else if (section === 'image_prompts') {
      generatedData.image_prompts = data.image_prompts || [];
      var prompts = generatedData.image_prompts;
      var countEl = document.getElementById('promptCount');
      if (countEl) countEl.textContent = '(' + prompts.length + ')';
      var body = document.getElementById('promptsBody');
      body.innerHTML = '';
      prompts.forEach(function(p, i) {
        var item = document.createElement('div');
        item.className = 'prompt-item';
        item.innerHTML = '<span class="prompt-num">' + String(i+1).padStart(2,'0') + '</span><span class="prompt-text">' + escapeHtml(p) + '</span>' +
          '<button class="prompt-copy-btn" onclick="copyPromptItem(this)" title="Copy prompt"><svg width="12" height="12" viewBox="0 0 14 14" fill="none"><rect x="4" y="4" width="8" height="8" rx="1.5" stroke="currentColor" stroke-width="1.2"/><path d="M10 4V3a1.5 1.5 0 0 0-1.5-1.5h-5A1.5 1.5 0 0 0 2 3v5A1.5 1.5 0 0 0 3.5 9.5H4" stroke="currentColor" stroke-width="1.2"/></svg></button>';
        body.appendChild(item);
      });
      var genBtn = document.getElementById('generateAllBtn');
      if (genBtn) genBtn.querySelector('#generateAllCount').textContent = prompts.length;
    } else if (section === 'animation_directives') {
      generatedData.animation_directives = data.animation_directives || [];
      var directives = generatedData.animation_directives;
      var body = document.getElementById('directivesBody');
      body.innerHTML = '';
      directives.forEach(function(d, i) {
        var item = document.createElement('div');
        item.className = 'prompt-item';
        item.innerHTML = '<span class="prompt-num">' + String(i+1).padStart(2,'0') + '</span><span class="prompt-text">' + escapeHtml(d) + '</span>' +
          '<button class="prompt-copy-btn" onclick="copyPromptItem(this)" title="Copy directive"><svg width="12" height="12" viewBox="0 0 14 14" fill="none"><rect x="4" y="4" width="8" height="8" rx="1.5" stroke="currentColor" stroke-width="1.2"/><path d="M10 4V3a1.5 1.5 0 0 0-1.5-1.5h-5A1.5 1.5 0 0 0 2 3v5A1.5 1.5 0 0 0 3.5 9.5H4" stroke="currentColor" stroke-width="1.2"/></svg></button>';
        body.appendChild(item);
      });
    }
  })
  .catch(function() {
    if (btn) { btn.classList.remove('regen-spinning'); btn.disabled = regenerationsLeft <= 0; }
  });
}

// ---------------------------------------------------------------------------
// GENERATE ALL IMAGES
// ---------------------------------------------------------------------------
function generateAllImages() {
  if (!generatedData || !generatedData.image_prompts) return;

  var prompts = generatedData.image_prompts;
  var total = prompts.length;
  var completed = 0;
  var failed = 0;

  // Create image gallery container if not exists
  var gallery = document.getElementById('imageGallery');
  if (!gallery) {
    gallery = document.createElement('div');
    gallery.id = 'imageGallery';
    gallery.className = 'image-gallery';
    document.getElementById('imagePreviewSection').appendChild(gallery);
  }
  gallery.innerHTML = '';

  // Create placeholder cards for all images
  prompts.forEach(function(prompt, i) {
    var card = document.createElement('div');
    card.className = 'gallery-card';
    card.id = 'galleryCard' + i;
    card.innerHTML =
      '<div class="gallery-num">' + String(i + 1).padStart(2, '0') + '</div>' +
      '<div class="gallery-skeleton" id="gallerySkeleton' + i + '">' +
        '<div class="skeleton-shimmer"></div>' +
        '<div class="gallery-loading-text">Queued...</div>' +
      '</div>' +
      '<img class="gallery-img" id="galleryImg' + i + '" style="display:none" alt="Scene ' + (i+1) + '">';
    gallery.appendChild(card);
  });

  // Update button state
  var btn = document.getElementById('generateAllBtn');
  btn.disabled = true;
  btn.innerHTML = 'Generating 1 / ' + total + '...';

  // Generate images sequentially to avoid rate limits
  function generateNext(index) {
    if (index >= total) {
      btn.disabled = false;
      btn.innerHTML = 'Regenerate All ' + total + ' Images';
      var saveBtn = document.getElementById('saveAllBtn');
      if (saveBtn && completed > 0) saveBtn.style.display = '';
      return;
    }

    var skeleton = document.getElementById('gallerySkeleton' + index);
    var img = document.getElementById('galleryImg' + index);
    skeleton.querySelector('.gallery-loading-text').textContent = 'Generating...';

    fetch('/generate-image', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ prompt: prompts[index], character_key: currentCharacterKey })
    })
    .then(function(r) { return r.json(); })
    .then(function(data) {
      if (data.image) {
        try {
          var base64 = data.image.split(',')[1];
          var mime = data.image.split(';')[0].split(':')[1];
          var byteChars = atob(base64);
          var byteArr = new Uint8Array(byteChars.length);
          for (var i = 0; i < byteChars.length; i++) {
            byteArr[i] = byteChars.charCodeAt(i);
          }
          var blob = new Blob([byteArr], { type: mime });
          var blobUrl = URL.createObjectURL(blob);
          img.onload = function() {
            skeleton.style.display = 'none';
            img.style.display = 'block';
          };
          img.src = blobUrl;
          completed++;
        } catch(e) {
          skeleton.querySelector('.gallery-loading-text').textContent = 'Failed';
          failed++;
        }
      } else {
        skeleton.querySelector('.gallery-loading-text').textContent = 'Failed';
        failed++;
      }
      btn.innerHTML = 'Generating ' + (index + 2) + ' / ' + total + '...';
      generateNext(index + 1);
    })
    .catch(function() {
      skeleton.querySelector('.gallery-loading-text').textContent = 'Failed';
      failed++;
      generateNext(index + 1);
    });
  }

  generateNext(0);
}

// ---------------------------------------------------------------------------
// SAVE ALL IMAGES
// ---------------------------------------------------------------------------
function saveAllImages() {
  var gallery = document.getElementById('imageGallery');
  if (!gallery) return;
  var imgs = gallery.querySelectorAll('.gallery-img');
  var saved = 0;
  imgs.forEach(function(img, i) {
    if (img.style.display === 'none' || !img.src) return;
    var a = document.createElement('a');
    a.href = img.src;
    a.download = 'scene_' + String(i + 1).padStart(2, '0') + '.png';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    saved++;
  });
  var btn = document.getElementById('saveAllBtn');
  if (btn && saved > 0) {
    var orig = btn.innerHTML;
    btn.innerHTML = '<svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M3 7l3 3 5-6" stroke="#2dd4a0" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg> Saved ' + saved + ' Images';
    setTimeout(function() { btn.innerHTML = orig; }, 2500);
  }
}

// ---------------------------------------------------------------------------
// REFERENCE IMAGE UPLOAD
// ---------------------------------------------------------------------------
function handleReferenceUpload(input) {
  var file = input.files[0];
  if (!file) return;

  var statusText = document.getElementById('refStatusText');
  statusText.textContent = 'Uploading...';

  var reader = new FileReader();
  reader.onload = function(e) {
    var imageData = e.target.result;

    fetch('/upload-reference', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        character_key: 'base',
        image_data: imageData
      })
    })
    .then(function(r) { return r.json(); })
    .then(function(data) {
      if (data.success) {
        setReferenceStatus(true, imageData);
      } else {
        statusText.textContent = 'Upload failed';
      }
    })
    .catch(function() {
      statusText.textContent = 'Upload failed';
    });
  };
  reader.readAsDataURL(file);
}

function setReferenceStatus(hasRef, imageData) {
  var dot = document.getElementById('refDot');
  var statusText = document.getElementById('refStatusText');
  var clearBtn = document.getElementById('refClearBtn');

  if (hasRef) {
    dot.classList.add('active');
    statusText.textContent = 'Reference active';
    if (clearBtn) clearBtn.style.display = '';
  } else {
    dot.classList.remove('active');
    statusText.textContent = 'No reference';
    if (clearBtn) clearBtn.style.display = 'none';
  }
}

function clearReference() {
  fetch('/upload-reference', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ character_key: 'base', image_data: null })
  })
  .then(function(r) { return r.json(); })
  .then(function() {
    setReferenceStatus(false);
  });
}

// Load active character from localStorage on page load
(function loadActiveCharacter() {
  var charId = localStorage.getItem('active_character_id');
  var charName = localStorage.getItem('active_character_name');
  if (charId && charName) {
    var input = document.getElementById('characterSelect');
    var btn = document.getElementById('charPickerName');
    if (input) input.value = charId;
    if (btn) btn.textContent = charName;
  }
})();

// Check reference status on page load
fetch('/get-reference', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ character_key: 'base' })
})
.then(function(r) { return r.json(); })
.then(function(data) {
  if (data.has_reference) {
    setReferenceStatus(true, null);
  }
});

// ---------------------------------------------------------------------------
// QUICK NAV
// ---------------------------------------------------------------------------
function scrollToSection(id) {
  var el = document.getElementById(id);
  if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

// ---------------------------------------------------------------------------
// HELPERS
// ---------------------------------------------------------------------------
function escapeHtml(str) {
  var div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

// ---------------------------------------------------------------------------
// AI GUIDE
// ---------------------------------------------------------------------------
var aiGuideHistory = [];

function toggleAiGuide() {
  var panel = document.getElementById('aiGuidePanel');
  if (!panel) return;
  var visible = panel.style.display !== 'none';
  panel.style.display = visible ? 'none' : 'flex';
  if (!visible) {
    var input = document.getElementById('aiGuideInput');
    if (input) input.focus();
  }
}

function sendAiGuide() {
  var input = document.getElementById('aiGuideInput');
  var text = input.value.trim();
  if (!text) return;
  input.value = '';

  aiGuideHistory.push({ role: 'user', content: text });
  appendGuideMessage('user', text);

  var messages = document.getElementById('aiGuideMessages');
  var thinkingId = 'guide-thinking-' + Date.now();
  var thinking = document.createElement('div');
  thinking.className = 'ai-guide-msg ai-guide-msg-ai';
  thinking.id = thinkingId;
  thinking.innerHTML = '<div class="ai-guide-dots"><span></span><span></span><span></span></div>';
  messages.appendChild(thinking);
  messages.scrollTop = messages.scrollHeight;

  fetch('/ai-guide', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ messages: aiGuideHistory })
  })
  .then(function(r) { return r.json(); })
  .then(function(data) {
    var el = document.getElementById(thinkingId);
    if (el) el.remove();
    if (data.reply) {
      aiGuideHistory.push({ role: 'assistant', content: data.reply });
      appendGuideMessage('assistant', data.reply);
    } else if (data.error) {
      appendGuideMessage('assistant', 'Error: ' + data.error);
    }
  })
  .catch(function() {
    var el = document.getElementById(thinkingId);
    if (el) el.remove();
    appendGuideMessage('assistant', 'Connection error. Try again.');
  });
}

function appendGuideMessage(role, text) {
  var messages = document.getElementById('aiGuideMessages');
  var msg = document.createElement('div');
  msg.className = 'ai-guide-msg ai-guide-msg-' + (role === 'user' ? 'user' : 'ai');
  msg.textContent = text;
  messages.appendChild(msg);
  messages.scrollTop = messages.scrollHeight;
}
