"""Versioned MySQL entity schema. DDL is never treated as rollbackable DML."""
from pathlib import Path
import hashlib

VERSION='20261126-relational-v2'
ROOT=Path(__file__).resolve().parents[3]
DDL_PATH=ROOT/'database/migrations/002_relational_entities.sql'


def statements():
    text=DDL_PATH.read_text(encoding='utf-8')
    return [part.strip() for part in text.split(';') if part.strip()]


def checksum():
    # Git's Windows checkout may use CRLF. The same migration must have one
    # checksum on Windows and Linux, while substantive changes still fail.
    return hashlib.sha256(DDL_PATH.read_text(encoding='utf-8').encode('utf-8')).hexdigest()


# Parents first: insert in this order, delete in reverse. Never disable FKs.
TABLES=(
    'sources','products','product_suppliers','product_materials','product_decisions',
    'product_skus','sku_measurements','sku_attributes','sku_components','sku_costs',
    'profit_parameter_definitions','sku_profit_plans','sku_profit_parameters','sku_actual_costs',
    'product_evidence','buyer_feedback','business_policies','source_snapshots',
    'field_revisions','internal_submissions','integration_status',
)
PRIMARY={
    'sources':('source_id',),'products':('product_id',),'product_suppliers':('product_id',),
    'product_materials':('product_id','material_key'),'product_decisions':('product_id','position'),
    'product_skus':('product_id','merchant_sku'),'sku_measurements':('product_id','merchant_sku','scope'),
    'sku_attributes':('product_id','merchant_sku','position'),'sku_components':('product_id','merchant_sku','position'),
    'sku_costs':('product_id','merchant_sku','cost_key'),
    'profit_parameter_definitions':('model_version','parameter_key'),
    'sku_profit_plans':('product_id','merchant_sku'),
    'sku_profit_parameters':('product_id','merchant_sku','parameter_key'),
    'sku_actual_costs':('product_id','merchant_sku','cost_key'),
    'product_evidence':('product_id','position'),'buyer_feedback':('feedback_id',),
    'business_policies':('policy_id',),'source_snapshots':('source_ref',),
    'field_revisions':('revision_id',),'internal_submissions':('submission_id',),
    'integration_status':('port_key',),
}
