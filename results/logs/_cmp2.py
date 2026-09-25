import csv,collections,sys
def load(p):
    d=collections.defaultdict(dict)
    for r in csv.DictReader(open(p,encoding='utf-8')):
        if r.get('feasible') not in('True','true','1') or not r.get('makespan') or not r.get('baseline_makespan'):continue
        v=float(r['baseline_makespan'])/float(r['makespan'])
        k=(int(r['problem']),int(r['num_cores']))
        d[k][r['case']]=max(d[k].get(r['case'],0),v)
    return {k:sum(v.values())/len(v) for k,v in d.items()}
a=load('results/logs/final_T07.csv');b=load('results/final.csv')
ok=True
for k in sorted(b):
    if k[1]<2:continue
    flag='OK' if b[k]>=a.get(k,0)-1e-9 else 'REGRESS'
    ok&=flag=='OK'
    print('P%dN%d  T07=%.4f  now=%.4f  %+.2f%%  %s'%(k[0],k[1],a.get(k,0),b[k],(b[k]/a[k]-1)*100 if k in a else 0,flag))
print('ALL_OK' if ok else 'HAS_REGRESSION')
