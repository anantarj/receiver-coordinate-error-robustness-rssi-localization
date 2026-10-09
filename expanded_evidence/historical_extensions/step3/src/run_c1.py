"""Run every locked deterministic C1 condition, without outcome-based selection."""
from pathlib import Path
import argparse,csv,json,hashlib,time,platform,sys
import numpy as np
from boundary_model import distances,fit_intercepts,normalize_log_weights,policy_intercepts,shifted_centroid

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def dump(path,obj):path.write_text(json.dumps(obj,indent=2,sort_keys=True,allow_nan=False)+'\n')
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--registry',type=Path,required=True);ap.add_argument('--lock',type=Path,required=True);ap.add_argument('--out',type=Path,required=True);args=ap.parse_args()
 reg=json.loads(args.registry.read_text()); lock=json.loads(args.lock.read_text());assert sha(args.registry)==lock['registry_sha256'],'Registry changed after lock.'
 if args.out.exists():raise FileExistsError('Fresh result directory required.')
 args.out.mkdir(parents=True)
 start=time.monotonic(); L=reg['L_m'];n=reg['n_fit'];d0=reg['d0_m'];cal=np.array(reg['calibration_positions_m']);records=[];stats=[]
 checks={'row_count':0,'zero_displacement':0,'shared_cancellation':0,'finite_identity':0,'mass_identity':0,'reverse_triangle':0,'empty_target':0,'normalization':0,'no_support_rows':0};maxima={k:0. for k in ['zero_displacement_m','shared_prediction_difference_m','finite_identity_m','mass_identity','reverse_triangle_excess_m','normalization_error']}
 for case in reg['cases']:
  a=np.array(reg['layouts_m'][case['layout']]);targets=np.array(case['targets'],dtype=int);mask=np.isin(np.arange(6),targets);U=~mask;directions=np.array(case['directions']);q=np.array(case['queries']);Atrue=np.full(6,-30.) if case['shared_A_true'] else np.array(reg['A_true_dbm']);
  rcal=Atrue-10*reg['n_true']*np.log10((distances(cal,a)+d0)/d0)
  rq=Atrue-10*reg['n_true']*np.log10((distances(q,a)+d0)/d0)+np.array(case['query_bias_db'])
  A0=fit_intercepts(rcal,cal,a,n,d0)
  for kappa in reg['kappa']:
   alpha=np.log(10)*kappa/(10*n);p0=normalize_log_weights(rq,A0,n,kappa);x0=shifted_centroid(p0,a);e0=np.linalg.norm(x0-q,axis=1)
   if U.any():
    u=shifted_centroid(p0[:,U]/p0[:,U].sum(axis=1,keepdims=True),a[U]);erem=np.linalg.norm(u-q,axis=1);Pu=p0[:,U].sum(axis=1)
   else:u=erem=Pu=None
   for ratio in reg['D_over_L']:
    D=L*ratio;newa=a.copy();newa[mask]+=D*directions[mask];fit=fit_intercepts(rcal,cal,newa,n,d0)
    xfrozen=shifted_centroid(p0,newa)
    for pol in reg['calibration_policies']:
     A=policy_intercepts(pol,A0,fit);p=normalize_log_weights(rq,A,n,kappa);pred=shifted_centroid(p,newa);err=np.linalg.norm(pred-q,axis=1);b=p[:,mask].sum(axis=1)
     normerror=np.abs(p.sum(axis=1)-1);assert np.all(normerror<2e-13);maxima['normalization_error']=max(maxima['normalization_error'],float(normerror.max()));checks['normalization']+=len(q)
     # Roundoff tolerance scales with the computational coordinate magnitude, not physical accuracy.
     coordscale=max(float(np.max(np.abs(newa))),1.);tol=reg['analysis']['absolute_coordinate_tolerance_m']+reg['analysis']['relative_coordinate_tolerance']*coordscale
     if ratio==0:
      diff=np.linalg.norm(pred-x0,axis=1);assert np.all(diff<=tol);maxima['zero_displacement_m']=max(maxima['zero_displacement_m'],float(diff.max()));checks['zero_displacement']+=len(q)
     if pol=='shared_update':
      diff=np.linalg.norm(pred-xfrozen,axis=1);assert np.all(diff<=tol);maxima['shared_prediction_difference_m']=max(maxima['shared_prediction_difference_m'],float(diff.max()));checks['shared_cancellation']+=len(q)
     if not mask.any():assert np.all(np.linalg.norm(pred-x0,axis=1)<=tol);checks['empty_target']+=len(q)
     if U.any():
      contribution=np.sum(p[:,mask,None]*(newa[None,mask,:]-u[:,None,:]),axis=1)
      influence=np.linalg.norm(contribution,axis=1)
      residual=np.linalg.norm((pred-u)-contribution,axis=1);assert np.all(residual<=tol)
      maxima['finite_identity_m']=max(maxima['finite_identity_m'],float(residual.max()));checks['finite_identity']+=len(q)
      excess=np.abs(err-erem)-influence;assert np.all(excess<=tol);maxima['reverse_triangle_excess_m']=max(maxima['reverse_triangle_excess_m'],float(np.maximum(excess,0).max()));checks['reverse_triangle']+=len(q)
      # Remove the common non-target shift before evaluating the historical mass-odds expression.
      common=float(np.mean((A-A0)[U]));zz=np.exp(-alpha*((A-A0)-common));st=(p0[:,mask]*zz[mask]).sum(axis=1);bodds=st/(Pu+st)
      massres=np.abs(b-bodds);assert np.all(massres<2e-13);maxima['mass_identity']=max(maxima['mass_identity'],float(massres.max()));checks['mass_identity']+=len(q)
      leverage=np.divide(influence,b,out=np.zeros_like(b),where=b>0)
     else:
      influence=leverage=None; checks['no_support_rows']+=len(q)
     for j in range(len(q)):
      rec={'case':case['id'],'query':j,'targets':len(targets),'remaining':int(U.sum()),'removal_operational_eligible':bool(U.sum()>=3),'kappa':kappa,'policy':pol,'D_over_L':ratio,'D_m':D,'reference_error_m':float(e0[j]),'error_m':float(err[j]),'prediction_x_m':float(pred[j,0]),'prediction_y_m':float(pred[j,1]),'target_mass':float(b[j]),'reference_remaining_mass':float(Pu[j]) if Pu is not None else 0.,'influence_to_removal_m':float(influence[j]) if influence is not None else None,'leverage_m':float(leverage[j]) if leverage is not None else None,'removal_error_m':float(erem[j]) if erem is not None else None,'removal_status':'defined' if U.any() else 'undefined_no_untargeted_support','max_target_intercept_change_db':float(np.max((A-A0)[mask])) if mask.any() else 0.,'mean_intercept_change_db':float(np.mean(A-A0))}
      records.append(rec)
     if time.monotonic()-start>reg['resource_ceiling']['elapsed_seconds']:raise TimeoutError('Locked resource ceiling exceeded; no outcomes discarded.')
 checks['row_count']=len(records); assert len(records)==lock['query_evaluations']
 with open(args.out/'c1_all_rows.csv','w',newline='') as f:
  wr=csv.DictWriter(f,fieldnames=list(records[0]));wr.writeheader();wr.writerows(records)
 # Rate checks use direct influence, not subtraction of near-identical centroid coordinates.
 rates=[]
 from collections import defaultdict
 groups=defaultdict(list)
 for rec in records:
  if rec['D_over_L']>=1e5:groups[(rec['case'],rec['query'],rec['kappa'],rec['policy'])].append(rec)
 for (c,j,k,pol),rs in groups.items():
  if c=='spread_empty' or c=='symmetric_two_opposite':continue
  expected=None;measure=None
  if rs[0]['remaining']>0 and pol=='unrestricted':expected=1-k;measure='influence_to_removal_m'
  elif rs[0]['targets']==1:expected=1.;measure='influence_to_removal_m'
  elif rs[0]['remaining']==0 and '_coherent_' in c:expected=1.;measure='prediction_norm'
  if measure is None:continue
  xs=np.array([r['D_over_L'] for r in rs]);ys=np.array([np.hypot(r['prediction_x_m'],r['prediction_y_m']) if measure=='prediction_norm' else r[measure] for r in rs]);
  if not np.all(ys>0):raise ValueError('Unexpected zero in prespecified noncancelling rate comparison.')
  slope=float(np.polyfit(np.log10(xs),np.log10(ys),1)[0]);ok=abs(slope-expected)<=reg['analysis']['rate_tolerance']
  rates.append({'case':c,'query':j,'kappa':k,'policy':pol,'measure':measure,'slope':slope,'expected':expected,'within_locked_tolerance':ok})
 with open(args.out/'c1_rate_checks.csv','w',newline='') as f:
  wr=csv.DictWriter(f,fieldnames=list(rates[0]));wr.writeheader();wr.writerows(rates)
 dump(args.out/'C1_CHECKS.json',{'status':'PASS' if all(r['within_locked_tolerance'] for r in rates) else 'RATE_CHECK_FAILURE_RETAINED','counts':checks,'maxima':maxima,'rate_checks':len(rates),'rate_pass_count':sum(r['within_locked_tolerance'] for r in rates),'max_rate_error':max(abs(r['slope']-r['expected']) for r in rates),'reg_sha256':sha(args.registry),'scope':'Deterministic known-geometry controls, not MC/field validation, no new article novelty assertion.'})
 dump(args.out/'ENVIRONMENT.json',{'python':platform.python_version(),'numpy':np.__version__,'platform':platform.platform()})
 receipt={'elapsed_seconds':time.monotonic()-start,'result_bytes':sum(p.stat().st_size for p in args.out.iterdir()),'registry_sha256':sha(args.registry)}
 assert receipt['result_bytes']<reg['resource_ceiling']['output_bytes'];dump(args.out/'RUN_RECEIPT.json',receipt)
 print(json.dumps(json.loads((args.out/'C1_CHECKS.json').read_text()),indent=2));print(receipt)
if __name__=='__main__':main()
