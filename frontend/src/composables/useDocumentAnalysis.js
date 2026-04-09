import { computed, ref } from 'vue'
import { useDocumentAnalysisStore } from '@/stores/documentAnalysis.js'

const POLL_INTERVAL_MS = 2_500
const MAX_POLLS        = 48
const _RISK_CATEGORIES   = new Set(['risk_high', 'risk_medium', 'risk_low'])
const _CLAUSE_CATEGORIES = new Set(['clause_key', 'obligation'])

export function useDocumentAnalysis(chatId, documentId, compareDocumentId = null) {
  const store = useDocumentAnalysisStore()
  const activeType      = ref('full')
  const analysisLoading = ref(false)
  const analysisError   = ref(false)
  let _pollTimer  = null
  let _pollCount  = 0
  const _chatId  = () => (typeof chatId      === 'object' ? chatId.value      : chatId)
  const _docId   = () => (typeof documentId  === 'object' ? documentId.value  : documentId)
  const _cmpId   = () => {
    const v = typeof compareDocumentId === 'object'
      ? compareDocumentId?.value
      : compareDocumentId
    return v || null
  }

  const analysis = computed(() => {
    const docId    = _docId()
    const cmpId    = _cmpId()
    const type     = activeType.value
    const dedicated = store.getAnalysis(docId, type, cmpId)
    if (dedicated) return dedicated

    if (type === 'risk' || type === 'clauses') {
      const full = store.getAnalysis(docId, 'full', cmpId)
      if (full?.status === 'done') {
        const cats = type === 'risk' ? _RISK_CATEGORIES : _CLAUSE_CATEGORIES
        return {
          ...full,
          analysis_type: type,
          highlights: (full.highlights ?? []).filter(h => cats.has(h.category)),
          _derived: true,
        }
      }
    }

    return null
  })

  async function triggerAnalysis(force = false) {
    const cId = _chatId()
    const dId = _docId()
    if (!cId || !dId) return

    _stopPolling()
    analysisLoading.value = true
    analysisError.value   = false

    try {
      const result = await store.triggerAnalysis(cId, dId, activeType.value, {
        compareDocumentId: _cmpId(),
        force,
      })

      if (result.status === 'done') {
        analysisLoading.value = false
      } else if (result.status === 'failed') {
        analysisLoading.value = false
        analysisError.value   = true
      } else {
        _startPolling()
      }
    } catch {
      analysisLoading.value = false
      analysisError.value   = true
    }
  }

  async function pollAnalysis() {
    const existing = analysis.value

    if (!existing || existing.status === 'done') return
    if (existing.status === 'failed') {
      analysisError.value = true
      return
    }

    analysisLoading.value = true
    _startPolling()
  }

  function setAnalysisType(type) {
    if (type === activeType.value) return

    _stopPolling()
    activeType.value      = type
    analysisLoading.value = false
    analysisError.value   = false
    if (type === 'risk' || type === 'clauses') {
      const full = store.getAnalysis(_docId(), 'full', _cmpId())
      if (full?.status === 'done') return
    }

    const existing = analysis.value
    if (!existing || existing.status !== 'done') {
      triggerAnalysis()
    }
  }

  function dispose() {
    _stopPolling()
  }

  function _startPolling() {
    _pollCount = 0
    _pollTimer = setInterval(_poll, POLL_INTERVAL_MS)
  }

  function _stopPolling() {
    if (_pollTimer) {
      clearInterval(_pollTimer)
      _pollTimer = null
    }
    _pollCount = 0
  }

  async function _poll() {
    _pollCount++

    if (_pollCount > MAX_POLLS) {
      _stopPolling()
      analysisLoading.value = false
      analysisError.value   = true
      return
    }

    try {
      const result = await store.fetchAnalysis(
        _chatId(),
        _docId(),
        activeType.value,
        _cmpId(),
      )

      if (result?.status === 'done') {
        _stopPolling()
        analysisLoading.value = false
      } else if (result?.status === 'failed') {
        _stopPolling()
        analysisLoading.value = false
        analysisError.value   = true
      }
    } catch {
    }
  }

  return {
    analysis,
    analysisLoading,
    analysisError,
    activeType,
    triggerAnalysis,
    pollAnalysis,
    setAnalysisType,
    dispose,
  }
}
