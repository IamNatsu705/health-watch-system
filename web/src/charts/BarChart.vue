<script setup>
// Cột nhóm SVG: đầu cột bo 4px, khe 2px giữa các cột, tooltip khi rê chuột/chạm từng cột.
import { computed, onMounted, onUnmounted, ref } from 'vue'

const props = defineProps({
  groups: { type: Array, required: true },   // [{ label, values: { key: number|null } }]
  series: { type: Array, required: true },   // [{ key, label, color }]
  formatY: { type: Function, default: (y) => Math.round(y).toLocaleString('vi-VN') },
  labelKeys: { type: Array, default: () => [] },  // chỉ ghi số trực tiếp trên các series này
  height: { type: Number, default: 220 },
  yMax: { type: Number, default: null },
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
const pad = { top: 14, right: 8, bottom: 40, left: 40 }
const hover = ref(null)

function niceCeil(value) {
  // Trần "đẹp" gần nhất: 1, 1,2, 1,5, 2, 2,5, 3, 4, 5, 6, 8, 10 × 10^k.
  const magnitude = 10 ** Math.floor(Math.log10(value))
  const step = [1, 1.2, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10].find(s => s * magnitude >= value)
  return step * magnitude
}
const top = computed(() => {
  if (props.yMax) return props.yMax
  const all = props.groups.flatMap(g => props.series.map(s => g.values[s.key] || 0))
  return niceCeil(Math.max(1, ...all))
})
const plotH = computed(() => props.height - pad.top - pad.bottom)
const groupW = computed(() => (W.value - pad.left - pad.right) / props.groups.length)
const barW = computed(() => Math.min(34, (groupW.value * 0.78) / props.series.length - 2))
const sy = (v) => props.height - pad.bottom - (v / top.value) * plotH.value
const ticks = computed(() => [0, 0.25, 0.5, 0.75, 1].map(f => f * top.value))

const bars = computed(() => props.groups.flatMap((g, gi) => {
  const width = props.series.length * (barW.value + 2) - 2
  const start = pad.left + gi * groupW.value + (groupW.value - width) / 2
  return props.series.map((s, si) => {
    const value = g.values[s.key]
    const x = start + si * (barW.value + 2)
    const y = value === null || value === undefined ? sy(0) : sy(value)
    return { key: `${gi}-${s.key}`, group: g.label, series: s, value, x, y, h: sy(0) - y }
  })
}))
function barPath(b) {
  if (b.value === null || b.value === undefined || b.h <= 0) return ''
  const r = Math.min(4, b.h, barW.value / 2)
  const base = sy(0)
  return `M${b.x},${base}V${b.y + r}Q${b.x},${b.y} ${b.x + r},${b.y}H${b.x + barW.value - r}Q${b.x + barW.value},${b.y} ${b.x + barW.value},${b.y + r}V${base}Z`
}
</script>

<template>
  <div ref="root" class="chart" :aria-label="ariaLabel" role="img">
    <svg :viewBox="`0 0 ${W} ${height}`" :width="W" :height="height" @mouseleave="hover = null">
      <g class="grid">
        <line v-for="t in ticks" :key="t" :x1="pad.left" :x2="W - pad.right" :y1="sy(t)" :y2="sy(t)" />
      </g>
      <g class="axis">
        <text v-for="t in ticks" :key="`t${t}`" :x="pad.left - 6" :y="sy(t) + 4" text-anchor="end">{{ formatY(t) }}</text>
        <text v-for="(g, gi) in groups" :key="g.label" :x="pad.left + (gi + 0.5) * groupW" :y="height - 22" text-anchor="middle">{{ g.label }}</text>
        <text v-for="(g, gi) in groups" :key="`s${g.label}`" :x="pad.left + (gi + 0.5) * groupW" :y="height - 8" text-anchor="middle" class="axis-sub">{{ g.sublabel || '' }}</text>
      </g>
      <g v-for="b in bars" :key="b.key">
        <path :d="barPath(b)" :fill="b.series.color" />
        <text v-if="labelKeys.includes(b.series.key) && b.value !== null && b.value !== undefined" class="bar-label" :x="b.x + barW / 2" :y="b.y - 5" text-anchor="middle">{{ formatY(b.value) }}</text>
        <rect :x="b.x - 1" :y="pad.top" :width="barW + 2" :height="plotH" fill="transparent"
              @mouseenter="hover = b" @touchstart.passive="hover = b" />
      </g>
    </svg>
    <div v-if="hover" class="chart-tip" :style="{ left: `${Math.min(Math.max((hover.x + barW / 2) / W * 100, 18), 82)}%` }">
      <strong>{{ hover.group }}</strong>
      <span><i :style="{ background: hover.series.color }"></i>{{ hover.series.label }}: <b>{{ hover.value === null || hover.value === undefined ? '—' : formatY(hover.value) }}</b></span>
    </div>
  </div>
</template>
