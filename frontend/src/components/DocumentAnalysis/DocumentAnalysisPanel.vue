<template>
  <div class="dap-root">
    <div class="dap-header">
      <div class="dap-header-left">
        <button class="dap-close" @click="emit('close')" title="Close">
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
            <path d="M1 1l12 12M13 1L1 13" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
          </svg>
        </button>
        <div class="dap-doc-name">
          <span class="dap-doc-badge" :class="docBadgeClass">{{ docBadgeLabel }}</span>
          <span class="dap-doc-title" :title="document?.original_name">
            {{ document?.original_name || '—' }}
          </span>
        </div>
      </div>

      <div class="dap-header-right">
        <div class="dap-type-tabs" v-if="!isCompareMode">
          <button
            v-for="tab in analysisTabs"
            :key="tab.value"
            class="dap-type-tab"
            :class="{ 'dap-type-tab--active': activeType === tab.value }"
            @click="setAnalysisType(tab.value)"
          >
            {{ tab.label }}
          </button>
        </div>

        <button
          v-if="compareDocument"
          class="dap-compare-btn"
          :class="{ 'dap-compare-btn--active': isCompareMode }"
          @click="toggleCompare"
        >
          <svg width="13" height="13" viewBox="0 0 13 13" fill="none">
            <rect x="1" y="2" width="4" height="9" rx="1" stroke="currentColor" stroke-width="1.2"/>
            <rect x="8" y="2" width="4" height="9" rx="1" stroke="currentColor" stroke-width="1.2"/>
          </svg>
          Compare
        </button>

        <button
          class="dap-reanalyze"
          @click="triggerAnalysis(true)"
          :disabled="analysisLoading"
          title="Re-analyze"
        >
          <svg
            width="13" height="13" viewBox="0 0 13 13" fill="none"
            :class="{ 'dap-spin': analysisLoading }"
          >
            <path d="M11.5 6.5a5 5 0 11-1.5-3.5" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/>
            <path d="M11.5 3v3.5H8" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
        </button>
      </div>
    </div>

    <div class="dap-body" :class="{ 'dap-body--compare': isCompareMode }">
      <template v-if="!isCompareMode">
        <div class="dap-viewer-wrap">
          <DocumentViewer
            ref="viewerRef"
            :document="document"
            :highlights="activeHighlights"
            :active-highlight-id="activeHighlightId"
            :file-url="fileUrl"
            :extracted-text="document?.extracted_text || ''"
            @highlight-click="onHighlightClick"
          />
        </div>
        <div class="dap-sidebar-wrap">
          <DocumentAnalysisSidebar
            :highlights="activeHighlights"
            :metrics="analysis?.metrics || null"
            :active-id="activeHighlightId"
            :loading="analysisLoading"
            :error="analysisError"
            @finding-click="onFindingClick"
          />
        </div>
      </template>

      <DocumentCompareView
        v-else
        :document-a="document"
        :document-b="compareDocument"
        :file-url-a="fileUrl"
        :file-url-b="compareFileUrl"
        :highlights-a="analysis?.highlights || []"
        :highlights-b="analysis?.compare_highlights || []"
        :metrics="analysis?.metrics || null"
        :compare-summary="analysis?.compare_summary || ''"
        :loading="analysisLoading"
      />
    </div>

    <DocumentHighlightTooltip
      :visible="tooltipVisible"
      :highlight="tooltipHighlight"
      :anchor-rect="tooltipRect"
      @close="tooltipVisible = false"
    />

  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { useDocumentAnalysis } from '@/composables/useDocumentAnalysis.js'
import DocumentViewer from './DocumentViewer.vue'
import DocumentAnalysisSidebar from './DocumentAnalysisSidebar.vue'
import DocumentHighlightTooltip from './DocumentHighlightTooltip.vue'
import DocumentCompareView from './DocumentCompareView.vue'

const props = defineProps({
  document:        { type: Object, required: true },
  compareDocument: { type: Object, default: null  },
  chatId:          { type: String, required: true },
  fileUrl:         { type: String, default: null  },
  compareFileUrl:  { type: String, default: null  },
})

const emit = defineEmits(['close'])

const {
  analysis,
  analysisLoading,
  analysisError,
  activeType,
  triggerAnalysis,
  pollAnalysis,
  setAnalysisType,
  dispose,
} = useDocumentAnalysis(
  computed(() => props.chatId),
  computed(() => props.document?.id),
  computed(() => props.compareDocument?.id ?? null),
)

const viewerRef          = ref(null)
const activeHighlightId  = ref(null)
const isCompareMode      = ref(false)
const tooltipVisible     = ref(false)
const tooltipHighlight   = ref(null)
const tooltipRect        = ref(null)
const activeHighlights = computed(() => analysis.value?.highlights ?? [])
const analysisTabs = [
  { value: 'full',    label: 'Full Review' },
  { value: 'risk',    label: 'Risk Scan'   },
  { value: 'clauses', label: 'Clauses'     },
]

const docBadgeClass = computed(() => {
  const name = props.document?.original_name ?? ''
  const mime = props.document?.mime_type ?? ''
  if (mime.includes('pdf') || name.endsWith('.pdf'))    return 'dap-doc-badge--pdf'
  if (mime.includes('word') || /\.docx?$/i.test(name)) return 'dap-doc-badge--doc'
  return 'dap-doc-badge--txt'
})

const docBadgeLabel = computed(() => {
  if (docBadgeClass.value === 'dap-doc-badge--pdf') return 'PDF'
  if (docBadgeClass.value === 'dap-doc-badge--doc') return 'DOC'
  return 'TXT'
})

onMounted(() => {
  if (!analysis.value) {
    triggerAnalysis()
  } else {
    pollAnalysis()
  }
})

onUnmounted(() => dispose())

watch(
  () => props.document?.id,
  () => {
    activeHighlightId.value = null
    isCompareMode.value     = false
    setAnalysisType('full')
    triggerAnalysis()
  },
)

function onHighlightClick(hl, markEl) {
  activeHighlightId.value = hl.id
  tooltipHighlight.value  = hl
  tooltipRect.value       = markEl?.getBoundingClientRect() ?? null
  tooltipVisible.value    = true
}

function onFindingClick(hl) {
  activeHighlightId.value = hl.id
  tooltipVisible.value    = false
  viewerRef.value?.scrollToHighlight(hl.id)
}

function toggleCompare() {
  isCompareMode.value = !isCompareMode.value
  if (isCompareMode.value) {
    setAnalysisType('compare')
    triggerAnalysis()
  } else {
    setAnalysisType('full')
  }
}
</script>

<style scoped>
.dap-root {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: #fff;
  overflow: hidden;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
}

.dap-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 44px;
  min-height: 44px;
  padding: 0 12px 0 8px;
  border-bottom: 1px solid #e5e7eb;
  gap: 8px;
  background: #fff;
  flex-shrink: 0;
}

.dap-header-left  { display: flex; align-items: center; gap: 8px; min-width: 0; flex: 1; }
.dap-header-right { display: flex; align-items: center; gap: 6px; flex-shrink: 0; }

.dap-close {
  width: 28px; height: 28px;
  display: flex; align-items: center; justify-content: center;
  border: none; background: none; cursor: pointer;
  color: #9ca3af; border-radius: 4px;
  transition: color 0.12s, background 0.12s;
  flex-shrink: 0;
}
.dap-close:hover { color: #374151; background: #f3f4f6; }

.dap-doc-name  { display: flex; align-items: center; gap: 6px; min-width: 0; }
.dap-doc-badge {
  font-size: 9px; font-weight: 700;
  padding: 2px 5px; border-radius: 3px;
  letter-spacing: 0.04em; flex-shrink: 0;
  text-transform: uppercase;
}
.dap-doc-badge--pdf { background: #fee2e2; color: #b91c1c; }
.dap-doc-badge--doc { background: #dbeafe; color: #1d4ed8; }
.dap-doc-badge--txt { background: #d1fae5; color: #065f46; }

.dap-doc-title {
  font-size: 12.5px; font-weight: 600; color: #111;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}

/* Analysis type tabs */
.dap-type-tabs { display: flex; gap: 2px; }
.dap-type-tab {
  padding: 4px 10px;
  font-size: 11px; font-weight: 500;
  border: 1px solid transparent; border-radius: 4px;
  background: none; cursor: pointer; color: #6b7280;
  transition: all 0.12s;
}
.dap-type-tab:hover { background: #f3f4f6; color: #374151; }
.dap-type-tab--active { background: #111; color: #fff; border-color: #111; }

.dap-compare-btn {
  display: flex; align-items: center; gap: 5px;
  padding: 4px 10px;
  font-size: 11px; font-weight: 500;
  border: 1px solid #e5e7eb; border-radius: 4px;
  background: none; cursor: pointer; color: #6b7280;
  transition: all 0.12s;
}
.dap-compare-btn:hover { border-color: #9ca3af; color: #374151; }
.dap-compare-btn--active { border-color: #111; background: #111; color: #fff; }

.dap-reanalyze {
  width: 28px; height: 28px;
  display: flex; align-items: center; justify-content: center;
  border: 1px solid #e5e7eb; border-radius: 4px;
  background: none; cursor: pointer; color: #6b7280;
  transition: all 0.12s;
}
.dap-reanalyze:hover:not(:disabled) { border-color: #9ca3af; color: #374151; }
.dap-reanalyze:disabled { opacity: 0.4; cursor: default; }

.dap-spin { animation: dap-spin 0.9s linear infinite; }
@keyframes dap-spin { to { transform: rotate(360deg); } }

.dap-body {
  display: flex;
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

.dap-viewer-wrap {
  flex: 1;
  min-width: 0;
  overflow: hidden;
}

.dap-sidebar-wrap {
  width: 240px;
  min-width: 200px;
  max-width: 260px;
  flex-shrink: 0;
  overflow: hidden;
  border-left: 1px solid #e5e7eb;
}
</style>
