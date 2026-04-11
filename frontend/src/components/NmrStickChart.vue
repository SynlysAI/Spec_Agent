<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as echarts from 'echarts'

const props = defineProps({
  shifts: {
    type: Array,
    default: () => [],
  },
  title: {
    type: String,
    default: '',
  },
  color: {
    type: String,
    default: '#2f74ff',
  },
  axisMin: {
    type: Number,
    default: null,
  },
  axisMax: {
    type: Number,
    default: null,
  },
})

const chartRef = ref(null)
let chart = null
let resizeObserver = null

const normalizedShifts = computed(() =>
  (props.shifts || [])
    .map((item) => Number(item))
    .filter((item) => Number.isFinite(item))
    .sort((a, b) => b - a),
)

/**
 * 构建 NMR 棒状谱图的 ECharts 配置。
 *
 * Args:
 *   shifts: 化学位移列表。
 *
 * Returns:
 *   ECharts Option 对象。
 */
function buildChartOption(shifts) {
  const lineSegments = shifts.flatMap((value) => [[value, 0], [value, 1], [null, null]])
  return {
    title: {
      text: props.title,
      left: 'center',
      textStyle: {
        color: '#2a3f62',
        fontWeight: 600,
        fontSize: 14,
      },
    },
    grid: {
      left: 32,
      right: 18,
      top: 46,
      bottom: 28,
    },
    tooltip: {
      trigger: 'axis',
      formatter: (params) => {
        const first = params?.[0]
        const ppm = Number(first?.axisValue)
        if (!Number.isFinite(ppm)) {
          return ''
        }
        return `化学位移: ${ppm.toFixed(2)} ppm`
      },
    },
    xAxis: {
      type: 'value',
      inverse: true,
      name: '化学位移 (ppm)',
      nameLocation: 'middle',
      nameGap: 24,
      min: props.axisMin,
      max: props.axisMax,
      splitLine: {
        lineStyle: { color: '#e7eefb' },
      },
      axisLine: {
        lineStyle: { color: '#90a7cc' },
      },
    },
    yAxis: {
      type: 'value',
      min: 0,
      max: 1.1,
      show: false,
    },
    series: [
      {
        type: 'line',
        data: lineSegments,
        connectNulls: false,
        symbol: 'none',
        lineStyle: {
          color: props.color,
          width: 2,
        },
      },
    ],
    animationDuration: 350,
  }
}

/**
 * 渲染或更新谱图。
 *
 * Returns:
 *   Promise<void>
 */
async function renderChart() {
  await nextTick()
  if (!chartRef.value) {
    return
  }
  if (!chart) {
    chart = echarts.init(chartRef.value)
  }
  chart.setOption(buildChartOption(normalizedShifts.value), true)
}

/**
 * 清理图表与尺寸监听器。
 */
function disposeChart() {
  if (resizeObserver) {
    resizeObserver.disconnect()
    resizeObserver = null
  }
  if (chart) {
    chart.dispose()
    chart = null
  }
}

onMounted(async () => {
  await renderChart()
  if (chartRef.value) {
    resizeObserver = new ResizeObserver(() => {
      chart?.resize()
    })
    resizeObserver.observe(chartRef.value)
  }
})

watch(
  () => [normalizedShifts.value, props.title, props.color, props.axisMin, props.axisMax],
  async () => {
    await renderChart()
  },
  { deep: true },
)

onBeforeUnmount(() => {
  disposeChart()
})
</script>

<template>
  <div ref="chartRef" class="nmr-stick-chart" />
</template>

<style scoped>
.nmr-stick-chart {
  width: 100%;
  height: 320px;
}
</style>
