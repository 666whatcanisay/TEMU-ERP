"""Map stable DTO fields to SQL columns, retaining only extensions and wire shape.

The shape records presence, decimal formatting and key order, not a second copy
of business values. It lets old exports survive the relational migration intact.
"""
from copy import deepcopy
from datetime import date, datetime, timezone
from decimal import Decimal
import json


def dumps(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False)


def utc(value=None):
    if value:
        try:
            parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
            if parsed.tzinfo is None:parsed=parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc).replace(tzinfo=None)
        except ValueError:
            pass
    return datetime.now(timezone.utc).replace(tzinfo=None)


def orders(value):
    if isinstance(value, dict):
        return {'keys':list(value), 'children':{k:orders(v) for k,v in value.items() if isinstance(v,(dict,list))}}
    if isinstance(value, list):
        return [orders(v) for v in value]
    return None


def reorder(value, shape):
    if isinstance(value, dict) and isinstance(shape, dict):
        keys = list(shape['keys']) + [k for k in value if k not in shape['keys']]
        return {k:reorder(value[k], shape.get('children',{}).get(k)) for k in keys if k in value}
    if isinstance(value,list) and isinstance(shape,list):
        return [reorder(v,shape[i] if i<len(shape) else None) for i,v in enumerate(value)]
    return value


def read_path(value, path):
    for key in path.split('.'):
        if not isinstance(value,dict) or key not in value:
            return False, None
        value=value[key]
    return True,value


def write_path(value,path,item):
    keys=path.split('.')
    for key in keys[:-1]:
        if not isinstance(value.get(key),dict):value[key]={}
        value=value[key]
    value[keys[-1]]=item


def pop_path(value,path):
    keys=path.split('.')
    for key in keys[:-1]:value=value[key]
    return value.pop(keys[-1])


def encode(document, fields, collections=()):
    extra={'data':deepcopy(document),'shape':{},'order':orders(document),'collections':{}}
    columns={}
    for column,(path,kind) in fields.items():
        exists,value=read_path(document,path)
        metadata={'present':exists}
        columns[column]=None
        if exists:
            pop_path(extra['data'],path)
            metadata['kind']=type(value).__name__
            if value is None or value=='':
                metadata['blank']=value
            elif kind=='decimal':
                number=Decimal(str(value))
                # Avoid rounding silently in MySQL's fixed-precision columns.
                if not number.is_finite() or abs(number)>=Decimal('1e18') or number.as_tuple().exponent < -12:
                    raise ValueError(f'{path}: exceeds DECIMAL(30,12) storage range')
                columns[column]=number
                if isinstance(value,str):
                    metadata['scale']=max(0,-number.as_tuple().exponent)
                    metadata['width']=len(value.split('.')[0]) if value.isdigit() or '.' in value else 0
                    if value!=format(number,'f'):metadata['literal']=value
            elif kind=='bool':columns[column]=int(bool(value))
            elif kind=='int':columns[column]=int(value)
            elif kind in ('date','datetime'):
                try:
                    columns[column]=date.fromisoformat(str(value)[:10]) if kind=='date' else utc(value)
                    metadata['literal']=value
                except ValueError:metadata['unparsed']=value
            else:columns[column]=value
        extra['shape'][column]=metadata
    for key in collections:
        present=key in document
        extra['collections'][key]={'present':present,'null':document.get(key) is None}
        extra['data'].pop(key,None)
    columns['extension_json']=dumps(extra)
    return columns


def decode(row, fields, collections=None):
    envelope=json.loads(row['extension_json'])
    value=envelope['data']
    for column,(path,kind) in fields.items():
        item=row.get(column)
        shape=envelope['shape'].get(column,{})
        if not shape.get('present') and item is None:continue
        if item is None:
            item=shape.get('unparsed',shape.get('blank'))
        elif kind=='decimal':
            number=Decimal(str(item))
            text=format(number,'f')
            fraction=text.partition('.')[2].rstrip('0')
            scale=max(shape.get('scale',0),len(fraction))
            text=format(number,f'.{scale}f')
            integer,dot,fraction=text.partition('.')
            text=integer.zfill(shape.get('width',0))+(dot+fraction if dot else '')
            if shape.get('literal') and Decimal(shape['literal'])==number:text=shape['literal']
            item=int(number) if shape.get('kind')=='int' else float(number) if shape.get('kind')=='float' else text
        elif kind=='bool':item=bool(item)
        elif kind=='int':item=str(item) if shape.get('kind')=='str' else int(item)
        elif kind=='date':
            item=shape.get('literal') if shape.get('literal') and str(shape['literal'])[:10]==str(item) else str(item)
        elif kind=='datetime':
            original=shape.get('literal')
            item=original if original and utc(original)==item else item.replace(tzinfo=timezone.utc).isoformat()
        write_path(value,path,item)
    for key,items in (collections or {}).items():
        info=envelope.get('collections',{}).get(key,{})
        if info.get('present') or items:
            value[key]=None if info.get('null') and not items else items
    return reorder(value,envelope['order'])
