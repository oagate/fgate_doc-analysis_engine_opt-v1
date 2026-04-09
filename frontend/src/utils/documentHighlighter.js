export const HIGHLIGHT_COLORS = {
  risk_high:   { bg: 'rgba(239,68,68,0.18)',   border: '#ef4444', label: 'High Risk' },
  risk_medium: { bg: 'rgba(249,115,22,0.18)',  border: '#f97316', label: 'Medium Risk' },
  risk_low:    { bg: 'rgba(234,179,8,0.15)',   border: '#eab308', label: 'Low Risk' },
  clause_key:  { bg: 'rgba(59,130,246,0.15)',  border: '#3b82f6', label: 'Key Clause' },
  obligation:  { bg: 'rgba(168,85,247,0.15)',  border: '#a855f7', label: 'Obligation' },
  party:       { bg: 'rgba(34,197,94,0.15)',   border: '#22c55e', label: 'Party' },
  date:        { bg: 'rgba(20,184,166,0.15)',  border: '#14b8a6', label: 'Date' },
}

export function applyHighlights(container, highlights, onClick) {
  if (!container || !highlights?.length) return
  clearHighlights(container)

  for (const hl of highlights) {
    if (!hl.text?.trim()) continue
    _injectHighlight(container, hl, onClick)
  }
}

export function clearHighlights(container) {
  if (!container) return
  const marks = container.querySelectorAll('mark[data-hl-id]')
  for (const mark of marks) {
    const parent = mark.parentNode
    while (mark.firstChild) {
      parent.insertBefore(mark.firstChild, mark)
    }
    parent.removeChild(mark)
    parent.normalize()
  }
}

export function scrollToHighlight(container, highlightId) {
  if (!container || !highlightId) return
  const mark = container.querySelector(`mark[data-hl-id="${CSS.escape(highlightId)}"]`)
  if (!mark) return

  mark.scrollIntoView({ behavior: 'smooth', block: 'center' })
  mark.classList.remove('hl-pulse')
  void mark.offsetWidth
  mark.classList.add('hl-pulse')
}

function _injectHighlight(container, highlight, onClick) {
  const searchText = highlight.text.trim()
  const colors = HIGHLIGHT_COLORS[highlight.category] || HIGHLIGHT_COLORS.clause_key
  const textNodes = _collectTextNodes(container)

  for (const node of textNodes) {
    const idx = node.nodeValue.indexOf(searchText)
    if (idx === -1) continue

    const before = node.nodeValue.slice(0, idx)
    const after  = node.nodeValue.slice(idx + searchText.length)

    const mark = document.createElement('mark')
    mark.dataset.hlId = highlight.id
    mark.dataset.hlCategory = highlight.category
    mark.textContent = searchText
    mark.style.cssText = `
      background: ${colors.bg};
      border-bottom: 2px solid ${colors.border};
      border-radius: 2px;
      padding: 0 1px;
      cursor: pointer;
      transition: filter 0.15s;
    `

    mark.addEventListener('click', (e) => {
      e.stopPropagation()
      onClick(highlight, mark)
    })

    mark.addEventListener('mouseenter', () => {
      mark.style.filter = 'brightness(1.15)'
    })
    mark.addEventListener('mouseleave', () => {
      mark.style.filter = ''
    })

    const parent = node.parentNode
    parent.insertBefore(document.createTextNode(before), node)
    parent.insertBefore(mark, node)
    parent.insertBefore(document.createTextNode(after), node)
    parent.removeChild(node)

    break
  }
}

function _collectTextNodes(root) {
  const nodes = []
  const walker = document.createTreeWalker(
    root,
    NodeFilter.SHOW_TEXT,
    {
      acceptNode(node) {
        const tag = node.parentElement?.tagName?.toUpperCase()
        if (tag === 'SCRIPT' || tag === 'STYLE' || tag === 'MARK') {
          return NodeFilter.FILTER_REJECT
        }
        return node.nodeValue.trim()
          ? NodeFilter.FILTER_ACCEPT
          : NodeFilter.FILTER_SKIP
      },
    },
  )
  let node
  while ((node = walker.nextNode())) {
    nodes.push(node)
  }
  return nodes
}
