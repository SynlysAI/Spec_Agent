<script setup>
import { reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import NmrStickChart from '../components/NmrStickChart.vue'
import { getApiErrorMessage, nmrserverForward, nmrserverReverse, nmrserverSearch } from '../api/specAgentApi'

const activeMainTab = ref('forward')
const forwardSpectrumTab = ref('c13')

const forwardLoading = ref(false)
const reverseLoading = ref(false)
const searchLoading = ref(false)

const forwardItems = ref([])
const reverseItems = ref([])
const searchItems = ref([])

const forwardForm = reactive({
  smiles_input: '',
})

const reverseForm = reactive({
  h_shifts_input: '',
  h_split_input: '',
  c_shifts_input: '',
  formula: '',
  allowed_elements: '',
  candidates: '',
})

const searchForm = reactive({
  h_shifts_input: '',
  h_split_input: '',
  c_shifts_input: '',
  num_search: 500,
  topk: 10,
  allowed_elements: 'C,H,N,O',
})

const forwardExampleSmiles = ['CCO', 'C(C[C@H]1CCCc2ccccc21)=C1CC1', 'C1=CC=CC=C1'].join('\n')
const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000/api/v1'

/**
 * 将原始预测结果拆分为 13C 与 1H 化学位移列表。
 *
 * Args:
 *   item: 单个分子预测结果对象。
 *
 * Returns:
 *   包含 cShifts 与 hShifts 的结果对象。
 */
function splitForwardShifts(item) {
  const atomsShift = Array.isArray(item?.atoms_shift) ? item.atoms_shift : []
  const atomsElement = Array.isArray(item?.atoms_element) ? item.atoms_element : []

  const cShifts = []
  const hShifts = []

  atomsShift.forEach((value, index) => {
    const shift = Number(value)
    if (!Number.isFinite(shift)) {
      return
    }
    const element = Number(atomsElement[index])
    if (element === 6) {
      cShifts.push(shift)
    } else if (element === 1) {
      hShifts.push(shift)
    }
  })

  cShifts.sort((a, b) => b - a)
  hShifts.sort((a, b) => b - a)
  return { cShifts, hShifts }
}

/**
 * 填充正向预测示例数据。
 */
function fillForwardExample() {
  forwardForm.smiles_input = forwardExampleSmiles
}

/**
 * 填充反向预测示例数据。
 */
function fillReverseExample() {
  reverseForm.h_shifts_input = '7.30, 7.18, 7.05, 3.92, 1.25'
  reverseForm.h_split_input = 's,d,d,t,m'
  reverseForm.c_shifts_input = '170.1, 135.4, 129.8, 127.3, 60.2, 14.3'
  reverseForm.formula = 'C9H10O2'
  reverseForm.allowed_elements = 'C,H,O'
  reverseForm.candidates = 'CCOC1=CC=CC=C1,CC(=O)OC1=CC=CC=C1'
}

/**
 * 填充数据库搜索示例数据。
 */
function fillSearchExample() {
  searchForm.h_shifts_input = '7.26, 7.12, 6.98, 3.85'
  searchForm.h_split_input = 's,d,t,m'
  searchForm.c_shifts_input = '165.2, 134.8, 128.4, 114.6, 55.3'
}

/**
 * 构建外部分子结构图片地址。
 *
 * Args:
 *   smiles: 分子 SMILES。
 *
 * Returns:
 *   可直接用于 img 标签的 URL。
 */
function buildMolImageUrl(smiles) {
  if (!smiles) {
    return ''
  }
  return `${apiBaseUrl}/chemistry/molecule-image?smiles=${encodeURIComponent(smiles)}&size=320`
}

/**
 * 复制文本到系统剪贴板。
 *
 * Args:
 *   text: 需要复制的文本。
 *
 * Returns:
 *   Promise<void>
 */
async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text)
    ElMessage.success('SMILES 已复制到剪贴板')
  } catch (error) {
    ElMessage.error(`复制失败：${getApiErrorMessage(error)}`)
  }
}

/**
 * 提交 NMRServer 正向预测请求。
 *
 * Returns:
 *   Promise<void>
 */
async function submitForward() {
  if (!forwardForm.smiles_input.trim()) {
    ElMessage.warning('请先输入 SMILES 分子式')
    return
  }
  forwardLoading.value = true
  try {
    const data = await nmrserverForward({ ...forwardForm })
    forwardItems.value = data.items || []
    ElMessage.success(`预测完成，共 ${forwardItems.value.length} 个分子结果`)
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error))
  } finally {
    forwardLoading.value = false
  }
}

/**
 * 提交 NMRServer 反向预测请求。
 *
 * Returns:
 *   Promise<void>
 */
async function submitReverse() {
  if (!reverseForm.h_shifts_input.trim() && !reverseForm.c_shifts_input.trim()) {
    ElMessage.warning('请至少输入氢谱或碳谱化学位移')
    return
  }
  reverseLoading.value = true
  try {
    const data = await nmrserverReverse({ ...reverseForm })
    reverseItems.value = data.items || []
    ElMessage.success(`反向预测完成，共 ${reverseItems.value.length} 条候选结果`)
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error))
  } finally {
    reverseLoading.value = false
  }
}

/**
 * 提交 NMRServer 数据库搜索请求。
 *
 * Returns:
 *   Promise<void>
 */
async function submitSearch() {
  if (!searchForm.h_shifts_input.trim() && !searchForm.c_shifts_input.trim()) {
    ElMessage.warning('请至少输入氢谱或碳谱化学位移')
    return
  }
  searchLoading.value = true
  try {
    const data = await nmrserverSearch({ ...searchForm })
    searchItems.value = data.items || []
    ElMessage.success(`数据库搜索完成，返回 ${searchItems.value.length} 条结果`)
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error))
  } finally {
    searchLoading.value = false
  }
}
</script>

<template>
  <div class="panel">
    <div class="panel-header">
      <h3 class="panel-title">核磁预测服务（NMRServer）</h3>
    </div>
    <div class="panel-body">
      <el-tabs v-model="activeMainTab">
        <el-tab-pane label="正向预测" name="forward">
          <el-alert type="info" :closable="false" class="desc-block">
            <template #title>
              输入 SMILES 分子式，预测 13C NMR 与 1H NMR 化学位移。支持每行一个分子同时预测。
            </template>
          </el-alert>

          <el-form label-width="140px">
            <el-form-item label="SMILES 分子式">
              <el-input
                v-model="forwardForm.smiles_input"
                type="textarea"
                :rows="5"
                :placeholder="`每行一个 SMILES，示例：\n${forwardExampleSmiles}`"
              />
            </el-form-item>
          </el-form>

          <div class="action-row">
            <el-button plain @click="fillForwardExample">使用示例数据</el-button>
            <el-button type="primary" :loading="forwardLoading" @click="submitForward">开始预测</el-button>
          </div>

          <el-divider />
          <div class="result-title">预测结果</div>
          <el-empty v-if="forwardItems.length === 0" description="暂无结果，请先提交预测" />
          <el-collapse v-else accordion>
            <el-collapse-item
              v-for="(item, index) in forwardItems"
              :key="`${item.smiles || 'mol'}_${index}`"
              :name="String(index)"
            >
              <template #title>
                <div class="result-collapse-title">分子 {{ index + 1 }}：{{ item.smiles || '-' }}</div>
              </template>
              <el-row :gutter="14">
                <el-col :xl="7" :lg="8" :md="9" :sm="24">
                  <div class="molecule-card">
                    <div class="molecule-title">分子结构图</div>
                    <img
                      v-if="item.smiles"
                      :src="buildMolImageUrl(item.smiles)"
                      alt="molecule"
                      class="molecule-image"
                    />
                    <div class="smiles-line">{{ item.smiles || '-' }}</div>
                    <el-button text size="small" @click="copyText(item.smiles || '')">复制 SMILES</el-button>
                  </div>
                </el-col>
                <el-col :xl="17" :lg="16" :md="15" :sm="24">
                  <el-tabs v-model="forwardSpectrumTab" type="card">
                    <el-tab-pane label="13C 碳谱" name="c13">
                      <div class="metric-row">
                        <span>化学位移数量：</span>
                        <strong>{{ splitForwardShifts(item).cShifts.length }}</strong>
                      </div>
                      <NmrStickChart
                        v-if="splitForwardShifts(item).cShifts.length > 0"
                        :shifts="splitForwardShifts(item).cShifts"
                        title="13C NMR 碳谱"
                        color="#ff6b6b"
                        :axis-min="0"
                        :axis-max="220"
                      />
                      <el-empty
                        v-else
                        description="未检测到碳原子化学位移"
                        :image-size="80"
                        class="inner-empty"
                      />
                      <el-table
                        v-if="splitForwardShifts(item).cShifts.length > 0"
                        :data="splitForwardShifts(item).cShifts.map((v, i) => ({ index: i + 1, shift: v }))"
                        size="small"
                        stripe
                        class="shift-table"
                      >
                        <el-table-column prop="index" label="序号" width="80" />
                        <el-table-column label="化学位移 (ppm)">
                          <template #default="scope">
                            {{ Number(scope.row.shift).toFixed(2) }}
                          </template>
                        </el-table-column>
                      </el-table>
                    </el-tab-pane>
                    <el-tab-pane label="1H 氢谱" name="h1">
                      <div class="metric-row">
                        <span>化学位移数量：</span>
                        <strong>{{ splitForwardShifts(item).hShifts.length }}</strong>
                      </div>
                      <NmrStickChart
                        v-if="splitForwardShifts(item).hShifts.length > 0"
                        :shifts="splitForwardShifts(item).hShifts"
                        title="1H NMR 氢谱"
                        color="#35b8ac"
                        :axis-min="0"
                        :axis-max="15"
                      />
                      <el-empty
                        v-else
                        description="未检测到氢原子化学位移"
                        :image-size="80"
                        class="inner-empty"
                      />
                      <el-table
                        v-if="splitForwardShifts(item).hShifts.length > 0"
                        :data="splitForwardShifts(item).hShifts.map((v, i) => ({ index: i + 1, shift: v }))"
                        size="small"
                        stripe
                        class="shift-table"
                      >
                        <el-table-column prop="index" label="序号" width="80" />
                        <el-table-column label="化学位移 (ppm)">
                          <template #default="scope">
                            {{ Number(scope.row.shift).toFixed(2) }}
                          </template>
                        </el-table-column>
                      </el-table>
                    </el-tab-pane>
                  </el-tabs>
                </el-col>
              </el-row>
            </el-collapse-item>
          </el-collapse>
        </el-tab-pane>

        <el-tab-pane label="反向预测" name="reverse">
          <el-alert type="info" :closable="false" class="desc-block">
            <template #title>
              输入氢谱/碳谱化学位移，预测可能的分子结构；支持分子式、元素、候选分子等约束条件。
            </template>
          </el-alert>

          <el-row :gutter="16">
            <el-col :md="12" :sm="24">
              <el-form label-width="170px">
                <el-form-item label="氢谱化学位移">
                  <el-input
                    v-model="reverseForm.h_shifts_input"
                    type="textarea"
                    :rows="3"
                    placeholder="示例：7.30, 7.18, 7.05, 3.92, 1.25"
                  />
                </el-form-item>
                <el-form-item label="峰裂分类型">
                  <el-input v-model="reverseForm.h_split_input" placeholder="示例：s,d,d,t,m" />
                </el-form-item>
              </el-form>
            </el-col>
            <el-col :md="12" :sm="24">
              <el-form label-width="170px">
                <el-form-item label="碳谱化学位移">
                  <el-input
                    v-model="reverseForm.c_shifts_input"
                    type="textarea"
                    :rows="3"
                    placeholder="示例：170.1, 135.4, 129.8, 127.3, 60.2, 14.3"
                  />
                </el-form-item>
                <el-form-item label="分子式约束">
                  <el-input v-model="reverseForm.formula" placeholder="可选，例如：C9H10O2" />
                </el-form-item>
                <el-form-item label="允许元素">
                  <el-input v-model="reverseForm.allowed_elements" placeholder="可选，例如：C,H,O" />
                </el-form-item>
                <el-form-item label="候选分子（SMILES）">
                  <el-input
                    v-model="reverseForm.candidates"
                    placeholder="可选，逗号分隔 SMILES"
                  />
                </el-form-item>
              </el-form>
            </el-col>
          </el-row>

          <div class="action-row">
            <el-button plain @click="fillReverseExample">使用示例数据</el-button>
            <el-button type="primary" :loading="reverseLoading" @click="submitReverse">开始反向预测</el-button>
          </div>

          <el-divider />
          <div class="result-title">反向预测结果</div>
          <el-empty v-if="reverseItems.length === 0" description="暂无结果，请先提交预测" />
          <div v-else class="result-list">
            <div v-for="(item, index) in reverseItems" :key="`${item.smiles || 'reverse'}_${index}`" class="result-card">
              <div class="card-head">
                <div class="card-rank">候选 {{ index + 1 }}</div>
                <el-button text @click="copyText(item.smiles || '')">复制 SMILES</el-button>
              </div>
              <el-image
                v-if="item.smiles"
                :src="buildMolImageUrl(item.smiles)"
                fit="contain"
                class="result-molecule-image"
                :preview-src-list="[buildMolImageUrl(item.smiles)]"
              />
              <div class="smiles-line">{{ item.smiles || '-' }}</div>
              <div class="score-grid">
                <div class="score-item">
                  <div class="score-name">总分</div>
                  <div class="score-value">{{ Number(item.score || 0).toFixed(4) }}</div>
                </div>
                <div class="score-item">
                  <div class="score-name">氢谱得分</div>
                  <div class="score-value">{{ Number(item.H_score || 0).toFixed(4) }}</div>
                </div>
                <div class="score-item">
                  <div class="score-name">碳谱得分</div>
                  <div class="score-value">{{ Number(item.C_score || 0).toFixed(4) }}</div>
                </div>
              </div>
            </div>
          </div>
        </el-tab-pane>

        <el-tab-pane label="数据库搜索" name="search">
          <el-alert type="info" :closable="false" class="desc-block">
            <template #title>
              输入化学位移后在 NMR 数据库内检索匹配分子，支持搜索规模、Top-K 与元素约束。
            </template>
          </el-alert>

          <el-row :gutter="16">
            <el-col :md="12" :sm="24">
              <el-form label-width="170px">
                <el-form-item label="氢谱化学位移">
                  <el-input
                    v-model="searchForm.h_shifts_input"
                    type="textarea"
                    :rows="3"
                    placeholder="示例：7.26, 7.12, 6.98, 3.85"
                  />
                </el-form-item>
                <el-form-item label="峰裂分类型">
                  <el-input v-model="searchForm.h_split_input" placeholder="示例：s,d,t,m" />
                </el-form-item>
              </el-form>
            </el-col>
            <el-col :md="12" :sm="24">
              <el-form label-width="170px">
                <el-form-item label="碳谱化学位移">
                  <el-input
                    v-model="searchForm.c_shifts_input"
                    type="textarea"
                    :rows="3"
                    placeholder="示例：165.2, 134.8, 128.4, 114.6, 55.3"
                  />
                </el-form-item>
                <el-form-item label="搜索数量">
                  <el-input-number v-model="searchForm.num_search" :min="10" :max="10000" :step="100" />
                </el-form-item>
                <el-form-item label="返回结果数（Top-K）">
                  <el-input-number v-model="searchForm.topk" :min="1" :max="100" />
                </el-form-item>
                <el-form-item label="允许元素">
                  <el-input v-model="searchForm.allowed_elements" placeholder="默认：C,H,N,O" />
                </el-form-item>
              </el-form>
            </el-col>
          </el-row>

          <div class="action-row">
            <el-button plain @click="fillSearchExample">使用示例数据</el-button>
            <el-button type="primary" :loading="searchLoading" @click="submitSearch">开始数据库搜索</el-button>
          </div>

          <el-divider />
          <div class="result-title">数据库搜索结果</div>
          <el-empty v-if="searchItems.length === 0" description="暂无结果，请先提交搜索" />
          <div v-else class="result-list">
            <div v-for="(item, index) in searchItems" :key="`${item.smiles || 'search'}_${index}`" class="result-card">
              <div class="card-head">
                <div class="card-rank">结果 {{ index + 1 }}</div>
                <el-button text @click="copyText(item.smiles || '')">复制 SMILES</el-button>
              </div>
              <el-image
                v-if="item.smiles"
                :src="buildMolImageUrl(item.smiles)"
                fit="contain"
                class="result-molecule-image"
                :preview-src-list="[buildMolImageUrl(item.smiles)]"
              />
              <div class="smiles-line">{{ item.smiles || '-' }}</div>
              <div class="score-grid">
                <div class="score-item">
                  <div class="score-name">总分</div>
                  <div class="score-value">{{ Number(item.score || 0).toFixed(4) }}</div>
                </div>
                <div class="score-item">
                  <div class="score-name">氢谱得分</div>
                  <div class="score-value">{{ Number(item.H_score || 0).toFixed(4) }}</div>
                </div>
                <div class="score-item">
                  <div class="score-name">碳谱得分</div>
                  <div class="score-value">{{ Number(item.C_score || 0).toFixed(4) }}</div>
                </div>
              </div>
            </div>
          </div>
        </el-tab-pane>
      </el-tabs>
    </div>
  </div>
</template>

<style scoped>
.desc-block {
  margin-bottom: 14px;
}

.action-row {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 4px;
}

.result-title {
  margin-bottom: 10px;
  font-weight: 700;
  color: #2a3f62;
}

.result-collapse-title {
  font-weight: 600;
  color: #2a3f62;
}

.molecule-card {
  border: 1px solid #e2ecfb;
  border-radius: 10px;
  padding: 10px;
  background: #fafcff;
}

.molecule-title {
  font-size: 13px;
  color: #506b93;
  margin-bottom: 8px;
}

.molecule-image {
  width: 100%;
  max-height: 220px;
  object-fit: contain;
  border: 1px dashed #d7e2f5;
  border-radius: 8px;
  background: #fff;
}

.smiles-line {
  margin-top: 8px;
  padding: 6px 8px;
  border-radius: 8px;
  background: #eef4ff;
  color: #35527f;
  word-break: break-all;
  font-family: Consolas, 'Courier New', monospace;
  font-size: 12px;
}

.metric-row {
  color: #58739d;
  margin-bottom: 6px;
}

.shift-table {
  margin-top: 10px;
}

.inner-empty {
  padding: 0 0 10px;
}

.result-list {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.result-card {
  border: 1px solid #deebfb;
  border-radius: 12px;
  background: linear-gradient(180deg, #ffffff 0%, #f8fbff 100%);
  padding: 12px;
}

.card-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.card-rank {
  color: #1f4676;
  font-weight: 700;
}

.score-grid {
  margin-top: 10px;
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
}

.result-molecule-image {
  margin-top: 8px;
  width: 100%;
  height: 160px;
  border: 1px solid #e1ecfc;
  border-radius: 8px;
  background: #f6f9ff;
}

.score-item {
  border: 1px solid #ddeafb;
  border-radius: 8px;
  padding: 8px 10px;
  background: #ffffff;
}

.score-name {
  font-size: 12px;
  color: #6b82a8;
}

.score-value {
  margin-top: 4px;
  font-family: Consolas, 'Courier New', monospace;
  font-weight: 700;
  color: #2a4d7f;
}

@media (max-width: 1200px) {
  .result-list {
    grid-template-columns: 1fr;
  }
}
</style>
