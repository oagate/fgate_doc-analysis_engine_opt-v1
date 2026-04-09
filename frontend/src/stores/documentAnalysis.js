import { defineStore } from 'pinia'
import { ref } from 'vue'
import api from '@/services/axios.js'

export const useDocumentAnalysisStore = defineStore('documentAnalysis', () => {
  const analyses = ref({})

  async function triggerAnalysis(chatId, documentId, analysisType = 'full', options = {}) {
    const payload = { analysis_type: analysisType }
    if (options.compareDocumentId) payload.compare_document_id = options.compareDocumentId
    if (options.force) payload.force = true

    const res = await api.post(
      `/api/chats/${chatId}/documents/${documentId}/analyze`,
      payload,
    )

    const key = _key(documentId, analysisType, options.compareDocumentId)
    analyses.value[key] = res.data
    return res.data
  }

  async function fetchAnalysis(chatId, documentId, analysisType = 'full', compareDocumentId = null) {
    const params = { analysis_type: analysisType }
    if (compareDocumentId) params.compare_document_id = compareDocumentId

    try {
      const res = await api.get(
        `/api/chats/${chatId}/documents/${documentId}/analysis`,
        { params },
      )
      const key = _key(documentId, analysisType, compareDocumentId)
      analyses.value[key] = res.data
      return res.data
    } catch (err) {
      if (err.response?.status === 404) return null
      throw err
    }
  }

  function getAnalysis(documentId, analysisType = 'full', compareDocumentId = null) {
    return analyses.value[_key(documentId, analysisType, compareDocumentId)] ?? null
  }

  function clearAnalysis(documentId) {
    for (const key of Object.keys(analyses.value)) {
      if (key.startsWith(documentId + ':')) {
        delete analyses.value[key]
      }
    }
  }

  function _key(docId, type, compareId) {
    return compareId
      ? `${docId}:${type}:${compareId}`
      : `${docId}:${type}`
  }

  return {
    analyses,
    triggerAnalysis,
    fetchAnalysis,
    getAnalysis,
    clearAnalysis,
  }
})
