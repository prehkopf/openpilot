# ruff: noqa
# Pull the fields the drive reports use out of a whole route into one JSON file.
# usage: extract.py <route prefix> <out.json>
#   e.g. extract.py ~/rlogs/00000008--83edc4fea4 /tmp/r8.json   (reads ~/rlogs/00000008--83edc4fea4--<n>/rlog.zst)
import glob
import json
import sys
from openpilot.tools.lib.logreader import LogReader


def segments(prefix):
  return sorted(glob.glob(f"{prefix}--*/rlog.zst"), key=lambda f: int(f.split("--")[-1].split("/")[0]))


def read(prefix):
  for fn in segments(prefix):
    yield from LogReader(fn)


route, out_path = sys.argv[1], sys.argv[2]
t0=None
cs=[];cc=[];co=[];ctl=[];sd=[];lp=[];ev=[];tq=[];err=[];ps=[];logs=[];rad=[]
for m in read(route):
    t=m.logMonoTime*1e-9
    if t0 is None: t0=t
    t-=t0
    w=m.which()
    if w=='carState':
        c=m.carState
        cs.append((t,c.vEgo,c.aEgo,c.gasPressed,c.brakePressed,c.steeringPressed,c.steeringTorque,c.steeringAngleDeg,c.vCruise,c.cruiseState.enabled,c.cruiseState.available,c.standstill,c.steerFaultTemporary,c.steerFaultPermanent,c.accFaulted,str(c.gearShifter),c.leftBlinker or c.rightBlinker))
    elif w=='carControl':
        c=m.carControl
        cc.append((t,c.enabled,c.latActive,c.longActive,c.actuators.accel,c.actuators.torque,str(c.actuators.longControlState),c.orientationNED[1] if len(c.orientationNED)>1 else 0))
    elif w=='carOutput':
        a=m.carOutput.actuatorsOutput
        co.append((t,a.accel,a.torque,a.torqueOutputCan,a.gas,a.brake))
    elif w=='controlsState':
        c=m.controlsState; ts=c.lateralControlState.torqueState
        ctl.append((t,ts.saturated,ts.actualLateralAccel,ts.desiredLateralAccel,ts.output,c.curvature,c.desiredCurvature,str(c.longControlState)))
    elif w=='selfdriveState':
        s=m.selfdriveState
        sd.append((t,str(s.state),s.enabled,s.experimentalMode,str(s.personality),s.alertText1,s.alertText2))
    elif w=='longitudinalPlan':
        p=m.longitudinalPlan
        lp.append((t,str(p.longitudinalPlanSource),p.aTarget if hasattr(p,'aTarget') else 0,p.shouldStop,p.allowThrottle,p.allowBrake,p.hasLead))
    elif w=='radarState':
        l=m.radarState.leadOne
        rad.append((t,l.present,l.dRel,l.vRel,l.vLead,l.radar))
    elif w=='onroadEvents':
        for e in m.onroadEvents:
            ev.append((t,str(e.name),e.enable,e.noEntry,e.warning,e.userDisable,e.softDisable,e.immediateDisable,e.preEnable,e.permanent,e.overrideLateral,e.overrideLongitudinal))
    elif w=='lateralTorqueParameters':
        p=m.lateralTorqueParameters
        tq.append((t,p.useParams,p.latAccelFactorFiltered,p.frictionCoefficientFiltered,p.latAccelOffsetFiltered,p.calPerc,p.totalBucketPoints))
    elif w=='errorLogMessage':
        err.append((t,m.errorLogMessage[:600]))
    elif w=='pandaStates':
        for p in m.pandaStates:
            ps.append((t,p.controlsAllowed,p.safetyRxInvalid,p.safetyTxBlocked,str(p.faultStatus),str(p.safetyModel),p.safetyParam, p.ignitionLine))
    elif w=='logMessage':
        s=m.logMessage
        if any(k in s for k in ('"levelnum": 40','"levelnum": 50','Traceback','"levelnum": 30')): logs.append((t,s[:500]))
json.dump(dict(cs=cs,cc=cc,co=co,ctl=ctl,sd=sd,lp=lp,ev=ev,tq=tq,err=err,ps=ps,logs=logs,rad=rad),open(out_path,'w'))
print('done',len(cs),len(ev),len(err),len(logs))
