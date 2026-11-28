<script setup>
// So sánh đếm bước CÓ AI và KHÔNG AI trên dữ liệu trực tiếp từ Pi (Pi luôn gửi cả hai bộ đếm).
import { computed, ref } from 'vue'
import BarChart from './charts/BarChart.vue'
import LineChart from './charts/LineChart.vue'

const props = defineProps({
  daily: { type: Array, default: () => [] },
  history: { type: Array, default: () => [] },
  current: { type: Object, default: null },
  fresh: { type: Boolean, default: false },
})

// Bảng màu dataviz (dark), đã kiểm tra mù màu trên nền thẻ #142331.
const AI = { key: 'ai', label: 'Có AI', color: '#338ced' }
const ALG = { key: 'algorithm', label: 'Không AI (chỉ thuật toán)', color: '#00a888' }

const HIDE_KEY = 'health-watch-hide-ai-compare'
const hidden = ref(localStorage.getItem(HIDE_KEY) === '1')
function toggle() {
  hidden.value = !hidden.value
  localStorage.setItem(HIDE_KEY, hidden.value ? '1' : '0')
}

const number = (v) => (v === null || v === undefined ? '—' : Math.round(v).toLocaleString('vi-VN'))
const today = computed(() => (props.daily.length ? props.daily[props.daily.length - 1] : null))
const hasModel = computed(() => Boolean(props.current?.step_model))
const todayDiff = computed(() => {
  const t = today.value
  if (!t?.sessions || t.steps_ai === null || t.steps_ai === undefined) return null
  return t.steps_algorithm - t.steps_ai
})

// Phiên đang chạy: hai bộ đếm cộng dồn theo thời gian server nhận (cùng boot_id).
const sessionSeries = computed(() => {
  const bootId = props.current?.boot_id
  const rows = props.history.filter(r => r.boot_id === bootId && !r.legacy)
  const points = (field) => rows.map(r => [new Date(r.received_at).getTime(), r[field]])
  return [
    { ...ALG, points: points('steps_algorithm_session') },
    { ...AI, points: points('steps_ai_session') },
  ]
})
const clock = (ms) => new Date(ms).toLocaleTimeString('vi-VN', { hour: '2-digit', minute: '2-digit', second: '2-digit' })

const weekGroups = computed(() => props.daily.map(d => ({
  label: `${d.date.slice(8, 10)}/${d.date.slice(5, 7)}`,
  values: { ai: d.sessions ? d.steps_ai : null, algorithm: d.sessions ? d.steps_algorithm : null },
})))

</script>

<template>
  <section class="compare-panel" aria-labelledby="compare-title">
    <div class="compare-head">
      <div>
        <p class="eyebrow">AI ĐẾM BƯỚC</p>
        <h2 id="compare-title">Có AI và không AI</h2>
      </div>
      <button type="button" class="compare-toggle" :aria-expanded="!hidden" @click="toggle">{{ hidden ? 'Hiện so sánh' : 'Ẩn so sánh' }}</button>
    </div>

    <template v-if="!hidden">
      <div class="compare-block">
        <p v-if="!hasModel" class="compare-note">Pi chưa nạp mô hình AI, nên chỉ có số của thuật toán.</p>
        <div class="compare-tiles">
          <div class="compare-tile"><span class="swatch" :style="{ background: AI.color }"></span><small>Hôm nay · có AI</small><strong>{{ today?.sessions ? number(today.steps_ai) : '--' }}</strong></div>
          <div class="compare-tile"><span class="swatch" :style="{ background: ALG.color }"></span><small>Hôm nay · không AI</small><strong>{{ today?.sessions ? number(today.steps_algorithm) : '--' }}</strong></div>
          <div class="compare-tile wide">
            <small>Chênh lệch</small>
            <strong v-if="todayDiff === null">--</strong>
            <strong v-else-if="todayDiff > 0">AI bỏ {{ number(todayDiff) }} bước</strong>
            <strong v-else-if="todayDiff < 0">AI đếm thêm {{ number(-todayDiff) }} bước</strong>
            <strong v-else>Bằng nhau</strong>
            <p>AI bỏ các đỉnh nằm trong khoảng không phải đi bộ (vẫy tay, gõ phím, rung xe).</p>
          </div>
        </div>
        <div class="compare-charts">
          <figure>
            <figcaption>Phiên đang chạy · bước cộng dồn {{ fresh ? '' : '(dữ liệu cũ)' }}</figcaption>
            <div class="legend"><span><i :style="{ background: AI.color }"></i>{{ AI.label }}</span><span><i :style="{ background: ALG.color }"></i>{{ ALG.label }}</span></div>
            <LineChart :series="sessionSeries" :format-x="clock" :height="190" aria-label="Số bước cộng dồn của phiên, có AI và không AI" />
          </figure>
          <figure>
            <figcaption>7 ngày gần nhất</figcaption>
            <div class="legend"><span><i :style="{ background: AI.color }"></i>{{ AI.label }}</span><span><i :style="{ background: ALG.color }"></i>{{ ALG.label }}</span></div>
            <BarChart :groups="weekGroups" :series="[AI, ALG]" :height="190" aria-label="Số bước theo ngày, có AI và không AI" />
          </figure>
        </div>
        <p class="compare-note">Khi chạy trực tiếp không có số bước thật để đối chiếu. Muốn kiểm chứng trên thiết bị: vừa đi vừa đếm tay, hoặc ghi phiên bằng <code>record_imu.py</code>.</p>
      </div>
    </template>
  </section>
</template>
