<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { api, getApiBase, isNativeApp, setApiBase } from './api'

const devices = ref([])
const selectedId = ref('')
const latest = ref(null)
const history = ref([])
const events = ref([])
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

const current = computed(() => latest.value?.telemetry)
const device = computed(() => latest.value?.device)
const isFresh = computed(() => {
  if (!device.value?.online || !current.value) return false
  return Date.now() - new Date(current.value.received_at).getTime() < 10000
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

async function refresh() {
  try {
    const list = await api.devices()
    devices.value = list
    if (!selectedId.value && list.length) selectedId.value = list[0].id
    if (!selectedId.value) {
      latest.value = null
      history.value = []
      events.value = []
      remoteAlert.value = { known: false, buzzer_active: false, pending: false }
      error.value = ''
      return
    }
    const [last, samples, recentEvents] = await Promise.all([
      api.latest(selectedId.value), api.history(selectedId.value), api.events(selectedId.value),
    ])
    latest.value = last
    remoteAlert.value = last.remote_alert || { known: false, buzzer_active: false, pending: false }
    history.value = samples
    events.value = recentEvents
    updatedAt.value = new Date()
    error.value = ''
  } catch (exc) {
    error.value = exc.message || 'Không kết nối được API'
  } finally {
    loading.value = false
  }
}

function selectDevice(event) {
  selectedId.value = event.target.value
  commandMessage.value = ''
  remoteAlert.value = { known: false, buzzer_active: false, pending: false }
  logActivity('device_select', selectedId.value)
  refresh()
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
      <div class="topbar-right"><span class="demo-tag">LOCAL DEMO</span><span class="clock">{{ timeLabel(updatedAt) }}</span></div>
    </header>

    <main class="dashboard">
      <section class="intro">
        <div>
          <p class="eyebrow">TỔNG QUAN THIẾT BỊ</p>
          <h1>Sức khỏe trong tầm mắt.</h1>
          <p class="intro-copy">Dữ liệu từ mock hoặc Raspberry Pi đi qua MQTT, PostgreSQL và API.</p>
        </div>
        <div class="device-picker">
          <label for="device">THIẾT BỊ</label>
          <select id="device" :value="selectedId" @change="selectDevice">
            <option v-if="!devices.length" value="">Chưa có thiết bị</option>
            <option v-for="item in devices" :key="item.id" :value="item.id">{{ item.name }}</option>
          </select>
          <span class="device-state" :class="isFresh ? 'online' : 'offline'"><i></i>{{ isFresh ? 'Đang cập nhật' : 'Chưa có dữ liệu mới' }}</span>
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
      <div v-else-if="loading" class="notice">Đang kết nối hệ thống local…</div>
      <div v-else-if="!selectedId" class="notice">Đang chờ thiết bị gửi dữ liệu lên MQTT…</div>

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

      <section class="metrics-grid">
        <article class="metric-card heart-card">
          <div class="card-heading"><span class="metric-icon heart-icon">♥</span><span>NHỊP TIM</span></div>
          <div class="metric-value"><strong>{{ current?.heart_rate_bpm ?? '--' }}</strong><span>BPM ~</span></div>
          <p>{{ current?.finger_present ? 'Tín hiệu cảm biến hiện có' : 'Chưa có tín hiệu ngón tay' }}</p>
          <svg class="pulse-chart" viewBox="0 0 100 42" preserveAspectRatio="none" aria-label="Xu hướng nhịp tim">
            <line x1="0" y1="38" x2="100" y2="38" stroke="#294055" stroke-width="0.5" />
            <polyline v-if="heartPoints" :points="heartPoints" fill="none" stroke="#ff6675" stroke-width="1.4" vector-effect="non-scaling-stroke" />
          </svg>
        </article>

        <article class="metric-card"><div class="card-heading"><span class="metric-icon step-icon">↗</span><span>BƯỚC CHÂN</span></div><div class="metric-value"><strong>{{ current?.steps_session ?? '--' }}</strong><span>bước / phiên</span></div><p>Tính từ lần khởi động thiết bị hiện tại</p></article>
        <article class="metric-card"><div class="card-heading"><span class="metric-icon distance-icon">⌁</span><span>QUÃNG ĐƯỜNG</span></div><div class="metric-value"><strong>{{ current ? (current.distance_m_session / 1000).toFixed(3) : '--' }}</strong><span>km ~</span></div><p>Ước tính từ số bước</p></article>
        <article class="metric-card"><div class="card-heading"><span class="metric-icon calorie-icon">✦</span><span>NĂNG LƯỢNG</span></div><div class="metric-value"><strong>{{ current ? current.calories_kcal_session.toFixed(2) : '--' }}</strong><span>kcal ~</span></div><p>Giá trị minh họa, chưa hiệu chuẩn</p></article>
      </section>

      <section class="lower-grid">
        <article class="panel"><div class="panel-title"><div><p class="eyebrow">THIẾT BỊ</p><h2>Trạng thái kết nối</h2></div><span class="panel-dot" :class="isFresh ? 'online' : 'offline'"></span></div><div class="status-row"><span>Dữ liệu cuối</span><strong>{{ timeLabel(current?.measured_at) }}</strong></div><div class="status-row"><span>Server nhận lúc</span><strong>{{ timeLabel(current?.received_at) }}</strong></div><div class="status-row"><span>Phiên khởi động</span><code>{{ current?.boot_id?.slice(0, 8) || '—' }}</code></div></article>
        <article class="panel"><div class="panel-title"><div><p class="eyebrow">NHẬT KÝ</p><h2>Sự kiện gần đây</h2></div><span class="event-count">{{ events.length }}</span></div><p v-if="!events.length" class="empty-state">Chưa có sự kiện ngã hoặc SOS từ thiết bị.</p><ul v-else class="event-list"><li v-for="item in events" :key="item.event_id"><span class="event-bullet"></span><span>{{ eventLabels[item.event_type] || item.event_type }}</span><time>{{ timeLabel(item.occurred_at) }}</time></li></ul></article>
      </section>
      <p class="footnote">BPM, bước và calo hiện chỉ phục vụ thử luồng hệ thống, chưa phải dữ liệu y tế.</p>
    </main>
  </div>
</template>
