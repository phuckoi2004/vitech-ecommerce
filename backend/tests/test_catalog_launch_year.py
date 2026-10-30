import copy
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from add_catalog_launch_year import KEY, GuardError, make_plan, validate_transition
from audit_catalog_specs import digest


def snapshot():
    product = {'ProductId':'p1', 'Name':'Speaker Generation 2', 'Slug':'speaker-gen-2',
        'Specifications':{'Pin':'20 giờ','_vietech_variant_media':{'Variants':{'v1':{'ImageUrls':['/a.jpg']}}}},
        'Description':'<p>Mô tả và ảnh hiện có.</p>', 'UpdatedAt':'2026-10-30T10:00:00+07:00'}
    tables = {'Products':[product], 'ProductVariants':[{'ProductVariantId':'v1','Sku':'EXACT-SKU','Price':'100','StockQuantity':4}],
              'Categories':[], 'Brands':[], 'ProductImages':[]}
    return {'Source':'configured_postgresql_live_select','ReadOnly':True, 'Tables':tables,
        'Counts':{name:len(rows) for name,rows in tables.items()},'CatalogFingerprint':digest(tables),
        'SchemaFingerprint':'schema','ProtectedCostFingerprint':'cost'}


def evidence():
    return {'Operation':'add_launch_year','ReviewedAt':'2026-10-30','Products':[{
        'ProductId':'p1','Name':'Speaker Generation 2','Year':'2024','ModelMatch':'Exact generation 2',
        'Scope':'Giới thiệu dòng sản phẩm','Basis':'Thông báo của hãng giới thiệu thế hệ này năm 2024',
        'Sources':['https://www.bose.com/pressroom/launch']} ]}


def refresh(snap):
    snap['CatalogFingerprint'] = digest(snap['Tables'])
    return snap


def transition():
    before = snapshot()
    records = make_plan(before,evidence())['Records']
    after = copy.deepcopy(before)
    after['Tables']['Products'][0]['Specifications'] = copy.deepcopy(records[0]['AfterSpecs'])
    after['Tables']['Products'][0]['UpdatedAt'] = '2026-10-30T10:01:00+07:00'
    return before, after, records


def test_adds_only_year_and_preserves_private_media_and_original_snapshot():
    original = snapshot()
    saved = copy.deepcopy(original)
    plan = make_plan(original,evidence())
    assert plan['Records'][0]['AfterSpecs'] == {**saved['Tables']['Products'][0]['Specifications'],KEY:'2024'}
    assert original == saved
    before, after, records = transition()
    assert validate_transition(before,after,records)['OnlyLaunchYearAdded']


@pytest.mark.parametrize('key,value',[('Thời điểm ra mắt','09/2024'),('Ngày ra mắt','2024-09-18'),(KEY,'2024')])
def test_does_not_duplicate_or_rewrite_existing_launch_dates(key,value):
    snap=snapshot()
    snap['Tables']['Products'][0]['Specifications'][key] = value
    result=make_plan(refresh(snap),evidence())
    assert result['Records'] == [] and result['RetainedProductIds'] == ['p1']


def test_conflicting_date_or_unreviewed_existing_placeholder_cannot_be_overwritten():
    for key,value in [('Thời điểm ra mắt','2023'),(KEY,'Đang cập nhật')]:
        snap=snapshot()
        snap['Tables']['Products'][0]['Specifications'][key]=value
        with pytest.raises(GuardError):
            make_plan(refresh(snap),evidence())


@pytest.mark.parametrize('field,value',[
    ('Year',2024),('Year','2027'),('Year','2024, có thể 2023'),('Year','2024; DROP TABLE'),
    ('Name','Other generation'),('Scope',''),('ModelMatch',''),('Basis',''),
    ('Sources',[]),('Sources',['https://bose.com.attacker.invalid/launch']),
    ('Sources',['http://www.bose.com/launch']),('Sources',['https://secret@www.bose.com/launch']),
])
def test_unverified_or_invalid_evidence_is_refused(field,value):
    review=evidence()
    review['Products'][0][field]=value
    with pytest.raises(GuardError):
        make_plan(snapshot(),review)


def test_duplicate_evidence_cannot_update_a_product_twice():
    review=evidence()
    review['Products']*=2
    with pytest.raises(GuardError):
        make_plan(snapshot(),review)


def test_reviewed_catalog_sources_are_supported_and_coverage_groups_do_not_overlap():
    path=Path(__file__).resolve().parents[1]/'data/catalog-launch-year-evidence-2026-10-30.json'
    review=json.loads(path.read_text(encoding='utf-8'))
    groups=[{p['ProductId'] for p in review[key]} for key in ('Products','ExistingDatesRetained','Unresolved')]
    assert not groups[0]&groups[1] and not groups[0]&groups[2] and not groups[1]&groups[2]
    snap=snapshot()
    template=snap['Tables']['Products'][0]
    snap['Tables']['Products']=[{**copy.deepcopy(template),'ProductId':p['ProductId'],'Name':p['Name'],
                                'Slug':'product-'+p['ProductId']} for p in review['Products']]
    snap['Counts']['Products']=len(review['Products'])
    plan=make_plan(refresh(snap),review)
    assert len(plan['Records'])==len(review['Products'])


@pytest.mark.parametrize('tamper', ['battery','media','description','variant','count','schema','cost','other_key','missing'])
def test_post_update_guard_rejects_any_extra_change(tamper):
    before,after,records=transition()
    row=after['Tables']['Products'][0]
    if tamper=='battery': row['Specifications']['Pin']='25 giờ'
    elif tamper=='media': row['Specifications']['_vietech_variant_media']['Variants'].clear()
    elif tamper=='description': row['Description']='changed'
    elif tamper=='variant': after['Tables']['ProductVariants'][0]['Price']='1'
    elif tamper=='count': after['Counts']['Products']=2
    elif tamper=='schema': after['SchemaFingerprint']='changed'
    elif tamper=='cost': after['ProtectedCostFingerprint']='changed'
    elif tamper=='other_key':
        row['Specifications']['Extra']='value'
        records[0]['AfterSpecs']['Extra']='value'
    elif tamper=='missing': after['Tables']['Products']=[]
    with pytest.raises(GuardError):
        validate_transition(before,after,records)
