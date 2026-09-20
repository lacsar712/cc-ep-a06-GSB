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
      <h3 style="margin-top: 0">标签</h3>
      <div style="display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 12px">
        <n-tag
          v-for="t in run.tags || []"
          :key="t"
          size="small"
          :closable="auth.role === 'researcher'"
          :disabled="tagBusy"
          @close="doRemoveTag(t)"
        >
          {{ t }}
        </n-tag>
        <span v-if="!(run.tags || []).length" class="muted" style="font-size: 12px">暂无标签</span>
      </div>
      <div v-if="auth.role === 'researcher'" style="display: flex; gap: 8px; align-items: center; max-width: 420px">
        <n-input
          v-model:value="newTag"
          size="small"
          placeholder="新标签,如 night-run(1-64 字符)"
          @keyup.enter="doAddTag"
        />
        <n-button size="small" type="primary" :loading="tagBusy" :disabled="!newTag.trim()" @click="doAddTag">
          添加标签
        </n-button>
      </div>
      <p class="muted" style="font-size: 12px; margin-bottom: 0; margin-top: 8px">
        标签落库方式:通过命令写入事件(RunTagged / RunUntagged),可在「事件时间线」回看;
        列表页可按标签做服务端过滤。{{ auth.role === 'researcher' ? '' : '审计员只读,不可修改标签。' }}
      </p>
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
  addTag,
  attachArtifact,
  completeRun,
  getRun,
  recordMetric,
  removeTag,
} from '../api/client'
import { useAuthStore } from '../stores/auth'

const route = useRoute()
const auth = useAuthStore()
const message = useMessage()
const run = ref(null)
const busy = ref(false)
const completeSummary = ref('')
const abortReason = ref('')
const newTag = ref('')
const tagBusy = ref(false)

const metric = reactive({ name: 'loss', value: 0.5, step: 1 })
const artifact = reactive({
  name: 'checkpoint.pt',
  uri: 's3://lab-artifacts/checkpoint.pt',
  content_sha256: '',
  media_type: 'application/octet-stream',
})

const canWrite = computed(() => auth.role === 'researcher' && run.value?.status === 'running')
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

async function doAddTag() {
  const value = newTag.value.trim()
  if (!value) return
  tagBusy.value = true
  try {
    run.value = await addTag(run.value.id, {
      tag: value,
      expected_version: run.value.version,
    })
    newTag.value = ''
    message.success(`已添加标签「${value}」`)
  } catch (e) {
    message.error(e.message || '打标签失败')
    await load()
  } finally {
    tagBusy.value = false
  }
}

async function doRemoveTag(t) {
  tagBusy.value = true
  try {
    run.value = await removeTag(run.value.id, {
      tag: t,
      expected_version: run.value.version,
    })
    message.success(`已移除标签「${t}」`)
  } catch (e) {
    message.error(e.message || '移除标签失败')
    await load()
  } finally {
    tagBusy.value = false
  }
}

onMounted(async () => {
  try {
    await load()
  } catch (e) {
    message.error(e.message || '加载失败')
  }
})
</script>
