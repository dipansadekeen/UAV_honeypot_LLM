"""Figures 6, 7, 10 plus model metrics and component heatmaps."""
from pathlib import Path
import numpy as np
import pandas as pd
from config.settings import MODELS, OPERATIONS, COMPONENTS, CLASSES
from .common import plt, save, heatmap, CLASS_COLORS

def plot_llm(tables, out):
    cases=tables['cases']; metrics=tables['metrics']; components=tables['components']
    distribution=cases.groupby(['Model','Class']).size().unstack(fill_value=0).reindex(
        index=MODELS,columns=CLASSES,fill_value=0)
    totals=distribution.sum(axis=1).replace(0,np.nan)
    percent=100*distribution.div(totals,axis=0)
    distribution.assign(Total=totals).join(percent.add_suffix(' (%)')).to_csv(
        Path(out).parent/'class_distribution.csv')
    fig,ax=plt.subplots(figsize=(10,5.8)); bottom=np.zeros(len(distribution))
    for name in CLASSES:
        values=percent[name].fillna(0).to_numpy()
        ax.bar(MODELS,values,bottom=bottom,label=name,color=CLASS_COLORS[name],
               edgecolor='black',linewidth=.6,width=.65)
        bottom+=values
    ax.set_ylim(0,100); ax.set_ylabel('Cases (%)'); ax.tick_params(axis='x',rotation=20)
    ax.legend(ncol=4,frameon=False,loc='lower center',bbox_to_anchor=(.5,1.01))
    save(fig,out,'fig06_deception_categories')
    matrix=cases.pivot_table(index='Model',columns='Operation',values='Mean Compliance').reindex(
        index=MODELS,columns=OPERATIONS)
    heatmap(matrix,out,'fig07_operation_realism','UAV operation','Model')
    for model in MODELS:
        table=components[components.Model==model].set_index('Operation')[COMPONENTS].reindex(OPERATIONS)
        heatmap(table,out,f'components_{model}')
    names=['Precision (%)','Temptation (%)','ASR (%)','Accuracy (%)']
    fig,ax=plt.subplots(figsize=(11,5)); x=np.arange(len(names)); width=.15
    for i,r in metrics.iterrows():
        ax.bar(x+(i-(len(metrics)-1)/2)*width,r[names].to_numpy(float),width,label=r.Model)
    ax.set_xticks(x,[s.replace(' (%)','') for s in names]); ax.set_ylim(0,105)
    ax.set_ylabel('Score (%)'); ax.legend(ncol=3,frameon=False)
    save(fig,out,'deception_metrics')


def plot_hitl(tables,out):
    table=tables['components'].set_index('Operation')[COMPONENTS].reindex(OPERATIONS)
    heatmap(table,out,'hitl_component_compliance')


def plot_latency(summary,out):
    fig,ax=plt.subplots(figsize=(10,5.8))
    bars=ax.bar(summary.Model.astype(str),summary.Mean,yerr=summary.Std.fillna(0),capsize=5)
    ax.set_ylabel('Mean LLM latency (s)'); ax.tick_params(axis='x',rotation=20)
    for b,v in zip(bars,summary.Mean):
        ax.text(b.get_x()+b.get_width()/2,v,f'{v:.2f}',ha='center',va='bottom')
    save(fig,out,'fig10_model_latency')
