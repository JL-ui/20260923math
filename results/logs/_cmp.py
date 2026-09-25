import csv,collections,sys
def load(p):
    d=collections.defaultdict(dict)
    for r in csv.DictReader(open(p,encoding='utf-8')):
        if r.get('feasible') not in('True','true','1') or not r.get('makespan') or not r.get('baseline_makespan'):continue
        v=float(r['baseline_makespan'])/float(r['makespan'])
        k=(r['problem'],r['num_cores'])
        d[k][r['case']]=max(d[k].get(r['case'],0),v)
    return d
for f in sys.argv[1:]:
    d=load(f);print(f,' '.join('P%sN%s=%.4f'%(k[0],k[1],sum(v.values())/len(v)) for k,v in sorted(d.items()) if k[0]!='1'))
