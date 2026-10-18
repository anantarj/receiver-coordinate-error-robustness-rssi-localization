"""All-field choice-transfer penalties and fixed-prediction sensitivity."""
from collections import defaultdict,Counter
import json
import numpy as np
from common import *

def curve_intervals(a,b):
    """a=frozen, b=refit; positive F-R exceedance favors refitting."""
    cuts=np.unique(np.r_[0.,a,b]);width=np.diff(cuts)
    sa=np.searchsorted(np.sort(a),cuts[:-1],side='right')
    sb=np.searchsorted(np.sort(b),cuts[:-1],side='right')
    diff=(sb-sa)/len(a)
    adverse=diff<0
    longest=run=0.
    for bad,w in zip(adverse,width):
        run=run+w if bad else 0.;longest=max(longest,run)
    min_gap=float(diff.min(initial=0));at_max=adverse&(diff==min_gap)
    return cuts[:-1],cuts[1:],diff,{
        'finite_error_range_m':float(cuts[-1]),'improvement_interval_width_m':float(width[diff>0].sum()),
        'worsening_interval_width_m':float(width[diff<0].sum()),'equality_interval_width_m':float(width[diff==0].sum()),
        'improvement_probability_gap_area_m':float(np.dot(width,np.maximum(diff,0))),
        'worsening_probability_gap_area_m':float(np.dot(width,np.maximum(-diff,0))),
        'maximum_improvement_probability_gap':float(max(0,diff.max(initial=0))),
        'maximum_worsening_probability_gap':float(max(0,-diff.min(initial=0))),
        'maximum_worsening_gap_percentage_points':float(max(0,-diff.min(initial=0))*100),
        'total_width_at_maximum_worsening_gap_m':float(width[at_max].sum()),
        'largest_single_interval_at_maximum_worsening_gap_m':float(width[at_max].max(initial=0)),
        'longest_connected_worsening_interval_m':float(longest),
        'threshold_tie_convention':'Exact raw errors; equality is success; no cross-arm numerical canonicalization',
        'empirical_ordering':'crossing' if (diff>0).any() and (diff<0).any() else ('refit_no_worse' if (diff>0).any() else ('frozen_no_worse' if (diff<0).any() else 'equal'))}

def run():
    source=verify_source();out=HERE/'results/original';out.mkdir(parents=True,exist_ok=True)
    choices=[];contrasts=[];movement=[];curve_summary=[];curve_rows=[];cohorts=[];rankings=[]
    for path in block_files():
        b,r,m,e,f=load_block(path);zero=int(np.flatnonzero(b['field_D_m']==0)[0])
        for fi,ident,subset in fields(path,b,m):
            common=subset&f['wcl'][fi].all(axis=0)&f['nlls'][fi].all(axis=0)
            base={**ident,'common_four_arm_finite_n':int(common.sum()),'missing_from_common_four_arm_n':int((subset&~common).sum())}
            rows=b['source_rows'][common]
            base['ordered_source_rows_sha256']=__import__('hashlib').sha256(np.ascontiguousarray(rows.astype('<i8')).tobytes()).hexdigest()
            cohorts.append(base)
            for name,t in LEVELS:
                vals={k:[quantile(e[k][fi,pi,common],t) for pi in range(2)] for k in METHODS}
                rr={**base,'quantile':name}
                for pi,p in enumerate(POLICIES):
                    w,n=vals['wcl'][pi],vals['nlls'][pi]
                    rr.update({p+'_wcl_error_m':w,p+'_nlls_error_m':n,p+'_ordering':rank_category(w,n)})
                    if common.any():
                        d=w-n;contrasts.append({**base,'quantile':name,'comparison':'wcl_minus_nlls','policy':p,'signed_margin_m':d,'reference_delta_certificate_boundary_m':reference_boundary(d),'numerical_sign':sign(w,n)})
                rr['strict_reversal']=strict_reversal(rr['frozen_ordering'],rr['refit_ordering']);rankings.append(rr)
                for k in METHODS:
                    d=vals[k][0]-vals[k][1] if common.any() else None
                    contrasts.append({**base,'quantile':name,'comparison':'frozen_minus_refit','method':k,'signed_margin_m':d,'reference_delta_certificate_boundary_m':reference_boundary(d),'numerical_sign':sign(*vals[k])})
                for spi,dpi in [(0,1),(1,0)]:
                    row={**base,'quantile':name,'source_policy':POLICIES[spi],'destination_policy':POLICIES[dpi]}
                    if common.any():
                        selected,penalty=transfer(vals['wcl'][spi],vals['nlls'][spi],vals['wcl'][dpi],vals['nlls'][dpi])
                        row.update({'source_selected_method':selected,'source_numerical_ordering':rr[POLICIES[spi]+'_ordering'],'destination_selected_method':winner(vals['wcl'][dpi],vals['nlls'][dpi]),'source_wcl_minus_nlls_m':vals['wcl'][spi]-vals['nlls'][spi],'destination_wcl_minus_nlls_m':vals['wcl'][dpi]-vals['nlls'][dpi],'transfer_penalty_m':penalty,'reference_delta_both_orderings_certificate_boundary_m':min(abs(vals['wcl'][spi]-vals['nlls'][spi]),abs(vals['wcl'][dpi]-vals['nlls'][dpi]))/2})
                    choices.append(row)
            for k in METHODS:
                triple=common&f[k][zero,0]
                p=r[k+'_position_m'];p0=p[zero,0,triple];pf=p[fi,0,triple];pr=p[fi,1,triple]
                a=norm(pf-p0);bb=norm(pr-p0);c=norm(pr-pf)
                for name,t in LEVELS:movement.append({**base,'method':k,'quantile':name,'common_with_own_zero_n':int(triple.sum()),'direct_geometry_m':quantile(a,t),'net_refit_m':quantile(bb,t),'additional_refit_m':quantile(c,t),'frozen_minus_refit_movement_m':quantile(a,t)-quantile(bb,t) if triple.any() else None})
                if common.any():
                    lo,hi,d,s=curve_intervals(e[k][fi,0,common],e[k][fi,1,common]);curve_summary.append({**base,'method':k,**s})
                    for x,y,g in zip(lo,hi,d):curve_rows.append({'block':path.stem,'field_index':fi,'population':ident['population'],'method':k,'threshold_lo_m':x,'threshold_hi_m':y,'frozen_minus_refit_exceedance':g})
    for fn,rs in [('METHOD_CHOICE_TRANSFER',choices),('QUANTILE_CONTRAST_REFERENCE_BOUNDS',contrasts),('BASELINE_MOVEMENT',movement),('EXCEEDANCE_INTERVAL_SUMMARY',curve_summary),('EXCEEDANCE_INTERVALS',curve_rows),('PAIRED_COHORTS',cohorts),('ALL_FIELD_RANKINGS',rankings)]:writecsv(out/(fn+'.csv'),rs)
    # Independently recomputed original ranking quantities must match the frozen report.
    old=list(__import__('csv').DictReader((ORIGINAL/'results/analysis/RANKINGS.csv').open()))
    index={(r['block'],r['field_index'],r['population'],r['quantile']):r for r in old}
    checked=0;maximum=0.
    for rr in rankings:
        key=(rr['block'],str(rr['field_index']),rr['population'],rr['quantile'])
        if key not in index:continue
        oldrow=index[key]
        for k in ['frozen_wcl_error_m','frozen_nlls_error_m','refit_wcl_error_m','refit_nlls_error_m']:
            delta=abs(rr[k]-float(oldrow[k]));maximum=max(maximum,delta)
            if delta>1e-9:raise ValueError('Original reconstruction discrepancy '+str(key)+' '+k)
        if str(rr['strict_reversal'])!=oldrow['strict_reversal']:raise ValueError('Reversal mismatch')
        checked+=1
    if checked!=len(old):raise ValueError('Incomplete original ranking reconstruction')
    groups=defaultdict(list)
    keys=['study','map','fold','budget','replicate','target_ids','D_m','population','quantile','source_policy','destination_policy']
    for row in choices:groups[tuple(row[k] for k in keys)].append(row)
    summaries=[]
    for key,rs in groups.items():
        v=np.array([r['transfer_penalty_m'] for r in rs if 'transfer_penalty_m' in r]);z={**dict(zip(keys,key)),'field_count':len(rs),'finite_count':len(v)}
        if len(v):z.update({'zero_penalty_fields':int((v==0).sum()),'positive_penalty_fields':int((v>0).sum()),'penalty_min_m':v.min(),'penalty_median_m':np.median(v),'penalty_max_m':v.max()})
        summaries.append(z)
    writecsv(out/'TRANSFER_DIRECTION_SUMMARY.csv',summaries)
    result={'status':'COMPLETE_ORIGINAL_OUTPUT_DESCRIPTIVE_ANALYSIS','source':source,'protocol_sha256':sha(HERE/'protocol/CONSEQUENCE_PROTOCOL.json'),'code_sha256':{p.name:sha(p) for p in (HERE/'src').glob('*.py')},'original_ranking_reconstruction':{'rows_checked':checked,'maximum_absolute_difference_m':maximum},'rows':{'rankings':len(rankings),'transfer':len(choices),'contrasts':len(contrasts),'curves':len(curve_summary),'intervals':len(curve_rows)},'branch_sensitivity_status':'pending recovered candidate pools; original-output findings are provisional with respect to that sensitivity','interpretation':['Transfer penalty is descriptive choice-and-score on the same cohort, not out-of-sample regret.','Nonnegative penalties retain zeros; underlying signed contrasts retain negative and null effects.','Threshold widths are lengths on the error-tolerance axis, not application probabilities or justified operating requirements.','Exact raw threshold curves do not align cross-arm numerical ties; equality at a threshold is success.','abs(quantile contrast)/2 marks loss of the sufficient reference-uncertainty sign certificate, not an attained reversal. Predictions and calibration are held fixed.'],'files':{p.name:sha(p) for p in out.glob('*.csv')}}
    writej(out/'SUMMARY.json',result);print(json.dumps(native(result),indent=2))
if __name__=='__main__':run()
