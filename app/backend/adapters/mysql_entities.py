"""Entity repositories behind the existing application DTO contract.

Core data is read from typed columns and child rows. extension_json contains
unmodelled data and serialization shape, never an alternate complete product.
"""
from contextlib import nullcontext
from datetime import datetime, timezone
from decimal import Decimal
import json
import hashlib
from pathlib import Path

from ..domain import models, profit_model
from . import relational_codec as codec


def fields(**mapping):
    return {key:(value if isinstance(value,tuple) else (value,'str')) for key,value in mapping.items()}


PRODUCT=fields(product_id='id',title='title',listing_title='listing_title',market_title='market_title',
    material='material',research_market='research_market',market_currency='market_currency',
    mode_assumption='mode_assumption',mode_confirmed=('mode_confirmed','bool'),
    platform_product_id='platform_product_id',internal_decision='internal_decision',
    synthetic=('synthetic','bool'),rationale='rationale',advantage='advantage')
SUPPLIER=fields(supplier_url='url',moq=('moq','int'),lead_days=('lead_days','int'),
    source_ref='source_ref',reference_text='reference',confirmed=('confirmed','bool'))
SKU=fields(merchant_sku='merchant_sku',merchant_group_code='merchant_group_code',
    platform_sku_id='platform_sku_id',platform_skc_id='platform_skc_id',sales_unit='sales_unit',pieces=('pieces','int'),
    supply_amount=('supply_income.amount','decimal'),supply_currency='supply_income.currency',supply_unit='supply_income.sales_unit',
    supply_confirmed=('supply_income.confirmed','bool'),supply_source_ref='supply_income.source_ref')
COST=fields(cost_key='key',amount=('money.amount','decimal'),currency='money.currency',sales_unit='money.sales_unit',
    confirmed=('money.confirmed','bool'),source_ref='money.source_ref')
MEASURE=fields(length_cm=('dimensions.length_cm','decimal'),width_cm=('dimensions.width_cm','decimal'),
    height_cm=('dimensions.height_cm','decimal'),net_weight_g=('weight.net_weight_g','decimal'),gross_weight_g=('weight.gross_weight_g','decimal'))
ATTRIBUTE=fields(attribute_name='name',attribute_value='value',parent_spec_id='parent_spec_id',spec_id='spec_id',source_ref='source_ref')
COMPONENT=fields(component_name='name',quantity=('count','int'),classification='classification')
PLAN=fields(model_version='version',currency='currency',value_basis='value_basis')
PARAMETER=fields(parameter_value=('value','decimal'))
ACTUAL=fields(amount=('amount','decimal'),source_ref='source_ref')
DECISION=fields(decision='decision',reason='reason',reviewer='reviewer',decided_at=('at','datetime'))
SOURCE=fields(source_id='id',title='title',publisher='publisher',url='url',source_level='level',locator='locator',
    verification='verification',observed_on=('observed_at','date'),retrieved_on=('retrieved_at','date'),
    display_price=('facts.display_price','decimal'),currency='facts.currency',pieces=('scope.pieces','int'),
    snapshot_ref='snapshot_ref',sha256='sha256',note='note')
POLICY=fields(policy_id='id',metric='metric',threshold_percent=('threshold_percent','decimal'),confirmed=('confirmed','bool'),
    confirmed_by='confirmed_by',confirmed_on=('confirmed_at','date'),source_ref='source_ref',policy_version='version')
FEEDBACK=fields(feedback_id='id',product_id='candidate_id',sku_ref='sku_ref',platform_stage='platform_stage',verification='verification',
    feedback_on=('feedback_date','date'),feedback_text='feedback_text',evidence_ref='evidence_ref',
    quote_amount=('buyer_supply_income.amount','decimal'),quote_currency='buyer_supply_income.currency',
    quote_unit='buyer_supply_income.sales_unit',quote_confirmed=('buyer_supply_income.confirmed','bool'),quote_source_ref='buyer_supply_income.source_ref')
ROOTS={'candidate':('products','product_id',PRODUCT),'source':('sources','source_id',SOURCE),
       'feedback':('buyer_feedback','feedback_id',FEEDBACK),'policy':('business_policies','policy_id',POLICY)}


class EntityRepositories:
    def _atomic(self):
        return nullcontext() if self._in_transaction else self.transaction()

    def _put(self,table,row,keys):
        self._upsert(table,list(row),list(row.values()),keys,[key for key in row if key not in keys])

    def _row(self,table,keys):
        where=' AND '.join(f'`{key}`=?' for key in keys)
        return self._execute(f'SELECT * FROM `{table}` WHERE {where}',list(keys.values())).fetchone()

    def _children(self,table,product_id,merchant_sku=None,order='position'):
        where='product_id=?';params=[product_id]
        if merchant_sku is not None:where+=' AND merchant_sku=?';params.append(merchant_sku)
        return self._execute(f'SELECT * FROM `{table}` WHERE {where} ORDER BY `{order}`',params).fetchall()

    def _metadata(self,table,key,rid,provided=None):
        if provided:return provided
        old=self._row(table,{key:rid})
        now=models.now_iso()
        return {'created_at':json.loads(old['record_meta_json'])['created_at'] if old else now,'updated_at':now}

    def upsert_record(self,record):
        errors=models.validate_record(record)
        if errors:return errors
        if not record.get('id'):
            if record['record_type']=='policy':record['id']='POLICY-CURRENT'
            else:return ['id: required']
        if record['record_type']=='feedback' and not self._row('products',{'product_id':record['candidate_id']}):
            return ['candidate_id: product not found']
        with self._atomic():self._save_record(record)
        return []

    def _save_record(self,record,metadata=None):
        kind=record['record_type'];table,key,mapping=ROOTS[kind]
        meta=self._metadata(table,key,record['id'],metadata)
        if kind=='candidate':return self._save_product(record,meta)
        row=codec.encode(record,mapping)
        row.update(record_meta_json=codec.dumps(meta),created_at=codec.utc(meta['created_at']),updated_at=codec.utc(meta['updated_at']))
        if kind=='source':row['is_business_record']=1
        if kind=='feedback':
            code=record.get('sku_ref')
            row['linked_sku']=code if code and self._row('product_skus',{'product_id':record['candidate_id'],'merchant_sku':code}) else None
        self._put(table,row,[key])
        if kind=='source':
            self._execute('UPDATE product_evidence SET source_id=? WHERE source_ref=?',(record['id'],record['id']))
            self._execute('UPDATE source_snapshots SET source_id=? WHERE source_ref=?',(record['id'],record['id']))

    def _save_product(self,record,meta):
        pid=record['id']
        row=codec.encode(record,PRODUCT,('skus','supplier','materials','decision_history','evidence_refs'))
        row.update(record_meta_json=codec.dumps(meta),created_at=codec.utc(meta['created_at']),updated_at=codec.utc(meta['updated_at']))
        self._put('products',row,['product_id'])
        for table in ('product_suppliers','product_materials','product_decisions','product_evidence'):
            self._execute(f'DELETE FROM `{table}` WHERE product_id=?',(pid,))
        if record.get('supplier') is not None:
            self._put('product_suppliers',{'product_id':pid,**codec.encode(record['supplier'],SUPPLIER)},['product_id'])
        for key,value in (record.get('materials') or {}).items():
            self._put('product_materials',dict(product_id=pid,material_key=key,registered=bool(value),value_json=codec.dumps(value)),['product_id','material_key'])
        for i,item in enumerate(record.get('decision_history') or []):
            self._put('product_decisions',dict(product_id=pid,position=i,**codec.encode(item,DECISION)),['product_id','position'])
        for i,ref in enumerate(record.get('evidence_refs') or []):
            linked=ref if self._row('sources',{'source_id':ref}) else None
            self._put('product_evidence',dict(product_id=pid,position=i,source_ref=ref,source_id=linked),['product_id','position'])
        self._execute('UPDATE product_skus SET is_active=0 WHERE product_id=?',(pid,))
        for i,sku in enumerate(record['skus']):self._save_sku(pid,sku,i)

    def _save_sku(self,pid,sku,position):
        code=sku['merchant_sku'];keys={'product_id':pid,'merchant_sku':code}
        row=codec.encode(sku,SKU,('costs','specs','sale_spec_bindings','pack_composition','profit_plan'))
        self._put('product_skus',{**keys,**row,'position':position,'is_active':1},list(keys))
        for table in ('sku_measurements','sku_attributes','sku_components','sku_costs','sku_profit_plans'):
            self._execute(f'DELETE FROM `{table}` WHERE product_id=? AND merchant_sku=?',(pid,code))
        for i,cost in enumerate(sku.get('costs') or []):
            self._put('sku_costs',{**keys,**codec.encode(cost,COST),'position':i},[*keys,'cost_key'])
        for table,name,mapping in [('sku_attributes','sale_spec_bindings',ATTRIBUTE),('sku_components','pack_composition',COMPONENT)]:
            for i,item in enumerate(sku.get(name) or []):
                self._put(table,{**keys,**codec.encode(item,mapping),'position':i},[*keys,'position'])
        specs=sku.get('specs')
        if isinstance(specs,dict):
            self._put('sku_measurements',{**keys,'scope':'set',**codec.encode(specs,MEASURE,('item','package'))},[*keys,'scope'])
            for scope in ('item','package'):
                if isinstance(specs.get(scope),dict):
                    self._put('sku_measurements',{**keys,'scope':scope,**codec.encode(specs[scope],MEASURE)},[*keys,'scope'])
        plan=sku.get('profit_plan')
        if isinstance(plan,dict):
            self._put('sku_profit_plans',{**keys,**codec.encode(plan,PLAN,('inputs','actual_costs'))},list(keys))
            version=plan.get('version') or profit_model.VERSION
            for key,value in (plan.get('inputs') or {}).items():
                self._put('sku_profit_parameters',{**keys,'model_version':version,'parameter_key':key,**codec.encode({'value':value},PARAMETER)},[*keys,'parameter_key'])
            for key,value in (plan.get('actual_costs') or {}).items():
                self._put('sku_actual_costs',{**keys,'cost_key':key,**codec.encode(value,ACTUAL)},[*keys,'cost_key'])
        self._execute('UPDATE buyer_feedback SET linked_sku=? WHERE product_id=? AND sku_ref=?',(code,pid,code))

    def record_metadata(self,kind,rid):
        table,key,_=ROOTS[kind];row=self._row(table,{key:rid})
        return json.loads(row['record_meta_json']) if row else {}

    def get_record(self,kind,rid):
        with self._atomic():
            table,key,mapping=ROOTS[kind];row=self._row(table,{key:rid})
            if not row or (kind=='source' and not row['is_business_record']):return None
            if kind!='candidate':return codec.decode(row,mapping)
            return self._product(row)

    def list_records(self,kind,candidate_id=None):
        table,key,mapping=ROOTS[kind]
        where=' WHERE is_business_record=1' if kind=='source' else ''
        params=[]
        if candidate_id:
            if kind!='feedback':return []
            where=' WHERE product_id=?';params=[candidate_id]
        with self._atomic():
            rows=self._execute(f'SELECT * FROM `{table}`{where} ORDER BY updated_at DESC,`{key}`',params).fetchall()
            return [self._product(row) if kind=='candidate' else codec.decode(row,mapping) for row in rows]

    def _product(self,row):
        pid=row['product_id'];supplier=self._row('product_suppliers',{'product_id':pid})
        skus=[self._sku(s) for s in self._children('product_skus',pid) if s['is_active']]
        materials={v['material_key']:json.loads(v['value_json']) for v in self._children('product_materials',pid,order='material_key')}
        decisions=[codec.decode(v,DECISION) for v in self._children('product_decisions',pid)]
        sources=[v['source_ref'] for v in self._children('product_evidence',pid)]
        return codec.decode(row,PRODUCT,dict(skus=skus,supplier=codec.decode(supplier,SUPPLIER) if supplier else {},
                                            materials=materials,decision_history=decisions,evidence_refs=sources))

    def _sku(self,row):
        pid,code=row['product_id'],row['merchant_sku'];keys={'product_id':pid,'merchant_sku':code}
        measures={v['scope']:v for v in self._children('sku_measurements',pid,code,order='scope')}
        specs={}
        if 'set' in measures:
            specs=codec.decode(measures['set'],MEASURE,{scope:codec.decode(measures[scope],MEASURE) if scope in measures else {} for scope in ('item','package')})
        planrow=self._row('sku_profit_plans',keys);plan={}
        if planrow:
            params={v['parameter_key']:codec.decode(v,PARAMETER)['value'] for v in self._children('sku_profit_parameters',pid,code,order='parameter_key')}
            actual={v['cost_key']:codec.decode(v,ACTUAL) for v in self._children('sku_actual_costs',pid,code,order='cost_key')}
            plan=codec.decode(planrow,PLAN,dict(inputs=params,actual_costs=actual))
        return codec.decode(row,SKU,dict(costs=[codec.decode(v,COST) for v in self._children('sku_costs',pid,code)],
            specs=specs,profit_plan=plan,
            sale_spec_bindings=[codec.decode(v,ATTRIBUTE) for v in self._children('sku_attributes',pid,code)],
            pack_composition=[codec.decode(v,COMPONENT) for v in self._children('sku_components',pid,code)]))

    def add_revision(self,candidate_id,sku_ref,field_key,before,after,reviewer,method):
        payload=dict(id=models.new_id('REV'),candidate_id=candidate_id,sku_ref=sku_ref,field_key=field_key,
                     before=before,after=after,reviewer=reviewer,extraction_method=method)
        self._save_revision(dict(id=payload['id'],candidate_id=candidate_id,sku_ref=sku_ref,field_key=field_key,
                                 payload=codec.dumps(payload),created_at=models.now_iso()))

    def _save_revision(self,row):
        data=json.loads(row['payload'])
        self._put('field_revisions',dict(revision_id=row['id'],product_id=row['candidate_id'],sku_ref=row['sku_ref'],field_key=row['field_key'],
            before_json=codec.dumps(data.get('before')),after_json=codec.dumps(data.get('after')),reviewer=data.get('reviewer'),
            method=data.get('extraction_method'),payload_json=row['payload'],created_at=codec.utc(row['created_at']),original_at=row['created_at']),['revision_id'])

    def revision_history(self,candidate_id):
        rows=self._execute('SELECT * FROM field_revisions WHERE product_id=? ORDER BY created_at,revision_id',(candidate_id,)).fetchall()
        return [dict(json.loads(r['payload_json']),created_at=r['original_at']) for r in rows]

    def save_submission(self,submission):
        with self._atomic():
            existing=self._row('internal_submissions',{'submission_id':submission['id']})
            if existing:
                if json.loads(existing['snapshot_json'])!=submission:raise ValueError('Historical submission ID cannot be overwritten')
                return
            self._put('internal_submissions',dict(submission_id=submission['id'],product_id=submission['candidate_id'],
                title=submission.get('title'),research_market=submission.get('research_market'),created_at=codec.utc(submission['created_at']),
                original_at=submission['created_at'],snapshot_json=codec.dumps(submission)),['submission_id'])

    def list_submissions(self,candidate_id=None):
        where=' WHERE product_id=?' if candidate_id else ''
        rows=self._execute('SELECT snapshot_json FROM internal_submissions'+where+' ORDER BY created_at DESC',
                           [candidate_id] if candidate_id else []).fetchall()
        return [json.loads(r['snapshot_json']) for r in rows]

    def set_adapter_status(self,port_key,status,detail):
        now=models.now_iso()
        self._put('integration_status',dict(port_key=port_key,status=status,detail_json=codec.dumps(detail),updated_at=codec.utc(now),original_at=now),['port_key'])

    def adapter_statuses(self):
        return {r['port_key']:dict(status=r['status'],detail=json.loads(r['detail_json']),updated_at=r['original_at'])
                for r in self._execute('SELECT * FROM integration_status').fetchall()}

    def save_snapshot(self,source_id,snapshot_ref,sha256,file_path,status,payload):
        now=models.now_iso()
        self._save_snapshot(dict(source_id=source_id,snapshot_ref=snapshot_ref,sha256=sha256,file_path=file_path,
                                  status=status,payload=codec.dumps(payload),captured_at=now))

    def _save_snapshot(self,r):
        linked=r['source_id'] if self._row('sources',{'source_id':r['source_id']}) else None
        path=Path(r['file_path']) if r.get('file_path') else None
        exists=path.is_file() if path else None
        verified=hashlib.sha256(path.read_bytes()).hexdigest()==r['sha256'] if exists and r.get('sha256') else None
        self._put('source_snapshots',dict(source_ref=r['source_id'],source_id=linked,snapshot_ref=r['snapshot_ref'],
            sha256=r['sha256'],file_path=r['file_path'],status=r['status'],captured_at=codec.utc(r['captured_at']),
            original_at=r['captured_at'],payload_json=r['payload'],file_exists=exists,hash_verified=verified),['source_ref'])

    def get_snapshot(self,source_id):
        row=self._row('source_snapshots',{'source_ref':source_id})
        return dict(json.loads(row['payload_json']),status=row['status'],captured_at=row['original_at']) if row else None

    def ensure_reference_sources(self,entries):
        with self._atomic():
            for entry in entries:
                row=self._row('sources',{'source_id':entry['id']})
                if row and row.get('registry_json'):continue
                if row:
                    self._execute('UPDATE sources SET registry_json=? WHERE source_id=?',(codec.dumps(entry),entry['id']))
                else:
                    now=models.now_iso();columns=codec.encode(entry,SOURCE)
                    columns.update(is_business_record=0,registry_json=codec.dumps(entry),record_meta_json=codec.dumps({'created_at':now,'updated_at':now}),
                                   created_at=codec.utc(now),updated_at=codec.utc(now))
                    self._put('sources',columns,['source_id'])
                    self._execute('UPDATE product_evidence SET source_id=? WHERE source_ref=?',(entry['id'],entry['id']))

    def reference_sources(self):
        return [json.loads(row['registry_json']) for row in self._execute('SELECT registry_json FROM sources WHERE registry_json IS NOT NULL ORDER BY source_id').fetchall()]

    def ensure_parameter_definitions(self):
        for definition in profit_model.SCHEMA:
            row=dict(model_version=profit_model.VERSION,parameter_key=definition['key'],label=definition['label'],
                cost_group=definition['group'],unit=definition['unit'],default_value=Decimal(definition['default']),
                category_source_ref=definition['source_id'],value_source_ref=definition['value_source_id'],note=definition['note'])
            self._put('profit_parameter_definitions',row,['model_version','parameter_key'])

    def validate_parameter_definitions(self):
        definitions=self._execute('SELECT parameter_key,default_value FROM profit_parameter_definitions WHERE model_version=?',(profit_model.VERSION,)).fetchall()
        stored={r['parameter_key']:r['default_value'] for r in definitions}
        expected={key:Decimal(value) for key,value in profit_model.DEFAULTS.items()}
        if stored!=expected:
            raise RuntimeError('数据库参数字典与已发布模型版本不一致；请恢复字典或发布新版本，不会静默计算。')
