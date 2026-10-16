// 用量页、概览、任务详情共用的格式化
export const KINDS = { agent: '对话', cheap: '轻量', vision: '看图', image: '生图' }
export const num = (n) => (n || 0).toLocaleString('zh-CN')
export const short = (n) => (n >= 1e6 ? +(n / 1e6).toFixed(1) + 'M' : n >= 1e3 ? +(n / 1e3).toFixed(1) + 'K' : String(+n.toFixed(2)))
export const yuan = (v) => (v == null ? '—' : '¥' + (v === 0 ? '0' : v < 0.01 ? v.toFixed(4) : v.toFixed(2)))
export const money = (b) => (b.cost || !b.unpriced ? yuan(b.cost) : '—') + (b.unpriced ? `（${b.unpriced} 条无官方价）` : '')
export function price(p) {
  if (!p) return '无'
  if (!p.verified) return '未核实'
  if (p.unit === 'per_image') return `¥${p.per_image}/张`
  const { offpeak: o, peak: k } = p.tiers
  return `入 ${o.input}/${k.input} · 缓存 ${o.cache_hit}/${k.cache_hit} · 出 ${o.output}/${k.output} 元/百万（空闲/高峰）`
}
// 坐标轴：取整到 1/2/5×10^n，返回 [max, 刻度]
export function ticks(max, count = 4) {
  if (!(max > 0)) return [count, Array.from({ length: count + 1 }, (_, i) => i)]
  const raw = max / count
  const mag = 10 ** Math.floor(Math.log10(raw))
  const step = [1, 2, 5, 10].map((m) => m * mag).find((s) => s >= raw)
  const top = step * Math.ceil(max / step)
  return [top, Array.from({ length: Math.round(top / step) + 1 }, (_, i) => +(i * step).toPrecision(6))]
}
