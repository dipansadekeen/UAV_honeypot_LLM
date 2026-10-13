"""Figure 9 from offline HP and SITL tlogs; includes empty seconds in rates."""
from pathlib import Path
import numpy as np
import pandas as pd
from plotting.common import plt,save
MESSAGES=['HEARTBEAT','SYS_STATUS','GPS_RAW_INT','GLOBAL_POSITION_INT','ATTITUDE','VFR_HUD']

def read_tlog(path,sysid=1,compid=1):
    from pymavlink import mavutil
    path=Path(path)
    if not path.is_file(): raise FileNotFoundError(path)
    connection=mavutil.mavlink_connection(str(path)); rows=[]
    try:
        while True:
            msg=connection.recv_match(blocking=False)
            if msg is None: break
            if msg.get_type() in MESSAGES and msg.get_srcSystem()==sysid and msg.get_srcComponent()==compid:
                rows.append({'timestamp':msg._timestamp,'message_type':msg.get_type()})
    finally:
        connection.close()
    df=pd.DataFrame(rows)
    if df.empty: raise ValueError(f'No selected vehicle messages in {path}')
    df=df.sort_values('timestamp')
    df['elapsed_sec']=df.timestamp-df.timestamp.min()
    df['second_bin']=np.floor(df.elapsed_sec).astype(int)
    return df


def analyze_connectivity(hp,sitl,out,sysid=1,compid=1):
    out=Path(out); out.mkdir(parents=True,exist_ok=True)
    sources={'HP':read_tlog(hp,sysid,compid),'SITL':read_tlog(sitl,sysid,compid)}
    intervals={}
    for label,d in sources.items():
        rates=d.groupby(['second_bin','message_type']).size().unstack(fill_value=0).reindex(
            index=range(int(d.second_bin.max())+1),columns=MESSAGES,fill_value=0).fillna(0)
        rates.to_csv(out/f'{label.lower()}_message_rates.csv')
        hb=d[d.message_type=='HEARTBEAT'].copy()
        hb['interval_s']=hb.timestamp.diff()
        hb=hb.dropna(subset=['interval_s']); hb.to_csv(out/f'{label.lower()}_heartbeat_intervals.csv',index=False)
        if hb.empty: raise ValueError(f'{label} needs at least two heartbeat messages')
        intervals[label]=hb
        if label=='HP':
            fig,ax=plt.subplots(figsize=(11,5))
            for name in MESSAGES[1:]: ax.plot(rates.index/60,rates[name],label=name,lw=1)
            ax.set(xlabel='Elapsed time (minutes)',ylabel='Messages / second'); ax.legend(ncol=2); ax.grid(alpha=.2)
            save(fig,out,'fig09a_hp_telemetry_rate')
            fig,ax=plt.subplots(figsize=(11,4))
            ax.plot(hb.elapsed_sec/60,hb.interval_s,lw=1)
            ax.set(xlabel='Elapsed time (minutes)',ylabel='Heartbeat interval (s)'); ax.grid(alpha=.2)
            save(fig,out,'hp_heartbeat_intervals')
    common=min(v.elapsed_sec.max() for v in intervals.values())
    fig,ax=plt.subplots(figsize=(7,5))
    ax.boxplot([intervals[k].loc[intervals[k].elapsed_sec<=common,'interval_s'] for k in ['HP','SITL']])
    ax.set_xticks([1,2],['HP','SITL']); ax.set_ylabel('Heartbeat interval (s)')
    save(fig,out,'fig09b_heartbeat_comparison')
