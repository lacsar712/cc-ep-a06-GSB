<template>
  <div class="page">
    <div style="display: flex; justify-content: space-between; align-items: center; gap: 12px">
      <div>
        <h1 style="margin-bottom: 4px">实验 Run 列表</h1>
        <p class="muted" style="margin-top: 0">按项目、状态与标签筛选投影视图（标签过滤走服务端）</p>
      </div>
      <div style="display: flex; gap: 8px">
        <n-button @click="drawerShow = true">🏷 标签</n-button>
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
        <n-form-item label="标签（服务端过滤）" :show-feedback="false">
          <n-input
            v-model:value="tag"
            clearable
            placeholder="例如 night-run"
            @keyup.enter="applyFilter"
          />
        </n-form-item>
      </div>
      <div style="margin-top: 8px; display: flex; gap: 8px; align-items: center; flex-wrap: wrap">
        <n-button type="primary" @click="applyFilter">筛选</n-button>
        <n-tag
          v-if="activeTag"
          type="success"
          closable
          @close="clearTag"
        >
          标签：{{ activeTag }}
        </n-tag>
        <n-button quaternary size="small" @click="drawerShow = true">
          打开标签面板打标签 / 选择标签
        </n-button>
      </div>
    </div>

    <div class="card">
      <n-data-table :columns="columns" :data="rows" :loading="loading" :bordered="false" />
    </div>

    <TagsDrawer
      v-model:show="drawerShow"
      :runs="rows"
      :active-tag="activeTag"
      @filter="onDrawerFilter"
      @changed="load"
    />
  </div>
</template>

<script setup>
import { h, onMounted, ref } from 'vue'
import { NButton, NTag, useMessage } from 'naive-ui'
import { useRouter } from 'vue-router'
import { listRuns } from '../api/client'
import { useAuthStore } from '../stores/auth'
import TagsDrawer from '../components/TagsDrawer.vue'

const auth = useAuthStore()
const router = useRouter()
const message = useMessage()
const rows = ref([])
const loading = ref(false)
const project = ref('')
const status = ref(null)
const tag = ref('')
const activeTag = ref('')
const drawerShow = ref(false)

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

function renderTags(row) {
  const tags = row.tags_json || []
  if (!tags.length) return h('span', { class: 'muted', style: 'font-size:12px' }, '—')
  return h(
    'div',
    { style: 'display:flex;gap:4px;flex-wrap:wrap' },
    tags.map((t) =>
      h(
        NTag,
        {
          size: 'small',
          type: t === activeTag.value ? 'success' : 'info',
          style: 'cursor:pointer',
          onClick: () => onRowTagClick(t),
        },
        { default: () => t },
      ),
    ),
  )
}

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
  { title: '标签', key: 'tags_json', render: renderTags },
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
    if (activeTag.value) params.tag = activeTag.value
    rows.value = await listRuns(params)
  } catch (e) {
    message.error(e.message || '加载失败')
  } finally {
    loading.value = false
  }
}

function applyFilter() {
  activeTag.value = tag.value.trim()
  load()
}

function clearTag() {
  activeTag.value = ''
  tag.value = ''
  load()
}

function onRowTagClick(t) {
  activeTag.value = activeTag.value === t ? '' : t
  tag.value = activeTag.value
  load()
}

function onDrawerFilter(t) {
  activeTag.value = t
  tag.value = t
  load()
}

onMounted(load)
</script>
