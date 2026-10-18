"""Every prescribed field for primary map and spatial all-budget contexts."""
import json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from common import HERE,writej,sha

def run():
    p=HERE/'results/candidates';summary=json.loads((p/'SUMMARY.json').read_text())
    if summary['status']!='COMPLETE':raise ValueError('Complete recovery sensitivity required')
    x=pd.read_csv(p/'TRANSFER_PENALTY_ENVELOPES.csv')
    x=x[(x.band_db2==.01)&(x['map']=='official32_minus71')&(x.budget=='all')&(x.population=='full_sample')].copy()
    out=HERE/'results/presentation';out.mkdir(parents=True,exist_ok=True)
    x.to_csv(out/'TRANSFER_FIGURE_SOURCE.csv',index=False)
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':8,'axes.titlesize':9,'axes.labelsize':8,'legend.fontsize':8,'xtick.labelsize':7,'ytick.labelsize':7,'pdf.fonttype':42,'ps.fonttype':42})
    fig,axes=plt.subplots(2,2,figsize=(8.4,6.5),layout='constrained')
    colors={'frozen':'#006E8A','refit':'#9C3A62'};markers={'frozen':'o','refit':'s'}
    labels={'frozen':'Frozen choice → refitted evaluation','refit':'Refitted choice → frozen evaluation'}
    for row,study in enumerate(['study1','study2']):
        for col,q in enumerate(['p50','p95']):
            ax=axes[row,col];z=x[(x.study==study)&(x['quantile']==q)].copy()
            if study=='study1':
                groups=[('',0),( '14',100),('14',1000),('14',5000),('14,69',100),('14,69',1000),('14,69',5000)]
                xt=['0\nbaseline','1 / 100','1 / 1000','1 / 5000','2 / 100','2 / 1000','2 / 5000']
                def key(r):return ('' if r.D_m==0 else str(r.target_ids),int(r.D_m))
                xlabel='Displaced receivers / coordinate displacement (m)'
            else:
                groups=[(fold,d) for fold in ['SW','SE','NW','NE'] for d in [0,1000,5000]]
                xt=[fold+'\n'+str(d) for fold,d in groups]
                def key(r):return (r.fold,int(r.D_m))
                xlabel='Held-out spatial fold / coordinate displacement (m)'
            for policy in ['frozen','refit']:
                a=z[z.source_policy==policy]
                xx=np.array([groups.index(key(r)) for _,r in a.iterrows()],float)
                xx+=(-.14 if policy=='frozen' else .14)+np.where(a.draw.to_numpy()>=0,(a.draw.to_numpy()-1.5)*.045,0)
                y=a.primary_transfer_penalty_m.to_numpy();lo=a.source_choice_uncertainty_penalty_lower_m.to_numpy();hi=a.source_choice_uncertainty_penalty_upper_m.to_numpy()
                # The incumbent belongs to its found pool; tolerance absorbs only
                # subnanometre floating reconstruction in plotting coordinates.
                if (lo>y+1e-6).any() or (hi<y-1e-6).any():raise ValueError('Primary point outside transfer envelope')
                ax.errorbar(xx,y,yerr=np.vstack([np.maximum(y-lo,0),np.maximum(hi-y,0)]),fmt=markers[policy],color=colors[policy],markersize=3.8,capsize=2,elinewidth=.8,alpha=.85,label=labels[policy])
            ax.set_xticks(range(len(groups)),xt,rotation=25 if row==0 else 0,ha='right' if row==0 else 'center')
            ax.set_xlabel(xlabel);ax.set_ylabel('Excess '+q.upper()+' error (m)');ax.grid(axis='y',alpha=.25);ax.spines[['top','right']].set_visible(False)
            ax.set_title(('Primary catalogue map' if row==0 else 'Spatial holdouts, all-fit budget')+' · '+q.upper(),loc='left')
            if row==0:ax.set_ylim(-4,115)
            else:ax.set_ylim(-40,1200)
            ax.axhline(0,color='#555555',linewidth=.6)
    handles,labels=axes[0,0].get_legend_handles_labels();fig.legend(handles,labels,loc='outside lower center',ncol=2,frameon=False)
    fig.savefig(out/'choice_transfer.pdf',bbox_inches='tight');fig.savefig(out/'choice_transfer.png',dpi=180,bbox_inches='tight')
    plt.close(fig)
    caption=('Descriptive excess error when the estimator with the lower error quantile under one calibration policy is evaluated under the other, using the full fixed cohort in each block. Each point is one prescribed field; both transfer directions and all zero-baseline fields are retained. Upper panels: primary catalogue map, one or two displaced receivers, four directions at 100, 1000 and 5000 m. Lower panels: four spatial holdouts with all-fit calibration, two displaced receivers and four directions at 1000 and 5000 m. Vertical ranges propagate the 0.01 dB² found-candidate pool, including uncertainty in the source winner; they are conservative sensitivity ranges, not confidence intervals. Overlapping ranges may be visually smaller than markers. Choice and evaluation use the same cohort, so the quantity is not out-of-sample decision regret. The historical-map, ten-reception and target-affected sensitivities remain in the complete tables.')
    (out/'CHOICE_TRANSFER_CAPTION.txt').write_text(caption+'\n')
    writej(out/'FIGURE_RECEIPT.json',{'figure_source_rows':len(x),'all_zero_fields_included':True,'candidate_summary_sha256':sha(p/'SUMMARY.json'),'plot_code_sha256':sha(__file__),'files':{v.name:sha(v) for v in out.iterdir() if v.is_file()}})
    print(out)
if __name__=='__main__':run()
