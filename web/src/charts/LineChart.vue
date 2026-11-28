<script setup>
// Biểu đồ đường SVG nhẹ: lưới mờ, đường 2px, crosshair + tooltip khi rê chuột/chạm.
import { computed, onMounted, onUnmounted, ref } from 'vue'

const props = defineProps({
  series: { type: Array, required: true },   // [{ key, label, color, dashed, points: [[x, y], ...] }]
  formatX: { type: Function, default: (x) => String(x) },
  formatY: { type: Function, default: (y) => Math.round(y).toLocaleString('vi-VN') },
  height: { type: Number, default: 200 },
  ariaLabel: { type: String, default: '' },
})

const W = ref(600)
const root = ref(null)
let observer
onMounted(() => {
  // Vẽ theo kích thước thật của khung để chữ không bị kéo giãn trên điện thoại.
  observer = new ResizeObserver(([entry]) => { W.value = Math.max(260, Math.round(entry.contentRect.width)) })
  observer.observe(root.value)
})
onUnmounted(() => observer?.disconnect())
const pad = { top: 12, right: 44, bottom: 26, left: 44 }
const hover = ref(null)

const visible = computed(() => props.series.filter(s => s.points.some(p => p[1] !== null && p[1] !== undefined)))
const xs = computed(() => visible.value.flatMap(s => s.points.map(p => p[0])))
const ys = computed(() => visible.value.flatMap(s => s.points.map(p => p[1]).filter(v => v !== null && v !== undefined)))
const xMin = computed(() => Math.min(...xs.value))
const xMax = computed(() => Math.max(...xs.value))
function niceCeil(value) {
  // Trần "đẹp" gần nhất: 1, 1,2, 1,5, 2, 2,5, 3, 4, 5, 6, 8, 10 × 10^k.
  const magnitude = 10 ** Math.floor(Math.log10(value))
  const step = [1, 1.2, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10].find(s => s * magnitude >= value)
  return step * magnitude
}
const yMax = computed(() => niceCeil(Math.max(1, ...ys.value)))
const sx = (x) => pad.left + (xMax.value === xMin.value ? 0 : (x - xMin.value) / (xMax.value - xMin.value)) * (W.value - pad.left - pad.right)
const sy = (y) => props.height - pad.bottom - (y / yMax.value) * (props.height - pad.top - pad.bottom)

const yTicks = computed(() => [0, 0.25, 0.5, 0.75, 1].map(f => f * yMax.value))
const xTicks = computed(() => {
  if (!xs.value.length) return []
  return [0, 0.5, 1].map(f => xMin.value + f * (xMax.value - xMin.value))
})
function path(points) {
  let d = ''
  let pen = false
  for (const [x, y] of points) {
    if (y === null || y === undefined) { pen = false; continue }
    d += `${pen ? 'L' : 'M'}${sx(x).toFixed(1)},${sy(y).toFixed(1)}`
    pen = true
  }
  return d
}
const ends = computed(() => {
  const placed = []
  const gap = 13
  return visible.value
    .map(s => {
      const last = [...s.points].reverse().find(p => p[1] !== null && p[1] !== undefined)
      return { key: s.key, value: last[1], y: sy(last[1]) }
    })
    .sort((a, b) => b.y - a.y)
    .filter((item, i, all) => i === 0 || item.value !== all[i - 1].value)
    .map(item => {
      const y = placed.length && placed[placed.length - 1] - item.y < gap ? placed[placed.length - 1] - gap : item.y
      placed.push(y)
      return { ...item, y }
    })
})

function onTouch(event) {
  const touch = event.touches[0]
  if (touch) onMove({ currentTarget: event.currentTarget, clientX: touch.clientX })
}

function onMove(event) {
  const box = event.currentTarget.getBoundingClientRect()
  const px = ((event.clientX - box.left) / box.width) * W.value
  const reference = visible.value[0]?.points || []
  if (!reference.length) return
  let best = 0
  for (let i = 1; i < reference.length; i++) {
    if (Math.abs(sx(reference[i][0]) - px) < Math.abs(sx(reference[best][0]) - px)) best = i
  }
  const x = reference[best][0]
  hover.value = {
    left: (sx(x) / W.value) * 100,
    x,
    rows: visible.value.map(s => ({ ...s, value: (s.points.find(p => p[0] === x) || [])[1] })),
  }
}
</script>

<template>
  <div ref="root" class="chart" :aria-label="ariaLabel" role="img">
    <p v-if="!visible.length" class="chart-empty">Chưa đủ dữ liệu để vẽ.</p>
    <template v-else>
      <svg :viewBox="`0 0 ${W} ${height}`" :width="W" :height="height" @mousemove="onMove" @touchmove.passive="onTouch" @mouseleave="hover = null">
        <g class="grid">
          <line v-for="t in yTicks" :key="`y${t}`" :x1="pad.left" :x2="W - pad.right" :y1="sy(t)" :y2="sy(t)" />
        </g>
        <g class="axis">
          <text v-for="t in yTicks" :key="`yl${t}`" :x="pad.left - 6" :y="sy(t) + 4" text-anchor="end">{{ formatY(t) }}</text>
          <text v-for="(t, i) in xTicks" :key="`xl${i}`" :x="sx(t)" :y="height - 6" :text-anchor="i === 0 ? 'start' : (i === xTicks.length - 1 ? 'end' : 'middle')">{{ formatX(t) }}</text>
        </g>
        <path v-for="s in visible" :key="s.key" :d="path(s.points)" :stroke="s.color" :stroke-dasharray="s.dashed ? '6 5' : null" fill="none" stroke-width="2" stroke-linejoin="round" vector-effect="non-scaling-stroke" />
        <g class="ends">
          <text v-for="e in ends" :key="`e${e.key}`" :x="W - pad.right + 6" :y="e.y + 4">{{ formatY(e.value) }}</text>
        </g>
        <line v-if="hover" class="crosshair" :x1="hover.left / 100 * W" :x2="hover.left / 100 * W" :y1="pad.top" :y2="height - pad.bottom" />
        <rect :x="pad.left" :y="0" :width="W - pad.left - pad.right" :height="height" fill="transparent" />
      </svg>
      <div v-if="hover" class="chart-tip" :style="{ left: `${Math.min(Math.max(hover.left, 18), 82)}%` }">
        <strong>{{ formatX(hover.x) }}</strong>
        <span v-for="row in hover.rows" :key="row.key"><i :style="{ background: row.color }"></i>{{ row.label }}: <b>{{ row.value === null || row.value === undefined ? '—' : formatY(row.value) }}</b></span>
      </div>
    </template>
  </div>
</template>
