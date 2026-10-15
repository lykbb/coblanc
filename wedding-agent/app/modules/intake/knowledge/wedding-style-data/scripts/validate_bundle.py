#!/usr/bin/env python3
"""Validate the data contract; optional local source SHA audit. No network or mutation."""
from pathlib import Path
import json,re,hashlib,argparse,collections

def validate(root,local_audit=None):
 def read(p):return json.loads(p.read_text())
 c=read(root/'catalog.json');cases=c['cases'];allsets={x['set_id'] for x in cases};assert len(allsets)==len(cases)
 ids=set();total=0;composites=0;orientations=0;aliases=0
 for item in cases:
  sid=item['set_id'];base=root/'cases'/sid;r=read(base/'recipe.json');assets=read(base/'assets.json');shots=read(base/'shots.json')
  assert item['primary'] in [f'{i:02d}' for i in range(1,8)]
  assert r['set_id']==sid and r['secondary_category_id']==item['secondary'] and r['primary_category_id']==item['primary']
  assert not r['validation']['generation_tested'] and not r['validation']['validated_models']
  assert r['prompt_recipe']['model'] is None and not r['prompt_recipe']['original_prompt_recovered']
  ii={a['image_id'] for a in assets};assert len(ii)==len(assets)==len(shots)==item['image_count']
  assert ii=={x['image_id'] for x in shots};assert not ids.intersection(ii);ids.update(ii);total+=len(ii)
  for a in assets:
   assert re.fullmatch('IMG[0-9]{6}',a['image_id']);assert re.fullmatch('[a-f0-9]{64}',a['sha256'])
   assert a['width']>0 and a['height']>0 and a['service_url'] is None
   assert Path(a['file_name']).stem==a['image_id']
   orientations+=('orientation_review_required' in a.get('reference_constraints',[]))
  for f in r['observations']:assert f['evidence_type']=='observed' and f['evidence_images'] and set(f['evidence_images'])<=ii
  assert set(r['reference_roles']['style_layout'])<=ii and r['reference_roles']['customer_identity']==[]
  for h in r['style_core_hypotheses']:assert h['supporting_case_ids']==[sid] and h['scope']=='single_case_only'
  for v in r['creative_variables']:assert v['evidence_type']=='proposed'
  for sh in shots:
   assert not sh['generation_tested']
   if sh.get('is_composite'):assert sh['prompt_fragment_draft'] is None;composites+=1
  if not item['independent_style_evidence']:
   aliases+=1;assert item['canonical_case_id'] in allsets and item['canonical_case_id']!=sid
   assert r['deduplication']['canonical_case_id']==item['canonical_case_id']
   assert next(x for x in cases if x['set_id']==item['canonical_case_id'])['independent_style_evidence']
  if sid=='SET000073':
   variant_ids={i for v in r['look_variants'] for i in v['image_ids']};assert variant_ids==ii
   assert all(s['look_id'] in ['A','B'] for s in shots)
 for p in root.rglob('*.json'):read(p)
 count=0
 for p in root.rglob('SKILL.md'):
  txt=p.read_text();assert txt.startswith('---\n');front=txt.split('---',2)[1]
  assert re.search(r'^name: [a-z0-9-]+$',front,re.M) and re.search(r'^description: .+',front,re.M)
  for target in re.findall(r'\]\(([^)]+)\)',txt):
   if not target.startswith(('https:','http:','#')):assert (p.parent/target).exists(),(str(p),target)
  count+=1
 assert len(cases)==c['case_count'] and total==c['image_record_count'] and len(cases)-aliases==c['independent_case_count']
 roottext=(root/'SKILL.md').read_text();assert '妆造师' in roottext and '优先于本Skill' in roottext
 local_count=0
 if local_audit:
  aa=read(local_audit);assert {(x['set_id'],x['image_id']) for x in aa}=={(i['set_id'],a['image_id']) for i in cases for a in read(root/'cases'/i['set_id']/'assets.json')}
  for a in aa:
   digest=hashlib.sha256(Path(a['local_source']).read_bytes()).hexdigest();assert digest==a['sha256'] and a['source_hash_match'] is True
   expected=next(x for x in read(root/'cases'/a['set_id']/'assets.json') if x['image_id']==a['image_id']);assert expected['sha256']==digest;local_count+=1
 return {'status':'passed','cases':len(cases),'images':total,'independent_cases':len(cases)-aliases,'alias_cases':aliases,'skill_files':count,'composite_files':composites,'orientation_review_files':orientations,'local_SHA256_checked':local_count,'generation_tested':False,'image_service_bound':False,'limitations':['Visual review is contact-sheet based, not pixel-level verification','Image service and model output validation pending']}
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1]);p.add_argument('--local-audit',type=Path);a=p.parse_args();print(json.dumps(validate(a.root,a.local_audit),ensure_ascii=False,indent=2))
