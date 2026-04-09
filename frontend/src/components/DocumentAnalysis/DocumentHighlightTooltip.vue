<template>
  <Teleport to="body">
    <Transition name="ht-fade">
      <div
        v-if="visible && highlight"
        class="ht-root"
        :style="positionStyle"
        @click.stop
      >
        <div class="ht-category" :style="{ color: color.border }">
          <span class="ht-dot" :style="{ background: color.border }" />
          {{ color.label }}
        </div>
        <p class="ht-explanation">{{ highlight.explanation }}</p>
        <div v-if="highlight.section" class="ht-section">{{ highlight.section }}</div>
        <button class="ht-close" @click="emit('close')" aria-label="Close">
          <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
            <path d="M1 1l10 10M11 1L1 11" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
          </svg>
        </button>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup>
import { computed } from 'vue'
import { HIGHLIGHT_COLORS } from '@/utils/documentHighlighter.js'

const props = defineProps({
  visible:    { type: Boolean, default: false },
  highlight:  { type: Object,  default: null  },
  anchorRect: { type: Object,  default: null  },
})

const emit = defineEmits(['close'])

const color = computed(() =>
  HIGHLIGHT_COLORS[props.highlight?.category] ?? HIGHLIGHT_COLORS.clause_key
)

const positionStyle = computed(() => {
  const r = props.anchorRect
  if (!r) return { top: '100px', left: '50%', transform: 'translateX(-50%)' }

  const top  = r.bottom + window.scrollY + 8
  const left = Math.min(
    window.innerWidth - 316,
    Math.max(8, r.left + window.scrollX),
  )

  return { position: 'fixed', top: `${r.bottom + 8}px`, left: `${left}px` }
})
</script>

<style scoped>
.ht-root {
  position: fixed;
  z-index: 9999;
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  box-shadow: 0 8px 24px rgba(0,0,0,0.12), 0 2px 6px rgba(0,0,0,0.06);
  padding: 12px 36px 12px 14px;
  max-width: 300px;
  min-width: 200px;
}

.ht-category {
  display: flex; align-items: center; gap: 6px;
  font-size: 10.5px; font-weight: 700;
  letter-spacing: 0.06em; text-transform: uppercase;
  margin-bottom: 6px;
}
.ht-dot { width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0; }

.ht-explanation {
  margin: 0 0 6px;
  font-size: 12.5px; line-height: 1.5; color: #374151;
}

.ht-section { font-size: 11px; color: #9ca3af; font-style: italic; }

.ht-close {
  position: absolute; top: 8px; right: 8px;
  background: none; border: none; color: #9ca3af;
  cursor: pointer; padding: 2px; line-height: 1;
  border-radius: 3px; transition: color 0.15s;
}
.ht-close:hover { color: #374151; }

.ht-fade-enter-active, .ht-fade-leave-active { transition: opacity 0.15s, transform 0.15s; }
.ht-fade-enter-from, .ht-fade-leave-to { opacity: 0; transform: translateY(-4px); }
</style>
