<script setup>
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as echarts from 'echarts'

const props = defineProps({
  xValues: {
    type: Array,
    default: () => [],
  },
  yValues: {
    type: Array,
    default: () => [],
  },
  title: {
    type: String,
    default: '谱图预览',
  },
  xAxisName: {
    type: String,
    default: '波数 (cm⁻¹)',
  },
  yAxisName: {
    type: String,
    default: '强度',
  },
  inverseXAxis: {
    type: Boolean,
    default: false,
  },
})

const chartRef = ref(null)
let chart = null
let resizeObserver = null

/**
 * 构建谱图折线图配置。
 *
 * Returns:
 *   ECharts 配置对象。
 */
function buildOption() {
  const lineData = props.xValues.map((x, idx) => [Number(x), Number(props.yValues[idx])])
  const xNumbers = lineData.map((item) => item[0]).filter((item) => Number.isFinite(item))
  let xMin = null
  let xMax = null
  if (xNumbers.length > 0) {
    xMin = Math.min(...xNumbers)
    xMax = Math.max(...xNumbers)
    if (xMin === xMax) {
      xMin -= 1
      xMax += 1
    }
  }

  return {
    title: {
      text: props.title,
      left: 'center',
      textStyle: { fontSize: 14, color: '#2a3f62' },
    },
    grid: {
      left: 56,
      right: 20,
      top: 44,
      bottom: 40,
    },
    tooltip: {
      trigger: 'axis',
      formatter: (params) => {
        const first = params?.[0]
        if (!first) {
          return ''
        }
        const [x, y] = first.data
        return `${props.xAxisName}: ${Number(x).toFixed(3)}<br/>${props.yAxisName}: ${Number(y).toFixed(5)}`
      },
    },
    xAxis: {
      type: 'value',
      name: props.xAxisName,
      inverse: Boolean(props.inverseXAxis),
      min: xMin,
      max: xMax,
      nameLocation: 'middle',
      nameGap: 26,
      splitLine: { lineStyle: { color: '#ecf2fb' } },
      axisLine: {
        lineStyle: { color: '#8ea6cc' },
        onZero: false,
      },
    },
    yAxis: {
      type: 'value',
      name: props.yAxisName,
      position: 'left',
      splitLine: { lineStyle: { color: '#ecf2fb' } },
      axisLine: {
        lineStyle: { color: '#8ea6cc' },
        onZero: false,
      },
    },
    series: [
      {
        type: 'line',
        data: lineData,
        symbol: 'none',
        lineStyle: { color: '#2f74ff', width: 1.5 },
      },
    ],
    animationDuration: 260,
  }
}

/**
 * 渲染图表。
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
  chart.setOption(buildOption(), true)
}

onMounted(async () => {
  await renderChart()
  if (chartRef.value) {
    resizeObserver = new ResizeObserver(() => chart?.resize())
    resizeObserver.observe(chartRef.value)
  }
})

watch(
  () => [props.xValues, props.yValues, props.title, props.xAxisName, props.yAxisName, props.inverseXAxis],
  async () => {
    await renderChart()
  },
  { deep: true },
)

onBeforeUnmount(() => {
  if (resizeObserver) {
    resizeObserver.disconnect()
    resizeObserver = null
  }
  if (chart) {
    chart.dispose()
    chart = null
  }
})
</script>

<template>
  <div ref="chartRef" class="spectrum-preview-chart" />
</template>

<style scoped>
.spectrum-preview-chart {
  width: 100%;
  height: 340px;
}
</style>
