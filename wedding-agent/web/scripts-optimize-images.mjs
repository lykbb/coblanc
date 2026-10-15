// 一次性：把 public 下的 PNG 转成 WebP（hero 1600px，其余 800px）
import sharp from 'sharp'
import { readdirSync, statSync } from 'node:fs'
import { join } from 'node:path'
const HERO = /hero|film-style-board|studio-framework/
function walk(dir) { return readdirSync(dir).flatMap((n) => { const p = join(dir, n); return statSync(p).isDirectory() ? walk(p) : [p] }) }
for (const file of walk('public').filter((f) => f.endsWith('.png'))) {
  const width = HERO.test(file) ? 1600 : 800
  const out = file.replace(/\.png$/, '.webp')
  const info = await sharp(file).resize({ width, withoutEnlargement: true }).webp({ quality: 78, effort: 5 }).toFile(out)
  console.log(out, Math.round(info.size / 1024) + 'KB')
}
