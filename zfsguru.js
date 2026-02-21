// Common JS helpers for ZFSguru module UI.

function zfsguruToggleDhcpOverwriteWarning() {
  var sel = document.querySelector('select[name="dhcp_client_mode"]');
  var warn = document.getElementById('dhcp-overwrite-warning');
  if (!sel || !warn) return;
  warn.classList.toggle('zfsguru-hidden', sel.value !== 'overwrite');
}

function zfsguruIsPartitionWipeOp(val) {
  return val === 'zerowrite' || val === 'randomwrite' || val === 'trimerase';
}

function zfsguruTogglePartitionWipeUI() {
  var sel = document.querySelector('select[name="part_operation"]');
  if (!sel) return;

  var isWipe = zfsguruIsPartitionWipeOp(sel.value);
  var isResize = sel.value === 'resize';
  var warn = document.getElementById('part-wipe-warning');
  var confirmRow = document.getElementById('part-wipe-confirm-row');
  var backgroundRow = document.getElementById('part-wipe-background-row');
  var resizeRow = document.getElementById('part-resize-row');

  if (warn) warn.classList.toggle('zfsguru-hidden', !isWipe);
  if (confirmRow) confirmRow.classList.toggle('zfsguru-hidden', !isWipe);
  if (backgroundRow) backgroundRow.classList.toggle('zfsguru-hidden', !isWipe);
  if (resizeRow) resizeRow.classList.toggle('zfsguru-hidden', !isResize);
}

function zfsguruToggleDiskWipeUI() {
  var sel = document.querySelector('select[name="wipe_mode"]');
  if (!sel) return;

  var isQuick = sel.value === 'quick';
  var sizeRow = document.getElementById('wipe-size-row');
  var warn = document.getElementById('wipe-mode-warning');

  if (sizeRow) sizeRow.classList.toggle('zfsguru-hidden', !isQuick);
  if (warn) warn.classList.toggle('zfsguru-hidden', !isQuick);
}

function zfsguruBindPoolPicker() {
  var form = document.getElementById('zfsguru-pool-picker-form');
  var poolSel = document.getElementById('zfsguru-pool-select');
  var actionSel = document.getElementById('zfsguru-pool-action');
  var actionHidden = document.getElementById('zfsguru-pool-action-hidden');
  var goBtn = document.getElementById('zfsguru-pool-go');
  if (!form || !poolSel || !actionSel || !goBtn) return;

  var actionMap = {
    view: 'advanced_pools.cgi?action=view&pool=',
    props: 'advanced_pools.cgi?action=props&pool=',
    scrub: 'advanced_pools.cgi?action=scrub&pool=',
    history: 'advanced_pools.cgi?action=history&pool=',
    datasets: 'advanced_datasets.cgi?action=list&pool='
  };

  var go = function () {
    var pool = (poolSel.value || '').trim();
    if (!pool) return;
    var action = actionSel.value || 'view';
    var base = actionMap[action] || actionMap.view;
    window.location.href = base + encodeURIComponent(pool);
  };

  form.addEventListener('submit', function (e) {
    e.preventDefault();
    go();
  });

  actionSel.addEventListener('change', function () {
    if (actionHidden) {
      actionHidden.value = actionSel.value || 'view';
    }
  });
}

function zfsguruBindCommonUI() {
  // Initial render
  zfsguruToggleDhcpOverwriteWarning();
  zfsguruTogglePartitionWipeUI();
  zfsguruToggleDiskWipeUI();
  zfsguruBindPoolPicker();

  // Live switching
  document.addEventListener('change', function (e) {
    if (!e.target || !e.target.name) return;
    if (e.target.name === 'dhcp_client_mode') zfsguruToggleDhcpOverwriteWarning();
    if (e.target.name === 'part_operation') zfsguruTogglePartitionWipeUI();
    if (e.target.name === 'wipe_mode') zfsguruToggleDiskWipeUI();
  });
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', zfsguruBindCommonUI);
} else {
  zfsguruBindCommonUI();
}
