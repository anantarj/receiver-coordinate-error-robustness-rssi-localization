"""Build explicit deterministic test registry; does not evaluate new cases."""
from pathlib import Path
import json,hashlib,zipfile,shutil,datetime,platform
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
def sha(p):
 h=hashlib.sha256()
 with open(p,'rb') as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return h.hexdigest()
def put(p,d):p.write_text(json.dumps(d,indent=2,sort_keys=True,allow_nan=False)+'\n')
parents=[Path('/mnt/data/PAPERB_STEP2_RAW_VALIDATION_AND_REMOVAL_20261007.zip'),Path('/mnt/data/PAPERB_PLAN_V2_AND_STEP1_RESULTS_20261007.zip'),Path('/mnt/data/paperb_s8_release/PAPERB_SENSORS_EVIDENCE_v1.1.0_S8_300926.zip'),Path('/mnt/data/lorawan_antwerp_2019_dataset(20261007-144453).csv')]
for f in ['PAPERB_CMC_MAIN.pdf','PAPERB_CMC_SUPPLEMENT.pdf','PAPERB_CMC_MAIN_LATEX.zip','PAPERB_CMC_SUPPLEMENT_LATEX.zip']:
 parents.append(Path('/mnt/data/paperb_cmc_c7_submission_20261004')/f)
parents += list(Path('/mnt/data/paperb_mechanism_step2_20261007/planning').glob('*'))+list(Path('/mnt/data/paperb_mechanism_step2_20261007/reports').glob('*.md'))
put(ROOT/'provenance/PARENTS_BEFORE.json',[{'path':str(p),'bytes':p.stat().st_size,'sha256':sha(p)} for p in parents])
assert sha(parents[2])=='01827be8265047edcdd159ab6fc96b954171cb25c03263292dbecda2f4f24268'
assert sha(parents[3])=='870abe60a4bd81f31ede6f269b6bc6329e05d2731343dff7015bae1a61218446'
with zipfile.ZipFile(parents[0]) as z:
 for name in ['planning/PAPERB_PROPOSED_PROTOCOL_V3_20261007.json','planning/PAPERB_RESEARCH_AND_REVISION_PLAN_V3_20261007.md','reports/CONTINUITY_HANDOFF.md','reports/STEP2_RESEARCH_FINDINGS.md','planning/PARENT_WRITING_AND_CLAIM_BLUEPRINT.md']:
  (ROOT/'planning'/('PARENT_'+Path(name).name)).write_bytes(z.read('paperb_mechanism_step2_20261007/'+name))
L=1000.
grid=np.array([(x,y) for y in [-.35,-.15,0.,.15,.35] for x in [-.4,-.2,0.,.2,.4]])*L
queries=np.array([[.05,.10],[-.2,.2],[.35,-.25],[-.3,-.1],[0.,0.]])*L
layouts={
 'spread':np.array([[-.8,-.6],[.9,-.4],[.75,.85],[-.65,.9],[.15,-.95],[.1,.6]])*L,
 'corridor':np.array([[-1.,-.08],[-.55,.12],[-.1,-.1],[.25,.08],[.6,-.12],[1.1,.10]])*L,
 'symmetric':np.array([[-.5,0.],[.5,0.],[0.,-.75],[0.,.75],[-.8,-.8],[.8,.8]])*L,
}
direc=np.array([[1.,0.],[0.,1.],[-1.,0.],[0.,-1.],[.6,.8],[-.8,.6]])
cases=[]
for layout in ['spread','corridor']:
 for target_ids in [[0],[0,1],[0,1,2,3,4],[0,1,2,3,4,5]]:
  patterns=['coherent','separate'] if len(target_ids)>1 else ['coherent']
  for pattern in patterns:
   for weak in [0.,40.]:
    qshift=np.zeros(6);qshift[[j for j in range(6) if j not in target_ids]]=-weak
    cases.append({'id':f'{layout}_k{len(target_ids)}_{pattern}_weak{int(weak)}','layout':layout,'targets':target_ids,'directions':(np.tile([1.,0.],(6,1)) if pattern=='coherent' else direc).tolist(),'query_bias_db':qshift.tolist(),'query_bias_interpretation':'fixed diagnostic attenuation of untargeted query RSS relative to calibration; not a campaign estimate','queries':queries.tolist(),'shared_A_true':False})
# Exact symmetric cancellation is an explicit separate geometry, not a positive-rate failure.
symd=direc.copy();symd[0]=[-1.,0.];symd[1]=[1.,0.]
cases.append({'id':'symmetric_two_opposite','layout':'symmetric','targets':[0,1],'directions':symd.tolist(),'query_bias_db':[0.]*6,'queries':[[0.,0.]],'shared_A_true':True})
# Empty-target neutrality as a registered control.
cases.append({'id':'spread_empty','layout':'spread','targets':[],'directions':direc.tolist(),'query_bias_db':[0.]*6,'queries':queries.tolist(),'shared_A_true':False})
# Ratios are exact decimal powers where possible; serialized floats are the input authority.
ratios=[0.]+[10.**(j/2) for j in range(-2,17)]
reg={'registry_id':'PAPERB-C1-20261007-v1','created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'purpose':'deterministic identity/asymptotic verification and finite counterexamples; not empirical generality or novelty certification','n_fit':4.7,'n_true':4.7,'d0_m':1.,'L_m':L,'A_true_dbm':[-30.,-32.,-29.,-31.,-33.,-28.],'calibration_positions_m':grid.tolist(),'layouts_m':{k:v.tolist() for k,v in layouts.items()},'cases':cases,'kappa':[.5,1.,2.,4.7],'D_over_L':ratios,'calibration_policies':['frozen','unrestricted','shared_update','bounded10','bounded30'],'shared_update_rule':'median of all receiver unrestricted-minus-reference updates; add same value to every reference intercept','selection':'all six receivers fixed, no simulated reception/eligibility filtering; removal minimum-three reported separately','fitting':'median over 25 calibration observations of RSS+10*n*log10((distance+d0)/d0)','generation':'fixed noiseless propagation plus registered query-only bias; no query noise and no RSSI clipping','analysis':{'relative_coordinate_tolerance':2e-12,'absolute_coordinate_tolerance_m':1e-7,'weight_tolerance':2e-13,'rate_fit_ratios':[1e5,10**5.5,1e6,10**6.5,1e7,10**7.5,1e8],'rate_statistic':'least-squares log10 direct target influence versus log10 D/L; exact cancellation and zero support excluded from decay-rate fits but always reported','expected_rates':'unrestricted positive support and noncancelled leading term: 1-kappa; frozen/shared/saturated bounded single-target: 1; coherent all-target prediction growth: 1','rate_tolerance':.06,'do_not_select_on_pass':True},'resource_ceiling':{'elapsed_seconds':180,'output_bytes':100_000_000},'knowledge_state':'Step1/2 finite-support extremes and all historical data already known; these particular generated controls not previously run; not external preregistration'}
put(ROOT/'protocol/C1_REGISTRY.json',reg)
put(ROOT/'protocol/C1_LOCK.json',{'locked_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'registry_sha256':sha(ROOT/'protocol/C1_REGISTRY.json'),'case_count':len(cases),'positive_ratio_count':len(ratios)-1,'D_including_zero':len(ratios),'kappa_count':4,'policy_count':5,'geometric_cases':len(cases)*len(ratios),'policy_weighting_conditions':len(cases)*len(ratios)*20,'query_evaluations':sum(len(c['queries']) for c in cases)*len(ratios)*20,'status':'LOCKED_BEFORE_C1_RUN','new_finite_monte_carlo_grid':'NOT_EXECUTED; separate registry/readiness required','real_grid':'NOT_EXECUTED','novelty_review':'PARTIAL; no new novelty assertion and no larger experiment gate cleared'})
print(json.dumps(json.loads((ROOT/'protocol/C1_LOCK.json').read_text()),indent=2))
