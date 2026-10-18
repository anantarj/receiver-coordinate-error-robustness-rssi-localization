#!/usr/bin/env python3
"""Describe three previously identified extreme candidate pairs, without solving."""
import csv
import json
from pathlib import Path
import numpy as np
from recover_candidates import ROOT,OLD,sha,write_json

CASES=[('study1_recovered29_sensitivity_all',82906,1,1),
       ('study1_official32_minus71_all',72127,2,2),
       ('study2_NW_all',95661,2,2)]

def main():
    reg=dict(np.load(ROOT/'inputs/UNIQUE_INPUTS.npz',allow_pickle=False));pilot=json.loads((ROOT/'protocol/PILOT_INPUT_IDS.json').read_text())
    cases=[]
    for block,row,draw,targets in CASES:
        with np.load(ROOT/'mappings'/(block+'.npz'),allow_pickle=False) as mp,np.load(OLD/'inputs/blocks'/(block+'.npz'),allow_pickle=False) as old:
            qi=int(np.where(mp['source_rows']==row)[0][0]);fi=int(np.where((mp['field_D_m']==5000)&(mp['field_draw']==draw)&(mp['field_target_count']==targets))[0][0]);uid=int(mp['input_id'][fi,1,qi])
            selected=old['selected_ids'][qi][old['selected_mask'][qi]].astype(int);mask=old['field_target_mask'][fi][selected-1];reference=old['query_xy_m'][qi]
        if uid in pilot:
            k=pilot.index(uid);name=f'pilot_{(k//16)*16:03d}.npz'
        else:
            work=uid-sum(p<uid for p in pilot);start=(work//128)*128;stop=min(start+128,len(reg['input_id'])-len(pilot));name=f'shard_{start:06d}_{stop:06d}.npz'
        p=ROOT/'candidates'/name
        with np.load(p,allow_pickle=False) as z:
            index=int(np.where(z['input_id']==uid)[0][0]);v=z['candidate_valid'][index];j=z['candidate_objective_db2'][index]
            keep=v&(j<=np.min(j[v])+.01);positions=z['candidate_position_m'][index,keep];objectives=j[keep]
            distances=np.linalg.norm(positions[:,None]-positions[None,:],axis=2);i,k=np.unravel_index(np.argmax(distances),distances.shape)
            pair=positions[[i,k]];pair_j=objectives[[i,k]]
        m=int(reg['receiver_count'][uid]);anchors=reg['anchors_m'][uid,:m];rss=reg['rss_dbm'][uid,:m];intercept=reg['intercepts_dbm'][uid,:m]
        unchanged=anchors[~mask];assert len(unchanged)==2
        line=unchanged[1]-unchanged[0];unit=line/np.linalg.norm(line);normal=np.array([-unit[1],unit[0]])
        displacement=pair[0]-unchanged[0];reflection=unchanged[0]+2*(displacement@unit)*unit-displacement
        signed=(pair-unchanged[0])@normal
        link_distance=np.linalg.norm(pair[:,None]-anchors[None],axis=2)
        residual=rss-intercept+47*np.log10(link_distance+1.)
        rec={'block':block,'source_row':row,'field_index':fi,'draw':draw,'D_m':5000,'policy':'refit','input_id':uid,
            'candidate_archive':name,'candidate_archive_sha256':sha(p),'selection':'Previously identified maximum-diameter state in each of three blocks; pair is maximum separation in recovered0.01dB2 pool.',
            'selected_receiver_ids':selected.tolist(),'selected_target_ids':selected[mask].tolist(),'unchanged_receiver_ids':selected[~mask].tolist(),
            'selected_receiver_count':m,'pair_positions_m':pair.tolist(),'pair_objectives_db2':pair_j.tolist(),
            'diameter_m':float(distances[i,k]),'reflection_discrepancy_m':float(np.linalg.norm(pair[1]-reflection)),
            'signed_distances_from_unchanged_anchor_line_m':signed.tolist(),
            'opposite_sides_of_unchanged_anchor_line':bool(signed[0]*signed[1]<0),
            'unchanged_link_distance_differences_m':(link_distance[0,~mask]-link_distance[1,~mask]).tolist(),
            'pair_residuals_db':residual.tolist(),'pair_unchanged_objective_db2':np.sum(residual[:,~mask]**2,axis=1).tolist(),
            'pair_target_objective_db2':np.sum(residual[:,mask]**2,axis=1).tolist(),
            'pair_reference_relative_error_m':np.linalg.norm(pair-reference,axis=1).tolist(),
            'interpretation':'Observed near-reflection geometry if discrepancies are small; no assertion of exact global optima, physical identifiability, or causal prevalence.'}
        cases.append(rec)
    result={'status':'READ_ONLY_DIAGNOSTIC_COMPLETE','case_selection':'Three already identified block-extreme candidate diameters; not representative sampling.','cases':cases,'script_sha256':sha(__file__)}
    write_json(ROOT/'results/BRANCH_GEOMETRY_DIAGNOSTICS.json',result)
    columns=['block','source_row','input_id','selected_receiver_count','diameter_m','reflection_discrepancy_m','opposite_sides_of_unchanged_anchor_line']
    with (ROOT/'results/BRANCH_GEOMETRY_DIAGNOSTICS.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=columns);writer.writeheader();writer.writerows({k:c[k] for k in columns} for c in cases)
    print(json.dumps([{k:c[k] for k in columns} for c in cases]))

if __name__=='__main__':main()
