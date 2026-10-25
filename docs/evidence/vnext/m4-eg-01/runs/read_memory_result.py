import json
from pathlib import Path
p=Path('docs/evidence/vnext/m4-eg-01/runs/memory-paired-20261025T100556Z')
j=json.loads((p/'RESULTS.json').read_text(encoding='utf-8'))
print('RUN',j['release_id'],'provider',j['provider_model'],'requests',j['provider_requests'],'top_total_tokens',j['total_tokens'],'status',j['status'])
for name in ['E1-MEMORY-ON.json','E1-MEMORY-OFF.json','E2-CURRENT-FACT-CONFLICT.json','E3-IRRELEVANT.json','E4-AFTER-REVOCATION.json']:
 x=json.loads((p/name).read_text(encoding='utf-8'))
 print(name,'task',x['task_id'],'outcome',(x.get('outcome') or {}).get('outcome'),'direction',(x.get('outcome') or {}).get('handling_direction'),'calls',len(x.get('model_traces',[])),'tokens',x.get('total_tokens'),'latency',x.get('elapsed_seconds'),'tools',[o.get('tool_name') for o in x.get('mcp_observations',[])],'failure',x.get('failure'))
 if x.get('model_traces'):
  q=x['model_traces'][0]
  print(' trace_keys',sorted(q.keys()),'usage',q.get('usage'),'token_fields',{k:q.get(k) for k in ['input_tokens','output_tokens','total_tokens','provider_response_id','model_id'] if k in q})
  text=x.get('run_result',{}).get('graph_state',{}).get('diagnosis_draft',{}).get('model_summary_untrusted','')
  print(' answer_excerpt',text[:360].replace('\n',' '))
