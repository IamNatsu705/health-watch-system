<script setup>
// So sánh đếm bước CÓ AI và KHÔNG AI: (1) trực tiếp từ Pi, (2) kiểm định trên dữ liệu thật có video.
import { computed, ref } from 'vue'
import BarChart from './charts/BarChart.vue'
import LineChart from './charts/LineChart.vue'
import evaluation from './data/step_evaluation.json'

const props = defineProps({
  daily: { type: Array, default: () => [] },
  history: { type: Array, default: () => [] },
  current: { type: Object, default: null },
  fresh: { type: Boolean, default: false },
})

// Bảng màu dataviz (dark), đã kiểm tra mù màu trên nền thẻ #142331.
const AI = { key: 'ai', label: 'Có AI', color: '#338ced' }
const ALG = { key: 'algorithm', label: 'Không AI (chỉ thuật toán)', color: '#00a888' }
const OLD = { key: 'old', label: 'Thuật toán cũ (peak-v1)', color: '#e76624' }
const TRUTH = { key: 'truth', label: 'Số bước thật (video)', color: '#e9f1f7', dashed: true }

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

const evalGroups = evaluation.groups.map(g => {
  const [dataset, ...rest] = g.label.split(' · ')
  return { label: dataset, sublabel: rest.join(' · '), values: g.mape }
})
const examples = evaluation.examples.map(e => ({
  title: e.title,
  series: [
    { ...TRUTH, points: e.series.map(r => [r[0], r[1]]) },
    { ...OLD, points: e.series.map(r => [r[0], r[2]]) },
    { ...ALG, points: e.series.map(r => [r[0], r[3]]) },
    { ...AI, points: e.series.map(r => [r[0], r[4]]) },
  ],
}))
const percent = (v) => `${Number(v).toLocaleString('vi-VN', { maximumFractionDigits: 1 })}%`
const seconds = (v) => `${Math.round(v)} s`
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
        <h3>Trên thiết bị này (dữ liệu trực tiếp)</h3>
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

      <div class="compare-block">
        <h3>Kiểm định trên dữ liệu thật có video gán nhãn</h3>
        <figure>
          <figcaption>Sai số trung bình mỗi người/phiên (%), thấp hơn là tốt hơn</figcaption>
          <div class="legend"><span><i :style="{ background: OLD.color }"></i>{{ OLD.label }}</span><span><i :style="{ background: ALG.color }"></i>{{ ALG.label }}</span><span><i :style="{ background: AI.color }"></i>{{ AI.label }}</span></div>
          <BarChart :groups="evalGroups" :series="[OLD, ALG, AI]" :label-keys="['old', 'algorithm', 'ai']" :format-y="percent" :y-max="100" :height="240" aria-label="Sai số đếm bước của ba bộ đếm trên OxWalk và Clemson" />
        </figure>
        <div class="compare-charts">
          <figure v-for="example in examples" :key="example.title">
            <figcaption>{{ example.title }}</figcaption>
            <div class="legend"><span v-for="s in example.series" :key="s.key"><i :class="{ dashed: s.dashed }" :style="{ background: s.dashed ? 'transparent' : s.color, borderColor: s.color }"></i>{{ s.label }}</span></div>
            <LineChart :series="example.series" :format-x="seconds" :height="190" :aria-label="`Ví dụ: ${example.title}`" />
          </figure>
        </div>
        <p class="compare-note">{{ evaluation.note }} Mô hình: {{ evaluation.model }}. Số liệu do <code>{{ evaluation.generated_by }}</code> sinh ra; CSV gốc ở <code>docs/figures/</code>.</p>
      </div>
    </template>
  </section>
</template>
