"""Lossless, versioned backup envelope shared by migration and MySQL recovery."""
import hashlib
import json

FORMAT = 'temu-workbench-backup/v1'
TABLES = {
    'records': ('record_type','id','payload','decision','market','candidate_id','synthetic','created_at','updated_at'),
    'revisions': ('id','candidate_id','sku_ref','field_key','payload','created_at'),
    'adapter_status': ('port_key','status','detail','updated_at'),
    'submissions': ('id','candidate_id','payload','created_at'),
    'snapshots': ('source_id','snapshot_ref','sha256','file_path','status','captured_at','payload'),
}
PRIMARY = {'records':('record_type','id'), 'revisions':('id',), 'adapter_status':('port_key',),
           'submissions':('id',), 'snapshots':('source_id',)}

def digest(tables):
    normalized = {table:sorted(rows, key=lambda r:tuple(str(r[k]) for k in PRIMARY[table]))
                  for table,rows in tables.items()}
    return hashlib.sha256(json.dumps(normalized, ensure_ascii=False, sort_keys=True,
                                     separators=(',',':'), allow_nan=False).encode('utf-8')).hexdigest()

def envelope(tables):
    state = {'format':FORMAT, 'tables':tables, 'sha256':digest(tables)}
    validate(state)
    return state

def validate(state):
    if not isinstance(state,dict) or state.get('format') != FORMAT:
        raise ValueError('not a workbench full backup')
    tables = state.get('tables')
    if not isinstance(tables,dict) or set(tables) != set(TABLES):
        raise ValueError('backup table set does not match')
    for table,columns in TABLES.items():
        rows = tables[table]
        if not isinstance(rows,list): raise ValueError('invalid backup rows')
        seen = set()
        for row in rows:
            if not isinstance(row,dict) or set(row) != set(columns):
                raise ValueError(f'{table}: unexpected columns')
            key = tuple(row[k] for k in PRIMARY[table])
            if any(not isinstance(x,str) or not x for x in key) or key in seen:
                raise ValueError(f'{table}: invalid or repeated primary key')
            seen.add(key)
            field = 'detail' if table == 'adapter_status' else 'payload'
            if not isinstance(row[field],str) or not isinstance(json.loads(row[field]),dict):
                raise ValueError(f'{table}: invalid JSON object')
    if state.get('sha256') != digest(tables):
        raise ValueError('backup checksum mismatch')
    return state
