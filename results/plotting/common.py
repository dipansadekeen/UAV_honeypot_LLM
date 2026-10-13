"""Headless publication figures saved as PNG and vector PDF."""
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

COLORS = ['#4C78A8','#F28E2B','#59A14F','#B279A2','#E15759']
MODEL_COLORS = dict(zip(['gpt-oss-20b','gpt-oss-120b','nemotron-super','nemotron-nano','gemma4'],COLORS))
CLASS_COLORS = dict(zip(['SALC','SANLC','FALC','FANLC'],
                       ['#4C78A8','#F2A541','#59A14F','#D66B6B']))
plt.rcParams.update({'font.size':12,'axes.labelsize':15,'legend.fontsize':11,
                     'pdf.fonttype':42,'ps.fonttype':42})

def save(fig, out, name):
    out=Path(out); out.mkdir(parents=True,exist_ok=True)
    fig.tight_layout()
    for ext in ['png','pdf']:
        fig.savefig(out/f'{name}.{ext}',dpi=240,bbox_inches='tight',pad_inches=.2)
    plt.close(fig)


def heatmap(table, out, name, xlabel='Component', ylabel='Operation'):
    import numpy as np
    import pandas as pd
    fig,ax=plt.subplots(figsize=(max(9,1.0*len(table.columns)),max(4,.55*len(table)+2)))
    cmap=plt.get_cmap('viridis').copy(); cmap.set_bad('#dddddd')
    im=ax.imshow(np.ma.masked_invalid(table.to_numpy(float)),aspect='auto',vmin=0,vmax=1,cmap=cmap)
    ax.set_xticks(range(len(table.columns)),table.columns,rotation=40,ha='right')
    ax.set_yticks(range(len(table)),table.index)
    ax.set_xlabel(xlabel); ax.set_ylabel(ylabel)
    for i in range(len(table)):
        for j in range(len(table.columns)):
            v=table.iloc[i,j]
            ax.text(j,i,'N/A' if pd.isna(v) else f'{v:.2f}',ha='center',va='center',fontsize=9,
                    color='white' if pd.notna(v) and v<.55 else 'black')
    fig.colorbar(im,ax=ax).set_label('Mean component score')
    save(fig,out,name)
