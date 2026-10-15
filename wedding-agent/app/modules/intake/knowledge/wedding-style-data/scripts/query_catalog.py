#!/usr/bin/env python3
"""Read-only bounded catalog query; no image/network requests."""
from pathlib import Path
import argparse,json
p=argparse.ArgumentParser();p.add_argument('--primary');p.add_argument('--secondary');p.add_argument('--set-id');p.add_argument('--include-aliases',action='store_true');p.add_argument('--limit',type=int,default=8);a=p.parse_args()
r=Path(__file__).resolve().parents[1];c=json.loads((r/'catalog.json').read_text());rows=c['cases']
if a.primary:rows=[x for x in rows if x['primary']==a.primary]
if a.secondary:rows=[x for x in rows if x['secondary']==a.secondary]
if a.set_id:rows=[x for x in rows if x['set_id']==a.set_id]
if not a.include_aliases and not a.set_id:rows=[x for x in rows if x['independent_style_evidence']]
print(json.dumps({'total':len(rows),'results':rows[:max(1,min(50,a.limit))]},ensure_ascii=False,indent=2))
