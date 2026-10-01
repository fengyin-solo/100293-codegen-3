<template>
  <section class="page" data-module="contractor">
    <header class="page-head">
      <div>
        <h2>外委单位资质准入</h2>
        <p class="page-desc">
          按「单位 × 资质类别」建册：准入状态只能 待审→已准入→已暂停→已清退 单向推进；
          清退后重新报审不沿用旧结论；材料缺项退回补正、从断点项接着核；准入结论实时同步派工清单。
        </p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">受理报审</button>
      </div>
    </header>

    <div class="tabs">
      <button
        class="tab"
        :class="{ active: tab === 'roster' }"
        type="button"
        @click="switchTab('roster')"
      >
        准入名册
      </button>
      <button
        class="tab"
        :class="{ active: tab === 'dispatch' }"
        type="button"
        @click="switchTab('dispatch')"
      >
        派工清单
      </button>
    </div>

    <!-- 准入名册 -->
    <div v-if="tab === 'roster'">
      <div class="stat-row">
        <article v-for="item in stats" :key="item.label" class="stat-card">
          <span class="stat-label">{{ item.label }}</span>
          <strong class="stat-value">{{ item.value }}</strong>
        </article>
      </div>

      <form class="filter-bar" @submit.prevent="reloadRoster">
        <label class="filter-item">
          <span>单位 / 报审编号</span>
          <input v-model="rosterFilter.keyword" placeholder="按单位或编号检索" />
        </label>
        <label class="filter-item">
          <span>资质类别</span>
          <input v-model="rosterFilter.category" placeholder="按资质类别检索" />
        </label>
        <label class="filter-item">
          <span>准入状态</span>
          <select v-model="rosterFilter.status">
            <option value="">全部</option>
            <option v-for="s in statuses" :key="s" :value="s">{{ s }}</option>
          </select>
        </label>
        <button class="btn" type="submit">查询</button>
        <button class="btn ghost" type="button" @click="resetRosterFilter">重置条件</button>
      </form>

      <table class="data-table">
        <thead>
          <tr>
            <th v-for="column in rosterColumns" :key="column">{{ column }}</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in roster" :key="String(row.id)">
            <td>{{ row['报审编号'] }}</td>
            <td>{{ row['外委单位'] }}<span v-if="Number(row.round) > 1" class="round-tag">第{{ row.round }}轮</span></td>
            <td>{{ row['资质类别'] }}</td>
            <td><span class="badge" :class="statusBadge(row.status)">{{ row.status }}</span></td>
            <td>{{ effectiveText(row) }}</td>
            <td class="row-actions">
              <button class="link" type="button" @click="openDetail(row.id)">报审详情 / 审核</button>
            </td>
          </tr>
          <tr v-if="!roster.length">
            <td :colspan="rosterColumns.length + 1" class="empty-state">暂无报审记录，可先受理报审</td>
          </tr>
        </tbody>
      </table>

      <footer class="page-foot">
        <span>共 {{ rosterTotal }} 条报审记录</span>
        <span v-if="message" class="error-text">{{ message }}</span>
      </footer>
    </div>

    <!-- 派工清单 -->
    <div v-if="tab === 'dispatch'">
      <div class="stat-row">
        <article class="stat-card">
          <span class="stat-label">可派工</span>
          <strong class="stat-value ok-text">{{ verdictCount('可派工') }}</strong>
        </article>
        <article class="stat-card">
          <span class="stat-label">暂停派工</span>
          <strong class="stat-value warn-text">{{ verdictCount('暂停派工') }}</strong>
        </article>
        <article class="stat-card">
          <span class="stat-label">禁止派工（拦截）</span>
          <strong class="stat-value danger-text">{{ verdictCount('禁止派工') }}</strong>
        </article>
      </div>

      <form class="filter-bar" @submit.prevent="reloadDispatch">
        <label class="filter-item">
          <span>单位 / 资质类别</span>
          <input v-model="dispatchFilter.keyword" placeholder="按单位或类别检索" />
        </label>
        <label class="filter-item">
          <span>派工结论</span>
          <select v-model="dispatchFilter.verdict">
            <option value="">全部</option>
            <option value="可派工">可派工</option>
            <option value="暂停派工">暂停派工</option>
            <option value="禁止派工">禁止派工</option>
          </select>
        </label>
        <button class="btn" type="submit">查询</button>
        <button class="btn ghost" type="button" @click="resetDispatchFilter">重置条件</button>
        <button class="btn ghost" type="button" @click="exportDispatch">导出派工清单</button>
      </form>

      <table class="data-table">
        <thead>
          <tr>
            <th v-for="column in dispatchColumns" :key="column">{{ column }}</th>
            <th>派工闸口</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in dispatchRows" :key="String(row.id)">
            <td>{{ row['派工编号'] }}</td>
            <td>{{ row['外委单位'] }}</td>
            <td>{{ row['资质类别'] }}</td>
            <td><span class="badge" :class="statusBadge(row['准入状态'])">{{ row['准入状态'] }}</span></td>
            <td><span class="badge" :class="verdictBadge(row['派工结论'])">{{ row['派工结论'] }}</span></td>
            <td :class="row['派工结论'] === '可派工' ? 'ok-text' : 'danger-text'">
              {{ row['拦截原因'] || '—' }}
            </td>
            <td>{{ row['有效证明'] }}</td>
            <td class="row-actions">
              <button class="link" type="button" @click="attemptDispatch(row)">试派工</button>
            </td>
          </tr>
          <tr v-if="!dispatchRows.length">
            <td :colspan="dispatchColumns.length + 1" class="empty-state">派工清单为空</td>
          </tr>
        </tbody>
      </table>

      <footer class="page-foot">
        <span>共 {{ dispatchTotal }} 家单位在册，准入结论已实时同步</span>
        <span v-if="message" class="error-text">{{ message }}</span>
      </footer>
    </div>

    <!-- 报审详情弹窗 -->
    <div v-if="detail" class="modal-mask" @click.self="closeDetail">
      <div class="modal">
        <header class="modal-head">
          <h3>{{ detail['报审编号'] }} · {{ detail['外委单位'] }}（{{ detail['资质类别'] }}）</h3>
          <button class="link" type="button" @click="closeDetail">关闭</button>
        </header>

        <p class="modal-line">
          第 {{ detail.round }} 轮报审，当前状态：
          <span class="badge" :class="statusBadge(detail.status)">{{ detail.status }}</span>
          <span v-if="detail.status === '已暂停'" class="warn-text">（已暂停不能恢复为已准入）</span>
        </p>

        <h4>报审材料逐项核验（补正从断点项接着核，已核项不重核）</h4>
        <table class="data-table inner-table">
          <thead>
            <tr><th>审核项</th><th>状态</th><th>说明</th></tr>
          </thead>
          <tbody>
            <tr v-for="(item, idx) in detail.checklist" :key="item['审核项']"
                :class="{ 'cursor-row': idx === cursorIndex(detail) }">
              <td>{{ item['审核项'] }}<span v-if="idx === cursorIndex(detail)" class="cursor-tag">断点</span></td>
              <td><span class="badge" :class="checkBadge(item['状态'])">{{ item['状态'] }}</span></td>
              <td>{{ item['说明'] || '—' }}</td>
            </tr>
          </tbody>
        </table>

        <div v-if="detail.status === '待审'" class="action-grid">
          <button class="btn primary" type="button" @click="doAction(detail.id, '核验项')">核验断点项</button>
          <button class="btn" type="button" @click="doAction(detail.id, '退回补正')">断点项退回补正</button>
          <button class="btn" type="button" @click="askSupplement(detail.id)">断点项提交补正</button>
          <button class="btn" type="button" @click="certOpen = true">登记资质证明</button>
          <button class="btn primary" type="button" @click="doAction(detail.id, '准入通过')">作出准入结论</button>
        </div>

        <h4>已交资质证明（只在发证机关认可的证明里取，打架按级别高的算）</h4>
        <table class="data-table inner-table">
          <thead>
            <tr><th>证书编号</th><th>发证机关</th><th>级别</th><th>有效期至</th><th>认可</th><th>取舍</th></tr>
          </thead>
          <tbody>
            <tr v-for="cert in detail.certificates" :key="cert['证书编号']"
                :class="{ winner: isWinner(detail, cert) }">
              <td>{{ cert['证书编号'] }}</td>
              <td>{{ cert['发证机关'] }}</td>
              <td>{{ cert['机关级别'] }}</td>
              <td>{{ cert['有效期至'] }}</td>
              <td>{{ cert['认可'] ? '认可' : '不认可' }}</td>
              <td>{{ isWinner(detail, cert) ? '★ 按这份算' : '—' }}</td>
            </tr>
            <tr v-if="!detail.certificates.length">
              <td colspan="6" class="empty-state">尚未登记资质证明</td>
            </tr>
          </tbody>
        </table>

        <div v-if="detail.status === '已准入'" class="action-grid">
          <button class="btn" type="button" @click="certOpen = true">补交 / 更新资质证明</button>
          <button class="btn warn" type="button" @click="askReason(detail.id, '暂停准入')">暂停准入</button>
          <button class="btn danger" type="button" @click="askReason(detail.id, '清退')">清退</button>
        </div>
        <div v-if="detail.status === '已暂停'" class="action-grid">
          <button class="btn danger" type="button" @click="askReason(detail.id, '清退')">清退</button>
        </div>

        <h4>流转日志</h4>
        <ul class="log-list">
          <li v-for="(log, idx) in [...detail.logs].reverse()" :key="idx">
            <span class="log-date">{{ log['时间'] }}</span>
            <strong>{{ log['动作'] }}</strong>：{{ log['说明'] }}
          </li>
        </ul>

        <p v-if="detailMessage" class="modal-message" :class="{ 'ok-text': detailOk }">{{ detailMessage }}</p>
      </div>
    </div>

    <!-- 资质证明登记表单 -->
    <div v-if="certOpen && detail" class="modal-mask" @click.self="certOpen = false">
      <div class="modal small-modal">
        <header class="modal-head">
          <h3>登记资质证明</h3>
          <button class="link" type="button" @click="certOpen = false">关闭</button>
        </header>
        <form class="form-stack" @submit.prevent="submitCertificate">
          <label><span>证书编号</span><input v-model="certForm['证书编号']" required /></label>
          <label><span>发证机关</span><input v-model="certForm['发证机关']" placeholder="如：山东省市场监督管理局" required /></label>
          <label><span>机关级别</span>
            <select v-model="certForm['机关级别']" required>
              <option value="国家级">国家级</option>
              <option value="省级">省级</option>
              <option value="市级">市级</option>
              <option value="县级">县级</option>
            </select>
          </label>
          <label><span>发证日期</span><input v-model="certForm['发证日期']" type="date" required /></label>
          <label><span>有效期至</span><input v-model="certForm['有效期至']" type="date" required /></label>
          <label class="checkbox-line">
            <input v-model="certForm['认可']" type="checkbox" />
            <span>发证机关认可这份证明（不认可的不作为准入依据）</span>
          </label>
          <button class="btn primary" type="submit">提交证明</button>
        </form>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'

import { request } from '@/api/client'

const ENDPOINT = '/api/contractor'

// 后端行结构随业务字段走，值类型混杂，统一用宽松的 any 索引值。
type Row = Record<string, any>
type Detail = Row & { checklist: Row[]; certificates: Row[]; logs: Row[] }

const rosterColumns = ['报审编号', '外委单位', '资质类别', '准入状态', '有效证明']
const dispatchColumns = ['派工编号', '外委单位', '资质类别', '准入状态', '派工结论', '拦截原因', '有效证明']
const statuses = ['待审', '已准入', '已暂停', '已清退']

const tab = ref<'roster' | 'dispatch'>('roster')
const message = ref('')
const stats = ref<{ label: string; value: number }[]>([])

const roster = ref<Row[]>([])
const rosterTotal = ref(0)
const rosterFilter = reactive({ keyword: '', status: '', category: '' })

const dispatchRows = ref<Row[]>([])
const dispatchTotal = ref(0)
const dispatchFilter = reactive({ keyword: '', verdict: '' })

const detail = ref<Detail | null>(null)
const detailMessage = ref('')
const detailOk = ref(false)
const certOpen = ref(false)
const certForm = reactive({
  证书编号: '', 发证机关: '', 机关级别: '省级', 发证日期: '', 有效期至: '', 认可: true,
})

function switchTab(target: 'roster' | 'dispatch') {
  tab.value = target
  if (target === 'dispatch') {
    void reloadDispatch()
  }
}

function statusBadge(status: string | number | null | undefined): string {
  return {
    待审: 'badge-pending',
    已准入: 'badge-ok',
    已暂停: 'badge-warn',
    已清退: 'badge-danger',
  }[String(status)] ?? 'badge-pending'
}

function verdictBadge(verdict: string | number | null | undefined): string {
  return {
    可派工: 'badge-ok',
    暂停派工: 'badge-warn',
    禁止派工: 'badge-danger',
  }[String(verdict)] ?? 'badge-pending'
}

function checkBadge(state: string | number | null | undefined): string {
  return {
    已核: 'badge-ok',
    待核: 'badge-pending',
    缺项: 'badge-danger',
  }[String(state)] ?? 'badge-pending'
}

function effectiveText(row: Row): string {
  const cert = row.effective_certificate as Row | null
  if (!cert) return '无认可证明'
  return `${String(cert['发证机关'])}（${String(cert['机关级别'])}）${String(cert['证书编号'])}，有效期至 ${String(cert['有效期至'])}`
}

function cursorIndex(entry: Detail): number {
  return Math.max(0, entry.checklist.findIndex((item) => item['状态'] !== '已核'))
}

function isWinner(entry: Detail, cert: Row): boolean {
  const winner = entry.effective_certificate as Row | null
  return !!winner && winner['证书编号'] === cert['证书编号']
}

function verdictCount(verdict: string): number {
  return dispatchRows.value.filter((row) => row['派工结论'] === verdict).length
}

async function loadStats() {
  try {
    const response = await request(`${ENDPOINT}/stats`)
    if (response.ok) {
      const payload = await response.json()
      stats.value = payload.items ?? []
    }
  } catch {
    /* 统计不阻断页面 */
  }
}

function resetRosterFilter() {
  rosterFilter.keyword = ''
  rosterFilter.status = ''
  rosterFilter.category = ''
  void reloadRoster()
}

function resetDispatchFilter() {
  dispatchFilter.keyword = ''
  dispatchFilter.verdict = ''
  void reloadDispatch()
}

async function reloadRoster() {
  message.value = ''
  const query = new URLSearchParams()
  if (rosterFilter.keyword) query.set('keyword', rosterFilter.keyword)
  if (rosterFilter.status) query.set('status', rosterFilter.status)
  if (rosterFilter.category) query.set('category', rosterFilter.category)
  try {
    const response = await request(`${ENDPOINT}?${query.toString()}`)
    if (!response.ok) throw new Error('准入名册读取失败')
    const payload = await response.json()
    roster.value = payload.items ?? []
    rosterTotal.value = payload.total ?? roster.value.length
  } catch (error) {
    message.value = error instanceof Error ? error.message : '准入名册读取失败'
  }
}

async function reloadDispatch() {
  message.value = ''
  const query = new URLSearchParams()
  if (dispatchFilter.keyword) query.set('keyword', dispatchFilter.keyword)
  if (dispatchFilter.verdict) query.set('verdict', dispatchFilter.verdict)
  try {
    const response = await request(`${ENDPOINT}/dispatch/list?${query.toString()}`)
    if (!response.ok) throw new Error('派工清单读取失败')
    const payload = await response.json()
    dispatchRows.value = payload.items ?? []
    dispatchTotal.value = payload.total ?? dispatchRows.value.length
  } catch (error) {
    message.value = error instanceof Error ? error.message : '派工清单读取失败'
  }
}

async function postAction(url: string, body: Record<string, unknown>) {
  const response = await request(url, { method: 'POST', body: JSON.stringify(body) })
  return (await response.json()) as { ok: boolean; message: string; entry?: Detail }
}

function openCreate() {
  const unit = window.prompt('外委单位名称')?.trim()
  if (!unit) return
  const category = window.prompt('资质类别（如：电梯安装维修）')?.trim()
  if (!category) return
  const materialText = window.prompt(
    '随报审提交的材料，用顿号分隔（营业执照、资质证书、安全生产许可证、人员持证名册、工伤保险凭证）',
    '营业执照、资质证书、安全生产许可证、人员持证名册、工伤保险凭证',
  )
  if (materialText === null) return
  const materials: Record<string, boolean> = {}
  materialText.split(/[、,，]/).map((part) => part.trim()).filter(Boolean)
    .forEach((name) => { materials[name] = true })
  void (async () => {
    const result = await postAction(ENDPOINT, {
      values: { 外委单位: unit, 资质类别: category, 材料: materials },
    })
    message.value = result.message
    await reloadRoster()
    await loadStats()
    if (result.ok && result.entry) openDetail(Number(result.entry.id))
  })()
}

async function openDetail(id: number) {
  try {
    const response = await request(`${ENDPOINT}/${id}`)
    if (!response.ok) throw new Error('报审明细读取失败')
    detail.value = (await response.json()) as Detail
    detailMessage.value = ''
    detailOk.value = false
  } catch (error) {
    message.value = error instanceof Error ? error.message : '报审明细读取失败'
  }
}

function closeDetail() {
  detail.value = null
  certOpen.value = false
  void reloadRoster()
  void reloadDispatch()
  void loadStats()
}

async function doAction(id: number, action: string, extra: Record<string, unknown> = {}) {
  detailMessage.value = ''
  const result = await postAction(`${ENDPOINT}/${id}/actions`, {
    values: { action, ...extra },
  })
  detailOk.value = result.ok
  detailMessage.value = result.message
  if (result.ok && result.entry) {
    detail.value = result.entry
  }
}

async function askSupplement(id: number) {
  if (!detail.value) return
  const cursor = detail.value.checklist[cursorIndex(detail.value)]
  const note = window.prompt(`请填写「${String(cursor['审核项'])}」的补正内容或材料说明`)?.trim()
  if (!note) return
  await doAction(id, '提交补正', { 审核项: cursor['审核项'], 补正说明: note })
}

async function askReason(id: number, action: string) {
  const reason = window.prompt(`${action}原因（将记入流转日志）`)?.trim()
  if (!reason) return
  await doAction(id, action, { 说明: reason })
  if (detail.value && detailOk.value) {
    await openDetail(id)
  }
}

async function submitCertificate() {
  if (!detail.value) return
  const result = await postAction(`${ENDPOINT}/${detail.value.id}/actions`, {
    values: { action: '登记资质证明', ...certForm },
  })
  detailOk.value = result.ok
  detailMessage.value = result.message
  if (result.ok && result.entry) {
    detail.value = result.entry
    certOpen.value = false
  }
}

async function attemptDispatch(row: Row) {
  message.value = ''
  const result = await postAction(`${ENDPOINT}/dispatch/${row.id}/attempt`, {})
  message.value = result.message
  await reloadDispatch()
}

function exportDispatch() {
  window.open(`${ENDPOINT}/dispatch/export`, '_blank')
}

onMounted(() => {
  void loadStats()
  void reloadRoster()
})
</script>
