#!/usr/bin/env python3
"""Scientific figure from complete saved fields; no fit or localizer call."""
from pathlib import Path
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
ROOT=Path(__file__).resolve().parents[1]
link=pd.read_csv(ROOT/'results/CALIBRATION_LOCALIZATION_LINK.csv')
effects=pd.read_csv(ROOT/'results/EXTENSION_POSITION_EFFECTS.csv')
link=link[link.policy=='selected'].copy()
effects=effects[(effects.comparison=='frozen_minus_selected')&(effects.cohort=='full')&(effects.metric=='p50')&((effects.estimator=='wcl')|(effects.candidate_band_db2==.01))]
keys=['block_id','field_index','estimator']
data=link.merge(effects[keys+['lower_benefit_m','upper_benefit_m']],on=keys,validate='one_to_one')
data['query_target_rss_mae_benefit_db']=-data.query_macro_rss_mae_change_db
out=ROOT/'report';out.mkdir(exist_ok=True);data.to_csv(out/'CALIBRATION_LOCALIZATION_FIGURE_DATA.csv',index=False)
plt.rcParams.update({'font.size':8,'axes.labelsize':8,'axes.titlesize':9,'legend.fontsize':7,'savefig.dpi':180,'pdf.fonttype':42,'ps.fonttype':42})
fig,axes=plt.subplots(1,2,figsize=(7.15,3.2))
for ax,D in zip(axes,[1000,5000]):
    z=data[data.D_m==D]
    for estimator,marker,color,label in [('wcl','o','#1565a8','WCL'),('nlls','^','#bf5d20','RSS-NLS')]:
        s=z[z.estimator==estimator]
        err=[(s.p50_benefit_m-s.lower_benefit_m).clip(lower=0),(s.upper_benefit_m-s.p50_benefit_m).clip(lower=0)]
        ax.errorbar(s.query_target_rss_mae_benefit_db,s.p50_benefit_m,yerr=err,fmt=marker,color=color,
                    markersize=4,capsize=1.5,elinewidth=.7,markerfacecolor='none',label=label,alpha=.85)
    ax.axvline(0,color='.5',lw=.65);ax.axhline(0,color='.5',lw=.65)
    ax.set_title('1 km metadata displacement' if D==1000 else '5 km metadata displacement')
    ax.set_xlabel('Held-out target RSS MAE benefit (dB)')
    ax.grid(alpha=.16);ax.spines[['top','right']].set_visible(False)
axes[0].set_ylabel('Full-cohort P50 benefit (m)');axes[0].legend(loc='best',frameon=False)
fig.tight_layout(pad=1.1);fig.savefig(out/'calibration_localization_link.pdf');fig.savefig(out/'calibration_localization_link.png');plt.close(fig)
(out/'CALIBRATION_FIGURE_CAPTION.txt').write_text('Validation-selected calibration versus freezing on fit-only inputs. Each marker denotes one of 16 fixed field/fold conditions per magnitude and estimator. All 32 positive-displacement conditions are retained for each estimator, including the four one-kilometre conditions that select no update and overlap at the origin; no jitter is added. Benefits equal frozen minus selected loss on both axes: positive horizontal/vertical values indicate lower target RSS MAE/lower full-cohort P50 positioning error under the selected policy. RSS assessment uses held-out selected receptions on the same 500-query cohorts. RSS-NLS bars bound P50 benefit over found candidate pools within 0.01 dB^2; they are not confidence intervals or exhaustive near-optimal regions. Both axes are relative changes, not absolute adequacy or accuracy certification.\n')
print(str(out/'calibration_localization_link.pdf'))
