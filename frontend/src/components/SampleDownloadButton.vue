<script setup>
const props = defineProps({
  assetPath: {
    type: String,
    required: true,
  },
  buttonText: {
    type: String,
    default: '下载范例文件',
  },
  downloadName: {
    type: String,
    default: '',
  },
})

/**
 * 下载前端静态目录中的范例文件。
 */
function downloadSampleFile() {
  if (typeof window === 'undefined') {
    return
  }
  const link = document.createElement('a')
  link.href = new URL(props.assetPath, window.location.origin).toString()
  if (props.downloadName) {
    link.download = props.downloadName
  }
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
}
</script>

<template>
  <el-link
    type="primary"
    :underline="false"
    class="task-submit-inline-link"
    @click.prevent="downloadSampleFile"
  >
    {{ buttonText }}
  </el-link>
</template>
