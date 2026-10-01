#!/usr/bin/env python3
"""Derive S4 reporting tables from retained S3 outputs; no localization or intercept refit.
Default --check is read-only. --out must be a new directory outside the evidence tree.
"""
from pathlib import Path
import argparse, hashlib, json, re, sys
import numpy as np
import pandas as pd

def require(x,msg):
    if not x: raise ValueError(msg)
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def compute(root):
    inputs={}
    def inp(s):
        p=root/s;inputs[s]=sha(p);return p
    e='calibration_extension/extension/'
    pairs=pd.read_csv(inp(e+'paired_results.csv'))
    require(len(pairs)==128,'128 pairs required')
    weights=[];intercepts=[];adverse=[]
    for name in ['recovered29','official32_minus71']:
        ref=np.load(inp(e+name+'_reference.npz'),allow_pickle=False)
        for k in [1,2]:
            g=pairs[(pairs['map']==name)&(pairs.k==k)].sort_values('draw')
            require(g.draw.tolist()==list(range(32)),'Complete ordered 32-field cell required')
            wf=[];wr=[];bf=[];br=[];bdelta=[];zs={t:[] for t in [14,69][:k]};shifts={t:[] for t in zs};rvals={t:[] for t in zs}
            touched0=None
            for row in g.itertuples():
                meta=json.loads(inp(e+'pairs/'+row.case+'.json').read_text())
                z=np.load(inp(e+'pairs/'+row.case+'.npz'),allow_pickle=False)
                sel=ref['selected_ids'];target=np.isin(sel,list(zs));touched=target.any(axis=1)
                require(np.array_equal(touched,z['touched']),'Affected subset differs')
                if touched0 is None: touched0=touched
                require(np.array_equal(touched,touched0),'Affected subset changed across fields')
                for arm in ['frozen','refit']:
                    mass=np.sum(z[arm+'_weights']*target,axis=1)
                    require(np.allclose(mass,z[arm+'_target_weight_mass'],rtol=1e-12,atol=1e-15),'Target mass mismatch')
                f=float(np.median(z['frozen_target_weight_mass'][touched]));v=float(np.median(z['refit_target_weight_mass'][touched]));wf.append(f);wr.append(v)
                ef=float(np.median(z['frozen_errors'][touched]));er=float(np.median(z['refit_errors'][touched]));bf.append(ef);br.append(er);bdelta.append(ef-er)
                require(abs((ef-er)-row.touched_delta_m)<1e-8,'Affected benefit mismatch')
                require(np.array_equal(z['frozen_predictions'][~touched],ref['predictions'][~touched]),'Untouched frozen changed')
                require(np.array_equal(z['refit_predictions'][~touched],ref['predictions'][~touched]),'Untouched refit changed')
                for t in zs:
                    a=meta['reference_a0'][str(t)];b=meta['refit_a0'][str(t)];rvals[t].append(a);shifts[t].append(b-a);zs[t].append(10**(-(b-a)/10))
                if row.delta_m<0:
                    adverse.append(dict(map=name,k=k,draw=row.draw,seed=row.seed,frozen_mass=f,refit_mass=v,whole_benefit_m=row.delta_m,affected_benefit_m=ef-er))
            weights.append(dict(map=name,k=k,fields=32,affected_n=int(touched0.sum()),total_n=len(touched0),affected_pct=100*float(touched0.mean()),frozen_mass=float(np.median(wf)),refit_mass=float(np.median(wr)),refit_mass_min=min(wr),refit_mass_max=max(wr),affected_frozen_m=float(np.median(bf)),affected_refit_m=float(np.median(br)),affected_benefit_m=float(np.median(bdelta)),affected_benefit_min=min(bdelta),affected_benefit_max=max(bdelta),helpful=int(sum(x>0 for x in bdelta)),harmful=int(sum(x<0 for x in bdelta))))
            for t in zs:
                require(len(set(rvals[t]))==1,'Reference intercept changed')
                d=np.array(shifts[t]);q=np.array(zs[t]);intercepts.append(dict(map=name,k=k,target=t,reference_a0_db=rvals[t][0],delta_median_db=float(np.median(d)),delta_min_db=float(d.min()),delta_max_db=float(d.max()),refit_median_db=rvals[t][0]+float(np.median(d)),weight_ratio_median=float(np.median(q)),weight_ratio_min=float(q.min()),weight_ratio_max=float(q.max())))
    require(len(adverse)==4 and [x['draw'] for x in adverse]==[4,5,9,14],'Contrary cases changed')
    # Original O33 substituted control: no new outcomes or inferred full-precision medians.
    base='results/rc5/official_core_tables/'
    exposure=pd.read_csv(inp(base+'exposure.csv'))
    counts=pd.read_csv(inp(base+'exhaustion_replayed.csv'))
    selected=pd.read_csv(inp(base+'message_identity_and_selection.csv'))
    old=pd.read_csv(inp(base+'top6_top7.csv'))
    methods=['WCL','ABS','DIFF','Min-Max'];windows=[];full=[];sets={};angle_fields={}
    for w,nfields in [(10,8),(5,4)]:
        run=f'O33R71_N4P7_D5000_W{w}'
        log=inp('results/rc5/official_core_logs/'+run+'.txt').read_text().splitlines()
        command=inp('results/rc5/official_core_logs/'+run+'.command.sh').read_text()
        require('--expose-dir-draws '+str(nfields) in command,'Direction count mismatch')
        c=counts[(counts['map']=='official33_repaired71.json')&(counts.window==w)]
        sel=selected[(selected['map']=='official33_repaired71.json')&(selected.window==w)]
        require(len(sel)==2495,'Wrong native O33 population')
        angle_fields[str(w)]={}
        for k in [6,7]:
            cr=c[c.k==k].iloc[0];prev=c[c.k==k-1].iloc[0]
            tg=set(map(int,cr.top_ids.split(',')));before=set(map(int,prev.top_ids.split(',')))
            ids=[int(x.working_message_index) for x in sel.itertuples() if set(map(int,x.selected_ids.split(',')))<=tg and not set(map(int,x.selected_ids.split(',')))<=before]
            require(len(ids)==int(cr.newly_exhausted_n),'Exhaustion count mismatch')
            if int(cr.added)==10: sets[str(w)]=sorted(ids)
            rec=dict(window=w,from_k=k-1,to_k=k,entering_receiver=int(cr.added),newly_exhausted=len(ids),N=2495,fields=nfields)
            for m in methods:
                a=exposure[(exposure.run==run)&(exposure.arm=='top')&(exposure.k==k-1)&(exposure.method==m)].iloc[0]
                b=exposure[(exposure.run==run)&(exposure.arm=='top')&(exposure.k==k)&(exposure.method==m)].iloc[0]
                # Bind extraction to the exact source log row, not just a secondary CSV.
                pat=r'^\s*(\d+)top\s+([-+\d.]+)\s+'+r'\s*([-+\d.]+)m\s+([-+\d.]+)%\s*'*4
                for rr in (a,b):
                    match=re.match(pat,log[int(rr.line)-1]); require(match is not None,'Unparsed historical top row')
                    nums=match.groups();pos=2+2*methods.index(m)
                    require(int(nums[0])==int(rr.k) and float(nums[pos])==rr.median_m and float(nums[pos+1])==rr.effect_pct,'CSV/log mismatch')
                delta=round(float(b.effect_pct-a.effect_pct),1);rec[m]=delta
                checkrow=old[(old.run==run)&(old.method==m)].iloc[0]
                require(abs(json.loads(checkrow.jumps_1to8)[str(k)]-delta)<1e-8,'Retained increment mismatch')
                full.append(dict(window=w,method=m,from_k=k-1,to_k=k,from_m=int(a.median_m),to_m=int(b.median_m),increment_m=int(b.median_m-a.median_m),from_pct=float(a.effect_pct),to_pct=float(b.effect_pct),increment_pp=delta,fields=nfields,source_log=run+'.txt',from_line=int(a.line),to_line=int(b.line)))
            windows.append(rec)
        angle_fields[str(w)]={str(k):[8800+k+101*d for d in range(nfields)] for k in [5,6,7]}
    require(sets['10']==sets['5'] and len(sets['10'])==335,'BS10 message identities differ')
    # Deterministic geometry definitions: no scoring, no parameter refit.
    canon=inp('code/baseline_001_e123_pairfallback_040926.py').read_text()
    for marker in ['np.random.default_rng(31337)','cen = np.mean(np.vstack(list(PHYS.values())), axis=0)','base_j = [build(PHYS, set(G), 20.0, 4400+d) for d in range(4)]']:
        require(marker in canon,'Canonical definition changed: '+marker)
    mp=json.loads(inp('maps/recovered29.json').read_text());order=json.loads(inp(e+'recovered29_reference.json').read_text())['rank_order'];ids=sorted(mp,key=int)
    centers=[order[0],order[len(order)//3],order[2*len(order)//3],order[-1]]
    clusters=[]
    for m in [3,7]:
        for s,g in enumerate(centers):
            tg=sorted(ids,key=lambda j:np.linalg.norm(np.array(mp[j])-mp[g]))[:m]
            clusters.append(dict(count=m,center_id=int(g),center_rank=order.index(g)+1,target_ids=list(map(int,tg)),direction_seeds=[5500+m+11*s+101*d for d in range(2)]))
    theta=float(np.random.default_rng(31337).uniform(0,2*np.pi));geometry=dict(coherent_angle_rad=theta,coherent_angle_deg=theta*180/np.pi,coherent_unit_easting=float(np.cos(theta)),coherent_unit_northing=float(np.sin(theta)),scale_pivot=np.mean(np.array([mp[g] for g in ids]),axis=0).tolist(),scale_factors=[.98,.99,1.01,1.02],cluster_centers=list(map(int,centers)),clusters=clusters,iteration_order='ascending numeric receiver ID; draw angles only for targeted receivers',background='fixed 20 m per receiver, independent uniform angles, not Gaussian; seed 4400+d for d=0..3',gross_seed='8800+k+101*d; k=1,3,6,7; d=0..3; identical vectors within each mixed/pure pair',o33_direction_seeds=angle_fields)
    same=dict(map='official33_repaired71.json',status='PASS',same_newly_exhausted_count=335,identity_type='retained working_message_index (not original CSV data row)',window10_k7=sets['10'],window5_k6=sets['5'])
    return {'weight_diagnostics.csv':pd.DataFrame(weights),'intercept_diagnostics.csv':pd.DataFrame(intercepts),'adverse_weight_diagnostics.csv':pd.DataFrame(adverse),'o33_window_increments.csv':pd.DataFrame(windows),'o33_window_full_values.csv':pd.DataFrame(full),'spatial_operator_register.json':geometry,'o33_identity_equality.json':same},inputs

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1]);p.add_argument('--out',type=Path);a=p.parse_args();root=a.root.resolve()
    tables,pins=compute(root)
    if a.out:
        out=a.out.resolve();require(not out.exists() and root!=out and root not in out.parents,'Choose fresh output outside package');out.mkdir(parents=True)
        for n,x in tables.items():
            if isinstance(x,pd.DataFrame):x.to_csv(out/n,index=False)
            else:(out/n).write_text(json.dumps(x,indent=2)+'\n')
        (out/'SOURCE_PINS.json').write_text(json.dumps(pins,indent=2)+'\n')
    else:
        expected=root/'results/s4';require(json.loads((expected/'SOURCE_PINS.json').read_text())==pins,'Source fingerprints changed')
        for n,x in tables.items():
            if isinstance(x,pd.DataFrame):pd.testing.assert_frame_equal(x,pd.read_csv(expected/n),check_exact=False,rtol=1e-10,atol=1e-10)
            else:require(json.loads((expected/n).read_text())==x,'JSON differs: '+n)
    print(json.dumps({'status':'PASS','pairs_checked':128,'weight_cells':4,'intercept_rows':6,'adverse_cases':4,'o33_table_rows':4,'o33_method_increments':16,'same_BS10_messages':335,'pinned_input_files':len(pins),'scope':'Saved-array and record-derived reporting; no localization, fit, bootstrap, new perturbation outcomes, or raw-data join.'},indent=2))
if __name__=='__main__':main()
