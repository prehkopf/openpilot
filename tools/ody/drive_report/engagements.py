# ruff: noqa
# Drive report part 1: engagements, disengage causes, events, errors.  usage: engagements.py <extract.json>
import json, sys, numpy as np, collections
D=json.load(open(sys.argv[1]))
MPH=2.23694
cs=D['cs']; T=np.array([r[0] for r in cs]); v=np.array([r[1] for r in cs]); a=np.array([r[2] for r in cs])
gasP=np.array([r[3] for r in cs]); brkP=np.array([r[4] for r in cs]); strP=np.array([r[5] for r in cs]); strT=np.array([r[6] for r in cs])
vc=np.array([r[8] for r in cs]); cru_av=np.array([r[10] for r in cs])
print(f"duration {T[-1]/60:.1f} min, max speed {v.max()*MPH:.0f} mph, gear set {set(r[15] for r in cs)}")
print("faults: steerTemp", sum(r[12] for r in cs), "steerPerm", sum(r[13] for r in cs), "accFaulted", sum(r[14] for r in cs), "cruise avail frac", cru_av.mean().round(3))
sd=D['sd']; st=np.array([r[0] for r in sd]); en=np.array([r[2] for r in sd])
print("experimental", collections.Counter(r[3] for r in sd), "personality", collections.Counter(r[4] for r in sd))
print("states", collections.Counter(r[1] for r in sd))
# engagement segments
def at(tq, arrT, arr):
    i=min(np.searchsorted(arrT,tq),len(arr)-1); return arr[i]
ev=D['ev']
chg=np.flatnonzero(np.diff(en.astype(int)))+1
print("\n== engagements ==")
eng_time=0; prev=None
for i in chg:
    t=st[i]
    if en[i]:
        prev=t
        vs=at(t,T,v)*MPH; vcs=[at(t+d,T,vc)*MPH*(1/MPH)*0.621371 for d in (0.5,2.0)]
        # vCruise in km/h
        print(f"ENGAGE  t={t/60:5.2f}m speed {vs:5.1f} mph  setspeed@+0.5s {at(t+0.5,T,vc)*0.621371:5.1f} mph @+2s {at(t+2,T,vc)*0.621371:5.1f} mph")
    else:
        if prev is not None: eng_time+=t-prev
        near=[e for e in ev if abs(e[0]-t)<0.6 and (e[5] or e[6] or e[7] or e[3])]
        names=sorted(set(e[1] for e in near))
        j=np.searchsorted(T,t)
        win=slice(max(0,j-50),j+5)
        print(f"DISENG  t={t/60:5.2f}m speed {at(t,T,v)*MPH:5.1f} mph  brake={brkP[win].any()} gas={gasP[win].any()} events={names}")
if en[-1] and prev is not None: eng_time+=st[-1]-prev
print(f"engaged {eng_time/60:.1f} of {T[-1]/60:.1f} min ({eng_time/T[-1]*100:.0f}%)")
print("\n== event counts (first time, approx duration s) ==")
evc=collections.defaultdict(list)
for e in ev: evc[e[1]].append(e[0])
for k,ts in sorted(evc.items(), key=lambda x:x[1][0]):
    flags=[n for n,f in zip(['enable','noEntry','warning','userDisable','softDisable','immediateDisable','preEnable','permanent','ovLat','ovLong'],ev[[e[1] for e in ev].index(k)][2:]) if f]
    print(f"  {k:32s} first {ts[0]/60:5.2f}m  ~{len(ts)*0.01*(1 if len(ts)>1 else 0):6.1f}s  n={len(ts)} {flags}")
print("\n== errors ==")
for t,s in D['err'][:8]: print(f"  {t/60:.2f}m", s[:300].replace('\n',' | '))
lv=collections.Counter()
for t,s in D['logs']:
    try: j=json.loads(s); key=(j.get('levelnum'), str(j.get('msg'))[:120], j.get('ctx',{}).get('daemon') if isinstance(j.get('ctx'),dict) else '')
    except Exception: key=('?',s[:120],'')
    lv[key]+=1
print("== warn/error log lines ==")
for k,n in lv.most_common(25): print(f"  {n:4d} {k}")
