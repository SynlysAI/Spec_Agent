<script setup>
import { nextTick, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Loading } from '@element-plus/icons-vue'
import {
  dialogueChat,
  getApiErrorMessage,
  listDialogueAnalysisTypes,
  listDialogueReports,
} from '../api/specAgentApi'

const loadingTypes = ref(false)
const loadingReports = ref(false)
const sending = ref(false)
const analysisTypes = ref([])
const reports = ref([])
const messages = ref([])
const chatScrollerRef = ref(null)

const form = reactive({
  analysisType: 'none',
  reportId: '',
  systemPrompt: '你是一个专业的谱图分析助手，请基于报告内容回答用户问题，先给结论，再给依据。',
  question: '',
})

/**
 * 初始化问答页面数据。
 *
 * Returns:
 *   Promise<void>
 */
async function initPage() {
  loadingTypes.value = true
  try {
    const data = await listDialogueAnalysisTypes()
    analysisTypes.value = data.items || []
    if (!analysisTypes.value.some((item) => item.analysis_type === form.analysisType) && analysisTypes.value.length > 0) {
      form.analysisType = analysisTypes.value[0].analysis_type
    }
    await loadReports()
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error))
  } finally {
    loadingTypes.value = false
  }
}

/**
 * 加载指定分析类型报告列表。
 *
 * Returns:
 *   Promise<void>
 */
async function loadReports() {
  if (!form.analysisType || form.analysisType === 'none') {
    reports.value = []
    form.reportId = ''
    return
  }
  loadingReports.value = true
  try {
    const data = await listDialogueReports(form.analysisType)
    reports.value = data.items || []
    if (!reports.value.some((item) => item.report_id === form.reportId)) {
      form.reportId = reports.value.length > 0 ? reports.value[0].report_id : ''
    }
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error))
  } finally {
    loadingReports.value = false
  }
}

/**
 * 发送问答消息。
 *
 * Returns:
 *   Promise<void>
 */
async function sendMessage() {
  const question = form.question.trim()
  if (!question) {
    ElMessage.warning('请输入问题')
    return
  }
  const historyPayload = messages.value.slice(-12).map((item) => ({
    role: item.role,
    content: item.content,
  }))
  messages.value.push({
    role: 'user',
    content: question,
  })
  form.question = ''
  await scrollToBottom()

  sending.value = true
  try {
    const data = await dialogueChat({
      analysis_type: form.analysisType,
      report_id: form.reportId || null,
      question,
      history: historyPayload,
      system_prompt: form.systemPrompt,
    })
    messages.value.push({
      role: 'assistant',
      content: data.answer || '',
    })
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error))
    messages.value.push({
      role: 'assistant',
      content: '对话服务调用失败，请稍后重试。',
    })
  } finally {
    sending.value = false
    await scrollToBottom()
  }
}

/**
 * 处理输入框回车发送。
 *
 * Args:
 *   event: 键盘事件对象。
 */
function handleEnterSend(event) {
  if (event.shiftKey) {
    return
  }
  event.preventDefault()
  if (!sending.value) {
    sendMessage()
  }
}

/**
 * 清空当前会话消息。
 */
function clearMessages() {
  messages.value = []
}

/**
 * 滚动到底部。
 *
 * Returns:
 *   Promise<void>
 */
async function scrollToBottom() {
  await nextTick()
  const scroller = chatScrollerRef.value
  if (scroller) {
    scroller.scrollTop = scroller.scrollHeight
  }
}

onMounted(async () => {
  await initPage()
})
</script>

<template>
  <div class="dialogue-page">
    <div class="panel config-panel">
      <div class="panel-header">
        <h3 class="panel-title">问答配置</h3>
      </div>
      <div class="panel-body">
        <el-form label-width="110px">
          <el-form-item label="基础 Prompt">
            <el-input
              v-model="form.systemPrompt"
              type="textarea"
              :rows="4"
              placeholder="可选：自定义系统提示词"
            />
          </el-form-item>
          <el-form-item label="分析类型">
            <el-select
              v-model="form.analysisType"
              style="width: 100%"
              :loading="loadingTypes"
              @change="loadReports"
            >
              <el-option
                v-for="item in analysisTypes"
                :key="item.analysis_type"
                :label="`${item.label}（${item.report_count}）`"
                :value="item.analysis_type"
              />
            </el-select>
          </el-form-item>
          <el-form-item label="报告选择">
            <el-select
              v-model="form.reportId"
              style="width: 100%"
              clearable
              filterable
              :loading="loadingReports"
              placeholder="可选：选择一份历史报告"
            >
              <el-option
                v-for="item in reports"
                :key="item.report_id"
                :label="`${item.task_id} ｜ ${item.created_at}`"
                :value="item.report_id"
              />
            </el-select>
          </el-form-item>
        </el-form>

        <el-alert
          type="info"
          :closable="false"
          show-icon
          title="提示"
          description="建议先选择分析类型和报告，再提问“结论总结/异常点/参数解释”等问题。"
        />
      </div>
    </div>

    <div class="panel chat-panel">
      <div class="panel-header panel-header-inline">
        <h3 class="panel-title">问答对话</h3>
        <el-button text type="primary" @click="clearMessages">清空会话</el-button>
      </div>
      <div class="panel-body chat-body">
        <div ref="chatScrollerRef" class="chat-scroll">
          <div v-if="messages.length === 0" class="chat-empty">
            还没有会话消息，输入问题开始对话。
          </div>
          <div
            v-for="(item, index) in messages"
            :key="`${item.role}-${index}`"
            class="chat-item"
            :class="item.role"
          >
            <div class="chat-role">{{ item.role === 'user' ? '你' : '助手' }}</div>
            <div class="chat-content">{{ item.content }}</div>
          </div>
          <div v-if="sending" class="chat-item assistant thinking">
            <div class="chat-role">助手</div>
            <div class="chat-content thinking-content">
              <el-icon class="is-loading"><Loading /></el-icon>
              <span>正在思考中，请稍候...</span>
            </div>
          </div>
        </div>

        <div class="chat-editor">
          <el-input
            v-model="form.question"
            type="textarea"
            :rows="3"
            placeholder="请输入你的问题，例如：请总结该报告中最重要的三点。"
            @keydown.enter="handleEnterSend"
          />
          <div class="chat-actions">
            <el-button type="primary" :loading="sending" @click="sendMessage">发送</el-button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.dialogue-page {
  display: grid;
  grid-template-columns: 340px 1fr;
  gap: 16px;
}

.panel-header-inline {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.chat-body {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.chat-scroll {
  height: 480px;
  overflow: auto;
  border: 1px solid #e4e8f0;
  border-radius: 10px;
  padding: 12px;
  background: #fbfcff;
}

.chat-empty {
  color: #8a94a8;
  font-size: 13px;
}

.chat-item {
  margin-bottom: 12px;
}

.chat-role {
  font-size: 12px;
  color: #7d879a;
  margin-bottom: 4px;
}

.chat-content {
  padding: 10px 12px;
  border-radius: 10px;
  line-height: 1.55;
  white-space: pre-wrap;
}

.chat-item.user .chat-content {
  background: #e8f2ff;
}

.chat-item.assistant .chat-content {
  background: #f2f5fa;
}

.thinking-content {
  display: flex;
  align-items: center;
  gap: 8px;
}

.chat-actions {
  margin-top: 8px;
  display: flex;
  justify-content: flex-end;
}

@media (max-width: 1080px) {
  .dialogue-page {
    grid-template-columns: 1fr;
  }

  .chat-scroll {
    height: 420px;
  }
}
</style>
