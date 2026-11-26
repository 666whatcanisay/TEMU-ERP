import unittest
from app.backend.adapters import relational_codec as codec


class RelationalCodecTests(unittest.TestCase):
    def test_unknown_null_blank_order_and_decimal_wire_format_survive(self):
        original={'unknown':{'kept':[1,{'id':'12345678901234567890'}]},'money':{'amount':'0008.40','blank':'','null':None},'list':[{'a':1}],'flag':False}
        fields={'amount':('money.amount','decimal'),'blank':('money.blank','decimal'),'null':('money.null','decimal'),
                'flag':('flag','bool'),'missing':('missing','decimal')}
        encoded=codec.encode(original,fields,('list',))
        self.assertNotIn('amount',__import__('json').loads(encoded['extension_json'])['data']['money'])
        decoded=codec.decode(encoded,fields,{'list':original['list']})
        self.assertEqual(codec.dumps(decoded),codec.dumps(original))
        encoded['amount']=__import__('decimal').Decimal('9.125000000000')
        self.assertEqual(codec.decode(encoded,fields,{'list':[]})['money']['amount'],'0009.125')

    def test_datetime_is_utc_in_sql_and_retains_original_offset_in_dto(self):
        doc={'when':'2026-11-26T12:15:01+08:00'}
        mapping={'when':('when','datetime')};row=codec.encode(doc,mapping)
        self.assertEqual(row['when'].hour,4)
        self.assertEqual(codec.decode(row,mapping),doc)

    def test_out_of_precision_range_is_rejected_without_rounding(self):
        for value in ['0.1234567890123','1000000000000000000']:
            with self.assertRaisesRegex(ValueError,'storage range'):
                codec.encode({'value':value},{'value':('value','decimal')})

    def test_valid_noncanonical_numeric_text_is_preserved(self):
        for text in ['.5','+1','5.','0003.50','1E-3']:
            mapping={'value':('value','decimal')};row=codec.encode({'value':text},mapping)
            self.assertEqual(codec.decode(row,mapping),{'value':text})
