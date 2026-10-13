"""Offline JSON/schema validation for prompt responses.
Checks structure, offsets, numeric types, and heartbeat armed-bit preservation.
Physical realism is evaluated separately by evaluation/telemetry.py.
"""
import json,math
GROUPS={
    'GLOBAL_POSITION_INT':{'lat','lon','alt','relative_alt','vx','vy','vz','hdg'},
    'ATTITUDE':{'roll','pitch','yaw'},
    'VFR_HUD':{'groundspeed','heading','throttle','alt','climb'},
    'SYS_STATUS':{'battery_remaining','voltage_battery','load'},
    'GPS_RAW_INT':{'fix_type'},
}
INTEGER_FIELDS={
    'GLOBAL_POSITION_INT':GROUPS['GLOBAL_POSITION_INT'],
    'VFR_HUD':{'heading','throttle'},'SYS_STATUS':GROUPS['SYS_STATUS'],
    'GPS_RAW_INT':GROUPS['GPS_RAW_INT'],
}

def load_response(response):
    value=json.loads(response) if isinstance(response,str) else response
    if not isinstance(value,dict): raise ValueError('Response must be a JSON object')
    return value


def validate_heartbeat(response,command_id,previous_heartbeat):
    obj=load_response(response)
    if set(obj)!={'heartbeat_patch','reason'} or not isinstance(obj['reason'],str):
        raise ValueError('Expected heartbeat_patch and a string reason')
    patch=obj['heartbeat_patch']
    if not isinstance(patch,dict) or set(patch)!={'base_mode','custom_mode','system_status'}:
        raise ValueError('Unexpected heartbeat fields')
    for field,maximum in [('base_mode',255),('custom_mode',2**32-1),('system_status',255)]:
        v=patch[field]
        if isinstance(v,bool) or not isinstance(v,int) or not 0<=v<=maximum:
            raise ValueError(f'{field} must be an unsigned MAVLink integer')
    if command_id!=400 and (patch['base_mode']&128)!=(int(previous_heartbeat['base_mode'])&128):
        raise ValueError('Only command 400 may change the armed bit')
    return patch


def validate_telemetry(response,allowed_groups=None):
    obj=load_response(response)
    if set(obj)!={'telemetry_series','reason'} or not isinstance(obj['reason'],str):
        raise ValueError('Expected telemetry_series and a string reason')
    series=obj['telemetry_series']
    if not isinstance(series,list) or len(series)!=5: raise ValueError('Expected five telemetry steps')
    allowed=GROUPS if allowed_groups is None else allowed_groups
    for step,dt in zip(series,[.5,1.,1.5,2.,2.5]):
        if not isinstance(step,dict) or set(step)!={'dt','fields'}: raise ValueError('Unexpected step keys')
        offset=step['dt']
        if isinstance(offset,bool) or not isinstance(offset,(int,float)) or not math.isfinite(offset) or abs(offset-dt)>1e-9:
            raise ValueError('Offsets must be 0.5, 1.0, 1.5, 2.0, 2.5 seconds')
        fields=step['fields']
        if not isinstance(fields,dict) or not fields: raise ValueError('fields must be a nonempty object')
        if 'battery_remaining' not in fields.get('SYS_STATUS',{}):
            raise ValueError('Each step requires SYS_STATUS.battery_remaining')
        for group,values in fields.items():
            if group not in allowed or not isinstance(values,dict) or not values:
                raise ValueError(f'Unknown or empty group: {group}')
            if not set(values)<=set(allowed[group]): raise ValueError(f'Unknown field in {group}')
            for field,value in values.items():
                if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value):
                    raise ValueError(f'{group}.{field} must be finite and numeric')
                if field in INTEGER_FIELDS.get(group,set()) and not isinstance(value,int):
                    raise ValueError(f'{group}.{field} must be an integer')
    return series
