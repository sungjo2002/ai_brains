const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

const store = {
  get(key, fallback) {
    try { return JSON.parse(localStorage.getItem(key)) ?? fallback; } catch { return fallback; }
  },
  set(key, value) { localStorage.setItem(key, JSON.stringify(value)); },
  remove(key) { localStorage.removeItem(key); }
};

const APP_BUILD_VERSION = '92';

async function resetOutdatedMobileServiceWorker() {
  if (!('serviceWorker' in navigator)) return;
  const resetKey = `mobile_sw_reset_${APP_BUILD_VERSION}`;
  try {
    const registrations = await navigator.serviceWorker.getRegistrations();
    const hasOldWorker = registrations.some(registration => [registration.active, registration.waiting, registration.installing].some(worker => worker?.scriptURL && !worker.scriptURL.includes(`v=${APP_BUILD_VERSION}`)));
    if (!hasOldWorker) return;
    await Promise.all(registrations.map(registration => registration.unregister().catch(() => false)));
    if ('caches' in window) {
      const keys = await caches.keys();
      await Promise.all(keys.map(key => caches.delete(key)));
    }
    if (!sessionStorage.getItem(resetKey)) {
      sessionStorage.setItem(resetKey, '1');
      const url = new URL(window.location.href);
      url.searchParams.set('v', APP_BUILD_VERSION);
      url.searchParams.set('swreset', String(Date.now()));
      window.location.replace(url.toString());
    }
  } catch (error) {
    console.warn('service worker reset skipped', error);
  }
}
resetOutdatedMobileServiceWorker();

function pad2(value) { return String(value).padStart(2, '0'); }
function formatDateKey(date = new Date()) {
  return `${date.getFullYear()}-${pad2(date.getMonth() + 1)}-${pad2(date.getDate())}`;
}
function formatMonthKey(date = new Date()) {
  return `${date.getFullYear()}-${pad2(date.getMonth() + 1)}`;
}
function formatDateTime(date = new Date()) {
  return `${formatDateKey(date)} ${pad2(date.getHours())}:${pad2(date.getMinutes())}`;
}
let APP_TODAY = new Date();
let APP_TODAY_DATE = formatDateKey(APP_TODAY);
let APP_TODAY_MONTH = formatMonthKey(APP_TODAY);

const API_BASE = `${window.location.origin}/api`;
const serverConnection = {
  online: false,
  usingServerTime: false,
  checkedAt: null,
  message: '서버 연결 확인 중'
};

let deferredInstallPrompt = null;

function isStandaloneMode() {
  return window.matchMedia('(display-mode: standalone)').matches || window.navigator.standalone === true;
}

function isLikelyManualShortcutMode() {
  const host = window.location.hostname;
  const isLocal = host === 'localhost' || host === '127.0.0.1';
  return window.location.protocol !== 'https:' && !isLocal;
}

function updateShortcutButtonState() {
  const button = $('#shortcutGuideOpen');
  const status = $('#shortcutInstallStatus');
  const httpNotice = $('#shortcutHttpNotice');
  const manualMode = isLikelyManualShortcutMode();
  if (button) {
    button.classList.toggle('installed', isStandaloneMode());
    if (isStandaloneMode()) {
      button.textContent = '앱처럼 실행 중';
    } else if (deferredInstallPrompt) {
      button.textContent = '앱 설치창 열기';
    } else {
      button.textContent = '홈 화면에 바로가기 추가';
    }
  }
  if (status) {
    status.textContent = isStandaloneMode()
      ? '현재 바탕화면 아이콘으로 앱처럼 실행 중입니다.'
      : deferredInstallPrompt
        ? '설치창이 준비되었습니다. 버튼을 누르면 설치 안내가 뜹니다.'
        : manualMode
          ? '자동 설치창이 안 뜨면 오른쪽 위 메뉴에서 직접 홈 화면에 추가하세요.'
          : '문자 링크 또는 크롬에서 열어 홈 화면에 추가하세요.';
  }
  if (httpNotice) httpNotice.hidden = !manualMode || isStandaloneMode();
}

window.addEventListener('beforeinstallprompt', event => {
  event.preventDefault();
  deferredInstallPrompt = event;
  updateShortcutButtonState();
});

window.addEventListener('appinstalled', () => {
  deferredInstallPrompt = null;
  updateShortcutButtonState();
  toast('홈 화면에 추가되었습니다. 바탕화면 아이콘으로 실행하세요.');
});


function setAppToday(date, options = {}) {
  if (!(date instanceof Date) || Number.isNaN(date.getTime())) return;
  APP_TODAY = date;
  APP_TODAY_DATE = formatDateKey(date);
  APP_TODAY_MONTH = formatMonthKey(date);
  selectedAttendanceDate = APP_TODAY_DATE;
  setSelectedMonth(APP_TODAY_MONTH);
  updateCurrentDateLabels();
}

function updateServerStatusUI() {
  const loginStatus = $('#loginServerStatus');
  if (loginStatus) {
    loginStatus.classList.remove('ok', 'fail');
    loginStatus.classList.add(serverConnection.online ? 'ok' : 'fail');
    loginStatus.textContent = serverConnection.online
      ? `서버 연결 정상 · 기준일 ${APP_TODAY_DATE}${serverConnection.usingServerTime ? '' : ' (기기 기준)'}`
      : '서버 연결 실패 · 관리자에게 문의하세요';
  }
  const syncText = $('#syncServerStatusText');
  const syncPill = $('#syncServerStatusPill');
  if (syncText) syncText.textContent = serverConnection.online ? '정상' : '연결 실패';
  if (syncPill) {
    syncPill.textContent = serverConnection.online ? '연결됨' : '오프라인';
    syncPill.classList.toggle('success', serverConnection.online);
    syncPill.classList.toggle('warn', !serverConnection.online);
  }
}

function getStoredAuthToken() {
  return store.get('mobileAuthToken', '') || currentUser?.token || '';
}

function getAuthHeaders() {
  const token = getStoredAuthToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, {
    cache: 'no-store',
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    ...options
  });
  let data = null;
  try { data = await response.json(); } catch { data = null; }
  if (!response.ok) {
    const error = new Error(data?.message || data?.error || `HTTP ${response.status}`);
    error.response = response;
    error.data = data;
    throw error;
  }
  return { data, response };
}

function isMissingApiError(error) {
  const status = error?.response?.status;
  return status === 404 || status === 405 || status === 501;
}

function isLoginRejectError(error) {
  const status = error?.response?.status;
  return status === 400 || status === 401 || status === 403;
}

function parseServerDateValue(value) {
  if (!value) return null;
  if (value instanceof Date) return value;
  const text = String(value);
  const normalized = /^\d{4}-\d{2}-\d{2}$/.test(text) ? `${text}T00:00:00` : text;
  const parsed = new Date(normalized);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

function extractServerTime(data, response) {
  const source = data?.server_time || data?.serverTime || data?.datetime || data?.now || data?.time || data?.date || response?.headers?.get('Date');
  return parseServerDateValue(source);
}

async function initializeServerConnection() {
  updateServerStatusUI();
  try {
    let serverDate = null;
    try {
      const result = await fetchJson(`${API_BASE}/server-time?ts=${Date.now()}`);
      serverDate = extractServerTime(result.data, result.response);
    } catch {
      const result = await fetchJson(`${API_BASE}/health?ts=${Date.now()}`);
      serverDate = extractServerTime(result.data, result.response);
    }
    serverConnection.online = true;
    serverConnection.checkedAt = new Date();
    if (serverDate) {
      serverConnection.usingServerTime = true;
      setAppToday(serverDate);
    } else {
      serverConnection.usingServerTime = false;
      updateCurrentDateLabels();
    }
  } catch {
    serverConnection.online = false;
    serverConnection.usingServerTime = false;
    updateCurrentDateLabels();
  }
  updateServerStatusUI();
}

let currentUser = null;
let currentHomeStatus = 'all';
const VEHICLE_LIST = [
  { car: '12가 3456', business: '그린시스템', site: '1공장' },
  { car: '34나 7890', business: '성조산업', site: '2공장' }
];
let serverVehicleList = [];
let serverVehicleRunLogs = [];
let serverVehicleFuelLogs = [];
let serverVehicleCostLogs = [];
let vehicleServerLoaded = false;
let vehicleServerLoading = false;
let vehicleServerLastError = '';
let vehicleServerCheckedAt = 0;
let currentVehicleTab = 'run';
const VEHICLE_REFRESH_MS = 2 * 60 * 1000;

let selectedCell = null;
let activeAttendanceMode = 'present';

const attendanceStateMeta = {
  empty: { label: '해제', icon: null, className: 'state-empty' },
  present: { label: '출석', icon: 'i-presence', className: 'state-present' },
  absent: { label: '결근', icon: 'i-absence', className: 'state-absent' },
  hospital: { label: '병원', icon: 'i-hospital', className: 'state-hospital' },
  late: { label: '지각', icon: 'i-clock', className: 'state-late' },
  early: { label: '조퇴', icon: 'i-early', className: 'state-early' },
  off: { label: '휴무', icon: 'i-off', className: 'state-off' },
  unauthorized_absent: { label: '무단결근', icon: 'i-ban', className: 'state-unauthorized' },
  unauthorized_leave: { label: '무단이탈', icon: 'i-ban', className: 'state-unauthorized' }
};

function isSuperUser() {
  if (!currentUser) return false;
  const role = String(currentUser.role || currentUser.role_code || currentUser.userType || '').toLowerCase().replace(/[\s_-]+/g, '');
  const label = String(currentUser.roleLabel || currentUser.role_name || '').toLowerCase().replace(/[\s_-]+/g, '');
  const userId = String(currentUser.id || currentUser.username || store.get('savedLoginId', '') || '').toLowerCase().trim();
  return role === 'super'
    || role === 'superadmin'
    || role === 'admin'
    || role === 'master'
    || label === '최고관리자'
    || currentUser.is_super === true
    || currentUser.is_admin === true
    || currentUser.can_view_all === true
    || userId === 'admin';
}
function normalizeScopeValue(value) {
  if (value === null || value === undefined) return '';
  if (typeof value === 'string' || typeof value === 'number') return String(value).trim();
  if (Array.isArray(value)) {
    for (const item of value) {
      const text = normalizeScopeValue(item);
      if (text) return text;
    }
    return '';
  }
  if (typeof value === 'object') {
    const keys = [
      'name', 'work_site', 'site', 'site_name', 'work_site_name',
      'business', 'business_name', 'company', 'company_name',
      'car', 'vehicle_no', 'plate_number', 'vehicleNumber',
      'vehicle_id', 'vehicle_name', 'username', 'login_id',
      'loginId', 'display_name', 'employee_name'
    ];
    for (const key of keys) {
      const text = normalizeScopeValue(value[key]);
      if (text) return text;
    }
    return '';
  }
  return String(value ?? '').trim();
}
function canonicalScopeValue(value) {
  return normalizeScopeValue(value).toLowerCase().replace(/[\s\-_/\.]+/g, '');
}
function isAllScopeValue(value) {
  return ['전체', '*', 'all'].includes(String(value || '').toLowerCase());
}
function scopeListHasSpecificValues(values = []) {
  return normalizeScopeList(values).some(value => value && !isAllScopeValue(value));
}
function scopeValueMatches(left = '', right = '') {
  const a = canonicalScopeValue(left);
  const b = canonicalScopeValue(right);
  return !!a && !!b && a === b;
}
function normalizeScopeList(values = []) {
  const source = Array.isArray(values) ? values : String(values || '').split(',');
  const seen = new Set();
  const result = [];
  source.forEach(item => {
    let value = '';
    if (typeof item === 'string' || typeof item === 'number') value = String(item);
    else if (item && typeof item === 'object') value = item.name || item.work_site || item.site || item.site_name || item.business || item.business_name || item.car || item.plate_number || item.vehicle_no || item.vehicleNumber || item.vehicle_id || '';
    value = normalizeScopeValue(value);
    if (!value || seen.has(value)) return;
    seen.add(value);
    result.push(value);
  });
  return result;
}
function scopeAllows(list = [], value = '') {
  if (isSuperUser()) return true;
  const target = normalizeScopeValue(value);
  const normalized = normalizeScopeList(list);
  if (normalized.some(item => isAllScopeValue(item))) return true;
  return !!target && normalized.some(item => scopeValueMatches(item, target));
}
function userAllowsBusiness(business) {
  return scopeAllows(currentUser?.businesses, business);
}
function userAllowsSite(site) {
  return scopeAllows(currentUser?.sites, site);
}
function userAllowsCar(car) {
  if (isSuperUser()) return true;
  if (!scopeListHasSpecificValues(currentUser?.cars)) return true;
  return scopeAllows(currentUser?.cars, car);
}
function vehicleFieldValues(vehicle = {}, keys = []) {
  return keys.map(key => normalizeScopeValue(vehicle?.[key] ?? vehicle?.raw?.[key] ?? '')).filter(Boolean);
}
function splitVehicleTextValues(value = '') {
  return normalizeScopeValue(value)
    .split(/[,:;|\/\\]+/)
    .map(item => normalizeScopeValue(item))
    .filter(Boolean);
}
function addVehicleValue(target, value) {
  splitVehicleTextValues(value).forEach(item => target.push(item));
}
function scopeListMatchesAny(list = [], values = []) {
  const specific = normalizeScopeList(list).filter(value => value && !isAllScopeValue(value));
  if (!specific.length) return true;
  return values.some(value => specific.some(item => scopeValueMatches(item, value)));
}
function currentUserVehicleIdentityValues() {
  const values = [];
  [
    currentUser?.loginId,
    currentUser?.username,
    currentUser?.name,
    currentUser?.display_name,
    currentUser?.displayName,
    store.get('savedLoginId', ''),
    store.get('currentUserId', '')
  ].forEach(value => addVehicleValue(values, value));
  const userId = normalizeScopeValue(currentUser?.id || '');
  if (userId && !/^\d+$/.test(userId)) addVehicleValue(values, userId);
  return normalizeScopeList(values);
}
function vehiclePersonValues(vehicle = {}) {
  const values = [];
  const source = vehicle || {};
  const raw = vehicle?.raw || {};
  [source, raw].forEach(target => {
    [
      'main_driver', 'mainDriver', 'primary_driver', 'primaryDriver', 'default_driver', 'defaultDriver',
      'driver', 'driver_name', 'driverName', 'manager', 'manager_name', 'managerName',
      'assigned_manager', 'assignedManager', 'assigned_user', 'assignedUser', 'assignee', 'owner', 'owner_name',
      'login_id', 'loginId', 'username', 'user_name', 'account_id', 'admin_id', 'admin_name'
    ].forEach(key => addVehicleValue(values, target?.[key]));
    ['drivers', 'assigned_drivers', 'assigned_users', 'managers'].forEach(key => {
      const list = Array.isArray(target?.[key]) ? target[key] : [];
      list.forEach(item => {
        if (typeof item === 'string' || typeof item === 'number') addVehicleValue(values, item);
        else if (item && typeof item === 'object') {
          addVehicleValue(values, item.login_id || item.loginId || item.username || item.name || item.display_name || item.id || '');
        }
      });
    });
  });
  return normalizeScopeList(values);
}
function userMatchesVehiclePerson(vehicle = {}) {
  const userValues = currentUserVehicleIdentityValues();
  const personValues = vehiclePersonValues(vehicle);
  if (!userValues.length || !personValues.length) return false;
  return personValues.some(person => userValues.some(user => scopeValueMatches(user, person)));
}
function userAllowsVehicle(vehicle = {}) {
  if (isSuperUser()) return true;
  const carValues = vehicleFieldValues(vehicle, ['car', 'vehicle_no', 'vehicleNumber', 'plate_number', 'vehicle_id', 'vehicle_name']);
  const explicitCarOk = scopeListHasSpecificValues(currentUser?.cars) && scopeListMatchesAny(currentUser?.cars, carValues);
  const personOk = userMatchesVehiclePerson(vehicle);
  return explicitCarOk || personOk;
}
function userAllowsWorker(worker) {
  return !!worker && userAllowsBusiness(worker.business) && userAllowsSite(worker.site);
}
function uniqueValues(values) {
  return [...new Set(values.filter(Boolean))];
}
function populateSelect(select, values, options = {}) {
  if (!select) return;
  const { includeAll = false, placeholder = '' } = options;
  const oldValue = select.value;
  const items = [];
  if (placeholder) items.push(`<option value="">${escapeHtml(placeholder)}</option>`);
  if (includeAll) items.push('<option>전체</option>');
  values.forEach(value => items.push(`<option>${escapeHtml(value)}</option>`));
  select.innerHTML = items.join('');
  if (oldValue && [...select.options].some(option => option.value === oldValue)) select.value = oldValue;
  else if (!placeholder && select.options.length) select.selectedIndex = 0;
}
function getScopedAttendanceWorkersBase() {
  if (isSuperUser()) return attendanceWorkers;
  return attendanceWorkers.filter(worker => userAllowsWorker(worker));
}
function getScopedHomeRows(rows) {
  return rows.filter(row => userAllowsBusiness(row.business) && userAllowsSite(row.site));
}
function vehicleIdentityKeys(vehicle = {}) {
  const raw = vehicle.raw || {};
  const values = [
    vehicle.vehicle_id,
    vehicle.vehicle_name,
    vehicle.plate_number,
    vehicle.vehicle_no,
    vehicle.vehicleNumber,
    vehicle.car,
    raw.vehicle_id,
    raw.vehicle_name,
    raw.name,
    raw.display_name,
    raw.plate_number,
    raw.vehicle_no,
    raw.vehicleNumber,
    raw.car
  ];
  return normalizeScopeList(values)
    .filter(value => value && !['-', '전체', '*', 'all'].includes(String(value).toLowerCase()));
}

function hasVehicleIdentity(seen, vehicle = {}) {
  return vehicleIdentityKeys(vehicle).some(key => seen.has(key));
}

function rememberVehicleIdentity(seen, vehicle = {}) {
  vehicleIdentityKeys(vehicle).forEach(key => seen.add(key));
}

function getScopedVehicles() {
  const baseVehicles = serverVehicleList.length ? serverVehicleList : VEHICLE_LIST;
  const vehicles = [];
  const existing = new Set();

  baseVehicles.forEach(vehicle => {
    if (!userAllowsVehicle(vehicle)) return;
    if (hasVehicleIdentity(existing, vehicle)) return;
    const copy = { ...vehicle };
    vehicles.push(copy);
    rememberVehicleIdentity(existing, copy);
  });

  // 서버 차량 목록이 정상으로 내려온 뒤에는 관리자 배정값(currentUser.cars)을
  // 별도 차량처럼 다시 추가하지 않는다.
  // 배정값에는 vehicle_id(V003)와 표시명(aaa)이 함께 들어올 수 있어
  // select 목록에 aaa / V003 / aaa 중복이 생길 수 있다.
  const shouldUseAssignedFallback = !vehicleServerLoaded && !serverVehicleList.length;
  if (shouldUseAssignedFallback) {
    const assignedCars = normalizeScopeList(currentUser?.cars)
      .filter(value => value && !['전체', '*', 'all'].includes(String(value).toLowerCase()));
    const fallbackBusiness = normalizeScopeList(currentUser?.businesses).find(value => !['전체', '*', 'all'].includes(String(value).toLowerCase())) || '';
    const fallbackSite = normalizeScopeList(currentUser?.sites).find(value => !['전체', '*', 'all'].includes(String(value).toLowerCase())) || '';

    assignedCars.forEach(car => {
      const key = normalizeScopeValue(car);
      if (!key || existing.has(key)) return;
      const fallbackVehicle = { vehicle_id: key, car: key, business: fallbackBusiness, site: fallbackSite };
      vehicles.push(fallbackVehicle);
      rememberVehicleIdentity(existing, fallbackVehicle);
    });
  }

  return vehicles;
}

function getWorkerRegistrationSiteValues() {
  const scopedWorkers = getScopedAttendanceWorkersBase();
  const assignedSites = normalizeScopeList(currentUser?.sites).filter(value => !['전체', '*', 'all'].includes(String(value).toLowerCase()));
  const workerSites = isSuperUser()
    ? uniqueValues(attendanceWorkers.map(worker => worker.site))
    : uniqueValues(scopedWorkers.map(worker => worker.site));
  const values = isSuperUser()
    ? workerSites
    : (assignedSites.length ? assignedSites : workerSites);
  return values.length ? values : ['근무사업장 미지정'];
}

function getBusinessForWorkerRegistrationSite(site = '') {
  const selectedSite = normalizeScopeValue(site);
  if (!selectedSite) return '';
  const assignedBusinesses = normalizeScopeList(currentUser?.businesses)
    .filter(value => !['전체', '*', 'all'].includes(String(value).toLowerCase()));
  const candidateWorkers = [...getScopedAttendanceWorkersBase(), ...attendanceWorkers];
  const matched = candidateWorkers.find(worker => normalizeScopeValue(worker.site) === selectedSite && normalizeScopeValue(worker.business));
  if (matched?.business) return normalizeScopeValue(matched.business);
  if (assignedBusinesses.length === 1) return assignedBusinesses[0];
  return assignedBusinesses[0] || '';
}

function updateWorkerRegistrationSiteOptions() {
  const siteSelect = $('#workerSiteSelect');
  if (!siteSelect) return;
  const sites = getWorkerRegistrationSiteValues();
  populateSelect(siteSelect, sites, { placeholder: '근무사업장을 선택하세요' });
}

function configurePermissionOptions() {
  const scopedWorkers = getScopedAttendanceWorkersBase();
  const assignedBusinesses = normalizeScopeList(currentUser?.businesses).filter(value => !['전체', '*', 'all'].includes(String(value).toLowerCase()));
  const assignedSites = normalizeScopeList(currentUser?.sites).filter(value => !['전체', '*', 'all'].includes(String(value).toLowerCase()));
  const businessValues = isSuperUser()
    ? uniqueValues(attendanceWorkers.map(worker => worker.business))
    : (assignedBusinesses.length ? assignedBusinesses : uniqueValues(scopedWorkers.map(worker => worker.business)));
  const siteValues = isSuperUser()
    ? uniqueValues(attendanceWorkers.map(worker => worker.site))
    : (assignedSites.length ? assignedSites : uniqueValues(scopedWorkers.map(worker => worker.site)));
  const attendanceSiteFilter = $('#attSiteFilter');
  populateSelect(attendanceSiteFilter, isSuperUser() ? [] : siteValues, { includeAll: true });
  if (attendanceSiteFilter) {
    if (isSuperUser()) {
      attendanceSiteFilter.value = '전체';
      attendanceSiteFilter.disabled = true;
      attendanceSiteFilter.title = '최고 관리자는 전체 근로자를 봅니다.';
    } else {
      attendanceSiteFilter.disabled = false;
      attendanceSiteFilter.title = '';
    }
  }
  updateWorkerRegistrationSiteOptions();
  populateSelect($('#vehicleCarSelect'), getScopedVehicles().map(vehicle => vehicle.car), { placeholder: '차량을 선택하세요' });
}
function saveLoginOptions(loginId, user) {
  const saveId = $('#saveLoginId')?.checked !== false;
  const keepLogin = $('#keepLogin')?.checked !== false;
  store.set('saveLoginIdEnabled', saveId);
  store.set('keepLoginEnabled', keepLogin);
  if (saveId) store.set('savedLoginId', loginId);
  else store.remove('savedLoginId');
  if (keepLogin) {
    const { password, ...safeUser } = user;
    store.set('currentUserId', user.id);
    store.set('savedUserSnapshot', safeUser);
    if (user.token) store.set('mobileAuthToken', user.token);
    else store.remove('mobileAuthToken');
  } else {
    store.remove('currentUserId');
    store.remove('savedUserSnapshot');
    store.remove('mobileAuthToken');
  }
}

function restoreLoginOptions() {
  const saveIdEnabled = store.get('saveLoginIdEnabled', true);
  const keepLoginEnabled = store.get('keepLoginEnabled', true);
  const savedId = store.get('savedLoginId', '');
  const saveIdEl = $('#saveLoginId');
  const keepLoginEl = $('#keepLogin');
  if (saveIdEl) saveIdEl.checked = saveIdEnabled;
  if (keepLoginEl) keepLoginEl.checked = keepLoginEnabled;
  if (saveIdEnabled && savedId && $('#loginId')) $('#loginId').value = savedId;
}

function updateUserStrip() {
  const strip = $('#userStrip');
  if (!strip || !currentUser) return;
  const loginId = String(
    currentUser.loginId
    || currentUser.login_id
    || currentUser.username
    || currentUser.userName
    || currentUser.displayName
    || currentUser.display_name
    || store.get('savedLoginId', '')
    || currentUser.name
    || currentUser.id
    || ''
  ).trim();
  strip.innerHTML = `<b>${escapeHtml(loginId)}</b>`;
  strip.hidden = false;
}
function setLoggedInUser(user, options = {}) {
  const { persist = true } = options;
  currentUser = user;
  if (persist) store.set('currentUserId', user.id);
  const shell = $('.app-shell');
  shell?.classList.remove('logged-out');
  shell?.classList.add('logged-in');
  clearLegacyMobileLocalData();
  updateUserStrip();
  configurePermissionOptions();
  renderHomeWorkers(currentHomeStatus);
  updateWorkers();
  updateSync();
  initializeAttendanceModule();
  showScreen('homeScreen');
  loadServerEmployees({ force: true });
  refreshCurrentUserScopeFromServer();
  processAttendanceRetryQueue({ reason: 'login', silent: true });
}
function logoutUser() {
  currentUser = null;
  store.remove('currentUserId');
  store.remove('savedUserSnapshot');
  store.remove('mobileAuthToken');
  store.set('keepLoginEnabled', false);
  const shell = $('.app-shell');
  shell?.classList.remove('logged-in', 'home-mode', 'attendance-mode');
  shell?.classList.add('logged-out');
  const strip = $('#userStrip');
  if (strip) strip.hidden = true;
  $('#loginPassword').value = '';
  $('#loginError').hidden = true;
  $('#loginId')?.focus();
}


function decodeWorkforceValue(value) {
  if (Array.isArray(value)) return value.map(item => decodeWorkforceValue(item));
  if (!value || typeof value !== 'object') return value;

  if (Array.isArray(value.__workforce_dict_items__)) {
    const decoded = {};
    value.__workforce_dict_items__.forEach(pair => {
      if (!Array.isArray(pair) || pair.length < 2) return;
      const key = pair[0];
      decoded[String(key)] = decodeWorkforceValue(pair[1]);
    });
    return decoded;
  }

  if (Array.isArray(value.__workforce_tuple__)) {
    return value.__workforce_tuple__.map(item => decodeWorkforceValue(item));
  }

  const decoded = {};
  Object.entries(value).forEach(([key, item]) => {
    decoded[key] = decodeWorkforceValue(item);
  });
  return decoded;
}

function managerAccountPairs(account = {}) {
  const decodedAccount = decodeWorkforceValue(account || {});
  const pairs = [];
  const fallbackBusiness = normalizeScopeValue(decodedAccount.business || decodedAccount.business_name || decodedAccount.assigned_business || '');
  const fallbackSite = normalizeScopeValue(decodedAccount.work_site || decodedAccount.site || decodedAccount.site_name || '');
  const rawSites = Array.isArray(decodedAccount.work_sites)
    ? decodedAccount.work_sites
    : Array.isArray(decodedAccount.assigned_sites)
      ? decodedAccount.assigned_sites
      : [];
  rawSites.forEach(item => {
    let business = fallbackBusiness;
    let site = '';
    if (typeof item === 'string') {
      site = item;
    } else if (item && typeof item === 'object') {
      business = normalizeScopeValue(item.business || item.business_name || fallbackBusiness);
      site = normalizeScopeValue(item.work_site || item.site || item.site_name || item.name || '');
    }
    business = normalizeScopeValue(business);
    site = normalizeScopeValue(site);
    if (business && site && !pairs.some(pair => pair.business === business && pair.site === site)) {
      pairs.push({ business, site });
    }
  });
  if (!pairs.length && fallbackBusiness && fallbackSite) {
    pairs.push({ business: fallbackBusiness, site: fallbackSite });
  }
  return pairs;
}

async function refreshCurrentUserScopeFromServer() {
  if (!currentUser) return;
  const token = currentUser.token || getStoredAuthToken();
  if (!token) return;
  try {
    const latestUser = await restoreServerSession();
    if (!latestUser) return;
    const previousSites = normalizeScopeList(currentUser.sites).join('|');
    const nextSites = normalizeScopeList(latestUser.sites).join('|');
    const previousBusinesses = normalizeScopeList(currentUser.businesses).join('|');
    const nextBusinesses = normalizeScopeList(latestUser.businesses).join('|');
    currentUser = { ...currentUser, ...latestUser, token: latestUser.token || token };
    store.set('currentUserId', currentUser.id);
    store.set('savedUserSnapshot', currentUser);
    store.set('mobileAuthToken', currentUser.token);
    updateUserStrip();
    configurePermissionOptions();
    renderHomeWorkers(currentHomeStatus);
    updateWorkers();
    if ($('#attendanceScreen')?.classList.contains('active')) renderAttendanceViews();
    if (previousSites !== nextSites || previousBusinesses !== nextBusinesses) {
      toast('관리자 배정 권한을 최신 기준으로 반영했습니다.');
    }
  } catch (error) {
    console.warn('manager scope refresh skipped', error);
  }
}


function normalizeServerUser(rawUser, loginId) {
  const response = rawUser || {};
  const source = response.user || response.account || response.admin || response.data?.user || response.data || response;
  const permissions = response.permissions || source.permissions || response.scope || source.scope || {};
  const roleValue = String(source.role || source.role_code || source.user_type || source.roleLabel || '').toLowerCase().replace(/\s+/g, '');
  const isSuper = ['super', 'admin', 'master', 'super_admin', 'superadmin', '최고관리자'].includes(roleValue)
    || source.is_super === true
    || source.is_admin === true
    || permissions.all === true
    || permissions.all_access === true;

  const pickList = (...keys) => {
    for (const target of [permissions, source, response]) {
      for (const key of keys) {
        const value = target?.[key];
        if (Array.isArray(value)) {
          return value.map(item => {
            if (typeof item === 'string') return item;
            return item.name || item.work_site || item.site || item.site_name || item.car || item.vehicle_no || item.vehicleNumber || item.business || item.business_name;
          }).filter(Boolean);
        }
        if (typeof value === 'string' && value) return value.split(',').map(item => item.trim()).filter(Boolean);
      }
    }
    return [];
  };

  const rawWorkSites = pickList('work_sites', 'assigned_sites', 'sites', 'site_list', 'site_names');
  let businesses = pickList('businesses', 'assigned_businesses', 'business_list', 'business_names');
  let sites = rawWorkSites;
  const accountPairs = managerAccountPairs(source);
  if (!businesses.length && accountPairs.length) businesses = accountPairs.map(pair => pair.business);
  if (!sites.length && accountPairs.length) sites = accountPairs.map(pair => pair.site);
  businesses = normalizeScopeList(businesses);
  sites = normalizeScopeList(sites);
  const cars = normalizeScopeList(pickList('cars', 'vehicles', 'assigned_cars', 'vehicle_list', 'vehicle_numbers'));
  const token = response.token || response.access_token || response.auth_token || source.token || response.data?.token || '';
  const displayLoginId = firstNonEmpty(source.login_id, source.loginId, source.username, source.user_name, source.account_id, loginId, source.name, source.display_name);
  const userId = source.id || source.user_id || displayLoginId || loginId;

  return {
    id: String(userId || loginId),
    loginId: String(displayLoginId || loginId || userId || ''),
    username: String(displayLoginId || loginId || userId || ''),
    password: '',
    name: source.name || source.display_name || displayLoginId || loginId,
    role: isSuper ? 'super' : 'manager',
    roleLabel: isSuper ? '최고 관리자' : '일반 관리자',
    businesses: isSuper ? ['전체'] : (businesses.length ? businesses : ['그린시스템']),
    sites: isSuper ? ['전체'] : (sites.length ? sites : ['1공장']),
    cars: isSuper ? ['전체'] : (cars.length ? cars : []),
    token
  };
}

async function requestServerLogin(loginId, password) {
  const payload = { login_id: loginId, username: loginId, loginId, password };
  const endpoints = [`${API_BASE}/auth/login`, `${API_BASE}/login`];
  let lastError = null;
  for (const endpoint of endpoints) {
    try {
      const result = await fetchJson(endpoint, {
        method: 'POST',
        body: JSON.stringify(payload)
      });
      return normalizeServerUser(result.data, loginId);
    } catch (error) {
      lastError = error;
      if (isLoginRejectError(error)) return null;
      if (!isMissingApiError(error)) break;
    }
  }
  throw lastError || new Error('서버 로그인 API를 사용할 수 없습니다.');
}

async function authenticateUser(loginId, password) {
  try {
    return await requestServerLogin(loginId, password);
  } catch (serverLoginError) {
    console.warn('server login failed', serverLoginError);
    return null;
  }
}

async function restoreServerSession() {
  const token = getStoredAuthToken();
  if (!token) return null;
  const endpoints = [`${API_BASE}/auth/me`, `${API_BASE}/me`];
  for (const endpoint of endpoints) {
    try {
      const result = await fetchJson(`${endpoint}?ts=${Date.now()}`, { headers: getAuthHeaders() });
      const user = normalizeServerUser({ ...result.data, token }, store.get('currentUserId', ''));
      return { ...user, token };
    } catch (error) {
      if (isLoginRejectError(error)) {
        store.remove('mobileAuthToken');
        store.remove('savedUserSnapshot');
        store.remove('currentUserId');
        return null;
      }
      if (!isMissingApiError(error)) return null;
    }
  }
  return null;
}

function initializeLogin() {
  const loginForm = $('#loginForm');
  loginForm?.addEventListener('submit', async event => {
    event.preventDefault();
    const loginButton = loginForm.querySelector('button[type="submit"]');
    const loginId = $('#loginId').value.trim();
    const password = $('#loginPassword').value;
    if (loginButton) {
      loginButton.disabled = true;
      loginButton.textContent = '로그인 확인 중...';
    }
    const user = await authenticateUser(loginId, password);
    if (loginButton) {
      loginButton.disabled = false;
      loginButton.textContent = '로그인';
    }
    if (!user) {
      $('#loginError').textContent = '아이디 또는 비밀번호를 확인하세요.';
      $('#loginError').hidden = false;
      return;
    }
    $('#loginError').hidden = true;
    saveLoginOptions(loginId, user);
    setLoggedInUser(user, { persist: $('#keepLogin')?.checked !== false });
  });
  $('#logoutButton')?.addEventListener('click', logoutUser);
  restoreLoginOptions();
}

async function restoreLoginSession() {
  const keepLoginEnabled = store.get('keepLoginEnabled', true);
  if (!keepLoginEnabled) {
    $('#loginId')?.focus();
    return;
  }
  const serverUser = await restoreServerSession();
  if (serverUser) {
    saveLoginOptions(store.get('savedLoginId', serverUser.id), serverUser);
    setLoggedInUser(serverUser);
    return;
  }
  store.remove('currentUserId');
  store.remove('savedUserSnapshot');
  store.remove('mobileAuthToken');
  $('#loginId')?.focus();
}

const attendanceStateMap = {
  '✓': 'present',
  '출': 'present',
  '결': 'absent',
  '병': 'hospital',
  '지': 'late',
  '조': 'early',
  '휴': 'off',
  '무결': 'unauthorized_absent',
  '무이탈': 'unauthorized_leave',
  '-': 'empty',
  '': 'empty'
};


const homeStatusConfig = {
  all: { title: '전체 근로자', states: [], pillClass: 'all', label: '전체' },
  present: { title: '출석 근로자', states: ['present'], pillClass: 'present', label: '출석' },
  absent: { title: '결근 근로자', states: ['absent'], pillClass: 'absent', label: '결근' },
  hospital: { title: '병원 근로자', states: ['hospital'], pillClass: 'hospital', label: '병원' },
  late: { title: '지각/조퇴 근로자', states: ['late', 'early'], pillClass: 'late', label: '지각/조퇴' },
  unauthorized: { title: '무단결근/무단이탈 근로자', states: ['unauthorized_absent', 'unauthorized_leave'], pillClass: 'unauthorized', label: '무단결근/무단이탈' }
};

function getStatePillClass(state) {
  if (state === 'present') return 'present';
  if (state === 'absent') return 'absent';
  if (state === 'hospital') return 'hospital';
  if (state === 'late' || state === 'early') return 'late';
  if (state === 'unauthorized_absent' || state === 'unauthorized_leave') return 'unauthorized';
  return 'all';
}

function getHomeStatusRows(key = 'all') {
  const config = homeStatusConfig[key] || homeStatusConfig.all;
  const rows = getScopedAttendanceWorkersBase()
    .map(worker => {
      const state = getAttendanceState(worker.id, APP_TODAY_DATE);
      const meta = attendanceStateMeta[state] || attendanceStateMeta.empty;
      return { ...worker, state, stateLabel: meta.label };
    });
  if (!config.states || !config.states.length) return rows;
  return rows.filter(row => config.states.includes(row.state));
}

function renderHomeWorkers(key = 'all') {
  currentHomeStatus = key;
  const config = homeStatusConfig[key] || homeStatusConfig.all;
  const title = $('#homeWorkerTitle');
  const total = $('#homeWorkerCount');
  const list = $('#homeWorkerList');
  if (title) title.textContent = config.title;

  $$('#homeStatusGrid [data-worker-status]').forEach(card => {
    const statusKey = card.dataset.workerStatus;
    const rows = getHomeStatusRows(statusKey);
    const strong = $('strong', card);
    if (strong) strong.textContent = rows.length;
  });

  const rows = getHomeStatusRows(key);
  if (total) total.textContent = `${rows.length}명`;
  if (!list) return;

  if (employeeServerLoading && !attendanceWorkers.length) {
    list.innerHTML = '<div class="home-worker-empty">서버 근로자 목록을 불러오는 중입니다.</div>';
    return;
  }
  if (employeeServerLastError && !attendanceWorkers.length) {
    list.innerHTML = '<div class="home-worker-empty">서버 근로자 목록을 불러오지 못했습니다. 동기화 상태를 확인하세요.</div>';
    return;
  }
  if (!attendanceWorkers.length) {
    list.innerHTML = '<div class="home-worker-empty">서버에 등록된 근로자가 없습니다.</div>';
    return;
  }
  if (!rows.length) {
    list.innerHTML = '<div class="home-worker-empty">해당 상태의 근로자가 없습니다.</div>';
    return;
  }
  list.innerHTML = rows.map(row => {
    const pillClass = key === 'all' ? getStatePillClass(row.state) : config.pillClass;
    return `
    <article class="home-worker-row home-worker-clickable" data-worker-id="${escapeHtml(row.id)}" tabindex="0" role="button" aria-label="${escapeHtml(row.name)} 간단 정보 보기">
      <b class="home-worker-name">${escapeHtml(row.name)}</b>
      <span>${escapeHtml(row.site)}</span>
      <span>${escapeHtml(row.type)}</span>
      <span class="state-pill ${pillClass}">${escapeHtml(row.stateLabel)}</span>
    </article>
  `;
  }).join('');
}


function getWorkerById(workerId) {
  const target = String(workerId || '').trim();
  return attendanceWorkers.find(worker => String(worker.id || '').trim() === target) || null;
}

function getCallablePhone(value = '') {
  return String(value || '').replace(/[^0-9+]/g, '');
}

function renderWorkerInfoLine(label, value) {
  const text = String(value || '').trim() || '-';
  return `<div class="worker-info-line"><span>${escapeHtml(label)}</span><b>${escapeHtml(text)}</b></div>`;
}

function renderWorkerMemoBox(worker) {
  const memo = String(worker?.memo || worker?.note || worker?.remark || '').trim();
  return `
    <section class="worker-info-memo-box" aria-label="메모장">
      <span>메모장</span>
      <p>${escapeHtml(memo || '등록된 메모 없음')}</p>
    </section>
  `;
}

function showHomeWorkerInfo(workerId) {
  const worker = getWorkerById(workerId);
  if (!worker) return;
  const modal = $('#homeWorkerInfoModal');
  const title = $('#homeWorkerInfoTitle');
  const body = $('#homeWorkerInfoBody');
  if (!modal || !title || !body) return;
  const phoneText = String(worker.phone || '').trim();
  const phoneDigits = getCallablePhone(phoneText);
  const phoneBlock = phoneDigits
    ? `<a class="worker-info-phone" href="tel:${escapeHtml(phoneDigits)}" aria-label="${escapeHtml(phoneText)} 전화 연결"><span>전화번호</span><strong>${escapeHtml(phoneText)}</strong><small>눌러서 전화 연결</small></a>`
    : `<div class="worker-info-phone disabled"><span>전화번호</span><strong>등록된 번호 없음</strong><small>PC 또는 근로자 등록에서 연락처를 입력하세요.</small></div>`;
  title.textContent = worker.name || '근로자 정보';
  body.innerHTML = `
    ${phoneBlock}
    <div class="worker-info-grid">
      ${renderWorkerInfoLine('근무사업장', worker.site)}
      ${renderWorkerInfoLine('현재상태', worker.status)}
      ${renderWorkerInfoLine('국적', worker.nationality)}
      ${renderWorkerInfoLine('성별', worker.gender)}
    </div>
    ${renderWorkerMemoBox(worker)}
  `;
  modal.hidden = false;
  modal.querySelector('#homeWorkerInfoClose')?.focus({ preventScroll: true });
}

function hideHomeWorkerInfo() {
  const modal = $('#homeWorkerInfoModal');
  if (modal) modal.hidden = true;
}

function toast(message) {
  const el = $('#toast');
  el.textContent = message;
  el.classList.add('show');
  clearTimeout(window.__toastTimer);
  window.__toastTimer = setTimeout(() => el.classList.remove('show'), 1800);
}

function showScreen(id) {
  $$('.screen').forEach(screen => screen.classList.toggle('active', screen.id === id));
  $$('.bottom-nav button').forEach(btn => btn.classList.toggle('active', btn.dataset.nav === id));
  const active = $('#' + id);
  $('#pageTitle').textContent = active.dataset.title || '홈';
  const shell = $('.app-shell');
  const content = $('.app-content');
  shell.classList.toggle('home-mode', id === 'homeScreen');
  shell.classList.toggle('attendance-mode', id === 'attendanceScreen');
  content.scrollTop = 0;
  if (currentUser && ['homeScreen', 'attendanceScreen', 'workerScreen'].includes(id)) {
    loadServerEmployees();
  }
  if (id === 'vehicleScreen') {
    renderVehicleScreen();
    loadServerVehicles();
  }
}

function updateWorkers() {
  const workers = getScopedAttendanceWorkersBase();
  const list = $('#workerList');
  const count = $('#workerCount');
  if (!list || !count) return;
  count.textContent = `${workers.length}명`;
  if (employeeServerLoading && !attendanceWorkers.length) {
    list.className = 'list-empty';
    list.textContent = '서버 근로자 목록을 불러오는 중입니다.';
    return;
  }
  if (employeeServerLastError && !attendanceWorkers.length) {
    list.className = 'list-empty';
    list.textContent = '서버 근로자 목록을 불러오지 못했습니다. 동기화 상태를 확인하세요.';
    return;
  }
  if (!workers.length) {
    list.className = 'list-empty';
    list.textContent = '서버 기준으로 표시할 근로자가 없습니다.';
    return;
  }
  list.className = '';
  const visibleWorkers = isSuperUser() ? workers : workers.slice(0, 8);
  list.innerHTML = visibleWorkers.map(worker => `
    <article class="worker-item">
      <div><b>${escapeHtml(worker.name)}</b><small>${escapeHtml(worker.site)} · ${escapeHtml(worker.phone || worker.nationality || worker.type)}</small></div>
      <span class="pill success">${escapeHtml(worker.status || '근무중')}</span>
    </article>
  `).join('');
}

function updateSync() {
  const pending = Number(store.get('pendingCount', 0) || 0);
  const failCount = Number(store.get('syncFailCount', 0) || 0);
  const lastSync = store.get('lastSync', formatDateTime(APP_TODAY));
  const syncState = store.get('syncState', 'success');
  const selectedMonth = getSelectedMonth();
  const serverSavedCount = Number(store.get(`serverSavedCount_${selectedMonth}`, store.get('serverSavedCount', 0)) || 0);

  const pendingEl = $('#pendingCount');
  if (pendingEl) pendingEl.textContent = pending;

  const lastSyncEl = $('#lastSyncFull');
  if (lastSyncEl) lastSyncEl.textContent = lastSync;

  const serverCountEl = $('#serverSavedCount');
  if (serverCountEl) serverCountEl.textContent = serverSavedCount;

  const serverMonthEl = $('#serverSavedMonth');
  if (serverMonthEl) serverMonthEl.textContent = `${selectedMonth} 서버 저장`;

  const failCountEl = $('#syncFailCount');
  if (failCountEl) failCountEl.textContent = failCount;

  const autoSyncText = $('#autoSyncStatusText');
  if (autoSyncText) {
    autoSyncText.textContent = serverConnection.online
      ? (failCount > 0 ? '확인 필요' : '자동 저장 중')
      : '오프라인';
  }

  const autoSyncPill = $('#autoSyncStatusPill');
  if (autoSyncPill) {
    autoSyncPill.textContent = serverConnection.online ? '자동' : '오프라인';
    autoSyncPill.classList.toggle('success', serverConnection.online && failCount === 0);
    autoSyncPill.classList.toggle('warn', !serverConnection.online || failCount > 0);
  }

  const pendingPill = $('#pendingStatusPill');
  if (pendingPill) {
    pendingPill.textContent = pending > 0 ? '대기' : '없음';
    pendingPill.classList.toggle('warn', pending > 0);
    pendingPill.classList.toggle('success', pending <= 0);
  }

  const failPill = $('#syncFailStatusPill');
  if (failPill) {
    failPill.textContent = failCount > 0 ? '확인' : '정상';
    failPill.classList.toggle('warn', failCount > 0);
    failPill.classList.toggle('success', failCount <= 0);
  }

  const history = store.get('syncHistory', []);
  const historyEl = $('#syncHistory');
  if (historyEl) {
    historyEl.innerHTML = history.map(item => `
      <article><span>${item.time}</span><b class="${item.status === '실패' ? 'fail' : ''}">${item.status}</b><span>${item.text}</span></article>
    `).join('');
  }

  const syncNav = $('.bottom-nav .nav-sync');
  if (syncNav) {
    syncNav.classList.remove('sync-success', 'sync-fail', 'sync-warning', 'has-pending');
    if (syncState === 'fail' || failCount > 0) syncNav.classList.add('sync-fail');
    else if (syncState === 'warning' || pending > 0) syncNav.classList.add('sync-warning');
    else syncNav.classList.add('sync-success');
    if (pending > 0) syncNav.classList.add('has-pending');
    syncNav.setAttribute('aria-label', (syncState === 'fail' || failCount > 0) ? '동기화 상태 실패' : '동기화 상태 정상');
  }
}

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"]/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[char]));
}

function formatPhoneNumber(value) {
  const digits = String(value || '').replace(/\D/g, '').slice(0, 11);
  if (digits.length <= 3) return digits;
  if (digits.length <= 7) return `${digits.slice(0, 3)}-${digits.slice(3)}`;
  return `${digits.slice(0, 3)}-${digits.slice(3, 7)}-${digits.slice(7)}`;
}

function bindWorkerPhoneAutoHyphen() {
  const phone = $('#workerPhone');
  if (!phone) return;
  phone.addEventListener('input', () => {
    phone.value = formatPhoneNumber(phone.value);
  });
}

let attendanceWorkers = [];
let employeeServerLoading = false;
let employeeServerLoaded = false;
let employeeServerLastError = '';
let employeeServerCheckedAt = 0;
const EMPLOYEE_REFRESH_MS = 60000;

function clearLegacyMobileLocalData() {
  if (store.get('mobileServerEmployeeModeVersion', 0) === 46) return;
  store.remove('workers');
  store.remove('attendanceRecords');
  store.set('pendingCount', 0);
  store.set('syncFailCount', 0);
  store.set('serverSavedCount', 0);
  store.set(`serverSavedCount_${APP_TODAY_MONTH}`, 0);
  store.set('syncState', 'success');
  store.set('syncHistory', []);
  store.set('mobileServerEmployeeModeVersion', 46);
}

function firstNonEmpty(...values) {
  for (const value of values) {
    if (value === 0) return '0';
    const text = String(value ?? '').trim();
    if (text) return text;
  }
  return '';
}

function normalizeEmployeeForMobile(row = {}, index = 0) {
  if (!row || typeof row !== 'object') return null;
  const id = firstNonEmpty(
    row.id,
    row.employee_id,
    row.employeeId,
    row.worker_id,
    row.workerId,
    row.staff_id,
    row.staffId,
    row.code,
    row.employee_no,
    row.employeeNumber
  ) || String(index + 1);
  const name = firstNonEmpty(row.name, row.employee_name, row.worker_name, row.korean_name, row.english_name, row.full_name);
  if (!name) return null;
  const status = firstNonEmpty(row.status, row.employee_status, row.state) || '근무중';
  if (status === '퇴사' || row.active === false || row.is_deleted === true) return null;
  const business = firstNonEmpty(row.affiliated_business, row.business, row.business_name, row.company, row.company_name, row.companyName);
  const site = firstNonEmpty(row.work_site, row.site, row.site_name, row.worksite, row.workSite, row.department, row.factory);
  const type = firstNonEmpty(row.work_type, row.type, row.workType, row.shift, row.work_shift, row.work_time) || '근무형태 미지정';
  return {
    id: String(id),
    name,
    business: business || '사업자 미지정',
    site: site || '근무사업장 미지정',
    type,
    phone: firstNonEmpty(row.phone, row.contact, row.mobile, row.tel, row.telephone, row.contact_phone, row.contactPhone, row.mobile_phone, row.mobilePhone),
    nationality: firstNonEmpty(row.nationality, row.nation, row.country),
    gender: firstNonEmpty(row.gender, row.sex),
    memo: firstNonEmpty(row.memo, row.note, row.remark, row.remarks),
    status,
    raw: row
  };
}

function extractEmployeeRowsFromResponse(data) {
  if (Array.isArray(data)) return data;
  if (!data || typeof data !== 'object') return [];
  const candidates = [
    data.employees,
    data.records,
    data.items,
    data.rows,
    data.data,
    data.data?.employees,
    data.data?.records,
    data.snapshot?.employees,
    data.app?.employees
  ];
  for (const candidate of candidates) {
    if (Array.isArray(candidate)) return candidate;
  }
  return [];
}

function sortAttendanceWorkersForDisplay(workers = []) {
  return [...workers].sort((a, b) => {
    const keyA = [a.business || '', a.site || '', a.name || '', a.id || ''].map(value => String(value).trim().toLocaleLowerCase('ko-KR'));
    const keyB = [b.business || '', b.site || '', b.name || '', b.id || ''].map(value => String(value).trim().toLocaleLowerCase('ko-KR'));
    for (let index = 0; index < keyA.length; index += 1) {
      const compared = keyA[index].localeCompare(keyB[index], 'ko-KR', { numeric: true, sensitivity: 'base' });
      if (compared !== 0) return compared;
    }
    return 0;
  });
}

function applyServerEmployees(rows = []) {
  const normalized = rows
    .map((row, index) => normalizeEmployeeForMobile(row, index))
    .filter(Boolean);
  const seen = new Set();
  attendanceWorkers = sortAttendanceWorkersForDisplay(normalized.filter(worker => {
    if (seen.has(worker.id)) return false;
    seen.add(worker.id);
    return true;
  }));
  pruneAttendanceRecordsToServerWorkers();
  configurePermissionOptions();
  renderHomeWorkers(currentHomeStatus);
  updateWorkers();
  if ($('#attendanceScreen')?.classList.contains('active')) renderAttendanceViews();
}

function pruneAttendanceRecordsToServerWorkers() {
  const validIds = new Set(attendanceWorkers.map(worker => worker.id));
  const records = getAttendanceStorage();
  if (!records || typeof records !== 'object') return;
  const next = {};
  Object.entries(records).forEach(([key, value]) => {
    const workerId = String(key).split('|')[0];
    if (validIds.has(workerId)) next[key] = value;
  });
  setAttendanceStorage(next);
}

async function loadServerEmployees(options = {}) {
  const { force = false } = options;
  if (!serverConnection.online || !currentUser) return attendanceWorkers;
  if (employeeServerLoading) return attendanceWorkers;
  if (!force && employeeServerLoaded && Date.now() - employeeServerCheckedAt < EMPLOYEE_REFRESH_MS) return attendanceWorkers;
  employeeServerLoading = true;
  employeeServerLastError = '';
  renderHomeWorkers(currentHomeStatus);
  updateWorkers();
  try {
    const { data } = await fetchJson(`${API_BASE}/employees?ts=${Date.now()}`, { headers: getAuthHeaders() });
    const rows = extractEmployeeRowsFromResponse(data);
    employeeServerLoaded = true;
    employeeServerCheckedAt = Date.now();
    employeeServerLastError = '';
    applyServerEmployees(rows);
    await refreshAttendanceMonthRecords(getSelectedMonth(), { forceRender: true });
    if (APP_TODAY_MONTH !== getSelectedMonth()) await refreshAttendanceMonthRecords(APP_TODAY_MONTH, { forceRender: true });
    toast(`서버 근로자 ${attendanceWorkers.length}명을 불러왔습니다.`);
  } catch (error) {
    employeeServerLoaded = false;
    employeeServerLastError = error?.message || '서버 근로자 목록 불러오기 실패';
    attendanceWorkers = [];
    configurePermissionOptions();
    renderHomeWorkers(currentHomeStatus);
    updateWorkers();
    console.warn('employee list load failed', error);
  } finally {
    employeeServerLoading = false;
    renderHomeWorkers(currentHomeStatus);
    updateWorkers();
  }
  return attendanceWorkers;
}

let currentAttendanceTab = 'today';
let selectedStatusFilter = 'present';
let selectedAttendanceDate = APP_TODAY_DATE;
let currentAttendanceMonth = APP_TODAY_MONTH;
const ATTENDANCE_EDIT_DEADLINE_DAY = 10;
const ATTENDANCE_LOCK_REFRESH_MS = 30000;
const ATTENDANCE_RECORD_REFRESH_MS = 20000;
const attendanceMonthLockCache = new Map();
const attendanceMonthLockRequests = new Map();
const attendanceMonthRecordCache = new Map();
const attendanceMonthRecordRequests = new Map();
const ATTENDANCE_SAVE_DEDUPE_MS = 2500;
const ATTENDANCE_RETRY_QUEUE_KEY = 'attendanceRetryQueue';
const ATTENDANCE_RETRY_MAX_ATTEMPTS = 20;
const attendanceSaveInFlightByCell = new Map();
const attendanceSaveInFlightBySignature = new Map();
const attendanceSaveRecentSignatures = new Map();
let attendanceRetryQueueProcessing = false;

function getAttendanceCellSaveKey(workerId, dateKey) {
  return `${String(workerId || '').trim()}|${String(dateKey || '').trim()}`;
}

function getAttendanceSaveSignatureFromPayload(payload) {
  return [
    String(payload?.worker_id || '').trim(),
    String(payload?.date || payload?.attendance_date || '').trim(),
    String(payload?.state || '').trim()
  ].join('|');
}

function pruneRecentAttendanceSaveSignatures(now = Date.now()) {
  attendanceSaveRecentSignatures.forEach((savedAt, signature) => {
    if (!savedAt || now - savedAt > ATTENDANCE_SAVE_DEDUPE_MS) attendanceSaveRecentSignatures.delete(signature);
  });
}

function isRecentAttendanceSaveDuplicate(signature) {
  if (!signature || signature.split('|').some(part => !part)) return false;
  const now = Date.now();
  pruneRecentAttendanceSaveSignatures(now);
  const savedAt = attendanceSaveRecentSignatures.get(signature);
  return !!savedAt && now - savedAt <= ATTENDANCE_SAVE_DEDUPE_MS;
}

function markRecentAttendanceSave(signature) {
  if (!signature || signature.split('|').some(part => !part)) return;
  attendanceSaveRecentSignatures.set(signature, Date.now());
  pruneRecentAttendanceSaveSignatures();
}

function getAttendanceRetryQueue() {
  const queue = store.get(ATTENDANCE_RETRY_QUEUE_KEY, []);
  return Array.isArray(queue)
    ? queue.filter(item => item?.payload?.worker_id && item?.payload?.date)
    : [];
}

function getAttendanceRetryKeyFromPayload(payload = {}) {
  return [
    String(payload.worker_id || '').trim(),
    String(payload.date || payload.attendance_date || '').trim()
  ].join('|');
}

function saveAttendanceRetryQueue(queue = []) {
  const cleanQueue = Array.isArray(queue)
    ? queue.filter(item => item?.payload?.worker_id && item?.payload?.date)
    : [];
  store.set(ATTENDANCE_RETRY_QUEUE_KEY, cleanQueue);
  store.set('pendingCount', cleanQueue.length);
  updateSync();
  return cleanQueue;
}

function queueAttendanceRetryPayload(payload, reason = 'attendance save retry') {
  const retryKey = getAttendanceRetryKeyFromPayload(payload);
  if (!retryKey || retryKey.includes('||')) return null;
  const nowText = new Date().toISOString();
  const queue = getAttendanceRetryQueue();
  const index = queue.findIndex(item => item.key === retryKey);
  const nextEntry = {
    key: retryKey,
    queuedAt: index >= 0 ? queue[index].queuedAt : nowText,
    updatedAt: nowText,
    attempts: index >= 0 ? Number(queue[index].attempts || 0) : 0,
    lastError: reason,
    payload: { ...payload }
  };
  if (index >= 0) queue[index] = nextEntry;
  else queue.push(nextEntry);
  saveAttendanceRetryQueue(queue);
  return nextEntry;
}

function removeAttendanceRetryPayload(payload) {
  const retryKey = getAttendanceRetryKeyFromPayload(payload);
  if (!retryKey) return;
  saveAttendanceRetryQueue(getAttendanceRetryQueue().filter(item => item.key !== retryKey));
}

function isTemporaryAttendanceSaveError(error) {
  const status = error?.response?.status;
  if (!status) return true;
  return status === 408 || status === 429 || status === 500 || status === 502 || status === 503 || status === 504;
}

function isPermanentAttendanceSaveError(error) {
  const status = error?.response?.status;
  return status === 400 || status === 403 || status === 422 || status === 423;
}

async function postAttendanceSavePayload(payload) {
  return fetchJson(`${API_BASE}/attendance/save`, {
    method: 'POST',
    headers: getAuthHeaders(),
    body: JSON.stringify(payload)
  });
}

async function processAttendanceRetryQueue(options = {}) {
  if (attendanceRetryQueueProcessing) return { ok: false, busy: true };
  const initialQueue = getAttendanceRetryQueue();
  if (!initialQueue.length) {
    saveAttendanceRetryQueue([]);
    return { ok: true, sent: 0, pending: 0 };
  }
  if (!serverConnection.online) {
    saveAttendanceRetryQueue(initialQueue);
    return { ok: false, offline: true, pending: initialQueue.length };
  }
  if (!getStoredAuthToken()) {
    saveAttendanceRetryQueue(initialQueue);
    return { ok: false, auth: true, pending: initialQueue.length };
  }

  attendanceRetryQueueProcessing = true;
  let sent = 0;
  let blocked = 0;
  const remaining = [];
  const refreshedMonths = new Set();
  try {
    for (const item of initialQueue) {
      const payload = item.payload || {};
      try {
        const { data } = await postAttendanceSavePayload(payload);
        if (data?.lock) updateAttendanceLockCacheFromServer(payload.year_month || getMonthFromDateKey(payload.date), data.lock);
        if (data?.record) mergeServerAttendanceRecords([data.record]);
        if (payload.year_month) refreshedMonths.add(payload.year_month);
        markRecentAttendanceSave(getAttendanceSaveSignatureFromPayload(payload));
        sent += 1;
      } catch (error) {
        if (isPermanentAttendanceSaveError(error)) {
          blocked += 1;
          console.warn('attendance retry removed by permanent error', { error, payload, serverData: error?.data });
          continue;
        }
        const attempts = Number(item.attempts || 0) + 1;
        if (attempts >= ATTENDANCE_RETRY_MAX_ATTEMPTS) {
          blocked += 1;
          console.warn('attendance retry removed after max attempts', { payload, attempts, error });
          continue;
        }
        remaining.push({
          ...item,
          attempts,
          updatedAt: new Date().toISOString(),
          lastError: error?.message || 'retry failed'
        });
      }
    }
  } finally {
    attendanceRetryQueueProcessing = false;
  }

  saveAttendanceRetryQueue(remaining);
  for (const monthValue of refreshedMonths) {
    await refreshAttendanceMonthRecords(monthValue, { forceRender: monthValue === getSelectedMonth() });
  }
  if (sent > 0) {
    markAttendanceSyncSuccess(`임시 근태 ${sent}건 서버 재전송 완료`);
    if (!options.silent) toast(`임시 근태 ${sent}건을 서버에 다시 저장했습니다.`);
  }
  if (remaining.length > 0) {
    markAttendanceSyncFailure(`임시 근태 ${remaining.length}건 재전송 대기`);
    saveAttendanceRetryQueue(remaining);
  } else if (blocked > 0 && sent === 0) {
    markAttendanceSyncFailure(`임시 근태 ${blocked}건은 서버에서 거부되어 제외됨`);
    saveAttendanceRetryQueue([]);
  }
  return { ok: remaining.length === 0, sent, pending: remaining.length, blocked };
}

window.addEventListener('online', () => {
  initializeServerConnection()
    .then(() => processAttendanceRetryQueue({ reason: 'online' }))
    .catch(() => {});
});

function loadStoredAttendanceMonthLocks() {
  const stored = store.get('serverAttendanceMonthLocks', {});
  Object.entries(stored || {}).forEach(([monthValue, info]) => {
    if (monthValue && info) attendanceMonthLockCache.set(monthValue, info);
  });
}

function saveStoredAttendanceMonthLocks() {
  const next = {};
  attendanceMonthLockCache.forEach((info, monthValue) => {
    if (monthValue && info) next[monthValue] = info;
  });
  store.set('serverAttendanceMonthLocks', next);
}

function normalizeAttendanceLockInfo(data = {}, monthValue = '') {
  const raw = data.detail && typeof data.detail === 'object' ? data.detail : data;
  return {
    locked: raw?.locked === true,
    editable: raw?.editable !== false,
    expired: raw?.expired === true,
    reason: raw?.reason || '',
    message: raw?.message || (raw?.locked ? '이 월은 PC에서 마감되어 수정할 수 없습니다.' : ''),
    editable_until: raw?.editable_until || '',
    server_date: raw?.server_date || '',
    checkedAt: Date.now()
  };
}

function updateAttendanceLockCacheFromServer(monthValue, data = {}) {
  if (!monthValue) return null;
  const info = normalizeAttendanceLockInfo(data, monthValue);
  attendanceMonthLockCache.set(monthValue, info);
  saveStoredAttendanceMonthLocks();
  if (monthValue === getSelectedMonth()) updateAttendanceLockUI();
  return info;
}

loadStoredAttendanceMonthLocks();

function getSelectedMonth() { return currentAttendanceMonth || APP_TODAY_MONTH; }
function updateAttendanceMonthDisplay(value = getSelectedMonth()) {
  const [year, month] = value.split('-').map(Number);
  const text = `${year}년 ${pad2(month)}월`;
  const el = $('#filterMonthText');
  if (el) el.textContent = text;
}
function setSelectedMonth(value) {
  currentAttendanceMonth = value;
  updateAttendanceMonthDisplay(value);
}
function getDaysInMonth(monthValue = getSelectedMonth()) {
  const [year, month] = monthValue.split('-').map(Number);
  return new Date(year, month, 0).getDate();
}
function getDateKey(day, monthValue = getSelectedMonth()) { return `${monthValue}-${pad2(day)}`; }
function getKoreanDayName(dateKey) {
  return ['일', '월', '화', '수', '목', '금', '토'][new Date(dateKey + 'T00:00:00').getDay()];
}
function updateCurrentDateLabels() {
  const [year, month, day] = APP_TODAY_DATE.split('-').map(Number);
  const homeDate = $('#homeDateLabel');
  if (homeDate) homeDate.textContent = `${month}월 ${day}일 (${getKoreanDayName(APP_TODAY_DATE)})`;
  updateAttendanceMonthDisplay(APP_TODAY_MONTH);
}
function isHolidayDate(dateKey) { return new Date(dateKey + 'T00:00:00').getDay() === 0; }
function getMonthFromDateKey(dateKey) { return String(dateKey || '').slice(0, 7); }
function getPcClosedAttendanceMonths() { return store.get('pcClosedAttendanceMonths', []); }

function getLocalAttendanceDeadline(monthValue) {
  const [year, month] = String(monthValue || '').split('-').map(Number);
  if (!year || !month) return null;
  return new Date(year, month, ATTENDANCE_EDIT_DEADLINE_DAY, 23, 59, 59, 999);
}

function getAttendanceMonthLockInfo(monthValue = getSelectedMonth()) {
  if (!monthValue) return { locked: false, editable: true, reason: 'editable', message: '수정 가능' };
  const serverInfo = attendanceMonthLockCache.get(monthValue);
  if (serverInfo?.locked === true) {
    return {
      locked: true,
      editable: false,
      reason: serverInfo.reason || 'pc_locked',
      message: serverInfo.message || '이 월은 PC에서 마감되어 수정할 수 없습니다.',
      source: 'server',
      checkedAt: serverInfo.checkedAt
    };
  }
  if (serverInfo?.editable === false) {
    return {
      locked: true,
      editable: false,
      reason: serverInfo.reason || (serverInfo.expired ? 'expired' : 'server_locked'),
      message: serverInfo.message || '이 월은 수정할 수 없습니다.',
      source: 'server',
      checkedAt: serverInfo.checkedAt
    };
  }
  if (getPcClosedAttendanceMonths().includes(monthValue)) {
    return { locked: true, editable: false, reason: 'local_pc_locked', message: '이 월은 PC에서 마감되어 수정할 수 없습니다.', source: 'local' };
  }
  const deadline = getLocalAttendanceDeadline(monthValue);
  if (deadline && APP_TODAY > deadline) {
    return {
      locked: true,
      editable: false,
      reason: 'expired',
      message: '해당 월 근태는 다음 달 10일까지 수정 가능합니다.',
      source: 'local'
    };
  }
  return {
    locked: false,
    editable: true,
    reason: serverInfo?.reason || 'editable',
    message: serverInfo?.message || '수정 가능',
    source: serverInfo ? 'server' : 'local',
    checkedAt: serverInfo?.checkedAt
  };
}

function isAttendanceMonthLocked(monthValue = getSelectedMonth()) {
  return getAttendanceMonthLockInfo(monthValue).locked === true;
}
function isAttendanceDateLocked(dateKey) { return isAttendanceMonthLocked(getMonthFromDateKey(dateKey)); }
function getAttendanceLockMessage(monthValue = getSelectedMonth()) {
  return getAttendanceMonthLockInfo(monthValue).message || '이 월은 PC에서 마감되어 수정할 수 없습니다.';
}
async function refreshAttendanceMonthLockStatus(monthValue = getSelectedMonth()) {
  if (!monthValue || !serverConnection.online) return null;
  if (attendanceMonthLockRequests.has(monthValue)) return attendanceMonthLockRequests.get(monthValue);
  const request = fetchJson(`${API_BASE}/attendance/month-lock-status?year_month=${encodeURIComponent(monthValue)}&ts=${Date.now()}`, {
    headers: getAuthHeaders()
  })
    .then(({ data }) => updateAttendanceLockCacheFromServer(monthValue, data))
    .catch(error => {
      if (!isMissingApiError(error)) console.warn('attendance month lock check failed', error);
      return null;
    })
    .finally(() => attendanceMonthLockRequests.delete(monthValue));
  attendanceMonthLockRequests.set(monthValue, request);
  return request;
}
function ensureAttendanceMonthLockStatus(monthValue = getSelectedMonth()) {
  if (!serverConnection.online || !monthValue) return;
  const cached = attendanceMonthLockCache.get(monthValue);
  const stale = !cached?.checkedAt || Date.now() - cached.checkedAt > ATTENDANCE_LOCK_REFRESH_MS;
  if (stale) refreshAttendanceMonthLockStatus(monthValue);
}
function showAttendanceLockPopup(message = getAttendanceLockMessage()) {
  const modal = $('#attendanceLockModal');
  if (!modal) return toast(message);
  const text = modal.querySelector('.modal-card p');
  if (text) text.textContent = message;
  modal.hidden = false;
  modal.classList.add('show');
  $('#attendanceLockModalOk')?.focus();
}
function hideAttendanceLockPopup() {
  const modal = $('#attendanceLockModal');
  if (!modal) return;
  modal.classList.remove('show');
  modal.hidden = true;
}

function showShortcutGuide() {
  const modal = $('#shortcutGuideModal');
  if (!modal) return toast('바로가기 추가 안내를 확인할 수 없습니다.');
  updateShortcutButtonState();
  modal.hidden = false;
  modal.classList.add('show');
  $('#shortcutGuideClose')?.focus();
}
async function handleShortcutInstallRequest() {
  if (isStandaloneMode()) {
    toast('이미 앱처럼 실행 중입니다.');
    showShortcutGuide();
    return;
  }

  // 자동 설치창이 안 뜨는 환경에서도 안내창이 먼저 보이도록 한다.
  showShortcutGuide();

  if (deferredInstallPrompt) {
    const promptEvent = deferredInstallPrompt;
    deferredInstallPrompt = null;
    try {
      promptEvent.prompt();
      const choice = await promptEvent.userChoice;
      updateShortcutButtonState();
      if (choice?.outcome === 'accepted') {
        toast('추가가 진행되었습니다. 바탕화면 아이콘으로 실행하세요.');
        return;
      }
    } catch {}
  } else {
    toast('오른쪽 위 메뉴에서 홈 화면에 추가를 눌러주세요.');
  }
}

async function copyShortcutLink() {
  const url = `${window.location.origin}/mobile-live/`;
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(url);
      toast('주소를 복사했습니다.');
      return;
    }
  } catch {}
  toast(url);
}
function hideShortcutGuide() {
  const modal = $('#shortcutGuideModal');
  if (!modal) return;
  modal.classList.remove('show');
  modal.hidden = true;
}
function updateAttendanceLockUI() {
  const monthValue = getSelectedMonth();
  const lockInfo = getAttendanceMonthLockInfo(monthValue);
  const locked = lockInfo.locked === true;
  const notice = $('#attendanceLockNotice');
  const screen = $('#attendanceScreen');
  if (screen) screen.classList.toggle('locked-month', locked);
  if (notice) {
    notice.hidden = !locked;
    notice.textContent = locked ? lockInfo.message : '';
  }
  $$('#quickStatus button[data-state]').forEach(btn => {
    btn.classList.toggle('locked', locked);
    btn.setAttribute('aria-disabled', locked ? 'true' : 'false');
  });
}
function monthLabel(monthValue = getSelectedMonth()) {
  const [year, month] = monthValue.split('-').map(Number);
  return `${year}년 ${month}월`;
}
function changeMonth(delta) {
  const [year, month] = getSelectedMonth().split('-').map(Number);
  const next = new Date(year, month - 1 + delta, 1);
  const nextMonth = `${next.getFullYear()}-${pad2(next.getMonth() + 1)}`;
  setSelectedMonth(nextMonth);
  refreshAttendanceMonthLockStatus(nextMonth);
  refreshAttendanceMonthRecords(nextMonth);
  selectedAttendanceDate = getDateKey(Math.min(Number(selectedAttendanceDate.slice(-2)) || 1, getDaysInMonth(nextMonth)), nextMonth);
  renderAttendanceViews();
}
function changeTodayDate(delta) {
  const current = new Date(selectedAttendanceDate + 'T00:00:00');
  current.setDate(current.getDate() + delta);
  const nextMonth = `${current.getFullYear()}-${pad2(current.getMonth() + 1)}`;
  setSelectedMonth(nextMonth);
  refreshAttendanceMonthLockStatus(nextMonth);
  refreshAttendanceMonthRecords(nextMonth);
  selectedAttendanceDate = `${nextMonth}-${pad2(current.getDate())}`;
  renderAttendanceViews();
}
function getFilteredAttendanceWorkers() {
  const workers = getScopedAttendanceWorkersBase();
  if (isSuperUser()) return workers;
  const site = $('#attSiteFilter')?.value || '전체';
  return workers.filter(worker => {
    const siteOk = site === '전체' || worker.site === site;
    return siteOk;
  });
}
function seedAttendanceState(workerId, dateKey) {
  return 'empty';
}
function getAttendanceStorage() { return store.get('attendanceRecords', {}); }
function setAttendanceStorage(records) { store.set('attendanceRecords', records); }
function getAttendanceState(workerId, dateKey) {
  const records = getAttendanceStorage();
  const key = `${workerId}|${dateKey}`;
  return records[key] || seedAttendanceState(workerId, dateKey);
}
function saveAttendanceState(workerId, dateKey, state) {
  const records = getAttendanceStorage();
  records[`${workerId}|${dateKey}`] = state;
  setAttendanceStorage(records);
}

function getAttendanceWorker(workerId) {
  return attendanceWorkers.find(worker => worker.id === workerId) || null;
}

function mergeServerAttendanceRecords(records = []) {
  if (!Array.isArray(records) || !records.length) return false;
  const localRecords = getAttendanceStorage();
  const allowedWorkerIds = new Set(getScopedAttendanceWorkersBase().map(worker => String(worker.id)));
  let changed = false;
  records.forEach(record => {
    const workerId = String(record.worker_id || record.workerId || record.employee_id || record.employeeId || record.id || '').trim();
    const dateKey = record.attendance_date || record.date;
    const state = record.state || 'empty';
    if (!workerId || !dateKey || (allowedWorkerIds.size && !allowedWorkerIds.has(workerId))) return;
    localRecords[`${workerId}|${dateKey}`] = attendanceStateMeta[state] ? state : String(state || 'empty');
    changed = true;
  });
  if (changed) setAttendanceStorage(localRecords);
  return changed;
}

function replaceServerAttendanceRecordsForMonth(monthValue, records = []) {
  if (!monthValue) return false;
  const localRecords = getAttendanceStorage();
  const allowedWorkerIds = new Set(getScopedAttendanceWorkersBase().map(worker => String(worker.id)));
  Object.keys(localRecords).forEach(key => {
    const [workerId, dateKey = ''] = String(key).split('|');
    if (dateKey.startsWith(monthValue) && (!allowedWorkerIds.size || allowedWorkerIds.has(String(workerId)))) delete localRecords[key];
  });
  let changed = false;
  (Array.isArray(records) ? records : []).forEach(record => {
    const workerId = String(record.worker_id || record.workerId || record.employee_id || record.employeeId || record.id || '').trim();
    const dateKey = record.attendance_date || record.date;
    const state = record.state || 'empty';
    if (!workerId || !dateKey || !String(dateKey).startsWith(monthValue) || (allowedWorkerIds.size && !allowedWorkerIds.has(workerId))) return;
    localRecords[`${workerId}|${dateKey}`] = attendanceStateMeta[state] ? state : String(state || 'empty');
    changed = true;
  });
  setAttendanceStorage(localRecords);
  return changed;
}

function markAttendanceSyncSuccess(text = '근태 1건 저장') {
  const now = new Date();
  const stamp = `${now.getFullYear()}-${pad2(now.getMonth()+1)}-${pad2(now.getDate())} ${pad2(now.getHours())}:${pad2(now.getMinutes())}`;
  const history = store.get('syncHistory', []);
  history.unshift({ time: stamp, status: '정상', text });
  store.set('lastSync', stamp);
  store.set('syncFailCount', 0);
  store.set('syncState', 'success');
  store.set('syncHistory', history.slice(0, 6));
  updateSync();
}

function markAttendanceSyncFailure(text = '근태 서버 저장 실패') {
  const now = new Date();
  const stamp = `${now.getFullYear()}-${pad2(now.getMonth()+1)}-${pad2(now.getDate())} ${pad2(now.getHours())}:${pad2(now.getMinutes())}`;
  const history = store.get('syncHistory', []);
  history.unshift({ time: stamp, status: '실패', text });
  store.set('lastSync', stamp);
  store.set('pendingCount', store.get('pendingCount', 0) + 1);
  store.set('syncFailCount', store.get('syncFailCount', 0) + 1);
  store.set('syncState', 'warning');
  store.set('syncHistory', history.slice(0, 6));
  updateSync();
}

async function refreshAttendanceMonthRecords(monthValue = getSelectedMonth(), options = {}) {
  if (!monthValue || !serverConnection.online) return null;
  if (attendanceMonthRecordRequests.has(monthValue)) return attendanceMonthRecordRequests.get(monthValue);
  const params = new URLSearchParams({ year_month: monthValue, ts: String(Date.now()) });
  const request = fetchJson(`${API_BASE}/attendance/month?${params.toString()}`, { headers: getAuthHeaders() })
    .then(({ data }) => {
      const serverCount = Number(data?.count || 0);
      attendanceMonthRecordCache.set(monthValue, { checkedAt: Date.now(), count: serverCount });
      store.set('serverSavedCount', serverCount);
      store.set(`serverSavedCount_${monthValue}`, serverCount);
      if (data?.lock) updateAttendanceLockCacheFromServer(monthValue, data.lock);
      const changed = replaceServerAttendanceRecordsForMonth(monthValue, data?.records || []);
      if ((changed || options.forceRender) && monthValue === getSelectedMonth()) {
        renderAttendanceViews();
      }
      if (monthValue === APP_TODAY_MONTH) renderHomeWorkers(currentHomeStatus);
      return data;
    })
    .catch(error => {
      if (!isMissingApiError(error)) console.warn('attendance month records load failed', error);
      return null;
    })
    .finally(() => attendanceMonthRecordRequests.delete(monthValue));
  attendanceMonthRecordRequests.set(monthValue, request);
  return request;
}

function ensureAttendanceMonthRecords(monthValue = getSelectedMonth()) {
  if (!serverConnection.online || !monthValue) return;
  const cached = attendanceMonthRecordCache.get(monthValue);
  const stale = !cached?.checkedAt || Date.now() - cached.checkedAt > ATTENDANCE_RECORD_REFRESH_MS;
  if (stale) refreshAttendanceMonthRecords(monthValue);
}

function normalizeAttendanceStateForServer(state) {
  const value = String(state || '').trim();
  return attendanceStateMeta[value] ? value : 'empty';
}

function getWorkerServerId(worker, fallbackId) {
  return firstNonEmpty(
    worker?.raw?.id,
    worker?.raw?.employee_id,
    worker?.raw?.employeeId,
    worker?.raw?.worker_id,
    worker?.raw?.workerId,
    worker?.raw?.staff_id,
    worker?.raw?.staffId,
    worker?.raw?.code,
    worker?.raw?.employee_no,
    worker?.raw?.employeeNumber,
    worker?.id,
    fallbackId
  );
}

function buildAttendanceSavePayload(workerId, dateKey, state) {
  const worker = getAttendanceWorker(workerId) || {};
  const serverWorkerId = String(getWorkerServerId(worker, workerId) || '').trim();
  const normalizedDate = String(dateKey || '').trim();
  const payload = {
    worker_id: serverWorkerId,
    worker_name: String(worker.name || worker.raw?.name || worker.raw?.worker_name || worker.raw?.employee_name || '').trim(),
    business: String(worker.business || worker.raw?.affiliated_business || worker.raw?.business || worker.raw?.business_name || '').trim(),
    site: String(worker.site || worker.raw?.work_site || worker.raw?.site || worker.raw?.site_name || '').trim(),
    work_type: String(worker.type || worker.raw?.work_type || worker.raw?.workType || '').trim(),
    date: normalizedDate,
    attendance_date: normalizedDate,
    year_month: getMonthFromDateKey(normalizedDate),
    state: normalizeAttendanceStateForServer(state),
    source: 'mobile',
    updated_by: String(currentUser?.name || currentUser?.id || 'mobile').trim() || 'mobile'
  };
  window.__lastAttendanceSavePayload = payload;
  return payload;
}

function validateAttendanceSavePayload(payload) {
  const missing = [];
  ['worker_id', 'worker_name', 'date', 'year_month', 'state'].forEach(key => {
    if (!String(payload?.[key] ?? '').trim()) missing.push(key);
  });
  if (!/^\d{4}-\d{2}-\d{2}$/.test(String(payload?.date || ''))) missing.push('date format');
  if (!/^\d{4}-\d{2}$/.test(String(payload?.year_month || ''))) missing.push('year_month format');
  return missing;
}


async function saveAttendanceStateToServer(workerId, dateKey, state) {
  const monthValue = getMonthFromDateKey(dateKey);
  const worker = getAttendanceWorker(workerId);
  if (!userAllowsWorker(worker)) {
    toast('담당 근무사업장 밖의 근태는 저장할 수 없습니다.');
    return { ok: false, permission: true };
  }
  const payload = buildAttendanceSavePayload(workerId, dateKey, state);
  const missing = validateAttendanceSavePayload(payload);
  if (missing.length) {
    const message = `save payload missing: ${missing.join(', ')}`;
    markAttendanceSyncFailure(message);
    toast(message);
    console.warn('attendance save payload invalid', payload, missing);
    return { ok: false, validation: true, message };
  }
  if (!serverConnection.online) {
    try { await initializeServerConnection(); } catch {}
  }
  if (!serverConnection.online) {
    queueAttendanceRetryPayload(payload, 'server offline');
    markAttendanceSyncFailure('server offline - retry queued');
    saveAttendanceRetryQueue(getAttendanceRetryQueue());
    return { ok: false, offline: true, queued: true };
  }
  const signature = getAttendanceSaveSignatureFromPayload(payload);
  if (isRecentAttendanceSaveDuplicate(signature)) {
    console.info('attendance duplicate save skipped', payload);
    return { ok: true, duplicate: true, skippedDuplicate: true };
  }
  const runningRequest = attendanceSaveInFlightBySignature.get(signature);
  if (runningRequest) return runningRequest;

  const request = (async () => {
    try {
      const { data } = await postAttendanceSavePayload(payload);
      removeAttendanceRetryPayload(payload);
      if (data?.lock) updateAttendanceLockCacheFromServer(monthValue, data.lock);
      if (data?.record) mergeServerAttendanceRecords([data.record]);
      await refreshAttendanceMonthRecords(monthValue, { forceRender: true });
      markRecentAttendanceSave(signature);
      markAttendanceSyncSuccess('attendance saved to server');
      return { ok: true, data };
    } catch (error) {
      const status = error?.response?.status;
      if (status === 423) {
        updateAttendanceLockCacheFromServer(monthValue, error.data?.detail || error.data || { locked: true, editable: false, message: 'locked' });
        showAttendanceLockPopup(getAttendanceLockMessage(monthValue));
        removeAttendanceRetryPayload(payload);
        return { ok: false, locked: true, error };
      }
      let message = 'attendance server save failed';
      if (status === 422) {
        const detail = error?.data?.detail;
        const detailText = Array.isArray(detail)
          ? detail.map(item => `${(item.loc || []).join('.')}: ${item.msg}`).join(' / ')
          : (typeof detail === 'string' ? detail : JSON.stringify(detail || error?.data || {}));
        message = `save payload error${detailText ? `: ${detailText}` : ''}`;
      }
      if (isTemporaryAttendanceSaveError(error) || status === 401) {
        queueAttendanceRetryPayload(payload, message);
        markAttendanceSyncFailure(`${message} - retry queued`);
        saveAttendanceRetryQueue(getAttendanceRetryQueue());
        toast('서버 저장 실패: 임시 저장 후 자동 재전송 대기 중입니다.');
        console.warn('attendance save queued for retry', { error, payload, serverData: error?.data });
        return { ok: false, error, queued: true, validation: status === 422 };
      }
      removeAttendanceRetryPayload(payload);
      markAttendanceSyncFailure(message);
      toast(message.length > 80 ? message.slice(0, 80) + '…' : message);
      console.warn('attendance save failed', { error, payload, serverData: error?.data });
      return { ok: false, error, validation: status === 422 };
    }
  })().finally(() => {
    attendanceSaveInFlightBySignature.delete(signature);
  });

  attendanceSaveInFlightBySignature.set(signature, request);
  return request;
}


async function changeAttendanceState(workerId, dateKey, nextState, previousState, renderAfterLocal, successMessage) {
  const cellKey = getAttendanceCellSaveKey(workerId, dateKey);
  if (attendanceSaveInFlightByCell.has(cellKey)) {
    toast('이미 저장 중입니다. 잠시 후 다시 눌러주세요.');
    return;
  }
  attendanceSaveInFlightByCell.set(cellKey, Date.now());
  try {
    saveAttendanceState(workerId, dateKey, nextState);
    renderAfterLocal?.();
    const result = await saveAttendanceStateToServer(workerId, dateKey, nextState);
    if (result.locked) {
      saveAttendanceState(workerId, dateKey, previousState);
      renderAfterLocal?.();
      return;
    }
    if (result.ok) {
      if (!result.skippedDuplicate) toast(successMessage);
    } else if (result.queued) {
      toast('기기에 임시 저장했습니다. 연결되면 자동으로 서버에 다시 보냅니다.');
    } else {
      toast('기기에 임시 저장했습니다. 서버 연결을 확인해 주세요.');
    }
  } finally {
    attendanceSaveInFlightByCell.delete(cellKey);
  }
}

function renderAttendanceCell(td, state) {
  const nextState = attendanceStateMeta[state] ? state : 'empty';
  const meta = attendanceStateMeta[nextState];
  td.dataset.state = nextState;
  td.classList.remove('state-empty', 'state-present', 'state-absent', 'state-hospital', 'state-late', 'state-early', 'state-off', 'state-unauthorized');
  td.classList.add(meta.className, 'interactive');
  td.setAttribute('aria-label', meta.label);
  if (!meta.icon) {
    td.innerHTML = '<span class="cell-icon cell-empty" aria-hidden="true"></span>';
    return;
  }
  td.innerHTML = `<span class="cell-icon ${meta.className}" aria-hidden="true"><svg><use href="#${meta.icon}" /></svg></span>`;
}

function setAttendanceMode(state) {
  activeAttendanceMode = attendanceStateMeta[state] ? state : 'present';
  $$('#quickStatus button[data-state]').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.state === activeAttendanceMode);
  });
}

function setSelectedAttendanceCell(td) {
  if (selectedCell) selectedCell.classList.remove('selected');
  selectedCell = td;
  td.classList.add('selected');
}

async function applyAttendanceStateToCell(td, state) {
  const workerId = td.dataset.workerId;
  const dateKey = td.dataset.date;
  if (isAttendanceDateLocked(dateKey)) {
    showAttendanceLockPopup();
    return;
  }
  const current = td.dataset.state || 'empty';
  const nextState = current === state ? 'empty' : state;
  const label = attendanceStateMeta[nextState]?.label || '상태';
  await changeAttendanceState(
    workerId,
    dateKey,
    nextState,
    current,
    () => {
      renderAttendanceCell(td, getAttendanceState(workerId, dateKey));
      renderAttendanceSupplementPanels();
    },
    nextState === 'empty' ? '선택한 칸이 해제되어 서버에 저장되었습니다.' : `선택한 칸이 ${label}으로 서버 저장되었습니다.`
  );
}

function bindAttendanceCellEvents(root = document) {
  $$('.attendance-table td[data-worker-id]', root).forEach(td => {
    renderAttendanceCell(td, td.dataset.state || 'empty');
    td.addEventListener('click', () => {
      setSelectedAttendanceCell(td);
      applyAttendanceStateToCell(td, activeAttendanceMode || 'present');
    });
  });
}

function renderMonthTable() {
  const table = $('#attendanceTable');
  if (!table) return;
  const monthValue = getSelectedMonth();
  const days = getDaysInMonth(monthValue);
  const monthTitle = $('#monthTitle');
  if (monthTitle) monthTitle.textContent = monthLabel(monthValue);
  const todayKey = selectedAttendanceDate;
  const header = Array.from({ length: days }, (_, i) => {
    const day = i + 1;
    const dateKey = getDateKey(day, monthValue);
    const cls = [isHolidayDate(dateKey) ? 'holiday' : '', dateKey === todayKey ? 'today' : ''].filter(Boolean).join(' ');
    return `<th class="${cls}">${day}<br><small>${getKoreanDayName(dateKey)}</small></th>`;
  }).join('');
  table.querySelector('thead').innerHTML = `<tr><th>이름</th>${header}</tr>`;
  table.querySelector('tbody').innerHTML = getFilteredAttendanceWorkers().map(worker => {
    const cells = Array.from({ length: days }, (_, i) => {
      const day = i + 1;
      const dateKey = getDateKey(day, monthValue);
      const state = getAttendanceState(worker.id, dateKey);
      const cls = isHolidayDate(dateKey) ? 'holiday-cell' : '';
      return `<td class="${cls}" data-worker-id="${worker.id}" data-date="${dateKey}" data-state="${state}"></td>`;
    }).join('');
    return `<tr><th title="${escapeHtml(worker.name)}">${escapeHtml(worker.name)}</th>${cells}</tr>`;
  }).join('');
  bindAttendanceCellEvents(table);
}

function renderTodayPanel() {
  const list = $('#todayAttendanceList');
  if (!list) return;
  $('#todayTitle').textContent = `${selectedAttendanceDate.slice(5, 7)}월 ${Number(selectedAttendanceDate.slice(-2))}일 ${getKoreanDayName(selectedAttendanceDate)}요일`;
  const workers = getFilteredAttendanceWorkers();
  if (!workers.length) {
    list.innerHTML = '<div class="attendance-empty">선택한 사업자/근무사업장에 표시할 근로자가 없습니다.</div>';
    return;
  }
  list.innerHTML = workers.map(worker => {
    const state = getAttendanceState(worker.id, selectedAttendanceDate);
    const meta = attendanceStateMeta[state] || attendanceStateMeta.empty;
    const icon = meta.icon ? `<span class="cell-icon ${meta.className}"><svg><use href="#${meta.icon}" /></svg></span>` : '<span class="cell-icon cell-empty"></span>';
    return `<button class="attendance-list-row" type="button" data-worker-id="${worker.id}" data-date="${selectedAttendanceDate}">${icon}<b>${escapeHtml(worker.name)}</b><span>${escapeHtml(worker.site)}</span><span>${escapeHtml(worker.type)}</span><em class="state-pill ${state}">${meta.label}</em></button>`;
  }).join('');
  $$('.attendance-list-row[data-worker-id]', list).forEach(row => {
    row.addEventListener('click', async () => {
      const workerId = row.dataset.workerId;
      const dateKey = row.dataset.date;
      if (isAttendanceDateLocked(dateKey)) {
        showAttendanceLockPopup();
        return;
      }
      const current = getAttendanceState(workerId, dateKey);
      const nextState = current === activeAttendanceMode ? 'empty' : activeAttendanceMode;
      await changeAttendanceState(
        workerId,
        dateKey,
        nextState,
        current,
        renderAttendanceViews,
        nextState === 'empty' ? '선택한 근로자 근태가 해제되어 서버에 저장되었습니다.' : `${attendanceStateMeta[nextState].label}으로 서버 저장되었습니다.`
      );
    });
  });
}

function renderWorkerPanel() {
  const select = $('#attWorkerSelect');
  const summary = $('#workerAttendanceSummary');
  const table = $('#workerMonthTable');
  if (!select || !summary || !table) return;
  const workers = getFilteredAttendanceWorkers();
  if (!workers.length) {
    select.innerHTML = '';
    summary.innerHTML = '<div class="attendance-empty">표시할 근로자가 없습니다.</div>';
    table.querySelector('thead').innerHTML = '';
    table.querySelector('tbody').innerHTML = '';
    return;
  }
  const currentValue = select.value || workers[0].id;
  select.innerHTML = workers.map(worker => `<option value="${worker.id}">${escapeHtml(worker.name)} · ${escapeHtml(worker.site)}</option>`).join('');
  select.value = workers.some(worker => worker.id === currentValue) ? currentValue : workers[0].id;
  const worker = workers.find(item => item.id === select.value) || workers[0];
  const monthValue = getSelectedMonth();
  const days = getDaysInMonth(monthValue);
  const counts = {};
  Object.keys(attendanceStateMeta).forEach(key => counts[key] = 0);
  for (let day = 1; day <= days; day++) counts[getAttendanceState(worker.id, getDateKey(day, monthValue))]++;
  summary.innerHTML = `<b>${escapeHtml(worker.name)}</b><span>${escapeHtml(worker.business)} · ${escapeHtml(worker.site)} · ${escapeHtml(worker.type)}</span><small>출석 ${counts.present || 0} / 결근 ${counts.absent || 0} / 병원 ${counts.hospital || 0} / 지각 ${counts.late || 0}</small>`;
  table.querySelector('thead').innerHTML = '<tr>' + Array.from({ length: days }, (_, i) => {
    const day = i + 1;
    const dateKey = getDateKey(day, monthValue);
    return `<th class="${isHolidayDate(dateKey) ? 'holiday' : ''}">${day}<br><small>${getKoreanDayName(dateKey)}</small></th>`;
  }).join('') + '</tr>';
  table.querySelector('tbody').innerHTML = '<tr>' + Array.from({ length: days }, (_, i) => {
    const day = i + 1;
    const dateKey = getDateKey(day, monthValue);
    const state = getAttendanceState(worker.id, dateKey);
    return `<td class="${isHolidayDate(dateKey) ? 'holiday-cell' : ''}" data-worker-id="${worker.id}" data-date="${dateKey}" data-state="${state}"></td>`;
  }).join('') + '</tr>';
  bindAttendanceCellEvents(table);
}

function renderStatusPanel() {
  const list = $('#statusAttendanceList');
  if (!list) return;
  const workers = getFilteredAttendanceWorkers().filter(worker => getAttendanceState(worker.id, selectedAttendanceDate) === selectedStatusFilter);
  const meta = attendanceStateMeta[selectedStatusFilter] || attendanceStateMeta.present;
  if (!workers.length) {
    list.innerHTML = `<div class="attendance-empty">${meta.label} 상태의 근로자가 없습니다.</div>`;
    return;
  }
  list.innerHTML = workers.map(worker => {
    const icon = meta.icon ? `<span class="cell-icon ${meta.className}"><svg><use href="#${meta.icon}" /></svg></span>` : '<span class="cell-icon cell-empty"></span>';
    return `<article class="attendance-list-row readonly">${icon}<b>${escapeHtml(worker.name)}</b><span>${escapeHtml(worker.site)}</span><span>${escapeHtml(worker.type)}</span><em class="state-pill ${selectedStatusFilter}">${meta.label}</em></article>`;
  }).join('');
}

function renderAttendanceSupplementPanels() {
  renderTodayPanel();
  renderWorkerPanel();
  renderStatusPanel();
}

function renderAttendanceViews() {
  const monthValue = getSelectedMonth();
  ensureAttendanceMonthLockStatus(monthValue);
  ensureAttendanceMonthRecords(monthValue);
  if (!selectedAttendanceDate.startsWith(monthValue)) {
    const todayDay = monthValue === APP_TODAY_MONTH ? APP_TODAY.getDate() : 1;
    selectedAttendanceDate = getDateKey(Math.min(todayDay, getDaysInMonth(monthValue)), monthValue);
  }
  updateAttendanceLockUI();
  renderMonthTable();
  renderAttendanceSupplementPanels();
}

function showAttendanceTab(tab) {
  currentAttendanceTab = tab;
  $$('#attendanceTabs .tab').forEach(btn => btn.classList.toggle('active', btn.dataset.attTab === tab));
  $$('.attendance-panel').forEach(panel => panel.classList.toggle('active', panel.dataset.panel === tab));
  renderAttendanceViews();
}

function initializeAttendanceModule() {
  updateAttendanceMonthDisplay(getSelectedMonth());
  $('#filterPrevMonthBtn')?.addEventListener('click', () => changeMonth(-1));
  $('#filterNextMonthBtn')?.addEventListener('click', () => changeMonth(1));
  $('#prevMonthBtn')?.addEventListener('click', () => changeMonth(-1));
  $('#nextMonthBtn')?.addEventListener('click', () => changeMonth(1));
  $('#todayPrevBtn')?.addEventListener('click', () => changeTodayDate(-1));
  $('#todayNextBtn')?.addEventListener('click', () => changeTodayDate(1));
  ['#attSiteFilter'].forEach(selector => $(selector)?.addEventListener('change', renderAttendanceViews));
  $('#attWorkerSelect')?.addEventListener('change', renderWorkerPanel);
  $$('#attendanceTabs .tab').forEach(btn => btn.addEventListener('click', () => showAttendanceTab(btn.dataset.attTab)));
  $('#attStatusFilter')?.addEventListener('click', event => {
    const btn = event.target.closest('button[data-status-filter]');
    if (!btn) return;
    selectedStatusFilter = btn.dataset.statusFilter;
    $$('#attStatusFilter button').forEach(item => item.classList.toggle('active', item === btn));
    renderStatusPanel();
  });
  const quickStatus = $('#quickStatus');
  if (quickStatus) {
    quickStatus.addEventListener('click', event => {
      const btn = event.target.closest('button[data-state]');
      if (!btn) return;
      if (isAttendanceMonthLocked(getSelectedMonth())) {
        showAttendanceLockPopup();
        return;
      }
      const state = btn.dataset.state || 'present';
      setAttendanceMode(state);
      toast(`${attendanceStateMeta[state].label} 상태가 선택되었습니다. 칸을 누르면 적용됩니다.`);
    });
  }
  setAttendanceMode('present');
  showAttendanceTab('today');
}

$('#attendanceLockModalOk')?.addEventListener('click', hideAttendanceLockPopup);
$('#attendanceLockModal')?.addEventListener('click', event => {
  if (event.target.id === 'attendanceLockModal') hideAttendanceLockPopup();
});
$('#shortcutGuideOpen')?.addEventListener('click', handleShortcutInstallRequest);
$('#shortcutGuideClose')?.addEventListener('click', hideShortcutGuide);
$('#copyShortcutLink')?.addEventListener('click', copyShortcutLink);
$('#shortcutGuideModal')?.addEventListener('click', event => {
  if (event.target.id === 'shortcutGuideModal') hideShortcutGuide();
});
window.addEventListener('keydown', event => {
  if (event.key === 'Escape') {
    hideAttendanceLockPopup();
    hideShortcutGuide();
    hideHomeWorkerInfo();
  }
});

$$('[data-nav]').forEach(el => el.addEventListener('click', () => showScreen(el.dataset.nav)));

$('#homeWorkerList')?.addEventListener('click', event => {
  const row = event.target.closest('.home-worker-clickable');
  if (!row) return;
  showHomeWorkerInfo(row.dataset.workerId);
});
$('#homeWorkerList')?.addEventListener('keydown', event => {
  if (event.key !== 'Enter' && event.key !== ' ') return;
  const row = event.target.closest('.home-worker-clickable');
  if (!row) return;
  event.preventDefault();
  showHomeWorkerInfo(row.dataset.workerId);
});
$('#homeWorkerInfoClose')?.addEventListener('click', hideHomeWorkerInfo);
$('#homeWorkerInfoModal')?.addEventListener('click', event => {
  if (event.target.id === 'homeWorkerInfoModal') hideHomeWorkerInfo();
});

$$('#homeStatusGrid [data-worker-status]').forEach(card => {
  const apply = () => {
    $$('#homeStatusGrid [data-worker-status]').forEach(item => item.classList.remove('active'));
    card.classList.add('active');
    renderHomeWorkers(card.dataset.workerStatus);
  };
  card.addEventListener('click', apply);
  card.addEventListener('keydown', event => {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      apply();
    }
  });
});


function normalizePhoneNumber(value = '') {
  const digits = String(value || '').replace(/\D/g, '').slice(0, 11);
  if (digits.length <= 3) return digits;
  if (digits.length <= 7) return `${digits.slice(0, 3)}-${digits.slice(3)}`;
  return `${digits.slice(0, 3)}-${digits.slice(3, 7)}-${digits.slice(7)}`;
}

function getWorkerRegistrationFormData(form) {
  const formData = new FormData(form);
  const name = String(formData.get('name') || '').trim();
  const site = String(formData.get('site') || '').trim();
  const business = getBusinessForWorkerRegistrationSite(site);
  const phone = normalizePhoneNumber(formData.get('phone') || '');
  const nationality = String(formData.get('nationality') || '').trim();
  const gender = String(formData.get('gender') || '').trim();
  const status = String(formData.get('status') || '근무중').trim() || '근무중';
  const memo = String(formData.get('memo') || '').trim();
  return { name, business, site, phone, nationality, gender, status, memo };
}

function validateWorkerRegistrationForm(values) {
  const required = [
    ['이름', values.name],
    ['근무사업장', values.site],
    ['연락처', values.phone],
    ['국적', values.nationality],
    ['성별', values.gender]
  ];
  const missing = required.find(([, value]) => !String(value || '').trim());
  if (missing) {
    toast(`${missing[0]}을(를) 입력하세요.`);
    return false;
  }
  return true;
}

function normalizeDuplicateName(value = '') {
  return String(value || '').trim().replace(/\s+/g, '').toLocaleLowerCase('ko-KR');
}

function normalizeDuplicatePhone(value = '') {
  return String(value || '').replace(/\D/g, '');
}

function normalizeEmployeeForDuplicateCheck(row = {}, index = 0) {
  if (!row || typeof row !== 'object') return null;
  const name = firstNonEmpty(row.name, row.employee_name, row.worker_name, row.korean_name, row.english_name, row.full_name);
  const phone = firstNonEmpty(row.phone, row.contact, row.mobile, row.tel, row.phone_number, row.mobile_phone);
  if (!name && !phone) return null;
  return {
    id: firstNonEmpty(row.id, row.employee_id, row.worker_id, row.code) || String(index + 1),
    name,
    phone,
    business: firstNonEmpty(row.affiliated_business, row.business, row.business_name, row.company, row.company_name),
    site: firstNonEmpty(row.work_site, row.site, row.site_name, row.worksite, row.workSite, row.department, row.factory),
    raw: row
  };
}

function buildDuplicateCheckWorkersFromRows(rows = []) {
  return rows
    .map((row, index) => normalizeEmployeeForDuplicateCheck(row, index))
    .filter(Boolean);
}

async function refreshEmployeesForDuplicateCheck() {
  if (!currentUser) return attendanceWorkers;
  try {
    const { data } = await fetchJson(`${API_BASE}/employees?ts=${Date.now()}`, { headers: getAuthHeaders() });
    const rows = extractEmployeeRowsFromResponse(data);
    applyServerEmployees(rows);
    return buildDuplicateCheckWorkersFromRows(rows);
  } catch (error) {
    console.warn('employee duplicate check refresh failed', error);
  }
  return attendanceWorkers;
}

async function confirmWorkerDuplicatePolicy(values) {
  const targetName = normalizeDuplicateName(values.name);
  const targetPhone = normalizeDuplicatePhone(values.phone);
  const workers = await refreshEmployeesForDuplicateCheck();
  const sameNameWorkers = workers.filter(worker => normalizeDuplicateName(worker.name) === targetName);
  const samePhoneWorkers = workers.filter(worker => normalizeDuplicatePhone(worker.phone) === targetPhone);
  const sameNameAndPhone = workers.find(worker => normalizeDuplicateName(worker.name) === targetName && normalizeDuplicatePhone(worker.phone) === targetPhone);

  if (sameNameAndPhone) {
    toast('이름과 연락처가 같은 근로자가 이미 등록되어 있습니다.');
    window.alert('이름과 연락처가 같은 근로자가 이미 등록되어 있어 등록할 수 없습니다.');
    return false;
  }

  if (sameNameWorkers.length) {
    const proceed = window.confirm(`같은 이름의 근로자가 ${sameNameWorkers.length}명 있습니다. 그래도 등록하시겠습니까?`);
    if (!proceed) return false;
  }

  if (samePhoneWorkers.length) {
    const proceed = window.confirm(`같은 연락처가 등록된 근로자가 ${samePhoneWorkers.length}명 있습니다. 기존 근로자 정보를 확인한 뒤 계속 등록하시겠습니까?`);
    if (!proceed) return false;
  }

  return true;
}

function buildWorkerRegistrationPayload(values) {
  const now = formatDateTime(new Date());
  return {
    name: values.name,
    employee_name: values.name,
    worker_name: values.name,
    affiliated_business: values.business,
    business: values.business,
    business_name: values.business,
    work_site: values.site,
    site: values.site,
    site_name: values.site,
    phone: values.phone,
    contact: values.phone,
    nation: values.nationality,
    nationality: values.nationality,
    gender: values.gender,
    sex: values.gender,
    status: values.status || '근무중',
    employee_status: values.status || '근무중',
    note: values.memo,
    memo: values.memo,
    work_type: '주간',
    source: 'mobile',
    mobile_simple_register: true,
    registered_at: now,
    updated_at: now
  };
}

async function createWorkerOnServer(values) {
  const payload = buildWorkerRegistrationPayload(values);
  const endpoints = [`${API_BASE}/employees`, `${API_BASE}/employees/register`];
  let lastError = null;
  for (const endpoint of endpoints) {
    try {
      const result = await fetchJson(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Accept': 'application/json', ...getAuthHeaders() },
        body: JSON.stringify(payload)
      });
      return result.data;
    } catch (error) {
      lastError = error;
      if (!isMissingApiError(error)) break;
    }
  }
  throw lastError || new Error('근로자 등록 실패');
}

$('#workerPhone')?.addEventListener('input', event => {
  event.target.value = normalizePhoneNumber(event.target.value);
});

$('#workerForm')?.addEventListener('submit', async event => {
  event.preventDefault();
  const form = event.currentTarget;
  const submitButton = form.querySelector('button[type="submit"]');
  const values = getWorkerRegistrationFormData(form);
  if (!validateWorkerRegistrationForm(values)) return;
  if (!await confirmWorkerDuplicatePolicy(values)) return;
  const oldText = submitButton?.textContent || '';
  if (submitButton) {
    submitButton.disabled = true;
    submitButton.textContent = '서버 등록 중...';
  }
  try {
    await createWorkerOnServer(values);
    toast('근로자를 서버에 등록했습니다.');
    form.reset();
    const statusSelect = $('#workerStatusSelect');
    if (statusSelect) statusSelect.value = '근무중';
    configurePermissionOptions();
    await loadServerEmployees({ force: true });
    renderHomeWorkers(currentHomeStatus);
    renderAttendanceViews();
  } catch (error) {
    console.warn('worker registration failed', error);
    toast(error?.message || '근로자 등록에 실패했습니다.');
  } finally {
    if (submitButton) {
      submitButton.disabled = false;
      submitButton.textContent = oldText || '근로자 서버 등록';
    }
  }
});

function normalizeVehicleFromServer(row = {}) {
  const car = normalizeScopeValue(row.car || row.plate_number || row.vehicle_no || row.vehicle_name || row.vehicle_id || '');
  if (!car || car === '-') return null;
  return {
    vehicle_id: normalizeScopeValue(row.vehicle_id || ''),
    vehicle_name: normalizeScopeValue(row.vehicle_name || ''),
    plate_number: normalizeScopeValue(row.plate_number || car),
    car,
    business: normalizeScopeValue(row.business || row.business_name || row.company || row.company_name || ''),
    site: normalizeScopeValue(row.site || row.site_name || row.work_site_name || row.work_site || row.worksite || row.workSite || row.factory || ''),
    vehicle_type: normalizeScopeValue(row.vehicle_type || ''),
    main_driver: normalizeScopeValue(row.main_driver || ''),
    status: normalizeScopeValue(row.status || ''),
    car_model: normalizeScopeValue(row.car_model || ''),
    contract_end: normalizeScopeValue(row.contract_end || ''),
    baseline_odometer: row.baseline_odometer ?? row.start_odometer ?? row.initial_odometer ?? row.raw?.baseline_odometer ?? 0,
    current_odometer: row.current_odometer ?? row.raw?.current_odometer ?? 0,
    raw: row.raw || row
  };
}


function getVehicleDisplayName(vehicle = {}) {
  const raw = vehicle.raw || {};
  const candidates = [
    vehicle.vehicle_name,
    raw.vehicle_name,
    raw.name,
    raw.display_name,
    vehicle.plate_number,
    raw.plate_number,
    raw.vehicle_no,
    raw.vehicleNumber,
    vehicle.car,
    raw.car,
    vehicle.vehicle_id,
    raw.vehicle_id
  ];
  for (const value of candidates) {
    const text = normalizeScopeValue(value);
    if (text && text !== '-') return text;
  }
  return '차량명 없음';
}

function getVehicleDetailText(vehicle = {}, title = '') {
  const raw = vehicle.raw || {};
  const titleText = normalizeScopeValue(title);
  const parts = [];
  const plate = normalizeScopeValue(vehicle.plate_number || raw.plate_number || raw.vehicle_no || raw.vehicleNumber || '');
  const site = normalizeScopeValue(vehicle.site || raw.site || raw.site_name || raw.work_site_name || raw.work_site || '');
  const business = normalizeScopeValue(vehicle.business || raw.business || raw.business_name || '');
  if (plate && plate !== titleText && plate !== '-') parts.push(plate);
  const location = [business, site].filter(Boolean).join(' · ');
  if (location && location !== titleText) parts.push(location);
  return parts.length ? parts.join(' / ') : '배정 정보 없음';
}

function normalizeVehicleRunLogFromServer(row = {}) {
  const car = normalizeScopeValue(row.car || row.plate_number || row.vehicle_no || row.vehicle_name || row.vehicle_id || '');
  return {
    log_id: normalizeScopeValue(row.log_id || ''),
    vehicle_id: normalizeScopeValue(row.vehicle_id || ''),
    car,
    business: normalizeScopeValue(row.business || row.business_name || row.company || row.company_name || ''),
    site: normalizeScopeValue(row.site || row.site_name || row.work_site_name || row.work_site || row.worksite || row.workSite || row.factory || ''),
    savedAt: normalizeScopeValue(row.savedAt || row.saved_at || row.date || row.log_date || ''),
    km: row.km ?? row.end_odometer ?? 0,
    trip: row.trip ?? row.round_trips ?? row.round_trip_count ?? '',
    driver: normalizeScopeValue(row.driver || row.driver_name || ''),
    note: normalizeScopeValue(row.note || '')
  };
}


function normalizeVehicleFuelLogFromServer(row = {}) {
  const car = normalizeScopeValue(row.car || row.plate_number || row.vehicle_no || row.vehicle_name || row.vehicle_id || '');
  return {
    fuel_id: normalizeScopeValue(row.fuel_id || ''),
    vehicle_id: normalizeScopeValue(row.vehicle_id || ''),
    car,
    business: normalizeScopeValue(row.business || row.business_name || row.company || row.company_name || ''),
    site: normalizeScopeValue(row.site || row.site_name || row.work_site_name || row.work_site || row.worksite || row.workSite || row.factory || ''),
    savedAt: normalizeScopeValue(row.savedAt || row.saved_at || row.fuel_date || row.date || ''),
    fuel_date: normalizeScopeValue(row.fuel_date || row.date || ''),
    amount: row.amount ?? 0,
    note: normalizeScopeValue(row.note || '')
  };
}

function normalizeVehicleCostLogFromServer(row = {}) {
  const car = normalizeScopeValue(row.car || row.plate_number || row.vehicle_no || row.vehicle_name || row.vehicle_id || '');
  return {
    cost_id: normalizeScopeValue(row.cost_id || ''),
    vehicle_id: normalizeScopeValue(row.vehicle_id || ''),
    car,
    business: normalizeScopeValue(row.business || row.business_name || row.company || row.company_name || ''),
    site: normalizeScopeValue(row.site || row.site_name || row.work_site_name || row.work_site || row.worksite || row.workSite || row.factory || ''),
    savedAt: normalizeScopeValue(row.savedAt || row.saved_at || row.cost_date || row.date || ''),
    cost_date: normalizeScopeValue(row.cost_date || row.date || ''),
    category: normalizeScopeValue(row.category || '기타'),
    amount: row.amount ?? 0,
    description: normalizeScopeValue(row.description || ''),
    note: normalizeScopeValue(row.note || '')
  };
}


function toVehicleNumber(value) {
  const parsed = Number(String(value ?? '').replace(/,/g, '').trim());
  return Number.isFinite(parsed) ? parsed : 0;
}

function vehicleLogDateValue(log = {}) {
  return normalizeScopeValue(log.date || log.log_date || log.savedAt || '').slice(0, 10);
}

function sameVehicleForLog(log = {}, vehicle = {}) {
  const logVehicleId = normalizeScopeValue(log.vehicle_id || '');
  const vehicleId = normalizeScopeValue(vehicle.vehicle_id || '');
  const logCar = normalizeScopeValue(log.car || '');
  const vehicleCar = normalizeScopeValue(vehicle.car || vehicle.plate_number || '');
  return (!!vehicleId && logVehicleId === vehicleId) || (!!vehicleCar && logCar === vehicleCar);
}

function getVehicleBaselineOdometer(vehicle = {}) {
  return toVehicleNumber(
    vehicle.baseline_odometer ??
    vehicle.start_odometer ??
    vehicle.initial_odometer ??
    vehicle.raw?.baseline_odometer ??
    vehicle.raw?.start_odometer ??
    0
  );
}

function getPreviousVehicleOdometer(vehicle = null, targetDate = '') {
  if (!vehicle) return 0;
  const baseline = getVehicleBaselineOdometer(vehicle);
  const dateText = normalizeScopeValue(targetDate || $('#vehicleRunDate')?.value || APP_TODAY_DATE).slice(0, 10);
  const logs = (serverVehicleRunLogs.length ? serverVehicleRunLogs : getVehicleLogs())
    .filter(log => sameVehicleForLog(log, vehicle))
    .map(log => ({ ...log, _date: vehicleLogDateValue(log), _km: toVehicleNumber(log.km ?? log.end_odometer) }))
    .filter(log => log._km > 0)
    .filter(log => !dateText || !log._date || log._date <= dateText)
    .sort((a, b) => String(a._date || '').localeCompare(String(b._date || '')) || Number(a._km || 0) - Number(b._km || 0));
  return logs.length ? logs[logs.length - 1]._km : baseline;
}

function updatePreviousVehicleOdometerDisplay() {
  const box = $('#vehiclePreviousOdometerBox');
  const text = $('#vehiclePreviousOdometerText');
  const hint = $('#vehiclePreviousOdometerHint');
  const vehicle = selectedVehicleForMobileLog();
  if (!box || !text) return;
  if (!vehicle) {
    text.textContent = '-';
    if (hint) hint.textContent = '차량을 선택하면 자동으로 표시됩니다.';
    return;
  }
  const targetDate = $('#vehicleRunDate')?.value || APP_TODAY_DATE;
  const previous = getPreviousVehicleOdometer(vehicle, targetDate);
  text.textContent = `${Number(previous || 0).toLocaleString('ko-KR')} km`;
  if (hint) {
    const hasLogs = (serverVehicleRunLogs.length ? serverVehicleRunLogs : getVehicleLogs())
      .some(log => sameVehicleForLog(log, vehicle) && toVehicleNumber(log.km ?? log.end_odometer) > 0);
    hint.textContent = hasLogs ? '해당 차량의 마지막 종료 계기판 기준입니다.' : '첫 운행기록은 차량 등록 시 시작 계기판 기준입니다.';
  }
}

function selectedVehicleForMobileLog() {
  const vehicleId = normalizeScopeValue($('#vehicleLogVehicleSelect')?.value || '');
  return getScopedVehicles().find(vehicle => normalizeScopeValue(vehicle.vehicle_id || vehicle.car) === vehicleId) || null;
}

function getVehicleLogLabel(type) {
  if (type === 'fuel') return '주유기록';
  if (type === 'cost') return '기타비용';
  return '운행기록';
}

function toggleVehicleLogFormFields() {
  const type = $('#vehicleLogTypeSelect')?.value || 'run';
  $$('.vehicle-log-type-fields').forEach(group => {
    group.hidden = group.dataset.logType !== type;
  });
  const label = getVehicleLogLabel(type);
  const title = $('#vehicleLogFormTitle');
  const submit = $('#vehicleLogSubmitButton');
  if (title) title.textContent = `${label} 등록`;
  if (submit) submit.textContent = `${label} 저장`;
}

function setVehicleTab(tab) {
  currentVehicleTab = ['run', 'fuel', 'cost'].includes(tab) ? tab : 'run';
  $$('.vehicle-tab-button').forEach(button => {
    button.classList.toggle('active', button.dataset.vehicleTab === currentVehicleTab);
  });
  const form = $('#vehicleLogForm');
  if (form) form.hidden = false;
  if ($('#vehicleLogTypeSelect')) {
    $('#vehicleLogTypeSelect').value = currentVehicleTab;
    resetVehicleLogFormDates();
    toggleVehicleLogFormFields();
    updatePreviousVehicleOdometerDisplay();
  }
}

function resetVehicleLogFormDates() {
  const today = APP_TODAY_DATE || formatDateKey(new Date());
  ['vehicleRunDate', 'vehicleFuelDate', 'vehicleCostDate'].forEach(id => {
    const input = document.getElementById(id);
    if (input && !input.value) input.value = today;
  });
  updatePreviousVehicleOdometerDisplay();
}

async function saveMobileVehicleLog(form) {
  const vehicle = selectedVehicleForMobileLog();
  if (!vehicle) {
    toast('차량을 선택해 주세요.');
    return;
  }
  const type = $('#vehicleLogTypeSelect')?.value || 'run';
  const basePayload = {
    vehicle_id: vehicle.vehicle_id || '',
    car: vehicle.car || '',
    business: vehicle.business || '',
    site: vehicle.site || '',
    updated_by: currentUser?.name || currentUser?.id || 'mobile'
  };
  let endpoint = `${API_BASE}/vehicles/run-logs`;
  let payload = { ...basePayload };
  if (type === 'run') {
    const endOdometer = Number($('#vehicleRunOdometer')?.value || 0);
    if (!endOdometer || endOdometer < 0) {
      toast('종료 계기판 km를 입력해 주세요.');
      return;
    }
    const previousOdometer = getPreviousVehicleOdometer(vehicle, $('#vehicleRunDate')?.value || APP_TODAY_DATE);
    if (previousOdometer > 0 && endOdometer < previousOdometer) {
      toast(`종료 계기판 km가 이전 계기판 ${Number(previousOdometer).toLocaleString('ko-KR')}km보다 작습니다.`);
      return;
    }
    payload = {
      ...payload,
      date: $('#vehicleRunDate')?.value || APP_TODAY_DATE,
      end_odometer: endOdometer,
      round_trips: Number($('#vehicleRunTrips')?.value || 1),
      driver_name: $('#vehicleRunDriver')?.value || '',
      note: $('#vehicleRunNote')?.value || ''
    };
  } else if (type === 'fuel') {
    endpoint = `${API_BASE}/vehicles/fuel-logs`;
    const amount = Number($('#vehicleFuelAmount')?.value || 0);
    if (!amount || amount < 0) {
      toast('주유 금액을 입력해 주세요.');
      return;
    }
    payload = {
      ...payload,
      fuel_date: $('#vehicleFuelDate')?.value || APP_TODAY_DATE,
      amount,
      note: $('#vehicleFuelNote')?.value || ''
    };
  } else {
    endpoint = `${API_BASE}/vehicles/cost-logs`;
    const amount = Number($('#vehicleCostAmount')?.value || 0);
    if (!amount || amount < 0) {
      toast('기타비용 금액을 입력해 주세요.');
      return;
    }
    payload = {
      ...payload,
      cost_date: $('#vehicleCostDate')?.value || APP_TODAY_DATE,
      category: $('#vehicleCostCategory')?.value || '기타',
      amount,
      description: $('#vehicleCostDescription')?.value || '',
      note: $('#vehicleCostNote')?.value || ''
    };
  }
  const submitButton = form?.querySelector('button[type="submit"]');
  const oldText = submitButton?.textContent || '';
  if (submitButton) {
    submitButton.disabled = true;
    submitButton.textContent = '서버 저장 중...';
  }
  try {
    await fetchJson(endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Accept': 'application/json', ...getAuthHeaders() },
      body: JSON.stringify(payload)
    });
    toast(type === 'run' ? '운행기록을 저장했습니다.' : type === 'fuel' ? '주유기록을 저장했습니다.' : '기타비용을 저장했습니다.');
    form.reset();
    if ($('#vehicleLogTypeSelect')) $('#vehicleLogTypeSelect').value = type;
    resetVehicleLogFormDates();
    toggleVehicleLogFormFields();
    await loadServerVehicles({ force: true });
  } catch (error) {
    console.warn('vehicle log save failed', error);
    toast(error?.message || '차량기록 저장에 실패했습니다.');
  } finally {
    if (submitButton) {
      submitButton.disabled = false;
      submitButton.textContent = oldText || '차량 기록 저장';
    }
  }
}

async function loadServerVehicles(options = {}) {
  const { force = false } = options;
  if (!serverConnection.online || !currentUser) return serverVehicleList;
  if (vehicleServerLoading) return serverVehicleList;
  if (!force && vehicleServerLoaded && Date.now() - vehicleServerCheckedAt < VEHICLE_REFRESH_MS) return serverVehicleList;
  vehicleServerLoading = true;
  vehicleServerLastError = '';
  renderVehicleScreen();
  try {
    const { data } = await fetchJson(`${API_BASE}/vehicles?ts=${Date.now()}`, { headers: getAuthHeaders() });
    const rows = Array.isArray(data?.vehicles) ? data.vehicles : [];
    const runRows = Array.isArray(data?.run_logs) ? data.run_logs : [];
    const fuelRows = Array.isArray(data?.fuel_logs) ? data.fuel_logs : [];
    const costRows = Array.isArray(data?.cost_logs) ? data.cost_logs : [];
    serverVehicleList = rows.map(normalizeVehicleFromServer).filter(Boolean);
    serverVehicleRunLogs = runRows.map(normalizeVehicleRunLogFromServer).filter(Boolean);
    serverVehicleFuelLogs = fuelRows.map(normalizeVehicleFuelLogFromServer).filter(Boolean);
    serverVehicleCostLogs = costRows.map(normalizeVehicleCostLogFromServer).filter(Boolean);
    vehicleServerLoaded = true;
    vehicleServerCheckedAt = Date.now();
    vehicleServerLastError = '';
    updatePreviousVehicleOdometerDisplay();
  } catch (error) {
    vehicleServerLoaded = false;
    vehicleServerLastError = error?.message || '서버 차량 목록 불러오기 실패';
    console.warn('vehicle list load failed', error);
  } finally {
    vehicleServerLoading = false;
    renderVehicleScreen();
  }
  return serverVehicleList;
}

function getVehicleLogs() {
  const logs = store.get('vehicleLogs', []);
  return Array.isArray(logs) ? logs : [];
}

function formatVehicleDateTime(value) {
  if (!value) return '-';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return `${date.getFullYear()}-${pad2(date.getMonth() + 1)}-${pad2(date.getDate())} ${pad2(date.getHours())}:${pad2(date.getMinutes())}`;
}

function vehicleDisplayIdentity(vehicle = {}) {
  return canonicalScopeValue(getVehicleDisplayName(vehicle) || vehicle.car || vehicle.vehicle_name || vehicle.vehicle_id || '');
}

function dedupeVehiclesForSelect(vehicles = []) {
  const result = [];
  const seen = new Set();
  vehicles.forEach(vehicle => {
    const keys = vehicleIdentityKeys(vehicle);
    const displayKey = vehicleDisplayIdentity(vehicle);
    if (displayKey) keys.push(displayKey);
    if (keys.some(key => seen.has(key))) return;
    result.push(vehicle);
    keys.forEach(key => seen.add(key));
  });
  return result;
}

function renderVehicleScreen() {
  const vehicles = dedupeVehiclesForSelect(getScopedVehicles());
  const baseLogs = serverVehicleRunLogs.length ? serverVehicleRunLogs : getVehicleLogs();
  const logs = baseLogs.filter(log => !log?.car || vehicles.some(vehicle => normalizeScopeValue(vehicle.car) === normalizeScopeValue(log.car)));
  const fuelLogs = serverVehicleFuelLogs.filter(log => !log?.car || vehicles.some(vehicle => normalizeScopeValue(vehicle.car) === normalizeScopeValue(log.car)));
  const costLogs = serverVehicleCostLogs.filter(log => !log?.car || vehicles.some(vehicle => normalizeScopeValue(vehicle.car) === normalizeScopeValue(log.car)));
  const vehicleSelect = $('#vehicleLogVehicleSelect');
  if (vehicleSelect) {
    const current = vehicleSelect.value;
    vehicleSelect.innerHTML = '<option value="">차량을 선택하세요</option>' + vehicles.map(vehicle => {
      const value = escapeHtml(vehicle.vehicle_id || vehicle.car);
      const label = escapeHtml(getVehicleDisplayName(vehicle));
      return `<option value="${value}">${label}</option>`;
    }).join('');
    if ([...vehicleSelect.options].some(option => option.value === current)) vehicleSelect.value = current;
    updatePreviousVehicleOdometerDisplay();
  }

  const list = $('#vehicleListView');
  if (list) {
    if (vehicleServerLoading && !vehicles.length) {
      list.innerHTML = '<div class="vehicle-empty">서버 차량 목록을 불러오는 중입니다.</div>';
    } else if (!vehicles.length) {
      list.innerHTML = `<div class="vehicle-empty">${escapeHtml(vehicleServerLastError || '배정된 차량이 없습니다.')}</div>`;
    } else {
      list.innerHTML = vehicles.map(vehicle => {
        const vehicleLogs = logs.filter(log => normalizeScopeValue(log.car) === normalizeScopeValue(vehicle.car));
        const latest = vehicleLogs[vehicleLogs.length - 1];
        const kmText = latest?.km ? `${Number(latest.km).toLocaleString('ko-KR')}km` : '운행기록 없음';
        const titleText = getVehicleDisplayName(vehicle);
        const detailText = getVehicleDetailText(vehicle, titleText);
        const statusText = vehicle.status || vehicle.vehicle_type || '조회';
        return `<article class="vehicle-card">
          <div><b>${escapeHtml(titleText)}</b><small>${escapeHtml(detailText)}</small></div>
          <span class="pill success">${escapeHtml(kmText || statusText)}</span>
        </article>`;
      }).join('');
    }
  }

  const recent = $('#vehicleRecentLogs');
  if (recent) {
    const mixedLogs = [
      ...logs.map(log => ({ type: '운행', car: log.car, savedAt: log.savedAt || log.date, text: `${log.km ? Number(log.km).toLocaleString('ko-KR') + 'km' : 'km 미입력'} · ${log.trip ? escapeHtml(log.trip) + '회' : '횟수 없음'}` })),
      ...fuelLogs.map(log => ({ type: '주유', car: log.car, savedAt: log.savedAt || log.fuel_date, text: `${Number(log.amount || 0).toLocaleString('ko-KR')}원` })),
      ...costLogs.map(log => ({ type: log.category || '기타비용', car: log.car, savedAt: log.savedAt || log.cost_date, text: `${Number(log.amount || 0).toLocaleString('ko-KR')}원` }))
    ].sort((a, b) => String(b.savedAt || '').localeCompare(String(a.savedAt || ''))).slice(0, 8);
    if (!mixedLogs.length) {
      recent.innerHTML = '<div class="vehicle-empty">최근 차량기록이 없습니다. 모바일에서 운행·주유·기타비용을 등록할 수 있습니다.</div>';
    } else {
      recent.innerHTML = mixedLogs.map(log => {
        return `<article class="vehicle-log-row">
          <div><b>${escapeHtml(log.car || '차량 미지정')} · ${escapeHtml(log.type)}</b><small>${escapeHtml(formatVehicleDateTime(log.savedAt))}</small></div>
          <span>${log.text}</span>
        </article>`;
      }).join('');
    }
  }
}


$$('.vehicle-tab-button').forEach(button => {
  button.addEventListener('click', () => setVehicleTab(button.dataset.vehicleTab || 'run'));
});
$('#vehicleLogTypeSelect')?.addEventListener('change', toggleVehicleLogFormFields);
$('#vehicleLogVehicleSelect')?.addEventListener('change', updatePreviousVehicleOdometerDisplay);
$('#vehicleRunDate')?.addEventListener('change', updatePreviousVehicleOdometerDisplay);
$('#vehicleLogForm')?.addEventListener('submit', async event => {
  event.preventDefault();
  await saveMobileVehicleLog(event.currentTarget);
});
resetVehicleLogFormDates();
toggleVehicleLogFormFields();
setVehicleTab('run');

const syncNowButton = $('#syncNow');
if (syncNowButton) {
  syncNowButton.addEventListener('click', async () => {
    const now = new Date();
    const stamp = `${now.getFullYear()}-${String(now.getMonth()+1).padStart(2,'0')}-${String(now.getDate()).padStart(2,'0')} ${String(now.getHours()).padStart(2,'0')}:${String(now.getMinutes()).padStart(2,'0')}`;
    const monthValue = getSelectedMonth();
    const pendingBefore = Number(store.get('pendingCount', 0) || 0);
    const history = store.get('syncHistory', []);

    if (!serverConnection.online) {
      await initializeServerConnection();
    }

    await loadServerVehicles({ force: true });
    const retryResult = await processAttendanceRetryQueue({ reason: 'manual-sync' });
    const data = await refreshAttendanceMonthRecords(monthValue, { forceRender: true });
    if (data?.status === 'ok') {
      const serverCount = Number(data?.count || 0);
      store.set('serverSavedCount', serverCount);
      store.set(`serverSavedCount_${monthValue}`, serverCount);
      const pendingAfter = getAttendanceRetryQueue().length;
      store.set('pendingCount', pendingAfter);
      store.set('syncFailCount', pendingAfter > 0 ? Math.max(1, Number(store.get('syncFailCount', 0) || 0)) : 0);
      store.set('lastSync', stamp);
      store.set('syncState', pendingAfter > 0 ? 'warning' : 'success');
      const retryText = retryResult?.sent ? ` / 재전송 ${retryResult.sent}건` : '';
      const pendingText = pendingAfter > 0 ? ` / 남은 대기 ${pendingAfter}건` : '';
      history.unshift({ time: stamp, status: pendingAfter > 0 ? '확인' : '정상', text: `서버 저장 ${serverCount}건 / 대기 ${pendingBefore}건${retryText}${pendingText}` });
      store.set('syncHistory', history.slice(0, 6));
      updateSync();
      toast(`자동 동기화 확인: 서버 저장 ${serverCount}건`);
      return;
    }

    store.set('lastSync', stamp);
    store.set('syncState', 'warning');
    history.unshift({ time: stamp, status: '실패', text: '서버 저장 건수 확인 실패' });
    store.set('syncHistory', history.slice(0, 6));
    updateSync();
    toast('서버 저장 건수를 확인하지 못했습니다.');
  });
}

// 50차 수정: 안정화된 자동 동기화 상태 표시
function setupServiceWorker() {
  if (!('serviceWorker' in navigator)) return;
  window.addEventListener('load', () => {
    navigator.serviceWorker.register(`sw.js?v=${APP_BUILD_VERSION}`, { scope: './', updateViaCache: 'none' })
      .then(registration => registration.update().catch(() => {}))
      .catch(() => {});
  });
}
setupServiceWorker();

async function initializeApp() {
  clearLegacyMobileLocalData();
  bindWorkerPhoneAutoHyphen();
  await initializeServerConnection();
  renderHomeWorkers(currentHomeStatus);
  updateWorkers();
  updateSync();
  initializeLogin();
  await restoreLoginSession();
  await processAttendanceRetryQueue({ reason: 'startup', silent: true });
}

initializeApp();
window.addEventListener("DOMContentLoaded", updateShortcutButtonState);
window.addEventListener("resize", updateShortcutButtonState);
