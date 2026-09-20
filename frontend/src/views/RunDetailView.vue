<template>
  <div class="page" v-if="run">
    <div style="display: flex; justify-content: space-between; gap: 12px; flex-wrap: wrap">
      <div>
        <h1 style="margin-bottom: 4px">{{ run.name }}</h1>
        <p class="muted" style="margin-top: 0">
          {{ run.project }} ·
          <n-tag size="small" :type="statusType">{{ statusLabel }}</n-tag>
          · version {{ run.version }}
        </p>
      </div>
      <div style="display: flex; gap: 8px">
        <n-button @click="$router.push(`/runs/${run.id}/events`)">事件时间线</n-button>
        <n-button @click="$router.push(`/runs/${run.id}/lineage`)">血缘</n-button>
      </div>
    </div>

    <div class="card" style="margin-bottom: 16px">
      <div class="grid-2">
        <div>
          <div class="muted">dataset_content_sha256</div>
          <div class="mono">{{ run.dataset_content_sha256 }}</div>
        </div>
        <div>
          <div class="muted">code_commit_sha</div>
          <div class="mono">{{ run.code_commit_sha }}</div>
        </div>
        <div>
          <div class="muted">started_by / started_at</div>
          <div>{{ run.started_by }} · {{ formatTime(run.started_at) }}</div>
        </div>
        <div>
          <div class="muted">finished_at</div>
          <div>{{ run.finished_at ? formatTime(run.finished_at) : '—' }}</div>
        </div>
      </div>
      <p v-if="run.description" style="margin-top: 12px">{{ run.description }}</p>
      <p v-if="run.result_summary"><strong>结果：</strong>{{ run.result_summary }}</p>
      <p v-if="run.abort_reason"><strong>中止原因：</strong>{{ run.abort_reason }}</p>
    </div>

    <div class="card" style="margin-bottom: 16px">
      <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:12px;flex-wrap:wrap">
        <div>
          <h3 style="margin: 0 0 6px">标签</h3>
          <div class="muted" style="font-size: 12px">
            落库方式：走命令写入 <span class="mono">event_store</span>（RunTagsAdded /
            RunTagsRemoved），并投影到详情；可在
            <a @click="$router.push(`/runs/${run.id}/events`)">事件时间线</a> 回看每次变更。
          </div>
        </div>
        <n-tag v-if="!canTag" size="small">审计员只读</n-tag>
      </div>
      <div style="margin-top: 10px">
        <template v-for="t in run.tags_json || []" :key="t">
          <n-tag
            type="info"
            size="small"
            :closable="canTag"
            @close="doRemoveTag(t)"
            style="margin: 0 8px 8px 0"
          >
            {{ t }}
          </n-tag>
        </template>
        <span v-if="!(run.tags_json || []).length" class="muted">暂无标签</span>
      </div>
      <div v-if="canTag" style="display:flex;gap:8px;margin-top:8px;max-width:520px">
        <n-input
          v-model:value="tagDraft"
          placeholder="输入标签后回车，可逗号分隔多个（如 night-run）"
          @keyup.enter="doAddTags"
        />
        <n-button type="primary" :loading="tagBusy" @click="doAddTags">打标签</n-button>
      </div>
    </div>

    <div class="grid-2" style="margin-bottom: 16px">
      <div class="card">
        <h3 style="margin-top: 0">指标（投影）</h3>
        <n-data-table
          size="small"
          :columns="metricCols"
          :data="run.metrics_json || []"
          :bordered="false"
        />
      </div>
      <div class="card">
        <h3 style="margin-top: 0">产物（投影）</h3>
        <n-data-table
          size="small"
          :columns="artifactCols"
          :data="run.artifacts_json || []"
          :bordered="false"
        />
      </div>
    </div>

    <div v-if="canWrite" class="card">
      <h3 style="margin-top: 0">命令操作区（乐观锁 expected_version = {{ run.version }}）</h3>
      <div class="grid-2">
        <div>
          <h4>RecordMetric</h4>
          <n-input v-model:value="metric.name" placeholder="指标名" style="margin-bottom: 8px" />
          <n-input-number v-model:value="metric.value" style="width: 100%; margin-bottom: 8px" />
          <n-input-number v-model:value="metric.step" :min="0" style="width: 100%; margin-bottom: 8px" />
          <n-button type="primary" :loading="busy" @click="doMetric">记录指标</n-button>
        </div>
        <div>
          <h4>AttachArtifact</h4>
          <n-input v-model:value="artifact.name" placeholder="产物名" style="margin-bottom: 8px" />
          <n-input v-model:value="artifact.uri" placeholder="URI" style="margin-bottom: 8px" />
          <n-input v-model:value="artifact.content_sha256" placeholder="content sha256" class="mono" style="margin-bottom: 8px" />
          <n-button text type="primary" @click="artifact.content_sha256 = randomHex(32)">随机指纹</n-button>
          <div style="margin-top: 8px">
            <n-button type="primary" :loading="busy" @click="doArtifact">挂载产物</n-button>
          </div>
        </div>
      </div>
      <div style="margin-top: 20px; display: flex; gap: 12px; flex-wrap: wrap; align-items: flex-end">
        <div style="flex: 1; min-width: 220px">
          <n-input v-model:value="completeSummary" type="textarea" placeholder="完成摘要" :rows="2" />
        </div>
        <n-button type="success" :loading="busy" @click="doComplete">CompleteRun</n-button>
        <div style="flex: 1; min-width: 220px">
          <n-input v-model:value="abortReason" type="textarea" placeholder="中止原因" :rows="2" />
        </div>
        <n-button type="warning" :loading="busy" @click="doAbort">AbortRun</n-button>
      </div>
    </div>
    <div v-else class="card muted">审计员只读：可查看事件与血缘，不可发送命令。</div>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import { useMessage } from 'naive-ui'
import {
  abortRun,
  addRunTags,
  attachArtifact,
  completeRun,
  getRun,
  recordMetric,
  removeRunTags,
} from '../api/client'
import { useAuthStore } from '../stores/auth'

const route = useRoute()
const auth = useAuthStore()
const message = useMessage()
const run = ref(null)
const busy = ref(false)
const tagBusy = ref(false)
const tagDraft = ref('')
const completeSummary = ref('')
const abortReason = ref('')

const metric = reactive({ name: 'loss', value: 0.5, step: 1 })
const artifact = reactive({
  name: 'checkpoint.pt',
  uri: 's3://lab-artifacts/checkpoint.pt',
  content_sha256: '',
  media_type: 'application/octet-stream',
})

const canWrite = computed(() => auth.role === 'researcher' && run.value?.status === 'running')
const canTag = computed(() => auth.role === 'researcher')
const statusLabel = computed(() => {
  const m = { running: '进行中', completed: '已完成', aborted: '已中止' }
  return m[run.value?.status] || run.value?.status
})
const statusType = computed(() => {
  const m = { running: 'info', completed: 'success', aborted: 'warning' }
  return m[run.value?.status] || 'default'
})

const metricCols = [
  { title: 'name', key: 'name' },
  { title: 'value', key: 'value' },
  { title: 'step', key: 'step' },
]
const artifactCols = [
  { title: 'name', key: 'name' },
  { title: 'uri', key: 'uri', ellipsis: { tooltip: true } },
]

function formatTime(v) {
  return v ? new Date(v).toLocaleString() : '—'
}

function randomHex(n) {
  const bytes = new Uint8Array(n)
  crypto.getRandomValues(bytes)
  return Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('')
}

async function load() {
  run.value = await getRun(route.params.id)
}

async function doAddTags() {
  const tags = tagDraft.value
    .split(/[,，]/)
    .map((t) => t.trim())
    .filter(Boolean)
  if (!tags.length) {
    message.warning('请输入至少一个标签')
    return
  }
  tagBusy.value = true
  try {
    run.value = await addRunTags(run.value.id, {
      tags,
      expected_version: run.value.version,
    })
    tagDraft.value = ''
    message.success('标签已添加（RunTagsAdded 事件已写入）')
  } catch (e) {
    message.error(e.message || '打标签失败')
    await load()
  } finally {
    tagBusy.value = false
  }
}

async function doRemoveTag(tag) {
  tagBusy.value = true
  try {
    run.value = await removeRunTags(run.value.id, {
      tags: [tag],
      expected_version: run.value.version,
    })
    message.success('标签已移除（RunTagsRemoved 事件已写入）')
  } catch (e) {
    message.error(e.message || '移除失败')
    await load()
  } finally {
    tagBusy.value = false
  }
}

async function withBusy(fn) {
  busy.value = true
  try {
    await fn()
    message.success('命令已接受')
    await load()
  } catch (e) {
    message.error(e.message || '命令失败')
  } finally {
    busy.value = false
  }
}

function doMetric() {
  return withBusy(async () => {
    await recordMetric(run.value.id, {
      name: metric.name,
      value: metric.value,
      step: metric.step,
      expected_version: run.value.version,
    })
    metric.step += 1
  })
}

function doArtifact() {
  if (!artifact.content_sha256 || artifact.content_sha256.length !== 64) {
    message.warning('请填写 64 位 content_sha256')
    return
  }
  return withBusy(() =>
    attachArtifact(run.value.id, {
      ...artifact,
      expected_version: run.value.version,
    }),
  )
}

function doComplete() {
  if (!completeSummary.value.trim()) {
    message.warning('请填写完成摘要')
    return
  }
  return withBusy(() =>
    completeRun(run.value.id, {
      result_summary: completeSummary.value,
      expected_version: run.value.version,
    }),
  )
}

function doAbort() {
  if (!abortReason.value.trim()) {
    message.warning('请填写中止原因')
    return
  }
  return withBusy(() =>
    abortRun(run.value.id, {
      reason: abortReason.value,
      expected_version: run.value.version,
    }),
  )
}

onMounted(async () => {
  try {
    await load()
  } catch (e) {
    message.error(e.message || '加载失败')
  }
})
</script>
