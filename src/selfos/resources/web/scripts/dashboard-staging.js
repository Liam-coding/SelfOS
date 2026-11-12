// ── Staging review ──
let _stagingFiles = [];
function checkStaging() {
  fetch('/__staging__').then(r => r.json()).then(data => {
    _stagingFiles = data.files || [];
    const btn = document.getElementById('staging-btn');
    if (_stagingFiles.length > 0) {
      btn.style.display = '';
      btn.textContent = lang === 'zh'
        ? `● ${_stagingFiles.length} 待审核`
        : `● ${_stagingFiles.length} Pending`;
    } else {
      btn.style.display = 'none';
    }
  }).catch(() => {});
}
function openStagingModal() {
  const list = document.getElementById('staging-file-list');
  list.innerHTML = '';
  _stagingFiles.forEach((f, i) => {
    const item = document.createElement('div');
    item.className = 'staging-file-item selected';
    item.dataset.idx = i;
    item.innerHTML = `<div class="staging-file-name">${f.name}</div>`
      + `<div class="staging-file-target">→ ${f.target || '(unknown target)'}</div>`;
    item.onclick = () => item.classList.toggle('selected');
    list.appendChild(item);
  });
  document.getElementById('staging-modal').classList.add('open');
}
function closeStagingModal() {
  document.getElementById('staging-modal').classList.remove('open');
}
function applySelectedStaging() {
  const items = document.querySelectorAll('.staging-file-item.selected');
  const filenames = Array.from(items).map(el => _stagingFiles[+el.dataset.idx].name);
  if (!filenames.length) { closeStagingModal(); return; }
  const btn = document.getElementById('staging-apply-btn');
  btn.disabled = true;
  btn.textContent = lang === 'zh' ? '应用中…' : 'Applying…';
  fetch('/__staging__/apply', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({files: filenames})
  }).then(r => r.json()).then(data => {
    closeStagingModal();
    checkStaging();
    btn.disabled = false;
    btn.textContent = lang === 'zh' ? '应用选中' : 'Apply Selected';
  }).catch(() => {
    btn.disabled = false;
    btn.textContent = lang === 'zh' ? '应用选中' : 'Apply Selected';
  });
}
document.getElementById('staging-modal').addEventListener('click', e => {
  if (e.target === e.currentTarget) closeStagingModal();
});
checkStaging();

