"""Extract explicit product metadata only; raw script/CSS tokens are not prices."""
from __future__ import annotations
import json
import re
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from ..domain.ports import AdapterResult, ExtractRequest


class ProductMetadata(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_ld = False
        self.buffer = ''
        self.documents = []
        self.prices = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == 'script' and a.get('type', '').lower() == 'application/ld+json':
            self.in_ld, self.buffer = True, ''
        if tag == 'meta' and (a.get('property') in ('product:price:amount','og:price:amount') or a.get('itemprop') == 'price'):
            self.prices.append((a.get('content'), 'meta product price'))

    def handle_data(self, data):
        if self.in_ld:
            self.buffer += data

    def handle_endtag(self, tag):
        if tag == 'script' and self.in_ld:
            self.in_ld = False
            try:
                self.documents.append(json.loads(self.buffer))
            except (ValueError, TypeError):
                pass


def products(value):
    if isinstance(value, list):
        for item in value:
            yield from products(item)
    elif isinstance(value, dict):
        types = value.get('@type') or []
        if isinstance(types, str):
            types = [types]
        if 'Product' in types:
            yield value
        if '@graph' in value:
            yield from products(value['@graph'])


class RuleExtractor:
    def extract(self, request: ExtractRequest) -> AdapterResult:
        path = Path(request.snapshot_ref)
        if not path.is_file():
            return AdapterResult('failed', error_code='SNAPSHOT_MISSING')
        text = path.read_text(encoding='utf-8', errors='replace')
        parser = ProductMetadata()
        parser.feed(text)
        fields = {}
        title = re.search(r'<title[^>]*>(.*?)</title>', text, re.I | re.S)
        if 'title' in request.field_keys and title:
            fields['title'] = {'value':unescape(re.sub(r'\s+', ' ', title[1])).strip()[:200],
                'locator':'<title>', 'extraction_method':'html_metadata', 'confirmation':'extracted_candidate'}
        observations = []
        for doc in parser.documents:
            for product in products(doc):
                offers = product.get('offers') or []
                if isinstance(offers, dict):
                    offers = [offers]
                for offer in offers:
                    # Do not silently use AggregateOffer lowPrice or a different variant's price.
                    if offer.get('price') is not None:
                        observations.append((str(offer['price']), offer.get('priceCurrency'), 'Product.offers.price'))
        if not observations:
            observations = [(str(p), None, loc) for p, loc in parser.prices if p is not None]
        observations = [x for x in observations if re.fullmatch(r'\d+(?:\.\d{1,2})?', x[0])]
        unique = {(x[0], x[1]) for x in observations}
        if 'display_price' in request.field_keys and len(unique) == 1:
            value, currency, locator = observations[0]
            fields['display_price'] = {'value':value, 'currency':currency, 'locator':locator,
                'extraction_method':'structured_product_metadata', 'confirmation':'extracted_candidate'}
        return AdapterResult('succeeded' if fields else 'needs_review', payload={
            'fields':fields, 'output_schema_version':request.output_schema_version,
            'note':'多个产品价格需人工选择' if len(unique)>1 else '只提取显式产品元数据；无可靠价格时留空'})
