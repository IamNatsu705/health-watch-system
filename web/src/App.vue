<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { api, getApiBase, isNativeApp, setApiBase } from './api'

const DEVICE_KEY = 'health-watch-device'
const devices = ref([])
const selectedId = ref('')
const latest = ref(null)
const history = ref([])
const events = ref([])
const daily = ref([])
const profile = ref(null)
const profileFor = ref('')
const profileForm = ref({ height_cm: '', weight_kg: '', step_length_m: '' })
const profileSaving = ref(false)
const profileMessage = ref('')
const profileError = ref(false)
let refreshToken = 0
const error = ref('')
const loading = ref(true)
const updatedAt = ref(null)
const apiAddress = ref(getApiBase())
const apiSaved = ref(false)
const commandSending = ref(false)
const commandMessage = ref('')
const commandError = ref(false)
const remoteAlert = ref({
  known: false,
  buzzer_active: false,
  red_led_active: false,
  source: 'unknown',
  pending: false,
  pending_active: null,
})
let timer

const eventLabels = {
  fall_detected: 'Phát hiện ngã',
  fall_acknowledged: 'Đã xác nhận ngã',
  sos_pressed: 'Đã nhấn SOS',
  sos_released: 'Đã thả SOS',
}

function sessionId() {
  let id = sessionStorage.getItem('health-watch-session')
  if (!id) {
    id = crypto.randomUUID()
    sessionStorage.setItem('health-watch-session', id)
  }
  return id
}

function logActivity(action, deviceId = null) {
  api.activity({ session_id: sessionId(), action, device_id: deviceId }).catch(() => {})
}

function timeLabel(value) {
  if (!value) return '—'
  return new Date(value).toLocaleString('vi-VN', { hour: '2-digit', minute: '2-digit', second: '2-digit', day: '2-digit', month: '2-digit' })
}

function ageLabel(seconds) {
  if (seconds === null || seconds === undefined) return '—'
  if (seconds < 60) return `${Math.round(seconds)} giây trước`
  if (seconds < 3600) return `${Math.round(seconds / 60)} phút trước`
  if (seconds < 86400) return `${Math.round(seconds / 3600)} giờ trước`
  return `${Math.round(seconds / 86400)} ngày trước`
}

const imuLabels = {
  starting: 'Đang khởi động cảm biến chuyển động',
  error: 'Lỗi cảm biến chuyển động MPU6050 — Pi đang thử khởi tạo lại, bước chân không được đếm',
  frozen: 'Cảm biến chuyển động bị treo — Pi đang khởi tạo lại, bước chân không được đếm',
  saturated: 'Có va chạm mạnh vượt thang đo ±8 g',
}

const current = computed(() => latest.value?.telemetry)
const device = computed(() => latest.value?.device)
// Chỉ coi là "hiện tại" khi thiết bị online và bản đo cuối do server nhận trong vài giây gần đây.
const isFresh = computed(() => Boolean(device.value?.online && current.value?.fresh))
const isStale = computed(() => Boolean(current.value && !isFresh.value))
const today = computed(() => (daily.value.length ? daily.value[daily.value.length - 1] : null))
const weekMax = computed(() => Math.max(1, ...daily.value.map(day => day.steps)))
const imuProblem = computed(() => {
  const status = current.value?.imu_status
  return status && status !== 'ok' ? imuLabels[status] || status : ''
})
const modelLabel = computed(() => {
  const model = current.value?.step_model
  return model ? `${model.name} ${model.version}` : ''
})
const stepSourceLabel = computed(() => {
  const source = today.value?.source || current.value?.steps_primary_source
  if (source === 'ai') return `Đếm bởi AI${modelLabel.value ? ` (${modelLabel.value})` : ''} trên tín hiệu MPU6050`
  if (source === 'algorithm') return 'Thuật toán xử lý tín hiệu (Pi chưa nạp mô hình AI)'
  if (source === 'mixed') return 'Hôm nay có phiên AI và phiên chỉ dùng thuật toán'
  return 'Chưa có dữ liệu bước chân hôm nay'
})
const walkingLabel = computed(() => {
  if (!isFresh.value || !current.value || current.value.walking === null) return ''
  if (!current.value.walking) return 'Hiện không đi bộ'
  const cadence = current.value.cadence_spm
  return cadence ? `Đang đi bộ · ${Math.round(cadence)} bước/phút` : 'Đang đi bộ'
})
const distanceBasisLabel = computed(() => {
  if (!profile.value) return 'Nhập chiều cao/cân nặng ở mục Hồ sơ để ước tính'
  const length = current.value?.step_length_m
  if (!length) return 'Đã lưu hồ sơ; chờ Pi nhận cấu hình'
  return `Ước tính: số bước × ${length.toFixed(2)} m/bước (${current.value.distance_method === 'measured' ? 'tự đo' : 'theo chiều cao'})`
})
const alertToggleOn = computed(() => (
  remoteAlert.value.pending
    ? remoteAlert.value.pending_active === true
    : remoteAlert.value.buzzer_active
))
const canToggleAlert = computed(() => (
  isFresh.value && remoteAlert.value.known &&
  (!remoteAlert.value.pending || remoteAlert.value.pending_active === true)
))
const alertStateLabel = computed(() => {
  if (!isFresh.value) return 'Không xác định — thiết bị đang offline'
  if (remoteAlert.value.pending) {
    return remoteAlert.value.pending_active
      ? 'Đang chờ Pi xác nhận bật còi…'
      : 'Đang chờ Pi xác nhận tắt còi…'
  }
  if (!remoteAlert.value.known) return 'Chưa nhận trạng thái còi từ Pi'
  if (!remoteAlert.value.buzzer_active) return 'Còi đang tắt'
  const sources = {
    remote: 'Còi đang bật — điều khiển từ xa',
    sos: 'Còi đang bật — nút SOS trên thiết bị',
    fall: 'Còi đang bật — cảnh báo ngã',
  }
  return sources[remoteAlert.value.source] || 'Còi đang bật'
})
const heartPoints = computed(() => {
  const valid = history.value.filter(item => item.heart_rate_bpm !== null)
  if (valid.length < 2) return ''
  const low = Math.min(...valid.map(item => item.heart_rate_bpm)) - 5
  const high = Math.max(...valid.map(item => item.heart_rate_bpm)) + 5
  const span = Math.max(high - low, 1)
  return valid.map((item, index) => `${(index / (valid.length - 1) * 100).toFixed(1)},${(38 - (item.heart_rate_bpm - low) / span * 34).toFixed(1)}`).join(' ')
})

function clearDeviceData() {
  latest.value = null
  history.value = []
  events.value = []
  daily.value = []
  remoteAlert.value = { known: false, buzzer_active: false, pending: false }
}

async function loadProfile(id) {
  const response = await api.profile(id)
  if (id !== selectedId.value) return
  profile.value = response.profile
  profileFor.value = id
  profileForm.value = {
    height_cm: response.profile?.height_cm ?? '',
    weight_kg: response.profile?.weight_kg ?? '',
    step_length_m: response.profile?.step_length_m ?? '',
  }
}

async function refresh() {
  const token = ++refreshToken
  try {
    const list = await api.devices()
    if (token !== refreshToken) return
    devices.value = list
    if (!list.some(item => item.id === selectedId.value)) {
      const remembered = localStorage.getItem(DEVICE_KEY)
      selectedId.value = list.find(item => item.id === remembered)?.id || list[0]?.id || ''
      clearDeviceData()
    }
    const id = selectedId.value
    if (!id) {
      clearDeviceData()
      error.value = ''
      return
    }
    const [last, samples, recentEvents, days] = await Promise.all([
      api.latest(id), api.history(id), api.events(id), api.dailySteps(id, 7),
    ])
    // Bỏ phản hồi đến muộn của lần tải cũ hoặc của thiết bị vừa bỏ chọn.
    if (token !== refreshToken || id !== selectedId.value) return
    latest.value = last
    remoteAlert.value = last.remote_alert || { known: false, buzzer_active: false, pending: false }
    history.value = samples
    events.value = recentEvents
    daily.value = days.days
    if (profileFor.value !== id) await loadProfile(id)
    updatedAt.value = new Date()
    error.value = ''
  } catch (exc) {
    if (token !== refreshToken) return
    error.value = exc.message || 'Không kết nối được API'
    // Không giữ số cũ trên màn hình như thể vẫn đang cập nhật.
    clearDeviceData()
  } finally {
    if (token === refreshToken) loading.value = false
  }
}

function selectDevice(event) {
  selectedId.value = event.target.value
  localStorage.setItem(DEVICE_KEY, selectedId.value)
  commandMessage.value = ''
  profileMessage.value = ''
  profile.value = null
  profileFor.value = ''
  clearDeviceData()
  logActivity('device_select', selectedId.value)
  refresh()
}

function optionalNumber(value) {
  return value === '' || value === null || value === undefined ? null : Number(value)
}

async function saveProfile() {
  if (!selectedId.value || profileSaving.value) return
  const payload = {
    height_cm: optionalNumber(profileForm.value.height_cm),
    weight_kg: optionalNumber(profileForm.value.weight_kg),
    step_length_m: optionalNumber(profileForm.value.step_length_m),
  }
  profileError.value = false
  if (payload.height_cm === null || payload.weight_kg === null) {
    profileError.value = true
    profileMessage.value = 'Cần nhập chiều cao và cân nặng thật của người đeo.'
    return
  }
  profileSaving.value = true
  try {
    const response = await api.saveProfile(selectedId.value, payload)
    profile.value = response.profile
    profileMessage.value = response.delivered_to_broker
      ? 'Đã lưu và gửi tới thiết bị.'
      : 'Đã lưu; sẽ gửi tới thiết bị khi API kết nối lại broker.'
    logActivity('profile_update', selectedId.value)
  } catch (exc) {
    profileError.value = true
    profileMessage.value = exc.message || 'Không lưu được hồ sơ.'
  } finally {
    profileSaving.value = false
  }
}

async function clearProfile() {
  if (!selectedId.value || profileSaving.value) return
  profileSaving.value = true
  try {
    await api.clearProfile(selectedId.value)
    profile.value = null
    profileForm.value = { height_cm: '', weight_kg: '', step_length_m: '' }
    profileError.value = false
    profileMessage.value = 'Đã xóa hồ sơ; thiết bị ngừng ước tính quãng đường/kcal.'
    logActivity('profile_clear', selectedId.value)
  } catch (exc) {
    profileError.value = true
    profileMessage.value = exc.message || 'Không xóa được hồ sơ.'
  } finally {
    profileSaving.value = false
  }
}

function saveApiAddress() {
  setApiBase(apiAddress.value)
  apiAddress.value = getApiBase()
  apiSaved.value = true
  selectedId.value = ''
  loading.value = true
  refresh()
  setTimeout(() => { apiSaved.value = false }, 2000)
}

async function sendRemoteAlert(active) {
  if (!selectedId.value || commandSending.value) return
  commandSending.value = true
  commandMessage.value = ''
  commandError.value = false
  try {
    const response = await api.remoteAlert(selectedId.value, active, 10)
    remoteAlert.value = response.state
    commandMessage.value = active
      ? 'Đã gửi lệnh bật; đang chờ Pi xác nhận.'
      : 'Đã gửi lệnh tắt; đang chờ Pi xác nhận.'
    logActivity(active ? 'remote_alert_start' : 'remote_alert_stop', selectedId.value)
  } catch (exc) {
    commandError.value = true
    commandMessage.value = exc.message || 'Không gửi được lệnh tới thiết bị.'
  } finally {
    commandSending.value = false
  }
}

function toggleRemoteAlert() {
  if (!canToggleAlert.value || commandSending.value) return
  sendRemoteAlert(!alertToggleOn.value)
}

onMounted(() => {
  logActivity('dashboard_view')
  refresh()
  timer = setInterval(refresh, 3000)
})
onUnmounted(() => clearInterval(timer))
</script>

<template>
  <div class="page-shell">
    <header class="topbar">
      <div class="brand"><span class="brand-mark">♥</span><span>HEALTH<span class="brand-accent">WATCH</span></span></div>
      <div class="topbar-right"><span class="clock">Cập nhật {{ timeLabel(updatedAt) }}</span></div>
    </header>

    <main class="dashboard">
      <section class="intro">
        <div>
          <p class="eyebrow">TỔNG QUAN THIẾT BỊ</p>
          <h1>Sức khỏe trong tầm mắt.</h1>
          <p class="intro-copy">Dữ liệu thật từ Raspberry Pi (MPU6050, MAX30102) qua MQTT, PostgreSQL và API.</p>
        </div>
        <div class="device-picker">
          <label for="device">THIẾT BỊ</label>
          <select id="device" :value="selectedId" @change="selectDevice">
            <option v-if="!devices.length" value="">Chưa có thiết bị đăng ký gửi dữ liệu</option>
            <option v-for="item in devices" :key="item.id" :value="item.id">{{ item.name }} — {{ item.online ? 'đang gửi' : 'offline' }}</option>
          </select>
          <span class="device-state" :class="isFresh ? 'online' : 'offline'"><i></i>{{ isFresh ? 'Đang cập nhật' : (current ? `Dữ liệu cũ · ${ageLabel(current.age_s)}` : 'Chưa có dữ liệu') }}</span>
        </div>
      </section>

      <section v-if="isNativeApp" class="native-settings">
        <div><p class="eyebrow">KẾT NỐI ANDROID</p><strong>API trên máy tính</strong></div>
        <div class="api-address-row">
          <input v-model="apiAddress" type="url" inputmode="url" placeholder="http://192.168.1.10:8000" aria-label="Địa chỉ API" />
          <button type="button" @click="saveApiAddress">{{ apiSaved ? 'Đã lưu' : 'Lưu' }}</button>
        </div>
        <small>Dùng IP LAN của máy tính, không dùng localhost trên điện thoại.</small>
      </section>

      <div v-if="error" class="notice error">Không tải được dữ liệu: {{ error }}</div>
      <div v-else-if="loading" class="notice">Đang kết nối hệ thống…</div>
      <div v-else-if="!selectedId" class="notice">Chưa có thiết bị nào trong MQTT_DEVICES gửi dữ liệu. Kiểm tra Pi đã chạy và dùng đúng tài khoản MQTT riêng.</div>
      <div v-else-if="!current" class="notice">Thiết bị chưa gửi số đo nào.</div>
      <div v-if="isStale" class="notice warning">Thiết bị không gửi dữ liệu mới từ {{ ageLabel(current.age_s) }}. Các số bên dưới là lần đo cuối, không phải giá trị hiện tại.</div>
      <div v-if="current?.legacy" class="notice warning">Bản đo cuối từ firmware cũ (thuật toán peak-v1, sai số lớn). Cập nhật mã trên Pi để có số bước đáng tin.</div>
      <div v-if="imuProblem && !isStale" class="notice error">{{ imuProblem }}</div>

      <section class="remote-alert-panel">
        <div class="remote-alert-copy">
          <p class="eyebrow">ĐIỀU KHIỂN TỪ XA</p>
          <h2>Còi và đèn cảnh báo</h2>
          <p>Bật LED đỏ và còi trong 10 giây. Thiết bị tự tắt nếu không nhận thêm lệnh.</p>
        </div>
        <div class="remote-alert-actions">
          <div class="alert-control-row">
            <div
              class="alert-state-badge"
              :class="{ active: remoteAlert.buzzer_active, pending: remoteAlert.pending }"
            ><i></i>{{ alertStateLabel }}</div>
            <button
              type="button"
              role="switch"
              class="alert-toggle"
              :class="{ on: alertToggleOn, pending: remoteAlert.pending }"
              :aria-checked="alertToggleOn"
              :aria-label="alertToggleOn ? 'Tắt còi cảnh báo' : 'Bật còi cảnh báo'"
              :disabled="!canToggleAlert || commandSending"
              @click="toggleRemoteAlert"
            >
              <span class="alert-toggle-track"><span class="alert-toggle-thumb"></span></span>
              <span class="alert-toggle-label">{{ alertToggleOn ? 'ON' : 'OFF' }}</span>
            </button>
          </div>
          <small v-if="commandMessage" :class="{ 'command-error': commandError }">{{ commandMessage }}</small>
          <small v-else>Trạng thái trên đây do chính Raspberry Pi xác nhận qua MQTT.</small>
        </div>
      </section>

      <section class="metrics-grid" :class="{ stale: isStale }">
        <article class="metric-card heart-card">
          <div class="card-heading"><span class="metric-icon heart-icon">♥</span><span>NHỊP TIM</span></div>
          <div class="metric-value"><strong>{{ current?.heart_rate_bpm ?? '--' }}</strong><span>BPM ~</span></div>
          <p>{{ current?.finger_present ? 'Tín hiệu cảm biến hiện có' : 'Chưa có tín hiệu ngón tay' }}</p>
          <svg class="pulse-chart" viewBox="0 0 100 42" preserveAspectRatio="none" aria-label="Xu hướng nhịp tim">
            <line x1="0" y1="38" x2="100" y2="38" stroke="#294055" stroke-width="0.5" />
            <polyline v-if="heartPoints" :points="heartPoints" fill="none" stroke="#ff6675" stroke-width="1.4" vector-effect="non-scaling-stroke" />
          </svg>
        </article>

        <article class="metric-card">
          <div class="card-heading"><span class="metric-icon step-icon">↗</span><span>BƯỚC CHÂN</span></div>
          <div class="metric-value"><strong>{{ today?.sessions ? today.steps.toLocaleString('vi-VN') : '--' }}</strong><span>bước hôm nay</span></div>
          <p>{{ stepSourceLabel }}</p>
          <p v-if="walkingLabel" class="step-live">{{ walkingLabel }}</p>
          <p v-if="current && !current.legacy" class="step-session">Phiên này: AI {{ current.steps_ai_session ?? '—' }} · thuật toán {{ current.steps_algorithm_session }}</p>
        </article>
        <article class="metric-card">
          <div class="card-heading"><span class="metric-icon distance-icon">⌁</span><span>QUÃNG ĐƯỜNG</span></div>
          <div class="metric-value"><strong>{{ today?.distance_m != null ? (today.distance_m / 1000).toFixed(2) : '--' }}</strong><span>km ~ hôm nay</span></div>
          <p>{{ distanceBasisLabel }}</p>
        </article>
        <article class="metric-card">
          <div class="card-heading"><span class="metric-icon calorie-icon">✦</span><span>NĂNG LƯỢNG</span></div>
          <div class="metric-value"><strong>{{ today?.calories_kcal != null ? Math.round(today.calories_kcal) : '--' }}</strong><span>kcal ~ hôm nay</span></div>
          <p>{{ profile ? 'Năng lượng vận động ước tính theo phương trình ACSM (đi 0,5 / chạy 1,0 kcal/kg/km)' : 'Cần cân nặng thật để ước tính' }}</p>
        </article>
      </section>

      <section class="lower-grid steps-grid">
        <article class="panel">
          <div class="panel-title"><div><p class="eyebrow">7 NGÀY</p><h2>Số bước theo ngày</h2></div></div>
          <p v-if="!daily.length" class="empty-state">Chưa có dữ liệu.</p>
          <div v-else class="week-chart" role="img" aria-label="Số bước 7 ngày gần nhất">
            <div v-for="day in daily" :key="day.date" class="week-bar">
              <span class="week-value">{{ day.sessions ? day.steps.toLocaleString('vi-VN') : '—' }}</span>
              <span class="week-track"><span class="week-fill" :class="day.source" :style="{ height: `${Math.round(day.steps / weekMax * 100)}%` }"></span></span>
              <span class="week-label">{{ day.date.slice(8, 10) }}/{{ day.date.slice(5, 7) }}</span>
            </div>
          </div>
          <small class="panel-note">Tính theo giờ server nhận dữ liệu; chỉ gồm firmware mới (v2).</small>
        </article>
        <article class="panel">
          <div class="panel-title"><div><p class="eyebrow">HỒ SƠ NGƯỜI ĐEO</p><h2>Ước tính quãng đường, kcal</h2></div></div>
          <form class="profile-form" @submit.prevent="saveProfile">
            <label>Chiều cao (cm)<input v-model="profileForm.height_cm" type="number" min="100" max="230" step="0.1" required /></label>
            <label>Cân nặng (kg)<input v-model="profileForm.weight_kg" type="number" min="25" max="250" step="0.1" required /></label>
            <label>Chiều dài bước tự đo (m, tùy chọn)<input v-model="profileForm.step_length_m" type="number" min="0.25" max="1.3" step="0.01" placeholder="đi 20 bước, đo, chia 20" /></label>
            <div class="profile-actions">
              <button type="submit" :disabled="!selectedId || profileSaving">Lưu</button>
              <button v-if="profile" type="button" class="secondary" :disabled="profileSaving" @click="clearProfile">Xóa</button>
            </div>
          </form>
          <small :class="{ 'command-error': profileError }">{{ profileMessage || 'Chỉ lưu trên máy chủ local và trên Pi; không gửi đi nơi khác.' }}</small>
        </article>
      </section>

      <section class="lower-grid">
        <article class="panel"><div class="panel-title"><div><p class="eyebrow">THIẾT BỊ</p><h2>Trạng thái</h2></div><span class="panel-dot" :class="isFresh ? 'online' : 'offline'"></span></div>
          <div class="status-row"><span>Server nhận lúc</span><strong>{{ timeLabel(current?.received_at) }}</strong></div>
          <div class="status-row"><span>Cảm biến chuyển động</span><strong>{{ current?.imu_status || '—' }}</strong></div>
          <div class="status-row"><span>Mô hình AI bước chân</span><strong>{{ modelLabel || 'chưa nạp' }}</strong></div>
          <div class="status-row"><span>Firmware</span><strong>{{ current?.firmware_version || device?.firmware_version || '—' }}</strong></div>
          <div class="status-row"><span>Đồng hồ Pi</span><strong>{{ current?.clock_synced === true ? 'đã đồng bộ NTP' : (current?.clock_synced === false ? 'chưa đồng bộ NTP' : '—') }}</strong></div>
          <div class="status-row"><span>Phiên khởi động</span><code>{{ current?.boot_id?.slice(0, 8) || '—' }}</code></div>
        </article>
        <article class="panel"><div class="panel-title"><div><p class="eyebrow">NHẬT KÝ</p><h2>Sự kiện gần đây</h2></div><span class="event-count">{{ events.length }}</span></div><p v-if="!events.length" class="empty-state">Chưa có sự kiện ngã hoặc SOS từ thiết bị.</p><ul v-else class="event-list"><li v-for="item in events" :key="item.event_id"><span class="event-bullet"></span><span>{{ eventLabels[item.event_type] || item.event_type }}</span><time>{{ timeLabel(item.occurred_at) }}</time></li></ul></article>
      </section>
      <p class="footnote">Không phải thiết bị y tế. Bước chân được đếm từ cảm biến thật; độ chính xác đã đánh giá trên dữ liệu thật OxWalk/Clemson (xem ml/README.md). Quãng đường và kcal là ước tính.</p>
    </main>
  </div>
</template>
