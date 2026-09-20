<template>
  <n-drawer :show="show" :width="440" @update:show="(v) => emit('update:show', v)">
    <n-drawer-content title="标签" closable>
      <n-alert type="info" :bordered="false" style="margin-bottom: 16px">
        <b>落库方式（命令写入事件，可回看）：</b
        >标签通过 <span class="mono">RunTagsAdded</span> /
        <span class="mono">RunTagsRemoved</span> 命令作为事件追加写入
        <span class="mono">event_store</span>（带 version 与操作人），并投影到
        <span class="mono">run_projections.tags_json</span>；每次打标/删标都能在该 Run
        的「事件时间线」里回看。
      </n-alert>

      <h4 style="margin: 8px 0">按标签筛选（服务端过滤）</h4>
      <div style="margin-bottom: 8px">
        <n-tag
          v-for="t in allTags"
          :key="t.tag"
          :type="activeTag === t.tag ? 'success' : 'default'"
          :bordered="true"
          style="margin: 0 8px 8px 0; cursor: pointer"
          @click="toggleFilter(t.tag)"
        >
          {{ t.tag }} · {{ t.count }}
        </n-tag>
        <span v-if="!allTags.length" class="muted">还没有任何标签</span>
      </div>
      <n-button
        v-if="activeTag"
        size="tiny"
        quaternary
        type="error"
        @click="toggleFilter(activeTag)"
      >
        清除筛选：{{ activeTag }}
      </n-button>

      <n-divider />

      <h4 style="margin: 8px 0">
        给 Run 打标签<span v-if="!isResearcher" class="muted">（审计员只读）</span>
      </h4>
      <div v-for="run in runs" :key="run.id" class="run-tag-block">
        <a class="run-name" @click="goDetail(run.id)">{{ run.name }}</a>
        <div class="muted" style="font-size: 12px">
          {{ run.project }} · v{{ run.version }}
        </div>
        <div style="margin: 6px 0">
          <template v-for="tag in run.tags_json || []" :key="tag">
            <n-tag
              size="small"
              :closable="isResearcher"
              @close="removeTag(run, tag)"
              style="margin: 0 6px 6px 0"
            >
              <span @click.stop="applyFilter(tag)">{{ tag }}</span>
            </n-tag>
          </template>
          <span v-if="!(run.tags_json || []).length" class="muted" style="font-size: 12px">
            暂无标签
          </span>
        </div>
        <n-input
          v-if="isResearcher"
          :value="drafts[run.id] || ''"
          size="small"
          placeholder="输入标签后回车，可逗号分隔多个"
          @update:value="(v) => (drafts[run.id] = v)"
          @keyup.enter="addTag(run)"
          #suffix
        >
          <n-button text size="small" type="primary" @click="addTag(run)">添加</n-button>
        </n-input>
      </div>
    </n-drawer-content>
  </n-drawer>
</template>

<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useMessage } from 'naive-ui'
import { addRunTags, listTags, removeRunTags } from '../api/client'
import { useAuthStore } from '../stores/auth'

const props = defineProps({
  show: { type: Boolean, default: false },
  runs: { type: Array, default: () => [] },
  activeTag: { type: String, default: '' },
})
const emit = defineEmits(['update:show', 'filter', 'changed'])

const auth = useAuthStore()
const router = useRouter()
const message = useMessage()
const allTags = ref([])
const drafts = reactive({})
const busy = ref(false)

const isResearcher = computed(() => auth.role === 'researcher')

async function loadTags() {
  try {
    allTags.value = await listTags()
  } catch (e) {
    message.error(e.message || '标签加载失败')
  }
}

watch(
  () => props.show,
  (v) => {
    if (v) loadTags()
  },
)

function toggleFilter(tag) {
  emit('filter', props.activeTag === tag ? '' : tag)
}

function applyFilter(tag) {
  if (props.activeTag !== tag) emit('filter', tag)
}

function goDetail(id) {
  emit('update:show', false)
  router.push(`/runs/${id}`)
}

async function addTag(run) {
  const raw = (drafts[run.id] || '').trim()
  if (!raw || busy.value) return
  const tags = raw.split(/[,，]/).map((t) => t.trim()).filter(Boolean)
  busy.value = true
  try {
    await addRunTags(run.id, { tags, expected_version: run.version })
    drafts[run.id] = ''
    message.success('标签已添加（事件已写入 event_store）')
    await Promise.all([loadTags(), emit('changed')])
  } catch (e) {
    message.error(e.message || '添加失败')
  } finally {
    busy.value = false
  }
}

async function removeTag(run, tag) {
  if (busy.value) return
  busy.value = true
  try {
    await removeRunTags(run.id, { tags: [tag], expected_version: run.version })
    message.success('标签已移除（事件已写入 event_store）')
    await Promise.all([loadTags(), emit('changed')])
  } catch (e) {
    message.error(e.message || '移除失败')
  } finally {
    busy.value = false
  }
}
</script>

<style scoped>
.run-tag-block {
  padding: 10px 0;
  border-bottom: 1px dashed var(--line, #d8e0e8);
}
.run-name {
  font-weight: 600;
  cursor: pointer;
}
</style>
