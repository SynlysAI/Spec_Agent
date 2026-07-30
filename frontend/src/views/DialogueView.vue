<script setup>
import { nextTick, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Loading } from '@element-plus/icons-vue'
import {
  dialogueChatStream,
  getApiErrorMessage,
  listDialogueModels,
  listDialogueAnalysisTypes,
  listDialogueReports,
} from '../api/specAgentApi'
import MessageContent from '../components/MessageContent.vue'

const loadingModels = ref(false)
const loadingTypes = ref(false)
const loadingReports = ref(false)
const sending = ref(false)
const dialogueModels = ref([])
const analysisTypes = ref([])
const reports = ref([])
const messages = ref([])
const chatScrollerRef = ref(null)
const abortControllerRef = ref(null)

const form = reactive({
  modelKey: '',
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
  loadingModels.value = true
  loadingTypes.value = true
  try {
    const [modelData, typeData] = await Promise.all([
      listDialogueModels(),
      listDialogueAnalysisTypes(),
    ])
    dialogueModels.value = modelData.items || []
    if (!dialogueModels.value.some((item) => item.model_key === form.modelKey)) {
      form.modelKey = modelData.default_model_key || dialogueModels.value[0]?.model_key || ''
    }
    analysisTypes.value = typeData.items || []
    if (!analysisTypes.value.some((item) => item.analysis_type === form.analysisType) && analysisTypes.value.length > 0) {
      form.analysisType = analysisTypes.value[0].analysis_type
    }
    await loadReports()
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error))
  } finally {
    loadingModels.value = false
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
 * 发送问答消息（流式）。
 *
 * Returns:
 *   Promise<void>
 */
async function sendMessage() {
  if (!form.modelKey) {
    ElMessage.warning('请先选择问答模型')
    return
  }
  const question = form.question.trim()
  if (!question) {
    ElMessage.warning('请输入问题')
    return
  }
  const historyPayload = messages.value
    .filter((item) => !item.streaming && item.content)
    .slice(-12)
    .map((item) => ({
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
  const assistantMsg = reactive({
    role: 'assistant',
    content: '',
    streaming: true,
  })
  messages.value.push(assistantMsg)
  await scrollToBottom()

  const controller = new AbortController()
  abortControllerRef.value = controller

  await dialogueChatStream(
    {
      model_key: form.modelKey,
      analysis_type: form.analysisType,
      report_id: form.reportId || null,
      question,
      history: historyPayload,
      system_prompt: form.systemPrompt,
    },
    {
      signal: controller.signal,
      onChunk: (_chunk, fullText) => {
        assistantMsg.content = fullText
        scrollToBottom()
      },
      onDone: (fullText) => {
        assistantMsg.content = fullText
        assistantMsg.streaming = false
        sending.value = false
        abortControllerRef.value = null
        scrollToBottom()
      },
      onError: (errorMessage) => {
        if (errorMessage.includes('该模型暂不可用')) {
          ElMessage.error('该模型暂不可用')
          messages.value = messages.value.filter((item) => item !== assistantMsg)
        } else if (!assistantMsg.content) {
          assistantMsg.content = `对话服务调用失败：${errorMessage}`
        } else {
          assistantMsg.content = `${assistantMsg.content}\n\n[错误] ${errorMessage}`
        }
        assistantMsg.streaming = false
        sending.value = false
        abortControllerRef.value = null
        scrollToBottom()
      },
    },
  )
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
  if (abortControllerRef.value) {
    abortControllerRef.value.abort()
    abortControllerRef.value = null
  }
  sending.value = false
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
          <el-form-item label="问答模型">
            <el-select
              v-model="form.modelKey"
              style="width: 100%"
              :loading="loadingModels"
              placeholder="请选择问答模型"
            >
              <el-option
                v-for="item in dialogueModels"
                :key="item.model_key"
                :label="item.label"
                :value="item.model_key"
              />
            </el-select>
          </el-form-item>
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
            <div class="chat-content">
              <template v-if="item.role === 'user'">{{ item.content }}</template>
              <template v-else-if="item.content">
                <MessageContent :content="item.content" />
              </template>
              <div v-else class="thinking-content">
                <el-icon class="is-loading"><Loading /></el-icon>
                <span>正在思考中，请稍候...</span>
              </div>
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
            <div class="dialogue-power-note">当前问答模型由昇腾提供算力支持</div>
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

.dialogue-power-note {
  color: #4a5a74;
  font-size: 12px;
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
}

.chat-item.user .chat-content {
  background: #e8f2ff;
  white-space: pre-wrap;
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
  align-items: center;
  justify-content: space-between;
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

<style>
.chat-markdown {
  color: inherit;
  font-size: 14px;
  line-height: 1.7;
  word-break: break-word;
}

.chat-markdown > :first-child {
  margin-top: 0;
}

.chat-markdown > :last-child {
  margin-bottom: 0;
}

.chat-markdown p {
  margin: 0 0 8px;
}

.chat-markdown h1,
.chat-markdown h2,
.chat-markdown h3,
.chat-markdown h4,
.chat-markdown h5,
.chat-markdown h6 {
  margin: 12px 0 6px;
  font-weight: 600;
  line-height: 1.4;
}

.chat-markdown h1 { font-size: 18px; }
.chat-markdown h2 { font-size: 16px; }
.chat-markdown h3 { font-size: 15px; }
.chat-markdown h4,
.chat-markdown h5,
.chat-markdown h6 { font-size: 14px; }

.chat-markdown ul,
.chat-markdown ol {
  margin: 6px 0;
  padding-left: 22px;
}

.chat-markdown li {
  margin: 2px 0;
}

.chat-markdown a {
  color: #1677ff;
  text-decoration: underline;
}

.chat-markdown blockquote {
  margin: 6px 0;
  padding: 4px 12px;
  border-left: 3px solid #cbd5e1;
  color: #64748b;
}

.chat-markdown code {
  padding: 1px 5px;
  border-radius: 4px;
  background: rgba(135, 150, 170, 0.18);
  font-family: "JetBrains Mono", "Fira Code", Menlo, Consolas, monospace;
  font-size: 13px;
}

.chat-markdown pre {
  margin: 8px 0;
  padding: 10px 12px;
  background: #f6f8fa;
  border-radius: 8px;
  overflow-x: auto;
  font-size: 13px;
  line-height: 1.5;
}

.chat-markdown pre code {
  padding: 0;
  background: transparent;
  font-size: inherit;
}

.chat-markdown table {
  width: 100%;
  max-width: 100%;
  margin: 8px 0;
  border-collapse: collapse;
  font-size: 13px;
  display: block;
  overflow-x: auto;
}

.chat-markdown th,
.chat-markdown td {
  padding: 6px 10px;
  border: 1px solid #d9e2ec;
  text-align: left;
}

.chat-markdown th {
  background: rgba(31, 94, 255, 0.06);
  font-weight: 600;
}

.chat-markdown img {
  max-width: 100%;
}

.chat-markdown hr {
  margin: 12px 0;
  border: 0;
  border-top: 1px solid #e4ebf3;
}
</style>
