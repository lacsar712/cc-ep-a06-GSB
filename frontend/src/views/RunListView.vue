<template>
  <div class="page">
    <div style="display: flex; justify-content: space-between; align-items: center; gap: 12px">
      <div>
        <h1 style="margin-bottom: 4px">实验 Run 列表</h1>
        <p class="muted" style="margin-top: 0">按项目、状态与标签筛选投影视图</p>
      </div>
      <div style="display: flex; gap: 8px">
        <n-button @click="openTagPanel()">标签面板</n-button>
        <n-button v-if="auth.role === 'researcher'" type="primary" @click="$router.push('/runs/new')">
          新建 Run
        </n-button>
      </div>
    </div>

    <div class="card" style="margin-bottom: 16px">
      <div class="grid-3">
        <n-form-item label="项目" :show-feedback="false">
          <n-input v-model:value="project" clearable placeholder="例如 protein-folding" />
        </n-form-item>
        <n-form-item label="状态" :show-feedback="false">
          <n-select
            v-model:value="status"
            clearable
            :options="statusOptions"
            placeholder="全部"
          />
        </n-form-item>
        <n-form-item label="标签(服务端过滤)" :show-feedback="false">
          <n-select
            v-model:value="tag"
            clearable
            filterable
            :options="tagOptions"
            placeholder="全部标签"
            @update:value="load"
          />
        </n-form-item>
      </div>
      <div style="display: flex; gap: 8px; align-items: center; margin-top: 8px">
        <n-button @click="load">筛选</n-button>
        <span v-if="tag" class="muted" style="font-size: 12px">
          当前按标签「{{ tag }}」过滤,共 {{ rows.length }} 条
        </span>
      </div>
    </div>

    <div class="card">
      <n-data-table :columns="columns" :data="rows" :loading="loading" :bordered="false" />
    </div>

    <n-drawer v-model:show="tagPanelVisible" :width="420" placement="right">
      <n-drawer-content title="标签面板" closable>
        <n-alert type="info" :bordered="false" style="margin-bottom: 16px">
          标签落库方式:通过命令写入事件(RunTagged / RunUntagged),可在「事件时间线」回看;
          列表的标签过滤由服务端查询完成。
        </n-alert>

        <h4 style="margin: 0 0 8px">按标签筛选</h4>
        <div v-if="allTags.length" style="display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 8px">
          <n-tag
            v-for="t in allTags"
            :key="t.tag"
            size="small"
            :type="tag === t.tag ? 'primary' : 'default'"
            style="cursor: pointer"
            @click="applyTagFilter(t.tag)"
          >
            {{ t.tag }}({{ t.run_count }})
          </n-tag>
        </div>
        <n-text v-else class="muted" style="font-size: 12px">暂无标签</n-text>
        <div style="margin-bottom: 20px">
          <n-button size="tiny" quaternary :disabled="!tag" @click="applyTagFilter(null)">
            清除标签筛选
          </n-button>
        </div>

        <h4 style="margin: 0 0 8px">给 Run 打标签</h4>
        <n-select
          v-model:value="tagPanelRunId"
          :options="runOptions"
          placeholder="选择 Run"
          filterable
          style="margin-bottom: 12px"
          @update:value="syncPanelRun"
        />
        <template v-if="panelRun">
          <div class="muted" style="font-size: 12px; margin-bottom: 6px">
            {{ panelRun.project }} · version {{ panelRun.version }} · 当前标签
          </div>
          <div style="display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 12px">
            <n-tag
              v-for="t in panelRun.tags || []"
              :key="t"
              size="small"
              :closable="auth.role === 'researcher'"
              :disabled="tagBusy"
              @close="submitRemoveTag(panelRun, t)"
            >
              {{ t }}
            </n-tag>
            <n-text v-if="!(panelRun.tags || []).length" class="muted" style="font-size: 12px">
              暂无标签
            </n-text>
          </div>
          <template v-if="auth.role === 'researcher'">
            <n-input
              v-model:value="newTag"
              size="small"
              placeholder="新标签,如 night-run(1-64 字符)"
              style="margin-bottom: 8px"
              @keyup.enter="submitAddTag(panelRun)"
            />
            <n-button
              size="small"
              type="primary"
              :loading="tagBusy"
              :disabled="!newTag.trim()"
              @click="submitAddTag(panelRun)"
            >
              添加标签
            </n-button>
          </template>
          <n-text v-else class="muted" style="font-size: 12px">
            审计员只读:可查看标签与筛选,不可修改。
          </n-text>
        </template>
        <n-text v-else class="muted" style="font-size: 12px">请选择要打标签的 Run</n-text>
      </n-drawer-content>
    </n-drawer>
  </div>
</template>

<script setup>
import { computed, h, onMounted, ref } from 'vue'
import { NButton, NTag, useMessage } from 'naive-ui'
import { useRouter } from 'vue-router'
import { addTag, listRuns, listTags, removeTag } from '../api/client'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const router = useRouter()
const message = useMessage()
const rows = ref([])
const loading = ref(false)
const project = ref('')
const status = ref(null)
const tag = ref(null)

const allTags = ref([])
const tagPanelVisible = ref(false)
const tagPanelRuns = ref([])
const tagPanelRunId = ref(null)
const newTag = ref('')
const tagBusy = ref(false)

const statusOptions = [
  { label: '进行中', value: 'running' },
  { label: '已完成', value: 'completed' },
  { label: '已中止', value: 'aborted' },
]

const statusMap = {
  running: { type: 'info', label: '进行中' },
  completed: { type: 'success', label: '已完成' },
  aborted: { type: 'warning', label: '已中止' },
}

const tagOptions = computed(() => allTags.value.map((t) => ({ label: t.tag, value: t.tag })))
const runOptions = computed(() =>
  tagPanelRuns.value.map((r) => ({ label: `${r.project} / ${r.name}`, value: r.id })),
)
const panelRun = computed(() => tagPanelRuns.value.find((r) => r.id === tagPanelRunId.value) || null)

const columns = [
  { title: '项目', key: 'project' },
  { title: '名称', key: 'name' },
  {
    title: '状态',
    key: 'status',
    render(row) {
      const m = statusMap[row.status] || { type: 'default', label: row.status }
      return h(NTag, { type: m.type, size: 'small' }, { default: () => m.label })
    },
  },
  {
    title: '标签',
    key: 'tags',
    render(row) {
      const tags = row.tags || []
      if (!tags.length) return h('span', { class: 'muted', style: 'font-size:12px' }, '—')
      return h(
        'div',
        { style: 'display:flex;gap:4px;flex-wrap:wrap' },
        tags.map((t) =>
          h(
            NTag,
            {
              size: 'small',
              style: 'cursor:pointer',
              onClick: () => applyTagFilter(t),
            },
            { default: () => t },
          ),
        ),
      )
    },
  },
  { title: '版本', key: 'version', width: 70 },
  {
    title: '开始时间',
    key: 'started_at',
    render(row) {
      return new Date(row.started_at).toLocaleString()
    },
  },
  {
    title: '操作',
    key: 'actions',
    render(row) {
      return h(
        'div',
        { style: 'display:flex;gap:8px;flex-wrap:wrap' },
        [
          h(NButton, { size: 'tiny', onClick: () => router.push(`/runs/${row.id}`) }, { default: () => '详情' }),
          h(NButton, { size: 'tiny', quaternary: true, onClick: () => router.push(`/runs/${row.id}/events`) }, { default: () => '事件' }),
          h(NButton, { size: 'tiny', quaternary: true, onClick: () => router.push(`/runs/${row.id}/lineage`) }, { default: () => '血缘' }),
          h(NButton, { size: 'tiny', quaternary: true, onClick: () => openTagPanel(row.id) }, { default: () => '标签' }),
        ],
      )
    },
  },
]

async function load() {
  loading.value = true
  try {
    const params = {}
    if (project.value.trim()) params.project = project.value.trim()
    if (status.value) params.status = status.value
    if (tag.value) params.tag = tag.value
    rows.value = await listRuns(params)
  } catch (e) {
    message.error(e.message || '加载失败')
  } finally {
    loading.value = false
  }
}

async function loadAllTags() {
  try {
    allTags.value = await listTags()
  } catch (e) {
    message.error(e.message || '标签加载失败')
  }
}

function applyTagFilter(t) {
  tag.value = t || null
  load()
}

async function openTagPanel(runId = null) {
  tagPanelVisible.value = true
  try {
    // 打标签候选不受当前筛选影响,始终拉全量
    tagPanelRuns.value = await listRuns({})
  } catch (e) {
    message.error(e.message || '加载失败')
  }
  if (runId) tagPanelRunId.value = runId
  syncPanelRun()
}

function syncPanelRun() {
  newTag.value = ''
}

function upsertRun(updated) {
  const i = tagPanelRuns.value.findIndex((r) => r.id === updated.id)
  if (i >= 0) tagPanelRuns.value.splice(i, 1, updated)
  const j = rows.value.findIndex((r) => r.id === updated.id)
  if (j >= 0) rows.value.splice(j, 1, updated)
}

async function submitAddTag(run) {
  const value = newTag.value.trim()
  if (!value) return
  tagBusy.value = true
  try {
    const updated = await addTag(run.id, { tag: value, expected_version: run.version })
    upsertRun(updated)
    newTag.value = ''
    message.success(`已添加标签「${value}」`)
    loadAllTags()
  } catch (e) {
    message.error(e.message || '打标签失败')
    load()
  } finally {
    tagBusy.value = false
  }
}

async function submitRemoveTag(run, t) {
  tagBusy.value = true
  try {
    const updated = await removeTag(run.id, { tag: t, expected_version: run.version })
    upsertRun(updated)
    message.success(`已移除标签「${t}」`)
    loadAllTags()
  } catch (e) {
    message.error(e.message || '移除标签失败')
    load()
  } finally {
    tagBusy.value = false
  }
}

onMounted(() => {
  load()
  loadAllTags()
})
</script>
