"""仅返回本地短摘要，不读取照片或调用生图。"""
from pathlib import Path
import argparse,json
p=argparse.ArgumentParser()
p.add_argument('--category');p.add_argument('--id');p.add_argument('--limit',type=int,default=5)
a=p.parse_args()
if a.limit<1:p.error('--limit must be positive')
c=json.loads((Path(__file__).resolve().parents[1]/'catalog.json').read_text())
rows=c['cases']
if a.id:rows=[x for x in rows if x['case_id']==a.id]
else:rows=[x for x in rows if x['default_retrieval_eligible']]
if a.category:rows=[x for x in rows if x['category_id']==a.category]
print(json.dumps({'scope':'review_only','production_ready':False,'total_matches':len(rows),'cases':rows[:a.limit]},ensure_ascii=False,indent=2))
