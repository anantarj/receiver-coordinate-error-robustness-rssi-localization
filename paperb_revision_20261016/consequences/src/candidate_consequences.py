"""Found-pool sensitivity; references score candidates but never select production."""
from collections import Counter
import argparse,itertools,json
import numpy as np
from common import *

NUMERICAL=HERE.parent/'numerical'
BANDS=[.01,.001,.0001]

def load_pools(require_complete=True, enhanced=None):
    reg=json.loads((NUMERICAL/'protocol/RECOVERY_PROTOCOL.json').read_text());n=reg['global_unique_inputs']
    points=np.full((n,39,2),np.nan);loss=np.full((n,39),np.inf);valid=np.zeros((n,39),bool);seen=np.zeros(n,bool)
    hashes={}
    for path in sorted((NUMERICAL/'candidates').glob('*.npz')):
        z=readz(path);ids=z['input_id'].astype(int)
        if seen[ids].any():raise ValueError('Duplicate candidate input IDs in '+path.name)
        points[ids]=z['candidate_position_m'];loss[ids]=z['candidate_objective_db2'];valid[ids]=z['candidate_valid'];seen[ids]=True;hashes[path.name]=sha(path)
    if require_complete and not seen.all():raise ValueError(f'Candidate recovery incomplete {seen.sum()}/{n}; no singleton imputation')
    valid &= np.isfinite(points).all(axis=-1)&np.isfinite(loss)
    if not valid[seen].any(axis=1).all():raise ValueError('Empty found pool')
    if enhanced is not None:
        overlay={}
        for path in sorted(enhanced.glob('input_*_stage*.npz')):
            z=readz(path);uid=int(z['input_id']);xy=z['candidate_position_m'];obj=z['candidate_objective_db2']
            good=np.isfinite(xy).all(axis=1)&np.isfinite(obj)
            if not good.all():raise ValueError('Nonfinite enhanced candidate '+path.name)
            overlay.setdefault(uid,[]).append((xy,obj));hashes['enhanced/'+path.name]=sha(path)
        if not overlay:raise ValueError('No enhanced candidate archives supplied')
        extra=max(sum(len(xy) for xy,obj in chunks) for chunks in overlay.values())
        # Enhanced diagnostics cover a small subset. Dense padding preserves the
        # exactly same downstream calculations and never replaces primary pools.
        nslot=points.shape[1]
        points=np.pad(points,((0,0),(0,extra),(0,0)),constant_values=np.nan)
        loss=np.pad(loss,((0,0),(0,extra)),constant_values=np.inf)
        valid=np.pad(valid,((0,0),(0,extra)),constant_values=False)
        for uid,chunks in overlay.items():
            at=nslot
            for xy,obj in chunks:
                stop=at+len(xy);points[uid,at:stop]=xy;loss[uid,at:stop]=obj;valid[uid,at:stop]=True;at=stop
    return points,loss,valid,seen,hashes

def ordered_rule_slots(points,mask,rule):
    if rule=='earliest':return mask.argmax(axis=1)
    # np.lexsort's final key is primary. Invalid candidates sort after every valid.
    order=np.lexsort((np.broadcast_to(np.arange(points.shape[1]),mask.shape),points[:,:,1],points[:,:,0],~mask),axis=1)
    return order[:,0]

def quantile_interval_sign(w,nlo,nhi):
    slo=sign(w,nhi);shi=sign(w,nlo)
    if slo=='positive':return 'positive'
    if shi=='negative':return 'negative'
    if slo==shi=='numerical_tie':return 'numerical_tie'
    return 'unresolved'

def assignment_conflicts(ids,slots,points):
    seen={};conflicts=set()
    for uid,slot in zip(ids.ravel(),slots.ravel()):
        xy=tuple(points[uid,slot])
        if uid in seen and seen[uid]!=xy:conflicts.add(int(uid))
        seen[uid]=xy
    return len(conflicts)

def candidate_pair_distances(uids_a,uids_b,points,mask):
    lo=np.empty(len(uids_a));hi=np.empty(len(uids_a));unconstrained_hi=np.empty(len(uids_a))
    for j,(a,b) in enumerate(zip(uids_a,uids_b)):
        pa=points[a,mask[a]];pb=points[b,mask[b]]
        distances=norm(pa[:,None]-pb[None]);unconstrained_hi[j]=distances.max()
        # Same input under a consistent rule gives precisely the same prediction.
        if a==b:lo[j]=hi[j]=0.
        else:lo[j]=distances.min();hi[j]=distances.max()
    return lo,hi,unconstrained_hi

def run():
    ap=argparse.ArgumentParser();ap.add_argument('--allow-partial',action='store_true');ap.add_argument('--enhanced-directory',type=Path);args=ap.parse_args()
    source=verify_source();points,loss,valid,seen,poolhash=load_pools(not args.allow_partial,args.enhanced_directory)
    minimum=np.min(np.where(valid,loss,np.inf),axis=1)
    output=HERE/('results/candidates_enhanced' if args.enhanced_directory else 'results/candidates');output.mkdir(parents=True,exist_ok=True)
    assignments=output/'witness_assignments';assignments.mkdir(exist_ok=True)
    rankings=[];calibration=[];transfers=[];movements=[];witnesses=[];coverage=[]
    for band in BANDS:
        mask=valid&(loss<=minimum[:,None]+band)
        rule_slots={r:ordered_rule_slots(points,mask,r) for r in ['earliest','lexicographic']}
        np.savez_compressed(assignments/f'truth_independent_rules_band_{band:g}.npz',input_id=np.arange(len(seen)),pool_available=seen,**{k+'_candidate_slot':v for k,v in rule_slots.items()})
        for path in block_files():
            b,r,meta,e,finite=load_block(path);mapping=readz(NUMERICAL/'mappings'/path.name)
            if not np.array_equal(mapping['source_rows'],b['source_rows']):raise ValueError('Candidate row mapping mismatch')
            for key in ['field_D_m','field_draw','field_target_count']:
                if not np.array_equal(mapping[key],b[key]):raise ValueError('Candidate field mapping mismatch')
            ids=mapping['input_id'];zero=int(np.flatnonzero(b['field_D_m']==0)[0])
            # Per-query extrema are evaluated from all valid retained candidates.
            lower=np.full(ids.shape,np.nan);upper=lower.copy();minslots=np.full(ids.shape,-1,int);maxslots=minslots.copy()
            for fi in range(len(ids)):
                for pi in range(2):
                    uid=ids[fi,pi];present=seen[uid]
                    err=norm(points[uid]-b['query_xy_m'][:,None])
                    lo=np.where(mask[uid],err,np.inf);hi=np.where(mask[uid],err,-np.inf)
                    lower[fi,pi,present]=lo[present].min(axis=1);upper[fi,pi,present]=hi[present].max(axis=1)
                    minslots[fi,pi,present]=lo[present].argmin(axis=1);maxslots[fi,pi,present]=hi[present].argmax(axis=1)
            np.savez_compressed(assignments/f'{path.stem}_band_{band:g}.npz',input_id=ids,source_rows=b['source_rows'],reference_error_min_candidate_slot=minslots,reference_error_max_candidate_slot=maxslots)
            for fi,ident,subset in fields(path,b,meta):
                primary_common=subset&finite['wcl'][fi].all(axis=0)&finite['nlls'][fi].all(axis=0)
                complete=bool(seen[ids[fi,:,primary_common]].all())
                base={**ident,'band_db2':band,'original_common_four_arm_n':int(primary_common.sum()),'candidate_pools_complete_on_common_cohort':complete}
                coverage.append(base)
                if not complete:continue
                common=primary_common;cohort_ids=ids[fi][:,common];ref=b['query_xy_m'][common]
                for qname,t in LEVELS:
                    w=[quantile(e['wcl'][fi,pi,common],t) for pi in range(2)]
                    n=[quantile(e['nlls'][fi,pi,common],t) for pi in range(2)]
                    nl=[quantile(lower[fi,pi,common],t) for pi in range(2)]
                    nu=[quantile(upper[fi,pi,common],t) for pi in range(2)]
                    row={**base,'quantile':qname}
                    if not common.any():rankings.append(row);continue
                    categories=[];intervalsigns=[]
                    for pi,policy in enumerate(POLICIES):
                        s=quantile_interval_sign(w[pi],nl[pi],nu[pi]);intervalsigns.append(s)
                        categories.append(rank_category(w[pi],n[pi]))
                        lower_contrast=w[pi]-nu[pi];upper_contrast=w[pi]-nl[pi]
                        ref_boundary=max(0.,lower_contrast,-upper_contrast)/2
                        row.update({policy+'_wcl_m':w[pi],policy+'_primary_nlls_m':n[pi],policy+'_nlls_lower_m':nl[pi],policy+'_nlls_upper_m':nu[pi],policy+'_wcl_minus_nlls_lower_m':lower_contrast,policy+'_wcl_minus_nlls_upper_m':upper_contrast,policy+'_contrast_sign_over_pool':s,policy+'_primary_ordering':categories[-1],policy+'_reference_delta_pool_sign_certificate_boundary_m':ref_boundary})
                    primary_reversal=strict_reversal(*categories);row['primary_strict_reversal']=primary_reversal
                    row['original_selected_objective_outside_current_pool_band_states']=int(np.sum(r['nlls_objective_db2'][fi][:,common]>minimum[cohort_ids]+band+1e-10))
                    witness_outcomes=[];consistent_outcomes=[]
                    for selections in itertools.product(['min','max'],repeat=2):
                        chosen=np.array([(minslots if selection=='min' else maxslots)[fi,pi,common] for pi,selection in enumerate(selections)])
                        qn=[quantile(norm(points[cohort_ids[pi],chosen[pi]]-ref),t) for pi in range(2)]
                        cats=[rank_category(w[pi],qn[pi]) for pi in range(2)];rev=strict_reversal(*cats)
                        conflict=assignment_conflicts(cohort_ids,chosen,points);witness_outcomes.append(rev)
                        if not conflict:consistent_outcomes.append(rev)
                        witnesses.append({**base,'quantile':qname,'rule':'reference_error_extreme_'+selections[0]+'_'+selections[1],'uses_reference_for_sensitivity_only':True,'exact_input_consistency_conflict_ids':conflict,'frozen_ordering':cats[0],'refit_ordering':cats[1],'strict_reversal':rev,'frozen_nlls_m':qn[0],'refit_nlls_m':qn[1]})
                    operational_outcomes=[]
                    for rule,slots in rule_slots.items():
                        chosen=slots[cohort_ids];qn=[quantile(norm(points[cohort_ids[pi],chosen[pi]]-ref),t) for pi in range(2)]
                        cats=[rank_category(w[pi],qn[pi]) for pi in range(2)];rev=strict_reversal(*cats);operational_outcomes.append(rev)
                        witnesses.append({**base,'quantile':qname,'rule':'truth_independent_'+rule,'uses_reference_for_sensitivity_only':False,'exact_input_consistency_conflict_ids':0,'frozen_ordering':cats[0],'refit_ordering':cats[1],'strict_reversal':rev,'frozen_nlls_m':qn[0],'refit_nlls_m':qn[1]})
                    forced=set(intervalsigns)=={'positive','negative'}
                    forced_non=(all(s in ['positive','negative'] for s in intervalsigns) and len(set(intervalsigns))==1) or 'numerical_tie' in intervalsigns
                    identical_policy_inputs=np.array_equal(cohort_ids[0],cohort_ids[1])
                    if identical_policy_inputs:classification='invariant_no_strict_reversal_over_found_pools'
                    elif forced:classification='invariant_strict_reversal_over_found_pools'
                    elif forced_non:classification='invariant_no_strict_reversal_over_found_pools'
                    elif any(v!=primary_reversal for v in operational_outcomes):classification='branch_sensitive_demonstrated_truth_independent_rule'
                    elif any(v!=primary_reversal for v in consistent_outcomes):classification='branch_sensitive_demonstrated_consistent_reference_scored_assignment'
                    elif any(v!=primary_reversal for v in witness_outcomes):classification='branch_sensitive_demonstrated_unconstrained_assignment_only'
                    else:classification='unresolved_by_envelope_and_prescribed_witnesses'
                    row['classification']=classification;row['identical_policy_numerical_inputs']=identical_policy_inputs;rankings.append(row)
                    blo,bhi=nl[0]-nu[1],nu[0]-nl[1]
                    rawlo,rawhi=blo,bhi
                    if identical_policy_inputs:blo=bhi=0.
                    calibration.append({**base,'quantile':qname,'method':'nlls','primary_frozen_minus_refit_m':n[0]-n[1],'found_pool_lower_m':blo,'found_pool_upper_m':bhi,'unconstrained_per_query_lower_m':rawlo,'unconstrained_per_query_upper_m':rawhi,'identical_policy_numerical_inputs':identical_policy_inputs,'reference_delta_pool_sign_certificate_boundary_m':max(0.,blo,-bhi)/2,'envelope_note':'Identical policy input vectors force zero contrast; otherwise conservative per-query bounds may be jointly unattainable'})
                    for src,dst in [(0,1),(1,0)]:
                        chosen,penalty=transfer(w[src],n[src],w[dst],n[dst]);bounds=transfer_bounds(w[src],nl[src],nu[src],w[dst],nl[dst],nu[dst],chosen,np.array_equal(cohort_ids[src],cohort_ids[dst]))
                        transfers.append({**base,'quantile':qname,'source_policy':POLICIES[src],'destination_policy':POLICIES[dst],'primary_source_method':chosen,'primary_transfer_penalty_m':penalty,'fixed_primary_choice_penalty_lower_m':bounds[0],'fixed_primary_choice_penalty_upper_m':bounds[1],'source_choice_uncertainty_penalty_lower_m':bounds[2],'source_choice_uncertainty_penalty_upper_m':bounds[3],'possible_source_winners_by_envelope':bounds[4],'envelope_note':'Conservative; extrema need not share a consistent implementable rule'})
                triple=common&finite['nlls'][zero,0]
                if not seen[ids[zero,0,triple]].all():continue
                for label,fa,pa,fb,pb in [('direct_geometry',zero,0,fi,0),('net_refit',zero,0,fi,1),('additional_refit',fi,0,fi,1)]:
                    a,bids=ids[fa,pa,triple],ids[fb,pb,triple]
                    lo,hi,uhi=candidate_pair_distances(a,bids,points,mask)
                    original=norm(r['nlls_position_m'][fa,pa,triple]-r['nlls_position_m'][fb,pb,triple])
                    for qname,t in LEVELS:movements.append({**base,'quantile':qname,'movement':label,'common_with_own_zero_n':int(triple.sum()),'same_input_pair_count':int((a==bids).sum()),'primary_movement_m':quantile(original,t),'consistent_input_pair_lower_m':quantile(lo,t),'consistent_input_pair_upper_m':quantile(hi,t),'unconstrained_pool_pair_upper_m':quantile(uhi,t),'interpretation':'Per-pair bounds honor identical-input identity; extrema across other shared inputs remain conservative'})
    tables={'RANKING_ENVELOPES':rankings,'CALIBRATION_EFFECT_ENVELOPES':calibration,'TRANSFER_PENALTY_ENVELOPES':transfers,'BASELINE_MOVEMENT_ENVELOPES':movements,'EXPLICIT_BRANCH_WITNESSES':witnesses,'COHORT_POOL_COVERAGE':coverage}
    for name,rows in tables.items():writecsv(output/(name+'.csv'),rows)
    summary={'status':'COMPLETE' if seen.all() else 'PARTIAL_NO_COMPLETE_POPULATION_CLAIM','source':source,'unique_inputs_available':int(seen.sum()),'unique_inputs_expected':len(seen),'protocol_sha256':sha(HERE/'protocol/CONSEQUENCE_PROTOCOL.json'),'candidate_protocol_sha256':sha(NUMERICAL/'protocol/RECOVERY_PROTOCOL.json'),'bands_db2':BANDS,'classification_counts_by_band':{str(band):dict(Counter(row.get('classification','empty') for row in rankings if row['band_db2']==band)) for band in BANDS},'input_candidate_shards_sha256':poolhash,'tables':{name:{'rows':len(rows),'sha256':sha(output/(name+'.csv'))} for name,rows in tables.items()},'code_sha256':{p.name:sha(p) for p in (HERE/'src').glob('*.py')},'limitations':['Found pools only; not certified global or complete near-optimal regions.','Reference-scored assignments are sensitivity witnesses, not production selection.','Alternative deterministic rules are secondary diagnostics, never primary replacements.','Conservative extrema need not correspond to one deployable rule.']}
    summary['pool_scope']='primary recovered pools plus completed targeted enhanced archives' if args.enhanced_directory else 'primary recovered pools only'
    summary['enhanced_candidate_archives']=sum(k.startswith('enhanced/') for k in poolhash)
    summary['explicit_assignment_archives_sha256']={p.name:sha(p) for p in assignments.glob('*.npz')}
    if args.enhanced_directory:summary['limitations'].append('Enhanced archives exist only for the explicitly targeted audit subset; analysis completion is not complete enhanced-search coverage of all numerical inputs.')
    writej(output/'SUMMARY.json',summary);print(json.dumps({k:v for k,v in summary.items() if k!='input_candidate_shards_sha256'},indent=2))
if __name__=='__main__':run()
