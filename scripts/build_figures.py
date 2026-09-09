#!/usr/bin/env python3
"""Regenerate the ten scientific figures from frozen tables; no simulation or image synthesis.
Each chart is rendered as its own Matplotlib figure. Composite PDFs place those
independent vector charts on a page without rasterization.
"""
from pathlib import Path
import hashlib,json
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import fitz
ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'results/figure_data'; FIG=ROOT/'figures'; PANEL=FIG/'panels'
METHODS=['WCL','ABS','DIFF','Min-Max']; OUTS={}

def chart(title,xlabel,ylabel,w=4.1,h=3.15):
    fig=plt.figure(figsize=(w,h));ax=fig.add_axes([.17,.19,.78,.65])
    ax.set_title(title,fontsize=11,pad=9);ax.set_xlabel(xlabel,fontsize=9);ax.set_ylabel(ylabel,fontsize=9)
    ax.tick_params(labelsize=8);ax.grid(True,alpha=.22,linewidth=.5)
    return fig,ax

def save_panel(fig,name):
    p=PANEL/(name+'.pdf');fig.savefig(p,metadata={'CreationDate':None,'ModDate':None,'Creator':'Paper B deterministic figure builder'});plt.close(fig);return p

def assemble(name,panels,cols,sources,note):
    docs=[fitz.open(p) for p in panels];pw=docs[0][0].rect.width;ph=docs[0][0].rect.height;rows=(len(docs)+cols-1)//cols
    out=fitz.open();page=out.new_page(width=pw*cols,height=ph*rows)
    for i,d in enumerate(docs):
        row,col=divmod(i,cols);page.show_pdf_page(fitz.Rect(col*pw,row*ph,(col+1)*pw,(row+1)*ph),d,0)
    p=FIG/name;out.set_metadata({'title':name,'author':'Paper B authors','subject':note});out.save(p,garbage=4,deflate=True,no_new_id=True);out.close()
    for d in docs:d.close()
    OUTS[name]={'sources':sources,'panels':[str(p.relative_to(ROOT)) for p in panels],'note':note,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}

def main():
    FIG.mkdir(exist_ok=True);PANEL.mkdir(exist_ok=True)
    load=pd.read_csv(DATA/'paperb_load_surface.csv');parts=[]
    for i,m in enumerate(METHODS):
        fig,ax=chart(f'({chr(97+i)}) {m}','Corrupted receiver count','Displacement magnitude (m)')
        d=load[load.method==m].pivot(index='D_m',columns='f',values='effect_pct').sort_index()
        ax.set_position([.19,.19,.57,.65]);ax.grid(False);im=ax.imshow(d.values,origin='lower',aspect='auto',vmin=-2,vmax=846)
        ax.set_xticks(range(len(d.columns)),[str(x) for x in d.columns]);ax.set_yticks(range(len(d.index)),[f'{x:,}' for x in d.index])
        cax=fig.add_axes([.79,.19,.035,.65]);cb=fig.colorbar(im,cax=cax);cb.set_label('Median error change (%)',fontsize=8);cb.ax.tick_params(labelsize=7)
        parts.append(save_panel(fig,'Fig1_'+m.replace('-','')))
    assemble('Fig1_Corruption_Load_Surface.pdf',parts,2,['results/figure_data/paperb_load_surface.csv'],'R29; 8 draws except 500 m: 32 draws. All five expansion magnitudes; no antecedent 5-km cross-section.')
    e=pd.read_csv(DATA/'paperb_exposure_5km_w10.csv');parts=[]
    for i,m in enumerate(METHODS):
        fig,ax=chart(f'({chr(97+i)}) {m}','Corrupted receiver count, k','Median error change (%)')
        for arm,marker in [('top','o'),('random','s'),('bottom','^')]:
            d=e[(e.method==m)&(e.arm==arm)];ax.plot(d.k,d.effect_pct,marker=marker,markersize=3,linewidth=1.2,label=arm.capitalize())
        ax.set_xticks([1,3,5,7,10,14]);ax.legend(fontsize=8,loc='upper left');parts.append(save_panel(fig,'Fig2_'+m.replace('-','')))
    assemble('Fig2_Exposure_Topology.pdf',parts,2,['results/figure_data/paperb_exposure_5km_w10.csv'],'R29, 5 km. Top/bottom: 8 directions; random: 8 receiver-set/direction draws. No CIs inferred.')
    c=pd.read_csv(DATA/'paperb_coverage.csv');parts=[]
    for i,field in enumerate(['C_pct','delta_C_pct']):
        fig,ax=chart('(a) Cumulative exhaustion' if i==0 else '(b) Incremental exhaustion','Top-k corrupted receivers','Exhausted messages (%)' if i==0 else 'Newly exhausted messages (pp)',w=7.7,h=2.6)
        for dep in c.deployment.unique():
            d=c[c.deployment==dep];ax.plot(d.k,d[field],marker='o',markersize=3,linewidth=1.15,label=dep)
        ax.set_xticks(range(1,15));ax.legend(fontsize=8,ncol=2,loc='upper left');parts.append(save_panel(fig,'Fig3_'+str(i)))
    assemble('Fig3_Selection_Set_Exhaustion.pdf',parts,1,['results/figure_data/paperb_coverage.csv'],'Historical R29 and coordinate-free Sigfox topology; not spatially independent localization replications.')
    a=pd.read_csv(DATA/'paperb_a0_ablation.csv');fig,ax=chart('WCL: intercept refitting ablation','High-exposure corrupted receivers, k','Median error change (%)',w=6.2,h=3.2)
    for field,label,marker in [('refit_pct','Refit on each perturbed map','o'),('frozen_pct','Frozen on reference map','s')]:ax.plot(a.k,a[field],marker=marker,label=label)
    ax.set_xticks(a.k);ax.legend(fontsize=9);p=save_panel(fig,'Fig4');assemble('Fig4_A0_Refit_Ablation.pdf',[p],1,['results/figure_data/paperb_a0_ablation.csv'],'WCL-specific implemented intervention; does not independently manipulate exhaustion.')
    s=pd.read_csv(DATA/'paperb_spatial_families.csv');parts=[]
    for i,m in enumerate(METHODS):
        fig,ax=chart(f'({chr(97+i)}) {m}','Receiver displacement (m)','Median error change (%)')
        for family,marker,label in [('iso x8 med','o','Isotropic (8 draws)'),('coherent','s','Coherent'),('inward','^','Inward'),('outward','d','Outward')]:
            d=s[(s.method==m)&(s.family==family)];ax.plot(d.D_m,d.effect_pct,marker=marker,markersize=3,linewidth=1,label=label)
        ax.set_xscale('log');ax.set_yscale('symlog',linthresh=10);ax.set_yticks([-10,0,10,100,1000]);ax.set_yticklabels(['-10','0','10','100','1000']);ax.set_xticks([250,1000,10000],['250','1,000','10,000']);ax.legend(fontsize=7,loc='upper left');parts.append(save_panel(fig,'Fig5_'+m.replace('-','')))
    assemble('Fig5_Spatial_Error_Structure.pdf',parts,2,['results/figure_data/paperb_spatial_families.csv'],'R29; logarithmic x and symmetric-log y with linear region +/-10%. Isotropic: 8 directions; structured curves: registered constructions.')
    angles=pd.read_csv(DATA/'paperb_coherent_angles.csv');parts=[]
    fig,ax=chart('(a) Directional response on R29','Translation angle (degrees)','WCL error change (%)',w=4.1,h=3.6)
    for D,marker in [(250,'o'),(500,'s'),(1000,'^')]:
        d=angles[(angles.method=='WCL')&(angles.D_m==D)];ax.plot(d.angle_deg,d.effect_pct,marker=marker,markersize=3,linewidth=1,label=f'{D:,} m')
    ax.set_xticks([0,90,150,240,330]);ax.legend(fontsize=8);parts.append(save_panel(fig,'Fig6_angle'))
    g=pd.read_csv(ROOT/'results/b9c_author_remaining/g5_results.csv');d=g[(g.method=='WCL')&np.isclose(g.n,4.7)]
    rotation=[];iso=[]
    for field,control in [('legacy_rotation_effect_pct','legacy_iso8_effect_pct'),('opcenter_rotation_effect_pct','opcenter_exact_iso8_effect_pct')]:
        for sub in ['recovered29','official32_minus71']:
            row=d[d.substrate==sub].iloc[0];rotation.append(row[field]);iso.append(row[control])
    fig,ax=chart('(b) Transfer and explanatory control','WCL median error change (%)','',w=4.1,h=3.6)
    # Give labels room inside this independent chart; no multipart Matplotlib figure.
    ax.set_position([.34,.19,.61,.65]);y=np.arange(4)
    ax.scatter(rotation,y-.10,marker='o',label='Rotation',s=29);ax.scatter(iso,y+.10,marker='s',label='Isotropic, 8 draws',s=25)
    ax.set_yticks(y,['R29: legacy','O32−71: legacy','R29: controlled','O32−71: controlled']);ax.invert_yaxis();ax.legend(fontsize=7,loc='lower right');parts.append(save_panel(fig,'Fig6_transfer'))
    assemble('Fig6_Directional_and_Affine_Structure.pdf',parts,2,['results/figure_data/paperb_coherent_angles.csv','results/b9c_author_remaining/g5_results.csv'],'Legacy transfer uses unweighted map pivot and median displacement matching. Controlled rows: post-failure WCL operational pivot and exact receiver-wise displacement magnitudes. G4 remains FAIL; native populations differ.')
    t=pd.read_csv(DATA/'paperb_tails.csv');fig,ax=chart('WCL distributional response','Error percentile','Localization error (m)',w=6.6,h=3.6)
    labels={'reference':'Reference','f=24% @D':'24% at 5 km','f=100% @D':'All receivers at 5 km','top-6 @D':'Top six at 5 km','top-7 @D':'Top seven at 5 km'}
    for (_,row),marker in zip(t.iterrows(),['o','s','^','d','x']):ax.plot([50,75,90,95],[row[f'P{q}_m'] for q in [50,75,90,95]],marker=marker,label=labels[row.condition],markersize=4)
    ax.set_xticks([50,75,90,95]);ax.legend(fontsize=8,loc='upper left');p=save_panel(fig,'Fig7');assemble('Fig7_Reliability_Profile.pdf',[p],1,['results/figure_data/paperb_tails.csv'],'Perturbed rows pool 4 evaluations of each of 2,498 messages; 9,992 evaluations are not independent messages.')
    m=pd.read_csv(DATA/'paperb_matched_exposure.csv');fig,ax=chart('Exposure share is not sufficient','Exposure-share bin, S','WCL median error change (%)',w=6,h=3.3)
    ax.errorbar(m.S_bin,m.WCL_med_pct,yerr=np.vstack([m.WCL_med_pct-m.WCL_min_pct,m.WCL_max_pct-m.WCL_med_pct]),fmt='o',capsize=4,label='Subset median and min–max range');ax.set_xticks(m.S_bin);ax.legend(fontsize=9)
    p=save_panel(fig,'FigS1');assemble('FigS1_Matched_Exposure.pdf',[p],1,['results/figure_data/paperb_matched_exposure.csv'],'8 subsets per bin; min-max is a design range, not a confidence interval.')
    a=pd.read_csv(DATA/'paperb_affine.csv');d=a[(a['transform']=='scale')&(a.method=='WCL')];assert len(d)==4, 'Scale figure requires four WCL rows';fig,ax=chart('Uniform scale control on R29','Scale factor','WCL median error change (%)',w=6,h=3.3)
    ax.plot(d.parameter,d.effect_pct,marker='o',label='Uniform scale');ax.plot(d.parameter,d.matched_WCL_pct,marker='s',label='Median-displacement-matched isotropic');ax.set_xticks(d.parameter);ax.legend(fontsize=8)
    p=save_panel(fig,'FigS2');assemble('FigS2_Scale_Control.pdf',[p],1,['results/figure_data/paperb_affine.csv'],'Legacy four-direction isotropic comparator; small tested scales only.')
    m=pd.read_csv(DATA/'paperb_twopop.csv');fig,ax=chart('Mixed-error composition','High-exposure gross-error receivers, k','Mixed minus pure change (pp)',w=6,h=3.3)
    for method,field,marker in [('WCL','WCL_gap_pp','o'),('ABS','ABS_gap_pp','s'),('DIFF','DIFF_gap_pp','^'),('Min-Max','MinMax_gap_pp','d')]:ax.plot(m.k,m[field],marker=marker,label=method)
    ax.set_xticks(m.k);ax.legend(fontsize=9,ncol=2)
    p=save_panel(fig,'FigS3');assemble('FigS3_Two_Population.pdf',[p],1,['results/figure_data/paperb_twopop.csv'],'20-m background jitter + top-k 5-km corruption; 4 registered direction realizations. No general additivity theorem.')
    for info in OUTS.values():info['source_hashes']={n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in info['sources']}
    (FIG/'FIGURE_MANIFEST.json').write_text(json.dumps(OUTS,indent=2)+'\n')
    print(f'Created {len(OUTS)} vector PDF figures from frozen numerical sources.')
if __name__=='__main__':
    main()
    if (ROOT/'results/rc5/rotation_dispersion.csv').exists():
        from update_rc5_figures import main as update_rc5
        update_rc5()
