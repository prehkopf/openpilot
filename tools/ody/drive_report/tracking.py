# ruff: noqa
# Drive report part 2: steer faults, brake disengages in context, gas overrides, accel tracking by request band, lateral error by speed.  usage: tracking.py <extract.json>
import json, sys, numpy as np, collections
D=json.load(open(sys.argv[1])); MPH=2.23694
cs=D['cs']; T=np.array([r[0] for r in cs]); v=np.array([r[1] for r in cs]); a=np.array([r[2] for r in cs])
gasP=np.array([r[3] for r in cs]); brkP=np.array([r[4] for r in cs]); strP=np.array([r[5] for r in cs])
stf=np.array([r[12] for r in cs]); vc=np.array([r[8] for r in cs]); cren=np.array([r[9] for r in cs])
cc=D['cc']; Tc=np.array([r[0] for r in cc]); en=np.array([r[1] for r in cc]); lat=np.array([r[2] for r in cc]); lon=np.array([r[3] for r in cc]); acmd=np.array([r[4] for r in cc]); tcmd=np.array([r[5] for r in cc]); pitch=np.array([r[7] for r in cc])
co=D['co']; tcan=np.array([r[3] for r in co]); n=min(len(cs),len(cc),len(co))
T,v,a,gasP,brkP,strP,stf,vc,cren=[x[:n] for x in (T,v,a,gasP,brkP,strP,stf,vc,cren)]
en,lat,lon,acmd,tcmd,pitch,tcan=[x[:n] for x in (en,lat,lon,acmd,tcmd,pitch,tcan)]
def runs(mask):
    m=np.concatenate([[0],mask.astype(int),[0]]); d=np.diff(m); s=np.flatnonzero(d==1); e=np.flatnonzero(d==-1); return list(zip(s,e))
print("== steerFaultTemporary runs ==")
for s,e in runs(stf):
    print(f"  {T[s]/60:5.2f}m for {T[e-1]-T[s]:4.1f}s speed {v[s]*MPH:4.1f}->{v[e-1]*MPH:4.1f} mph engaged={en[s:e].any()} latActive={lat[s:e].any()}")
print("== cruiseState.enabled while OP disengaged runs (cruiseMismatch src) ==")
for s,e in runs(cren & ~en):
    if T[e-1]-T[s]>1: print(f"  {T[s]/60:5.2f}m for {T[e-1]-T[s]:4.1f}s")
print("== context before brake disengages (last 6s) ==")
rad=D['rad']; Tr=np.array([r[0] for r in rad])
lp=D['lp']; Tl=np.array([r[0] for r in lp])
for s,e in runs(en):
    j=e  # first disengaged idx
    if j<n and brkP[max(0,j-30):j+3].any():
        print(f" disengage at {T[j]/60:.2f}m, {v[j]*MPH:.1f} mph")
        for dt in (-6,-4,-3,-2,-1,-0.5,0):
            i=np.searchsorted(T,T[j]+dt); k=min(np.searchsorted(Tr,T[i]),len(rad)-1); l=min(np.searchsorted(Tl,T[i]),len(lp)-1)
            r=rad[k]; p=lp[l]
            lead=f"lead {r[2]:5.1f}m rel {r[3]*MPH:+5.1f}mph" if r[1] else "no lead"
            print(f"   {dt:+5.1f}s v {v[i]*MPH:5.1f} set {vc[i]*0.621371:5.1f}  aEgo {a[i]:+.2f} cmd {acmd[i]:+.2f}  {lead}  src {p[1]} stop={p[3]}")
print("== gas override runs > 1s (while engaged) ==")
for s,e in runs(gasP & en):
    if T[e-1]-T[s]>1:
        i=max(0,s-50)
        print(f"  {T[s]/60:5.2f}m for {T[e-1]-T[s]:4.1f}s v {v[i]*MPH:4.1f} set {vc[i]*0.621371:4.1f} cmd(before) {acmd[i]:+.2f} aEgo {a[i]:+.2f} pitch {np.degrees(pitch[i]):+.1f}deg")
# long tracking when longActive and not gas
m=lon & ~gasP & (v>0.5)
lag=50
err=a[lag:][m[:-lag]] - acmd[:-lag][m[:-lag]]
print(f"\n== long: engaged-long {m.sum()/100:.0f}s; accel tracking err (aEgo@+0.5s - cmd): mean {err.mean():+.2f} rms {np.sqrt((err**2).mean()):.2f}")
for lo,hi in ((-9,-1),(-1,-0.3),(-0.3,0.3),(0.3,1),(1,9)):
    mm=(acmd[:-lag]>=lo)&(acmd[:-lag]<hi)&m[:-lag]
    if mm.sum()>50: e2=a[lag:][mm]-acmd[:-lag][mm]; print(f"   cmd {lo:+}..{hi:+}: n={mm.sum()/100:5.0f}s mean err {e2.mean():+.2f}")
print(f"   min cmd {acmd[m].min():+.2f}, min aEgo engaged {a[m].min():+.2f}, max aEgo {a[m].max():+.2f}")
jerk=np.diff(a)/np.diff(T); jj=jerk[m[1:]]
print(f"   |jerk|>3 m/s3 frac {(np.abs(jj)>3).mean()*100:.1f}%  >5: {(np.abs(jj)>5).mean()*100:.2f}%")
# stops
print("== standstill episodes while engaged ==")
for s,e in runs((v<0.3)&en):
    print(f"  {T[s]/60:5.2f}m held {T[e-1]-T[s]:.1f}s")
# pitch / grade
print(f"pitch range engaged {np.degrees(pitch[en]).min():+.1f}..{np.degrees(pitch[en]).max():+.1f} deg")
# lateral
print("\n== lateral (latActive, no steer override) ==")
ctl=D['ctl']; sat=np.array([r[1] for r in ctl])[:n]; act=np.array([r[2] for r in ctl])[:n]; des=np.array([r[3] for r in ctl])[:n]
ml=lat&~strP&(v>1)
for lo,hi in ((0,15),(15,25),(25,35),(35,45),(45,60)):
    mm=ml&(v*MPH>=lo)&(v*MPH<hi)
    if mm.sum()<100: continue
    e=act[mm]-des[mm]
    print(f"  {lo:2d}-{hi:2d} mph: {mm.sum()/100:5.0f}s  |desLatAcc| p95 {np.percentile(abs(des[mm]),95):.2f}  err rms {np.sqrt((e**2).mean()):.3f}  |cmd| p99 {np.percentile(abs(tcmd[mm]),99):.2f} max {abs(tcmd[mm]).max():.2f}  |can| max {abs(tcan[mm]).max():.0f}  at>=2550 {(abs(tcan[mm])>=2550).mean()*100:.1f}%  >2560 {(abs(tcan[mm])>2560).mean()*100:.2f}%  saturated {sat[mm].mean()*100:.2f}%")
print("== steer override runs while engaged > 0.5s ==")
for s,e in runs(strP&en):
    if T[e-1]-T[s]>0.5:
        i=max(0,s-20); print(f"  {T[s]/60:5.2f}m for {T[e-1]-T[s]:4.1f}s v {v[i]*MPH:4.1f}  desLat {des[i]:+.2f} actLat {act[i]:+.2f} cmd {tcmd[i]:+.2f} can {tcan[i]:+.0f}")
print("== saturated runs ==")
for s,e in runs(sat&lat):
    if T[e-1]-T[s]>0.3: print(f"  {T[s]/60:5.2f}m for {T[e-1]-T[s]:4.1f}s v {v[s]*MPH:4.1f} desLat {des[s]:+.2f} actLat {act[s]:+.2f} can {tcan[s]:+.0f}")
tq=D['tq']; print("\ntorque learner last:", tq[-1] if tq else None)
ps=D['ps']; print("panda: rxInvalid max", max(p[2] for p in ps), "txBlocked max", max(p[3] for p in ps), "faults", collections.Counter(p[4] for p in ps), "safety", collections.Counter((p[5],p[6]) for p in ps))
