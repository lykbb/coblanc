// 把接口里的 plan（只读方案进度）整理成卡片上要显示的文字。
import { STYLE_LABELS } from './agents.js'

export function styleLabel(id) {
  return STYLE_LABELS[id] || id || ''
}

// 9 个镜头按景别计数，例如 [{ name: '全身', count: 3 }, …]
export function framingCounts(shots) {
  const counts = new Map()
  for (const shot of shots || []) counts.set(shot.framing, (counts.get(shot.framing) || 0) + 1)
  return [...counts].map(([name, count]) => ({ name, count }))
}

// 需求单里的身高顺序固定为「新郎、新娘」
export function heights(brief) {
  const list = brief?.heights_cm || []
  return list.length === 2 ? { groom: list[0], bride: list[1] } : null
}

export function short(text, max = 46) {
  if (!text) return ''
  if (typeof text !== 'string') text = flat(text)
  const data = parseJson(text)
  if (data) text = lookSummary(data)
  if (!text || looksLikeJson(text)) return ''
  return text.length > max ? text.slice(0, max) + '…' : text
}
