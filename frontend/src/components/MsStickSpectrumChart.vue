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
  labelPeaks: {
    type: Array,
    default: () => [],
  },
  title: {
    type: String,
    default: 'MS 谱图',
  },
})

const chartRef = ref(null)
let chart = null
let resizeObserver = null

/**
 * 构建 MS 棒状谱图配置。
 *
 * Returns:
 *   ECharts 配置对象。
 */
function buildOption() {
  const points = (props.xValues || []).map((xValue, index) => [Number(xValue), Number(props.yValues[index])])
  const validPoints = points.filter((item) => Number.isFinite(item[0]) && Number.isFinite(item[1]))
  const lineSegments = validPoints.flatMap((item) => [[item[0], 0], [item[0], item[1]], [null, null]])
  const labelPoints = (props.labelPeaks || [])
    .map((item) => ({
      value: [Number(item?.mz), Number(item?.intensity)],
      label: `${Number(item?.mz).toFixed(4)}`,
    }))
    .filter((item) => Number.isFinite(item.value[0]) && Number.isFinite(item.value[1]))

  const xNumbers = validPoints.map((item) => item[0])
  const yNumbers = validPoints.map((item) => item[1])
  const xMin = xNumbers.length > 0 ? Math.min(...xNumbers) : null
  const xMax = xNumbers.length > 0 ? Math.max(...xNumbers) : null
  const yMax = yNumbers.length > 0 ? Math.max(...yNumbers) : 1

  return {
    title: {
      text: props.title,
      left: 'center',
      textStyle: {
        color: '#203556',
        fontSize: 14,
        fontWeight: 600,
      },
    },
    grid: {
      left: 56,
      right: 22,
      top: 46,
      bottom: 42,
    },
    tooltip: {
      trigger: 'axis',
      formatter: (params) => {
        const first = params?.find((item) => Array.isArray(item?.data))
        if (!first || !Array.isArray(first.data)) {
          return ''
        }
        const [mz, intensity] = first.data
        if (!Number.isFinite(Number(mz)) || !Number.isFinite(Number(intensity))) {
          return ''
        }
        return `m/z: ${Number(mz).toFixed(4)}<br/>Intensity: ${Number(intensity).toFixed(2)}`
      },
    },
    xAxis: {
      type: 'value',
      name: 'm/z',
      nameLocation: 'middle',
      nameGap: 26,
      min: xMin,
      max: xMax,
      splitLine: {
        lineStyle: { color: '#ebf0f8' },
      },
      axisLine: {
        lineStyle: { color: '#8ea6cc' },
      },
    },
    yAxis: {
      type: 'value',
      name: 'Intensity',
      splitLine: {
        lineStyle: { color: '#ebf0f8' },
      },
      axisLine: {
        lineStyle: { color: '#8ea6cc' },
      },
      min: 0,
      max: yMax > 0 ? yMax * 1.18 : 1,
    },
    series: [
      {
        type: 'line',
        data: lineSegments,
        connectNulls: false,
        symbol: 'none',
        lineStyle: {
          color: '#0f7b6c',
          width: 1.35,
        },
        z: 2,
      },
      {
        type: 'scatter',
        data: labelPoints.map((item) => item.value),
        symbolSize: 7,
        itemStyle: {
          color: '#e35b38',
        },
        label: {
          show: true,
          position: 'top',
          color: '#4a2f2a',
          fontSize: 11,
          formatter: (params) => {
            const matched = labelPoints.find((item) => item.value[0] === params.value[0] && item.value[1] === params.value[1])
            return matched?.label || ''
          },
        },
        z: 4,
      },
    ],
    animationDuration: 260,
  }
}

/**
 * 渲染 MS 谱图。
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
  () => [props.xValues, props.yValues, props.labelPeaks, props.title],
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
  <div ref="chartRef" class="ms-stick-spectrum-chart" />
</template>

<style scoped>
.ms-stick-spectrum-chart {
  width: 100%;
  height: 360px;
}
</style>
