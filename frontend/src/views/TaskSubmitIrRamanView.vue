<script setup>
import { computed, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import FormLabelTooltip from '../components/FormLabelTooltip.vue'
import SampleDownloadButton from '../components/SampleDownloadButton.vue'
import TaskIntroCard from '../components/TaskIntroCard.vue'
import { createIrTask, createRamanTask, getApiErrorMessage, uploadFile } from '../api/specAgentApi'

const props = defineProps({
  spectype: {
    type: String,
    default: 'ir',
  },
})

const router = useRouter()
const submitting = ref(false)
const selectedUploadFile = ref(null)
const uploadedFileId = ref('')
const uploadedFilename = ref('')
const lastTaskId = ref('')

const pageTitle = computed(() => (props.spectype === 'raman' ? 'Raman 任务提交' : 'IR 任务提交'))
const uploadHint = computed(() =>
  props.spectype === 'raman'
    ? '支持 .txt / .csv，文件至少包含两列数值，通常为位移与强度。'
    : '支持 .txt / .csv，文件至少包含两列数值，通常为波数与强度。',
)
const sampleAssetPath = computed(() =>
  props.spectype === 'raman' ? '/example-spectra/raman-demo.txt' : '/example-spectra/ir-demo.txt',
)
const sampleDownloadName = computed(() =>
  props.spectype === 'raman' ? 'raman-demo.txt' : 'ir-demo.txt',
)
const introTitle = computed(() =>
  props.spectype === 'raman'
    ? '用于根据拉曼谱图识别官能团或候选分子结构'
    : '用于根据红外谱图识别官能团或候选结构信息',
)
const introDescription = computed(() =>
  props.spectype === 'raman'
    ? '适合对单张 Raman 谱图做智能识别。你可以选择不同分析模式，在官能团解释和候选结构结果之间切换重点。'
    : '适合对单张 IR 谱图做智能识别。你可以根据数据类型和分析范围选择更合适的模式，获得更贴近谱图特征的结果。',
)
const introHighlights = computed(() =>
  props.spectype === 'raman'
    ? ['官能团识别结果', '候选分子结构与评分', '分析范围与分析模式说明']
    : ['官能团识别结果', '候选结构或检索结果', '分析范围与分析模式说明'],
)

const IR_RAMAN_TOOLTIP_TEXT = {
  mode: '分析模式。greedy_decode 为直接生成；beam_search 返回多组生成候选；retrieval 偏向库检索；function_groups 更适合输出官能团解释。',
  k: '候选数量 K。仅在 beam_search 或 retrieval 模式下生效，值越大返回候选越多。',
  range: '分析范围。只截取 x0 到 x1 区间参与分析，x0 必须小于 x1。',
  device: '推理设备。auto 自动选择；cpu 更稳；cuda 需要可用 GPU，通常更快。',
  transmittance: '透射率转吸光度。仅对 IR 有效，只有原始数据是透射率谱时才建议开启。',
}

const form = reactive({
  mode: 'function_groups',
  k: 10,
  x0: 400,
  x1: 4000,
  transmittance: false,
  device: 'auto',
})

/**
 * 处理文件选择（仅缓存，不立即上传）。
 *
 * Args:
 *   file: 上传文件对象。
 *
 * Returns:
 *   boolean
 */
async function handleUpload(file) {
  selectedUploadFile.value = file
  uploadedFileId.value = ''
  uploadedFilename.value = file?.name || ''
  ElMessage.success(`已选择文件：${uploadedFilename.value}`)
  return false
}

/**
 * 构建任务输入对象。
 *
 * Returns:
 *   IR/Raman 输入参数。
 */
function buildInput() {
  return {
    input_type: 'file_id',
    input_path: null,
    file_id: uploadedFileId.value,
  }
}

/**
 * 提交 IR/Raman 任务。
 *
 * Returns:
 *   Promise<void>
 */
async function submitTask() {
  if (!uploadedFileId.value) {
    if (!selectedUploadFile.value) {
      ElMessage.warning('请先选择谱图文件')
      return
    }
  }
  if (form.x0 >= form.x1) {
    ElMessage.warning('x0 必须小于 x1')
    return
  }
  if (selectedUploadFile.value) {
    try {
      const data = await uploadFile(selectedUploadFile.value, props.spectype)
      uploadedFileId.value = data.file_id
      uploadedFilename.value = data.file_name
    } catch (error) {
      ElMessage.error(getApiErrorMessage(error))
      return
    }
  }

  const payload = {
    input: buildInput(),
    params: {
      spectype: props.spectype,
      mode: form.mode,
      k: Number(form.k),
      x0: Number(form.x0),
      x1: Number(form.x1),
      transmittance: props.spectype === 'ir' ? Boolean(form.transmittance) : false,
      device: form.device,
    },
  }

  submitting.value = true
  try {
    const data =
      props.spectype === 'raman'
        ? await createRamanTask(payload)
        : await createIrTask(payload)
    lastTaskId.value = data.task_id
    ElMessage.success(`任务创建成功：${data.task_id}`)
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error))
  } finally {
    submitting.value = false
  }
}

/**
 * 跳转到任务详情页。
 */
function goTaskDetail() {
  if (!lastTaskId.value) {
    return
  }
  router.push(`/tasks/detail/${lastTaskId.value}`)
}
</script>

<template>
  <div class="panel">
    <div class="panel-header">
      <h3 class="panel-title">{{ pageTitle }}</h3>
    </div>
    <div class="panel-body">
      <TaskIntroCard
        :title="introTitle"
        :description="introDescription"
        :highlights="introHighlights"
      />
      <el-form class="task-submit-form" label-width="180px">
        <el-form-item label="上传谱图文件">
          <el-upload :show-file-list="false" :before-upload="handleUpload" accept=".txt,.csv">
            <el-button type="primary" plain>选择文件</el-button>
          </el-upload>
          <SampleDownloadButton
            :asset-path="sampleAssetPath"
            :download-name="sampleDownloadName"
            button-text="下载范例谱图"
          />
          <el-tag v-if="uploadedFilename" style="margin-left: 10px">{{ uploadedFilename }}</el-tag>
          <div class="task-submit-help">{{ uploadHint }}</div>
        </el-form-item>

        <el-divider content-position="left">分析参数</el-divider>
        <el-form-item>
          <template #label>
            <FormLabelTooltip label="分析模式" :tooltip="IR_RAMAN_TOOLTIP_TEXT.mode" />
          </template>
          <el-select v-model="form.mode" style="width: 280px">
            <el-option label="greedy_decode" value="greedy_decode" />
            <el-option label="beam_search" value="beam_search" />
            <el-option label="retrieval" value="retrieval" />
            <el-option label="function_groups" value="function_groups" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="form.mode === 'beam_search' || form.mode === 'retrieval'">
          <template #label>
            <FormLabelTooltip label="候选数量 K" :tooltip="IR_RAMAN_TOOLTIP_TEXT.k" />
          </template>
          <el-input-number v-model="form.k" :min="1" :max="10" />
        </el-form-item>
        <el-form-item>
          <template #label>
            <FormLabelTooltip label="分析范围 x0/x1" :tooltip="IR_RAMAN_TOOLTIP_TEXT.range" />
          </template>
          <el-input-number v-model="form.x0" :min="0" />
          <span style="margin: 0 8px">-</span>
          <el-input-number v-model="form.x1" :min="0" />
        </el-form-item>
        <el-form-item>
          <template #label>
            <FormLabelTooltip label="推理设备" :tooltip="IR_RAMAN_TOOLTIP_TEXT.device" />
          </template>
          <el-radio-group v-model="form.device">
            <el-radio value="auto">auto</el-radio>
            <el-radio value="cpu">cpu</el-radio>
            <el-radio value="cuda">cuda</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item v-if="props.spectype === 'ir'">
          <template #label>
            <FormLabelTooltip label="透射率转吸光度" :tooltip="IR_RAMAN_TOOLTIP_TEXT.transmittance" />
          </template>
          <el-switch v-model="form.transmittance" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="submitting" @click="submitTask">提交任务</el-button>
        </el-form-item>
      </el-form>

      <el-alert
        v-if="lastTaskId"
        type="success"
        :closable="false"
        show-icon
        :title="`任务创建成功：${lastTaskId}`"
      >
        <p>
          可在任务中心查看进度和结果，
          <el-link type="primary" @click="goTaskDetail">点击查看任务详情</el-link>
        </p>
      </el-alert>
    </div>
  </div>
</template>

<style scoped>
:deep(.el-form-item__label) {
  white-space: nowrap;
}
</style>
