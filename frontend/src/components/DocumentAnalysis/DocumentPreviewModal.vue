<template>
  <Transition name="dp-fade">
    <div v-if="doc" class="dp-overlay" @click.self="emit('close')">
      <div class="dp-modal" role="dialog" aria-modal="true">

        <!-- Header -->
        <div class="dp-header">
          <div class="dp-file-info">
            <span class="dp-type-badge" :class="`dp-type-badge--${fileType}`">
              {{ fileType.toUpperCase() }}
            </span>
            <div class="dp-name-group">
              <p class="dp-filename">{{ doc.original_name }}</p>
              <p class="dp-meta">
                <span v-if="doc.word_count">{{ doc.word_count?.toLocaleString() }} words</span>
                <span v-if="doc.page_count"> · {{ doc.page_count }} pages</span>
                <span v-if="doc.file_size_human"> · {{ doc.file_size_human }}</span>
              </p>
            </div>
          </div>
          <button class="dp-close" @click="emit('close')" aria-label="Close">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
              <path d="M18 6 6 18M6 6l12 12"/>
            </svg>
          </button>
        </div>

        <!-- Body -->
        <div class="dp-body">
          <div v-if="loading" class="dp-center">
            <svg class="dp-spin" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/>
            </svg>
          </div>
          <div v-else-if="error" class="dp-center dp-error">{{ error }}</div>
          <div v-else-if="preview" class="dp-text-wrap">
            <pre class="dp-text">{{ preview.preview_text }}</pre>
            <p v-if="preview.truncated" class="dp-truncated-note">
              — preview truncated —
            </p>
          </div>
        </div>

      </div>
    </div>
  </Transition>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import api from '@/services/axios.js'

const props = defineProps({
  doc:    { type: Object, default: null },
  chatId: { type: String, default: null },
})

const emit = defineEmits(['close'])

const loading = ref(false)
const error   = ref('')
const preview = ref(null)

const fileType = computed(() => {
  const name = props.doc?.original_name ?? ''
  const mime = props.doc?.mime_type ?? ''
  if (mime.includes('pdf') || name.endsWith('.pdf'))    return 'pdf'
  if (mime.includes('word') || /\.docx?$/i.test(name)) return 'doc'
  return 'txt'
})

watch(
  () => props.doc,
  async (doc) => {
    if (!doc || !props.chatId) return
    loading.value = true
    error.value   = ''
    preview.value = null
    try {
      const res = await api.get(`/api/chats/${props.chatId}/documents/${doc.id}/preview`)
      preview.value = res.data
    } catch (e) {
      error.value = e?.response?.data?.error ?? 'Could not load document preview.'
    } finally {
      loading.value = false
    }
  },
  { immediate: true },
)
</script>

<style scoped>
.dp-overlay {
  position: fixed; inset: 0; z-index: 9500;
  background: rgba(0,0,0,0.6);
  display: flex; align-items: center; justify-content: center;
  padding: 16px;
}

.dp-modal {
  background: #0d1117; border: 1px solid #21262d; border-radius: 12px;
  width: 100%; max-width: 680px; max-height: 80vh;
  display: flex; flex-direction: column; overflow: hidden;
  box-shadow: 0 24px 64px rgba(0,0,0,0.5);
}

.dp-header {
  display: flex; align-items: center; justify-content: space-between;
  gap: 12px; padding: 16px 20px;
  border-bottom: 1px solid #21262d; flex-shrink: 0;
}

.dp-file-info { display: flex; align-items: center; gap: 12px; min-width: 0; }

.dp-type-badge {
  flex-shrink: 0; padding: 3px 8px; border-radius: 5px;
  font-size: 10px; font-weight: 700; letter-spacing: 0.04em;
}
.dp-type-badge--pdf { background: #fff0f0; color: #991b1b; border: 1px solid #fecaca; }
.dp-type-badge--doc { background: #eff6ff; color: #1d4ed8; border: 1px solid #bfdbfe; }
.dp-type-badge--txt { background: #f0fdf4; color: #166534; border: 1px solid #bbf7d0; }

.dp-name-group { min-width: 0; }
.dp-filename {
  font-size: 14px; font-weight: 600; color: #e6edf3;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 400px;
  margin: 0;
}
.dp-meta { font-size: 11px; color: #6e7681; margin: 2px 0 0; }

.dp-close {
  flex-shrink: 0; background: none; border: none; color: #6e7681;
  cursor: pointer; padding: 4px; border-radius: 4px;
  display: flex; align-items: center; transition: color 0.15s;
}
.dp-close:hover { color: #c9d1d9; }

.dp-body { flex: 1; overflow-y: auto; }

.dp-center {
  display: flex; align-items: center; justify-content: center;
  min-height: 200px; color: #6e7681;
}
.dp-error { color: #f97316; font-size: 13px; }

.dp-spin { animation: dp-spin 1s linear infinite; color: #6e7681; }
@keyframes dp-spin { to { transform: rotate(360deg); } }

.dp-text-wrap { padding: 20px; }
.dp-text {
  font-family: 'JetBrains Mono', 'Fira Code', ui-monospace, monospace;
  font-size: 12px; line-height: 1.7; color: #c9d1d9;
  white-space: pre-wrap; word-break: break-word; margin: 0;
}

.dp-truncated-note {
  text-align: center; font-size: 11px; color: #6e7681;
  margin-top: 16px; padding-top: 12px; border-top: 1px solid #21262d;
}

.dp-fade-enter-active, .dp-fade-leave-active { transition: opacity 0.2s ease; }
.dp-fade-enter-from, .dp-fade-leave-to { opacity: 0; }
</style>
