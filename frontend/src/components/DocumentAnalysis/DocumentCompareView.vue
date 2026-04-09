<template>
  <div class="dcv-root">
    <div class="dcv-summary-bar" v-if="compareSummary && !loading">
      <svg width="14" height="14" viewBox="0 0 14 14" fill="none" style="flex-shrink:0">
        <circle cx="7" cy="7" r="6" stroke="#6b7280" stroke-width="1.2"/>
        <path d="M7 5v3M7 9.5h.01" stroke="#6b7280" stroke-width="1.2" stroke-linecap="round"/>
      </svg>
      <p>{{ compareSummary }}</p>
    </div>

    <div v-if="loading" class="dcv-loading">
      <span class="dcv-spinner" />
      <span>Comparing documents…</span>
    </div>

    <div v-else class="dcv-panes">

      <div class="dcv-pane">
        <div class="dcv-pane-header">
          <span class="dcv-pane-label">A</span>
          <span class="dcv-pane-name" :title="documentA?.original_name">{{ documentA?.original_name }}</span>
          <span class="dcv-pane-count" v-if="highlightsA.length">
            {{ highlightsA.length }} findings
          </span>
        </div>
        <div class="dcv-pane-body">
          <DocumentViewer
            :document="documentA"
            :highlights="highlightsA"
            :active-highlight-id="activeIdA"
            :file-url="fileUrlA"
            @highlight-click="(hl, el) => onClickA(hl, el)"
          />
        </div>
      </div>

      <div class="dcv-divider" />

      <div class="dcv-pane">
        <div class="dcv-pane-header">
          <span class="dcv-pane-label">B</span>
          <span class="dcv-pane-name" :title="documentB?.original_name">{{ documentB?.original_name }}</span>
          <span class="dcv-pane-count" v-if="highlightsB.length">
            {{ highlightsB.length }} findings
          </span>
        </div>
        <div class="dcv-pane-body">
          <DocumentViewer
            :document="documentB"
            :highlights="highlightsB"
            :active-highlight-id="activeIdB"
            :file-url="fileUrlB"
            @highlight-click="(hl, el) => onClickB(hl, el)"
          />
        </div>
      </div>

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
import { ref } from 'vue'
import DocumentViewer from './DocumentViewer.vue'
import DocumentHighlightTooltip from './DocumentHighlightTooltip.vue'

const props = defineProps({
  documentA:      { type: Object,  required: true   },
  documentB:      { type: Object,  required: true   },
  fileUrlA:       { type: String,  default: null    },
  fileUrlB:       { type: String,  default: null    },
  highlightsA:    { type: Array,   default: () => [] },
  highlightsB:    { type: Array,   default: () => [] },
  metrics:        { type: Object,  default: null    },
  compareSummary: { type: String,  default: ''      },
  loading:        { type: Boolean, default: false   },
})

const activeIdA       = ref(null)
const activeIdB       = ref(null)
const tooltipVisible  = ref(false)
const tooltipHighlight = ref(null)
const tooltipRect     = ref(null)

function onClickA(hl, el) {
  activeIdA.value       = hl.id
  tooltipHighlight.value = hl
  tooltipRect.value     = el?.getBoundingClientRect() ?? null
  tooltipVisible.value  = true
}

function onClickB(hl, el) {
  activeIdB.value       = hl.id
  tooltipHighlight.value = hl
  tooltipRect.value     = el?.getBoundingClientRect() ?? null
  tooltipVisible.value  = true
}
</script>

<style scoped>
.dcv-root {
  display: flex; flex-direction: column;
  width: 100%; height: 100%; overflow: hidden;
}

.dcv-summary-bar {
  display: flex; align-items: flex-start; gap: 8px;
  padding: 10px 16px; background: #fafafa;
  border-bottom: 1px solid #e5e7eb;
  font-size: 12px; color: #4b5563; line-height: 1.5; flex-shrink: 0;
}
.dcv-summary-bar p { margin: 0; }

.dcv-loading {
  display: flex; align-items: center; gap: 10px;
  padding: 40px; color: #9ca3af; font-size: 13px;
}
.dcv-spinner {
  width: 16px; height: 16px;
  border: 2px solid #e5e7eb; border-top-color: #374151;
  border-radius: 50%; animation: dcv-spin 0.7s linear infinite;
}
@keyframes dcv-spin { to { transform: rotate(360deg); } }

.dcv-panes { display: flex; flex: 1; min-height: 0; overflow: hidden; }

.dcv-pane { flex: 1; min-width: 0; display: flex; flex-direction: column; overflow: hidden; }

.dcv-pane-header {
  display: flex; align-items: center; gap: 7px;
  padding: 6px 12px; border-bottom: 1px solid #e5e7eb;
  background: #fafafa; flex-shrink: 0;
}
.dcv-pane-label {
  font-size: 10px; font-weight: 700;
  background: #111; color: #fff;
  border-radius: 3px; padding: 1px 5px; letter-spacing: 0.04em;
}
.dcv-pane-name {
  flex: 1; font-size: 11.5px; font-weight: 500; color: #374151;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.dcv-pane-count { font-size: 10.5px; color: #9ca3af; }

.dcv-pane-body { flex: 1; overflow: hidden; }
.dcv-divider   { width: 1px; background: #e5e7eb; flex-shrink: 0; }
</style>
