<template>
  <div class="das-root">
    <div class="das-risk-block">
      <div class="das-risk-row">
        <span class="das-risk-score" :style="{ color: riskColor }">
          {{ metrics?.risk_score ?? '—' }}
        </span>
        <div class="das-risk-info">
          <span class="das-risk-label" :style="{ color: riskColor }">
            {{ metrics?.risk_label || 'Analyzing…' }}
          </span>
          <span class="das-risk-sub">Risk Score</span>
        </div>
      </div>
      <div class="das-risk-bar-track">
        <div
          class="das-risk-bar-fill"
          :style="{ width: `${metrics?.risk_score ?? 0}%`, background: riskColor }"
        />
      </div>
    </div>

    <div class="das-metrics-row" v-if="metrics">
      <div class="das-metric">
        <span class="das-metric-val">{{ metrics.clause_count || 0 }}</span>
        <span class="das-metric-lbl">Clauses</span>
      </div>
      <div class="das-metric">
        <span class="das-metric-val">{{ metrics.obligation_count || 0 }}</span>
        <span class="das-metric-lbl">Obligations</span>
      </div>
      <div class="das-metric">
        <span
          class="das-metric-val"
          :style="{ color: (metrics.flagged_count || 0) > 0 ? '#ef4444' : 'inherit' }"
        >
          {{ metrics.flagged_count || 0 }}
        </span>
        <span class="das-metric-lbl">Flagged</span>
      </div>
    </div>

    <div class="das-summary" v-if="metrics?.summary">
      <p>{{ metrics.summary }}</p>
    </div>

    <div class="das-chips-block" v-if="metrics?.parties?.length">
      <div class="das-chips-label">Parties</div>
      <div class="das-chips">
        <span v-for="p in metrics.parties" :key="p" class="das-chip das-chip--party">{{ p }}</span>
      </div>
    </div>

    <div class="das-chips-block" v-if="metrics?.key_dates?.length">
      <div class="das-chips-label">Key Dates</div>
      <div class="das-chips">
        <span v-for="d in metrics.key_dates" :key="d" class="das-chip das-chip--date">{{ d }}</span>
      </div>
    </div>

    <div class="das-divider" v-if="groupedHighlights.length" />

    <div class="das-section-label" v-if="groupedHighlights.length">
      Findings ({{ highlights.length }})
    </div>

    <div class="das-groups">
      <div v-for="group in groupedHighlights" :key="group.category" class="das-group">
        <button class="das-group-header" @click="toggleGroup(group.category)">
          <span class="das-group-dot" :style="{ background: group.color.border }" />
          <span class="das-group-name">{{ group.label }}</span>
          <span class="das-group-count">{{ group.items.length }}</span>
          <svg
            class="das-group-chevron"
            :class="{ 'das-group-chevron--open': openGroups.has(group.category) }"
            width="12" height="12" viewBox="0 0 12 12" fill="none"
          >
            <path d="M3 4.5l3 3 3-3" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
        </button>

        <Transition name="das-slide">
          <div v-if="openGroups.has(group.category)" class="das-group-items">
            <button
              v-for="hl in group.items"
              :key="hl.id"
              class="das-finding"
              :class="{ 'das-finding--active': activeId === hl.id }"
              :style="activeId === hl.id ? { borderLeftColor: group.color.border } : {}"
              @click="emit('finding-click', hl)"
            >
              <p class="das-finding-text">{{ hl.text }}</p>
              <p class="das-finding-exp">{{ hl.explanation }}</p>
              <span v-if="hl.section" class="das-finding-section">{{ hl.section }}</span>
            </button>
          </div>
        </Transition>
      </div>
    </div>

    <div class="das-empty" v-if="!highlights.length && !loading && !error">
      <svg width="28" height="28" viewBox="0 0 28 28" fill="none">
        <circle cx="14" cy="14" r="13" stroke="#d1d5db" stroke-width="1.5"/>
        <path d="M14 9v5.5M14 17.5h.01" stroke="#d1d5db" stroke-width="1.5" stroke-linecap="round"/>
      </svg>
      <span>No findings yet</span>
    </div>

    <div class="das-processing" v-if="loading">
      <span class="das-proc-spinner" />
      <span>Analyzing document…</span>
    </div>

    <div class="das-err" v-if="error && !loading">
      <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
        <circle cx="8" cy="8" r="7" stroke="#ef4444" stroke-width="1.5"/>
        <path d="M8 5v3.5M8 11h.01" stroke="#ef4444" stroke-width="1.5" stroke-linecap="round"/>
      </svg>
      <span>Analysis failed</span>
    </div>

  </div>
</template>

<script setup>
import { computed, reactive } from 'vue'
import { HIGHLIGHT_COLORS } from '@/utils/documentHighlighter.js'

const props = defineProps({
  highlights: { type: Array,   default: () => [] },
  metrics:    { type: Object,  default: null     },
  activeId:   { type: String,  default: null     },
  loading:    { type: Boolean, default: false    },
  error:      { type: Boolean, default: false    },
})

const emit = defineEmits(['finding-click'])

const openGroups = reactive(new Set(['risk_high', 'risk_medium']))

function toggleGroup(category) {
  openGroups.has(category) ? openGroups.delete(category) : openGroups.add(category)
}

const riskColor = computed(() => {
  const s = props.metrics?.risk_score ?? 0
  if (s >= 76) return '#dc2626'
  if (s >= 51) return '#ef4444'
  if (s >= 26) return '#f97316'
  return '#22c55e'
})

const GROUP_ORDER = ['risk_high', 'risk_medium', 'risk_low', 'clause_key', 'obligation', 'party', 'date']

const groupedHighlights = computed(() => {
  const map = {}
  for (const hl of props.highlights) {
    if (!map[hl.category]) map[hl.category] = []
    map[hl.category].push(hl)
  }
  return GROUP_ORDER
    .filter(cat => map[cat]?.length)
    .map(cat => ({
      category: cat,
      color:    HIGHLIGHT_COLORS[cat],
      label:    HIGHLIGHT_COLORS[cat].label,
      items:    map[cat],
    }))
})
</script>

<style scoped>
.das-root {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow-y: auto;
  padding: 16px 0;
  background: #fff;
}

.das-risk-block { padding: 0 16px 14px; }
.das-risk-row   { display: flex; align-items: center; gap: 12px; margin-bottom: 10px; }
.das-risk-score {
  font-size: 36px; font-weight: 700; line-height: 1;
  min-width: 52px; font-variant-numeric: tabular-nums;
}
.das-risk-info  { display: flex; flex-direction: column; gap: 2px; }
.das-risk-label { font-size: 13px; font-weight: 700; }
.das-risk-sub   { font-size: 10.5px; color: #9ca3af; text-transform: uppercase; letter-spacing: 0.05em; }
.das-risk-bar-track {
  height: 4px; background: #f3f4f6; border-radius: 4px; overflow: hidden;
}
.das-risk-bar-fill {
  height: 100%; border-radius: 4px;
  transition: width 0.6s cubic-bezier(0.4,0,0.2,1);
}

.das-metrics-row {
  display: flex;
  border-top: 1px solid #f3f4f6;
  border-bottom: 1px solid #f3f4f6;
  margin-bottom: 14px;
}
.das-metric {
  flex: 1; display: flex; flex-direction: column;
  align-items: center; padding: 10px 0; gap: 2px;
  border-right: 1px solid #f3f4f6;
}
.das-metric:last-child { border-right: none; }
.das-metric-val { font-size: 18px; font-weight: 700; color: #111; font-variant-numeric: tabular-nums; }
.das-metric-lbl { font-size: 10px; color: #9ca3af; text-transform: uppercase; letter-spacing: 0.06em; }

.das-summary { padding: 0 16px 14px; }
.das-summary p { margin: 0; font-size: 12.5px; line-height: 1.55; color: #4b5563; }

.das-chips-block { padding: 0 16px 12px; }
.das-chips-label {
  font-size: 10px; font-weight: 700; text-transform: uppercase;
  letter-spacing: 0.08em; color: #9ca3af; margin-bottom: 6px;
}
.das-chips { display: flex; flex-wrap: wrap; gap: 4px; }
.das-chip { font-size: 11px; padding: 2px 8px; border-radius: 3px; font-weight: 500; }
.das-chip--party { background: rgba(34,197,94,0.1);  color: #15803d; }
.das-chip--date  { background: rgba(20,184,166,0.1); color: #0f766e; }

.das-divider { height: 1px; background: #f3f4f6; margin: 0 0 12px; }
.das-section-label {
  padding: 0 16px 8px;
  font-size: 10px; font-weight: 700;
  text-transform: uppercase; letter-spacing: 0.08em; color: #9ca3af;
}

.das-groups { flex: 1; }
.das-group  { border-bottom: 1px solid #f3f4f6; }
.das-group-header {
  display: flex; align-items: center; gap: 7px;
  width: 100%; padding: 9px 16px;
  background: none; border: none; cursor: pointer; text-align: left;
  transition: background 0.12s;
}
.das-group-header:hover { background: #fafafa; }
.das-group-dot   { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.das-group-name  { flex: 1; font-size: 12px; font-weight: 600; color: #374151; }
.das-group-count {
  font-size: 10.5px; background: #f3f4f6; color: #6b7280;
  border-radius: 10px; padding: 1px 7px; font-weight: 600;
}
.das-group-chevron { color: #9ca3af; transition: transform 0.2s; flex-shrink: 0; }
.das-group-chevron--open { transform: rotate(180deg); }

.das-group-items { background: #fafafa; }
.das-finding {
  display: block; width: 100%;
  padding: 9px 16px 9px 20px;
  border: none; border-left: 3px solid transparent;
  background: none; text-align: left; cursor: pointer;
  transition: background 0.12s, border-color 0.12s;
  border-bottom: 1px solid #f0f0f0;
}
.das-finding:hover     { background: #f3f4f6; }
.das-finding--active   { background: #f0f4ff; }
.das-finding:last-child { border-bottom: none; }
.das-finding-text {
  margin: 0 0 3px;
  font-size: 11.5px; font-style: italic; color: #374151; line-height: 1.4;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
}
.das-finding-exp  { margin: 0; font-size: 11px; color: #6b7280; line-height: 1.4; }
.das-finding-section { font-size: 10px; color: #9ca3af; margin-top: 3px; display: block; }

.das-empty, .das-processing, .das-err {
  display: flex; flex-direction: column; align-items: center;
  gap: 10px; padding: 32px 20px; color: #9ca3af;
  font-size: 12.5px; text-align: center;
}
.das-err { color: #ef4444; }
.das-proc-spinner {
  width: 18px; height: 18px;
  border: 2px solid #e5e7eb; border-top-color: #374151;
  border-radius: 50%; animation: das-spin 0.7s linear infinite;
}
@keyframes das-spin { to { transform: rotate(360deg); } }

.das-slide-enter-active, .das-slide-leave-active { transition: all 0.18s ease; overflow: hidden; }
.das-slide-enter-from, .das-slide-leave-to { opacity: 0; max-height: 0; }
.das-slide-enter-to, .das-slide-leave-from { opacity: 1; max-height: 600px; }
</style>
