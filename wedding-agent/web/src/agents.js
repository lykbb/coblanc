// 页面上用到的人设、名称和图片。改名字、头像只改这里。
const ASSET = '/coblanc-film/assets/'

export const AMIE = {
  name: 'Amie 艾蜜',
  title: 'AMIE 艾蜜',
  intro: ['你的婚纱照 AI 创意伙伴', '和专属项目导演'],
  avatar: ASSET + 'amie-portrait.webp',
}

// 每个步骤由谁出面说话；key 对应接口里的 step
export const SPEAKERS = {
  intake: { name: 'Amie', role: '主理人', initial: 'A', color: '#D9775E' },
  styling: { name: '妆造师', role: '妆容、发型、服装', initial: '妆', color: '#B9667A' },
  framing: { name: '摄影师', role: '场景、镜头、灯光', initial: '摄', color: '#55789E' },
  composing: { name: 'Amie', role: '整理拍摄指令', initial: 'A', color: '#D9775E' },
  generating: { name: '生图师', role: '按方案出片', initial: '生', color: '#7466B0' },
  checking: { name: '修图师', role: '逐张质检', initial: '修', color: '#4C8C72' },
  retouching: { name: '修图师', role: '返修不满意的地方', initial: '修', color: '#4C8C72' },
  packaging: { name: 'Amie', role: '制作婚礼物料', initial: 'A', color: '#D9775E' },
}

export const speakerOf = (step) => SPEAKERS[step] || SPEAKERS.intake

// 风格编号 → 中文名（和妆造师模块的风格编号一致）
export const STYLE_LABELS = {
  chinese_red_gold: '东方中式喜嫁',
  korean_studio: '韩式影棚',
  french_editorial: '法式杂志',
  forest: '森系自然',
  retro: '复古胶片',
  cinematic: '电影感',
  keep_original: '保留原图场景',
  undecided: '还没定',
}

// 风格示意图（品牌自己的风格板，只在没有资产库图片时用）
export const STYLE_ART = {
  chinese_red_gold: ASSET + 'style-chinese.webp',
  korean_studio: ASSET + 'style-korean.webp',
  french_editorial: ASSET + 'style-french.webp',
  cinematic: ASSET + 'style-cinema.webp',
  retro: ASSET + 'style-film.webp',
  forest: ASSET + 'style-minimal.webp',
  keep_original: ASSET + 'style-minimal.webp',
}

export const MATERIAL_LABELS = {
  photo: '主视觉高清图',
  invitation: '请柬主视觉 4:5',
  welcome_poster: '迎宾海报 2:3',
  led_screen: '婚礼大屏 16:9',
  moments: '朋友圈图',
}

export const REDO_REASONS = [
  { value: 'face', label: '脸不太像' },
  { value: 'body', label: '身材比例不对' },
  { value: 'hands', label: '手部有问题' },
  { value: 'style', label: '想换一种风格' },
  { value: 'other', label: '其他' },
]
