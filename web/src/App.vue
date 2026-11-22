<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { api } from './api'

const devices = ref([])
const selectedId = ref('')
const latest = ref(null)
const history = ref([])
const events = ref([])
const error = ref('')
const loading = ref(true)
const updatedAt = ref(null)
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
      error.value = ''
      return
    }
    const [last, samples, recentEvents] = await Promise.all([
      api.latest(selectedId.value), api.history(selectedId.value), api.events(selectedId.value),
    ])
    latest.value = last
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
  logActivity('device_select', selectedId.value)
  refresh()
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
          <p class="intro-copy">Dữ liệu mô phỏng đi qua MQTT, PostgreSQL và API. Chưa kết nối cảm biến Pi thật.</p>
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

      <div v-if="error" class="notice error">Không tải được dữ liệu: {{ error }}</div>
      <div v-else-if="loading" class="notice">Đang kết nối hệ thống local…</div>
      <div v-else-if="!selectedId" class="notice">Đang chờ mock publisher gửi dữ liệu lên MQTT…</div>

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

        <article class="metric-card"><div class="card-heading"><span class="metric-icon step-icon">↗</span><span>BƯỚC CHÂN</span></div><div class="metric-value"><strong>{{ current?.steps_session ?? '--' }}</strong><span>bước / phiên</span></div><p>Tính từ lần khởi động mock hiện tại</p></article>
        <article class="metric-card"><div class="card-heading"><span class="metric-icon distance-icon">⌁</span><span>QUÃNG ĐƯỜNG</span></div><div class="metric-value"><strong>{{ current ? (current.distance_m_session / 1000).toFixed(3) : '--' }}</strong><span>km ~</span></div><p>Ước tính từ số bước</p></article>
        <article class="metric-card"><div class="card-heading"><span class="metric-icon calorie-icon">✦</span><span>NĂNG LƯỢNG</span></div><div class="metric-value"><strong>{{ current ? current.calories_kcal_session.toFixed(2) : '--' }}</strong><span>kcal ~</span></div><p>Giá trị minh họa, chưa hiệu chuẩn</p></article>
      </section>

      <section class="lower-grid">
        <article class="panel"><div class="panel-title"><div><p class="eyebrow">THIẾT BỊ</p><h2>Trạng thái kết nối</h2></div><span class="panel-dot" :class="isFresh ? 'online' : 'offline'"></span></div><div class="status-row"><span>Dữ liệu cuối</span><strong>{{ timeLabel(current?.measured_at) }}</strong></div><div class="status-row"><span>Server nhận lúc</span><strong>{{ timeLabel(current?.received_at) }}</strong></div><div class="status-row"><span>Phiên khởi động</span><code>{{ current?.boot_id?.slice(0, 8) || '—' }}</code></div></article>
        <article class="panel"><div class="panel-title"><div><p class="eyebrow">NHẬT KÝ</p><h2>Sự kiện gần đây</h2></div><span class="event-count">{{ events.length }}</span></div><p v-if="!events.length" class="empty-state">Chưa có sự kiện. Mock sẽ gửi thử ngã và SOS định kỳ.</p><ul v-else class="event-list"><li v-for="item in events" :key="item.event_id"><span class="event-bullet"></span><span>{{ eventLabels[item.event_type] || item.event_type }}</span><time>{{ timeLabel(item.occurred_at) }}</time></li></ul></article>
      </section>
      <p class="footnote">Bản local sử dụng dữ liệu mock. BPM, bước và calo chỉ phục vụ thử luồng hệ thống.</p>
    </main>
  </div>
</template>
