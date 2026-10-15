// 把接口里的 plan（只读方案进度）整理成卡片上要显示的文字。
import { STYLE_LABELS } from './agents.js'

export function styleLabel(id) {
  return STYLE_LABELS[id] || id || ''
}

function tidy(text) {
  return text.trim().replace(/^(新娘|新郎)[：:]?/, '').replace(/^[，。；;、\s]+|[，。；;、\s]+$/g, '')
}

// 妆造师的 look.text 一般同时写新娘和新郎：按句子拆，以"新娘""新郎"开头的句子分别归两边；
// 同一句里"新娘……，新郎……"再从逗号处切开。不以两人开头的句子（总体风格、注意事项）不放进卡片。
export function splitLook(text) {
  if (!text) return { bride: '', groom: '' }
  const out = { bride: [], groom: [] }
  for (const raw of text.split(/[。；;\n]/)) {
    const sentence = raw.trim()
    const who = sentence.startsWith('新娘') ? 'bride' : sentence.startsWith('新郎') ? 'groom' : null
    if (!who) continue
    const other = who === 'bride' ? 'groom' : 'bride'
    const cut = sentence.search(who === 'bride' ? /[，,、]新郎/ : /[，,、]新娘/)
    out[who].push(tidy(cut > 0 ? sentence.slice(0, cut) : sentence))
    if (cut > 0) out[other].push(tidy(sentence.slice(cut + 1)))
  }
  if (!out.bride.length && !out.groom.length) return { bride: tidy(text), groom: '' }
  return { bride: out.bride.join('；'), groom: out.groom.join('；') }
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
  return text.length > max ? text.slice(0, max) + '…' : text
}
