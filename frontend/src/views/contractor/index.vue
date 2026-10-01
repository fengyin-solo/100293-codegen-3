<template>
  <section class="page contractor-page" data-module="contractor-qualification">
    <header class="page-head">
      <div>
        <h2>外委单位资质准入</h2>
        <p class="page-desc">按“单位 + 资质类别”建册，先审资质再派工；暂停不可回退准入，清退再进场必须重新报审。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate()">报审外委资质</button>
        <button class="btn" type="button" @click="openDispatchCreate">新增派工项</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reloadAll">
      <label class="filter-item">
        <span>单位 / 证书编号</span>
        <input v-model="filters.keyword" placeholder="按单位或证书编号检索" />
      </label>
      <label class="filter-item">
        <span>准入状态</span>
        <select v-model="filters.status">
          <option value="">全部状态</option>
          <option v-for="status in meta.statuses" :key="status" :value="status">{{ status }}</option>
        </select>
      </label>
      <label class="filter-item">
        <span>资质类别</span>
        <input v-model="filters.category" placeholder="按资质类别检索" />
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <div class="table-block">
      <div class="table-title">
        <h3>资质准入册</h3>
        <span>材料补正从首个未核/缺项继续，已核项不再重核</span>
      </div>
      <table class="data-table">
        <thead>
          <tr>
            <th v-for="column in ledgerColumns" :key="column">{{ column }}</th>
            <th>材料核验</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in rows" :key="String(row.id)">
            <td v-for="column in ledgerColumns" :key="column">
              <span v-if="column === 'status'" :class="['status-badge', statusClass(String(row.status))]">{{ row.status }}</span>
              <span v-else-if="column === '派工状态'" :class="['status-badge', dispatchClass(String(row.派工状态))]">{{ row.派工状态 }}</span>
              <span v-else>{{ row[column] ?? '—' }}</span>
            </td>
            <td>
              <button class="link" type="button" @click="openMaterials(row)">查看 / 补正</button>
            </td>
            <td class="row-actions">
              <button
                v-if="row.status === '待审'"
                class="link"
                type="button"
                @click="runAction(row, '核验材料')"
              >
                继续核验
              </button>
              <button
                v-if="row.status === '待审'"
                class="link success"
                type="button"
                @click="runAction(row, '准入通过')"
              >
                准入通过
              </button>
              <button
                v-if="row.status === '已准入'"
                class="link warning"
                type="button"
                @click="runAction(row, '暂停准入')"
              >
                暂停准入
              </button>
              <button
                v-if="row.status === '已准入' || row.status === '已暂停'"
                class="link danger"
                type="button"
                @click="runAction(row, '清退单位')"
              >
                清退单位
              </button>
              <button
                v-if="row.status === '已清退'"
                class="link"
                type="button"
                @click="openCreate(row)"
              >
                重新报审
              </button>
            </td>
          </tr>
          <tr v-if="!rows.length">
            <td :colspan="ledgerColumns.length + 2" class="empty-state">暂无符合条件的资质建册记录</td>
          </tr>
        </tbody>
      </table>
    </div>

    <div class="table-block dispatch-block">
      <div class="table-title">
        <h3>派工清单同步结果</h3>
        <form class="inline-filter" @submit.prevent="reloadDispatch">
          <select v-model="dispatchFilter">
            <option value="">全部派工状态</option>
            <option v-for="status in dispatchStatuses" :key="status" :value="status">{{ status }}</option>
          </select>
          <button class="btn" type="submit">筛选</button>
        </form>
      </div>
      <table class="data-table">
        <thead>
          <tr>
            <th v-for="column in dispatchColumns" :key="column">{{ column }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in dispatchRows" :key="`dispatch-${String(row.id)}`" :class="{ blocked: !row.可派工 }">
            <td v-for="column in dispatchColumns" :key="column">
              <span v-if="column === '派工状态'" :class="['status-badge', dispatchClass(String(row.派工状态))]">{{ row.派工状态 }}</span>
              <span v-else>{{ row[column] ?? '—' }}</span>
            </td>
          </tr>
          <tr v-if="!dispatchRows.length">
            <td :colspan="dispatchColumns.length" class="empty-state">暂无派工清单记录</td>
          </tr>
        </tbody>
      </table>
    </div>

    <div v-if="showCreate" class="modal-mask" @click.self="closeCreate">
      <section class="modal">
        <header class="modal-head">
          <h3>{{ createForm.id ? '清退后重新报审' : '报审外委资质' }}</h3>
          <button class="modal-close" type="button" @click="closeCreate">×</button>
        </header>
        <p v-if="createForm.id" class="modal-tip warning-text">重新报审会生成新记录，只带出单位与类别，不沿用上一份准入结论或材料。</p>
        <div class="form-grid">
          <label>
            <span>单位名称 *</span>
            <input v-model="createForm.单位名称" :disabled="Boolean(createForm.id)" />
          </label>
          <label>
            <span>资质类别 *</span>
            <input v-model="createForm.资质类别" :disabled="Boolean(createForm.id)" />
          </label>
          <div class="certificate-list">
            <article v-for="(certificate, index) in createForm.certificates" :key="certificate.key" class="certificate-card">
              <header class="certificate-head">
                <strong>资质证明 {{ index + 1 }}</strong>
                <button
                  v-if="createForm.certificates.length > 1"
                  class="link danger"
                  type="button"
                  @click="removeCertificate(index)"
                >
                  删除
                </button>
              </header>
              <div class="form-grid nested">
                <label>
                  <span>证书编号 *</span>
                  <input v-model="certificate.证书编号" />
                </label>
                <label>
                  <span>发证机关 *</span>
                  <input v-model="certificate.发证机关" />
                </label>
                <label>
                  <span>发证机关级别 *</span>
                  <select v-model="certificate.发证机关级别">
                    <option value="" disabled>请选择</option>
                    <option v-for="level in meta.authority_levels" :key="level" :value="level">{{ level }}</option>
                  </select>
                </label>
                <label class="checkbox-line">
                  <input v-model="certificate.发证机关认可" type="checkbox" />
                  <span>发证机关已认可</span>
                </label>
                <label>
                  <span>发证日期 *</span>
                  <input v-model="certificate.发证日期" type="date" />
                </label>
                <label>
                  <span>有效期至 *</span>
                  <input v-model="certificate.有效期至" type="date" />
                </label>
              </div>
            </article>
            <button class="btn ghost" type="button" @click="addCertificate">添加同类资质证明</button>
          </div>
        </div>
        <footer class="modal-foot">
          <button class="btn" type="button" @click="closeCreate">取消</button>
          <button class="btn primary" type="button" :disabled="submitting" @click="submitCreate">提交报审</button>
        </footer>
      </section>
    </div>

    <div v-if="materialTarget" class="modal-mask" @click.self="closeMaterials">
      <section class="modal">
        <header class="modal-head">
          <h3>报审材料逐项核验</h3>
          <button class="modal-close" type="button" @click="closeMaterials">×</button>
        </header>
        <p class="modal-tip">补正后从第一个“待核/缺项”继续；“已核”项保持不变，不重复核验。</p>
        <div class="material-list">
          <label
            v-for="material in materialChecks"
            :key="material.name"
            :class="['material-item', material.state]"
          >
            <input v-model="material.checked" type="checkbox" :disabled="material.state === '已核'" />
            <span>{{ material.name }}</span>
            <em>{{ materialLabel(material.state) }}</em>
          </label>
        </div>
        <footer class="modal-foot">
          <button class="btn" type="button" @click="closeMaterials">关闭</button>
          <button class="btn primary" type="button" :disabled="submitting" @click="submitMaterials">提交本次核验</button>
        </footer>
      </section>
    </div>

    <div v-if="showDispatchCreate" class="modal-mask" @click.self="closeDispatchCreate">
      <section class="modal">
        <header class="modal-head">
          <h3>新增派工项</h3>
          <button class="modal-close" type="button" @click="closeDispatchCreate">×</button>
        </header>
        <p class="modal-tip">提交时先校验最新资质建册；未建册、待审、暂停或资质过期都会被拦截。</p>
        <div class="form-grid">
          <label><span>派工编号 *</span><input v-model="dispatchForm.派工编号" /></label>
          <label><span>单位名称 *</span><input v-model="dispatchForm.单位名称" /></label>
          <label><span>资质类别 *</span><input v-model="dispatchForm.资质类别" /></label>
          <label><span>作业项目 *</span><input v-model="dispatchForm.作业项目" /></label>
          <label><span>计划进场日期 *</span><input v-model="dispatchForm.计划进场" type="date" /></label>
        </div>
        <footer class="modal-foot">
          <button class="btn" type="button" @click="closeDispatchCreate">取消</button>
          <button class="btn primary" type="button" :disabled="submitting" @click="submitDispatchCreate">校验并加入清单</button>
        </footer>
      </section>
    </div>

    <footer class="page-foot">
      <span>共 {{ total }} 条资质建册，{{ dispatchTotal }} 条派工项</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
      <span v-else-if="successMessage" class="success-text">{{ successMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'

import { request } from '@/api/client'

type Json = string | number | boolean | null | Json[] | { [key: string]: Json }
type Row = Record<string, Json>

type CertificateForm = {
  key: number
  证书编号: string
  发证机关: string
  发证机关级别: string
  发证日期: string
  有效期至: string
  发证机关认可: boolean
}

type QualificationForm = {
  id: number | null
  单位名称: string
  资质类别: string
  certificates: CertificateForm[]
}

type MaterialCheck = {
  name: string
  state: string
  checked: boolean
}

const ENDPOINT = '/api/contractor-qualification'
const ledgerColumns = ['单位名称', '资质类别', '申请日期', '材料进度', '证书编号', '发证机关', '发证机关级别', '有效期至', 'status', '派工状态', '派工结论']
const dispatchColumns = ['派工编号', '单位名称', '资质类别', '作业项目', '计划进场', '作业状态', '派工状态', '派工结论']
const dispatchStatuses = ['可派工', '已暂停', '待审', '已清退', '资质过期', '未建册']

const meta = reactive({
  statuses: ['待审', '已准入', '已暂停', '已清退'],
  authority_levels: ['国家级', '省级', '市级', '区县级'],
})
const rows = ref<Row[]>([])
const dispatchRows = ref<Row[]>([])
const total = ref(0)
const dispatchTotal = ref(0)
const errorMessage = ref('')
const successMessage = ref('')
const submitting = ref(false)
const dispatchFilter = ref('')
const filters = reactive({ keyword: '', status: '', category: '' })

const showCreate = ref(false)
const showDispatchCreate = ref(false)
const materialTarget = ref<Row | null>(null)
const materialChecks = ref<MaterialCheck[]>([])

let certificateKeySeed = 0
const createForm = reactive<QualificationForm>(emptyCreateForm())
const dispatchForm = reactive({
  派工编号: '',
  单位名称: '',
  资质类别: '',
  作业项目: '',
  计划进场: '',
})

const stats = computed(() => [
  { label: '可派工单位', value: rows.value.filter(row => row.派工状态 === '可派工').length },
  { label: '待审建册', value: rows.value.filter(row => row.status === '待审').length },
  { label: '已暂停', value: rows.value.filter(row => row.status === '已暂停' || row.派工状态 === '已暂停').length },
  { label: '派工拦截', value: dispatchRows.value.filter(row => !row.可派工).length },
])

function emptyCertificateForm(): CertificateForm {
  return {
    key: certificateKeySeed++,
    证书编号: '',
    发证机关: '',
    发证机关级别: '',
    发证日期: '',
    有效期至: '',
    发证机关认可: true,
  }
}

function emptyCreateForm(): QualificationForm {
  return {
    id: null,
    单位名称: '',
    资质类别: '',
    certificates: [emptyCertificateForm()],
  }
}

function resetFilters() {
  filters.keyword = ''
  filters.status = ''
  filters.category = ''
  void reloadAll()
}

async function reloadMeta() {
  const response = await request(`${ENDPOINT}/meta`)
  if (response.ok) {
    Object.assign(meta, await response.json())
  }
}

async function reloadQualifications() {
  const query = new URLSearchParams()
  if (filters.keyword) query.set('keyword', filters.keyword)
  if (filters.status) query.set('status', filters.status)
  if (filters.category) query.set('category', filters.category)
  const response = await request(`${ENDPOINT}?${query.toString()}`)
  if (!response.ok) throw new Error('资质准入册读取失败')
  const payload = await response.json()
  rows.value = payload.items ?? []
  total.value = payload.total ?? rows.value.length
}

async function reloadDispatch() {
  const query = new URLSearchParams({ size: '500' })
  if (dispatchFilter.value) query.set('availability', dispatchFilter.value)
  const response = await request(`${ENDPOINT}/dispatch/list?${query.toString()}`)
  if (!response.ok) throw new Error('派工清单读取失败')
  const payload = await response.json()
  dispatchRows.value = payload.items ?? []
  dispatchTotal.value = payload.total ?? dispatchRows.value.length
}

async function reloadAll() {
  errorMessage.value = ''
  try {
    await reloadQualifications()
    await reloadDispatch()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '数据读取失败'
  }
}

function openCreate(source?: Row) {
  Object.assign(createForm, emptyCreateForm())
  if (source) {
    createForm.id = Number(source.id)
    createForm.单位名称 = String(source.单位名称 ?? '')
    createForm.资质类别 = String(source.资质类别 ?? '')
  }
  showCreate.value = true
}

function closeCreate() {
  showCreate.value = false
}

function addCertificate() {
  createForm.certificates.push(emptyCertificateForm())
}

function removeCertificate(index: number) {
  createForm.certificates.splice(index, 1)
}

function openDispatchCreate() {
  Object.assign(dispatchForm, {
    派工编号: '',
    单位名称: '',
    资质类别: '',
    作业项目: '',
    计划进场: '',
  })
  showDispatchCreate.value = true
}

function closeDispatchCreate() {
  showDispatchCreate.value = false
}

function openMaterials(row: Row) {
  materialTarget.value = row
  const materials = Array.isArray(row.materials) ? row.materials as Array<Record<string, string>> : []
  materialChecks.value = materials.map(item => ({
    name: item.name,
    state: item.state,
    checked: item.state === '已核',
  }))
}

function closeMaterials() {
  materialTarget.value = null
  materialChecks.value = []
}

async function submitCreate() {
  errorMessage.value = ''
  successMessage.value = ''
  submitting.value = true
  try {
    const payload = {
      单位名称: createForm.单位名称,
      资质类别: createForm.资质类别,
      certificates: createForm.certificates.map(certificate => ({
        证书编号: certificate.证书编号,
        发证机关: certificate.发证机关,
        发证机关级别: certificate.发证机关级别,
        发证日期: certificate.发证日期,
        有效期至: certificate.有效期至,
        发证机关认可: certificate.发证机关认可,
      })),
    }
    const data = await postJson('', payload)
    if (!data.ok) throw new Error(data.message)
    successMessage.value = data.message
    closeCreate()
    await reloadAll()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '报审提交失败'
  } finally {
    submitting.value = false
  }
}

async function submitMaterials() {
  if (!materialTarget.value) return
  errorMessage.value = ''
  successMessage.value = ''
  submitting.value = true
  try {
    const materials = Object.fromEntries(materialChecks.value.map(item => [item.name, item.checked]))
    const data = await postAction(materialTarget.value, '核验材料', { materials })
    if (data.ok) {
      successMessage.value = data.message
      closeMaterials()
      await reloadAll()
    } else {
      errorMessage.value = data.message
    }
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '材料核验失败'
  } finally {
    submitting.value = false
  }
}

async function runAction(row: Row, action: string) {
  errorMessage.value = ''
  successMessage.value = ''
  submitting.value = true
  try {
    const data = await postJson(`/${row.id}/actions`, { action })
    if (!data.ok) throw new Error(data.message)
    successMessage.value = data.message
    await reloadAll()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '状态流转失败'
  } finally {
    submitting.value = false
  }
}

async function postAction(row: Row, action: string, values: Record<string, unknown>) {
  return postJson(`/${row.id}/actions`, { action, values })
}

async function submitDispatchCreate() {
  errorMessage.value = ''
  successMessage.value = ''
  submitting.value = true
  try {
    const response = await request(`${ENDPOINT}/dispatch`, {
      method: 'POST',
      body: JSON.stringify({ values: { ...dispatchForm } }),
    })
    if (!response.ok) throw new Error('派工新增请求未生效')
    const data = await response.json()
    if (!data.ok) throw new Error(data.message)
    successMessage.value = data.message
    closeDispatchCreate()
    await reloadDispatch()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '新增派工失败'
  } finally {
    submitting.value = false
  }
}

async function postJson(path: string, values: Record<string, unknown>) {
  const response = await request(`${ENDPOINT}${path}`, {
    method: 'POST',
    body: JSON.stringify({ values }),
  })
  if (!response.ok) throw new Error('接口请求未生效')
  return response.json() as Promise<{ ok: boolean; message: string; entry: Row | null }>
}

function statusClass(status: string) {
  if (status === '已准入') return 'status-success'
  if (status === '待审') return 'status-pending'
  if (status === '已暂停') return 'status-warning'
  return 'status-danger'
}

function dispatchClass(status: string) {
  if (status === '可派工') return 'status-success'
  if (status === '待审') return 'status-pending'
  if (status === '已暂停') return 'status-warning'
  return 'status-danger'
}

function materialLabel(state: string) {
  if (state === '已核') return '已核，不重核'
  if (state === '缺项') return '缺项，从这里继续'
  return '待核'
}

onMounted(() => {
  void Promise.all([reloadMeta(), reloadAll()])
})
</script>
