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
// 卡片上绝不显示原始 JSON：能解析就转成中文摘要，不能就给一句友好的话
const FIELD_LABELS = [
  [/makeup|妆/i, '妆容'], [/hair|发/i, '发型'], [/dress|gown|outfit|cloth|suit|服|装/i, '服装'],
  [/access|jewel|veil|饰|头纱/i, '配饰'],
]
const SIDE_KEYS = { bride: ['bride', 'female', 'woman', '新娘', '女生'], groom: ['groom', 'male', 'man', '新郎', '男生'] }

export function parseJson(value) {
  if (value && typeof value === 'object') return value
  if (typeof value !== 'string') return null
  const t = value.trim()
  if (!/^[[{]/.test(t)) return null
  try { return JSON.parse(t) } catch { return null }
}

function flat(value) {
  if (value == null) return ''
  if (typeof value === 'string') return looksLikeJson(value) ? '' : value.trim()
  if (Array.isArray(value)) return value.map(flat).filter(Boolean).join('、')
  if (typeof value === 'object') return Object.values(value).map(flat).filter(Boolean).join('，')
  return String(value)
}

export function looksLikeJson(text) {
  return typeof text === 'string' && /^\s*[[{]\s*("|\[|\{|$)/.test(text)
}

// 一侧的造型对象 → 「妆容：…；发型：…；服装：…」
export function lookSummary(obj) {
  if (!obj) return ''
  if (typeof obj !== 'object') return flat(obj)
  const seen = new Set()
  const parts = []
  for (const [pattern, label] of FIELD_LABELS) {
    for (const [key, value] of Object.entries(obj)) {
      if (seen.has(key) || !pattern.test(key)) continue
      const text = flat(value)
      seen.add(key)
      if (text) parts.push(`${label}：${text}`)
    }
  }
  if (!parts.length) return flat(obj)
  return parts.join('；')
}

function sideFromJson(data, side) {
  const key = Object.keys(data).find((k) => SIDE_KEYS[side].includes(k.toLowerCase()))
  if (key) return lookSummary(data[key])
  // 没有分人的字段：从 makeup_retro / hair_xxx 这类平铺字段拼新娘摘要
  return side === 'bride' ? lookSummary(Object.fromEntries(Object.entries(data).filter(([k]) => k !== 'style'))) : ''
}

export function splitLook(text) {
  if (!text) return { bride: '', groom: '' }
  const data = parseJson(text)
  if (data && !Array.isArray(data)) return { bride: sideFromJson(data, 'bride'), groom: sideFromJson(data, 'groom') }
  if (looksLikeJson(text)) return { bride: '', groom: '' }
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
  if (typeof text !== 'string') text = flat(text)
  const data = parseJson(text)
  if (data) text = lookSummary(data)
  if (!text || looksLikeJson(text)) return ''
  return text.length > max ? text.slice(0, max) + '…' : text
}
