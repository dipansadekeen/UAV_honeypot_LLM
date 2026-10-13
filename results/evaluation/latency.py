"""Latency counted once per model/call, exactly as in notebook cell 3."""
from pathlib import Path
import numpy as np
import pandas as pd
from config.settings import MODEL_MAP, MODELS

def evaluate_latency(path, out):
    df = pd.read_csv(path, low_memory=False)
    df['Model'] = df.llm_model_name.map(MODEL_MAP)
    df['llm_latency_ms'] = pd.to_numeric(df.llm_latency_ms, errors='coerce')
    valid = df.dropna(subset=['Model','llm_call_id','llm_latency_ms'])
    if valid.empty:
        raise ValueError('No latency samples found')
    # Preserve experiment-wide call ID convention; reject conflicting reuse.
    grouping = valid.groupby(['Model','llm_call_id'], sort=False)
    if grouping.mission_run_id.nunique().gt(1).any():
        raise ValueError('A model/call ID is reused across missions; supply globally unique call IDs')
    if grouping.llm_latency_ms.nunique().gt(1).any():
        raise ValueError('Conflicting latency values within an LLM call')
    calls = grouping.agg(llm_latency_ms=('llm_latency_ms','first'),
        operation=('command_name','first'),mission_run_id=('mission_run_id','first'),
        mission_seq=('mission_seq','first')).reset_index()
    if calls.llm_latency_ms.lt(0).any() or not np.isfinite(calls.llm_latency_ms).all():
        raise ValueError('Latency must be finite and nonnegative')
    calls['Latency (s)'] = calls.llm_latency_ms/1000
    summary = calls.groupby('Model',sort=False)['Latency (s)'].agg(
        Calls='count',Mean='mean',Median='median',Std='std',Min='min',Max='max').reset_index()
    summary = summary.merge(calls.groupby('Model')['Latency (s)'].quantile(.95).rename('P95'),on='Model')
    summary['Model'] = pd.Categorical(summary.Model,MODELS,ordered=True)
    summary = summary.sort_values('Model').reset_index(drop=True)
    out = Path(out); out.mkdir(parents=True,exist_ok=True)
    calls.to_csv(out/'latency_calls.csv',index=False)
    summary.to_csv(out/'latency_summary.csv',index=False)
    return calls, summary
