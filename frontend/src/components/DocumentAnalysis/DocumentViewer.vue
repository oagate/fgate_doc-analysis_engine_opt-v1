<template>
  <div class="dv-root" ref="rootEl">

    <!-- Loading -->
    <div v-if="loading" class="dv-loading">
      <span class="dv-spinner" />
      <span class="dv-loading-text">{{ loadingText }}</span>
    </div>

    <!-- Error -->
    <div v-else-if="error" class="dv-error">
      <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
        <circle cx="10" cy="10" r="9" stroke="#ef4444" stroke-width="1.5"/>
        <path d="M10 6v4.5M10 13.5h.01" stroke="#ef4444" stroke-width="1.5" stroke-linecap="round"/>
      </svg>
      <span>{{ error }}</span>
    </div>

    <!-- PDF viewer -->
    <div v-else-if="isPdf" class="dv-pdf-wrap" ref="pdfWrap">
      <div
        v-for="page in renderedPages"
        :key="page.num"
        class="dv-pdf-page"
        :data-page="page.num"
      >
        <canvas :ref="el => setPageCanvas(el, page.num)" class="dv-canvas" />
        <div :ref="el => setTextLayer(el, page.num)" class="dv-text-layer" />
      </div>
    </div>

    <!-- DOCX / HTML viewer -->
    <div
      v-else-if="docHtml"
      class="dv-docx-wrap"
      ref="docxWrap"
      v-html="docHtml"
    />
    <div v-else-if="plainText" class="dv-plain-wrap" ref="plainWrap">
      <pre class="dv-plain">{{ plainText }}</pre>
    </div>

  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { applyHighlights, clearHighlights, scrollToHighlight } from '@/utils/documentHighlighter.js'

const props = defineProps({
  document:          { type: Object, required: true  },
  highlights:        { type: Array,  default: () => [] },
  activeHighlightId: { type: String, default: null   },
  fileUrl:           { type: String, default: null   },
  extractedText:     { type: String, default: ''     },
})

const emit = defineEmits(['highlight-click'])

const rootEl   = ref(null)
const pdfWrap  = ref(null)
const docxWrap = ref(null)
const plainWrap = ref(null)

const loading       = ref(false)
const loadingText   = ref('Loading document…')
const error         = ref(null)
const docHtml       = ref('')
const plainText     = ref('')
const renderedPages = ref([])

let _pdfDoc       = null
const _pageCanvases = {}
const _textLayers   = {}

const mime  = computed(() => props.document?.mime_type ?? '')
const isPdf = computed(() =>
  mime.value === 'application/pdf' ||
  props.document?.original_name?.endsWith('.pdf')
)
const isDocx = computed(() =>
  mime.value.includes('word') ||
  mime.value.includes('docx') ||
  /\.docx?$/i.test(props.document?.original_name ?? '')
)

watch(() => props.document, doc => { if (doc) _loadDocument() }, { immediate: true })
watch(() => props.highlights, async () => {
  await nextTick()
  _applyHighlights()
}, { deep: true })

watch(() => props.activeHighlightId, id => {
  if (!id) return
  const container = _getContainer()
  if (container) scrollToHighlight(container, id)
})

onBeforeUnmount(() => {
  if (_pdfDoc) { _pdfDoc.destroy(); _pdfDoc = null }
})

defineExpose({
  scrollToHighlight: (id) => {
    const c = _getContainer()
    if (c) scrollToHighlight(c, id)
  },
})

function setPageCanvas(el, num) { if (el) _pageCanvases[num] = el }
function setTextLayer(el, num)  { if (el) _textLayers[num]   = el }
function _getContainer() { return pdfWrap.value || docxWrap.value || plainWrap.value }

async function _loadDocument() {
  error.value         = null
  docHtml.value       = ''
  plainText.value     = ''
  renderedPages.value = []
  Object.keys(_pageCanvases).forEach(k => delete _pageCanvases[k])
  Object.keys(_textLayers).forEach(k => delete _textLayers[k])

  if (_pdfDoc) { _pdfDoc.destroy(); _pdfDoc = null }

  if (isPdf.value)      return _loadPdf()
  if (isDocx.value)     return _loadDocx()
  plainText.value = props.extractedText || ''
  await nextTick()
  _applyHighlights()
}

async function _loadPdf() {
  if (!props.fileUrl) {
    plainText.value = props.extractedText || ''
    return
  }

  loading.value   = true
  loadingText.value = 'Loading PDF…'

  try {
    const pdfjsLib = await import('pdfjs-dist')
    pdfjsLib.GlobalWorkerOptions.workerSrc = new URL(
      'pdfjs-dist/build/pdf.worker.mjs',
      import.meta.url,
    ).href

    _pdfDoc = await pdfjsLib.getDocument({ url: props.fileUrl }).promise
    renderedPages.value = Array.from({ length: _pdfDoc.numPages }, (_, i) => ({ num: i + 1 }))
    loading.value = false

    await nextTick()

    for (let p = 1; p <= _pdfDoc.numPages; p++) {
      await _renderPage(p)
    }

    await nextTick()
    _applyHighlights()
  } catch (err) {
    loading.value = false
    error.value   = `Could not load PDF: ${err.message}`
  }
}

async function _renderPage(pageNum) {
  const page     = await _pdfDoc.getPage(pageNum)
  const scale    = _calcScale()
  const viewport = page.getViewport({ scale })
  const canvas   = _pageCanvases[pageNum]
  const textEl   = _textLayers[pageNum]

  if (!canvas) return

  canvas.width  = viewport.width
  canvas.height = viewport.height
  canvas.style.width  = `${viewport.width}px`
  canvas.style.height = `${viewport.height}px`

  await page.render({ canvasContext: canvas.getContext('2d'), viewport }).promise

  if (textEl) {
    textEl.style.width  = `${viewport.width}px`
    textEl.style.height = `${viewport.height}px`

    const pdfjsLib   = await import('pdfjs-dist')
    const content    = await page.getTextContent()
    textEl.innerHTML = ''

    if (typeof pdfjsLib.TextLayer === 'function') {
      const tl = new pdfjsLib.TextLayer({ textContentSource: content, container: textEl, viewport })
      await tl.render()
    } else if (typeof pdfjsLib.renderTextLayer === 'function') {
      pdfjsLib.renderTextLayer({ textContentSource: content, container: textEl, viewport, textDivs: [] })
    }
  }
}

function _calcScale() {
  const w = pdfWrap.value?.clientWidth ?? 700
  return Math.min(2.0, Math.max(1.0, w / 700))
}

async function _loadDocx() {
  if (!props.fileUrl) {
    plainText.value = props.extractedText || ''
    return
  }

  loading.value   = true
  loadingText.value = 'Loading document…'

  try {
    const [mammoth, resp] = await Promise.all([
      import('mammoth'),
      fetch(props.fileUrl, { credentials: 'include' }),
    ])

    if (!resp.ok) throw new Error(`HTTP ${resp.status}`)

    const buffer = await resp.arrayBuffer()
    const result = await mammoth.convertToHtml({ arrayBuffer: buffer })

    docHtml.value = _sanitize(result.value)
    loading.value = false
    await nextTick()
    _applyHighlights()
  } catch (err) {
    loading.value   = false
    error.value     = `Could not load document: ${err.message}`
    plainText.value = props.extractedText || ''
  }
}

function _sanitize(html) {
  return html
    .replace(/<script[\s\S]*?<\/script>/gi, '')
    .replace(/<style[\s\S]*?<\/style>/gi, '')
    .replace(/\son\w+\s*=\s*["'][^"']*["']/gi, '')
    .replace(/href\s*=\s*["']javascript:[^"']*["']/gi, 'href="#"')
}

function _applyHighlights() {
  const container = _getContainer()
  if (!container || !props.highlights.length) return
  applyHighlights(container, props.highlights, (hl, markEl) => {
    emit('highlight-click', hl, markEl)
  })
}
</script>

<style scoped>
.dv-root {
  position: relative;
  width: 100%;
  height: 100%;
  overflow-y: auto;
  background: #f8f7f4;
}
.dv-loading {
  display: flex; align-items: center; gap: 10px;
  padding: 40px 24px; color: #888; font-size: 13px;
}
.dv-spinner {
  width: 16px; height: 16px;
  border: 2px solid #d1d5db; border-top-color: #374151;
  border-radius: 50%; animation: dv-spin 0.7s linear infinite; flex-shrink: 0;
}
@keyframes dv-spin { to { transform: rotate(360deg); } }
.dv-loading-text { color: #6b7280; }

.dv-error {
  display: flex; align-items: center; gap: 8px;
  padding: 24px; color: #ef4444; font-size: 13px;
}

.dv-pdf-wrap {
  display: flex; flex-direction: column; align-items: center;
  gap: 16px; padding: 24px 0 40px; background: #e8e6e0; min-height: 100%;
}
.dv-pdf-page { position: relative; box-shadow: 0 2px 12px rgba(0,0,0,0.18); }
.dv-canvas   { display: block; background: #fff; }
.dv-text-layer {
  position: absolute; inset: 0; overflow: hidden; opacity: 1; line-height: 1;
}
:deep(.dv-text-layer span) {
  color: transparent; position: absolute; white-space: pre;
  cursor: text; transform-origin: 0% 0%;
}
:deep(.dv-text-layer mark[data-hl-id]) {
  color: transparent; position: absolute;
}

.dv-docx-wrap {
  max-width: 760px; margin: 0 auto;
  padding: 48px 56px 64px; background: #fff; min-height: 100%;
  box-shadow: 0 0 0 1px rgba(0,0,0,0.06);
}
:deep(.dv-docx-wrap p)  { margin: 0 0 0.85em; line-height: 1.65; font-size: 14px; color: #1a1a1a; }
:deep(.dv-docx-wrap h1) { font-size: 1.4em; font-weight: 700; margin: 0 0 0.6em; color: #111; }
:deep(.dv-docx-wrap h2) { font-size: 1.2em; font-weight: 700; margin: 1.2em 0 0.5em; color: #111; }
:deep(.dv-docx-wrap h3) { font-size: 1.05em; font-weight: 600; margin: 1em 0 0.4em; color: #222; }
:deep(.dv-docx-wrap table) { border-collapse: collapse; width: 100%; margin: 1em 0; font-size: 13px; }
:deep(.dv-docx-wrap td, .dv-docx-wrap th) { border: 1px solid #d1d5db; padding: 6px 10px; }
:deep(.dv-docx-wrap th) { background: #f3f4f6; font-weight: 600; }

.dv-plain-wrap { padding: 32px 40px; max-width: 760px; margin: 0 auto; }
.dv-plain {
  font-family: 'Georgia', serif; font-size: 13.5px;
  line-height: 1.7; color: #1a1a1a; white-space: pre-wrap; word-break: break-word;
}

:deep(mark.hl-pulse) { animation: hl-pulse-anim 1.4s ease; }
@keyframes hl-pulse-anim {
  0%, 100% { filter: brightness(1); }
  30%      { filter: brightness(1.5); }
}
</style>
