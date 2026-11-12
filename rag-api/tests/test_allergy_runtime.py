"""Ollama 없이 신규 모듈 연결 기본 검증: python -m unittest discover -s tests -p test_allergy_runtime.py"""
import csv
from pathlib import Path
import tempfile
import unittest
from allergy.service import AllergyService, attach_allergy_to_top3

class FakeClient:
    def __init__(self): self.calls = 0
    def predict(self, allergies, products, rag_context):
        self.calls += 1
        assert rag_context["알레르기별_검색결과"]
        return {str(p["product_id"]): (i == 0) for i, p in enumerate(products)}

class AllergyIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        d = Path(self.temp.name)
        self.db=d/'allergy.csv'
        self.db.write_text("알레르기명,동의어,구분,관련성분명,관계\n리날룰,Linalool,접촉,리날룰,직접 동일 성분\n",encoding='utf-8-sig')
        self.csv=d/'products.csv'
        # 쉼표를 포함한 CSV는 CSV writer로 다시 작성
        with self.csv.open('w',encoding='utf-8-sig',newline='') as f:
            w=csv.DictWriter(f, fieldnames=['product_id','name_clean','ingredients']); w.writeheader()
            for i,ingredients in [(101,'정제수, 리날룰'),(102,'정제수, 글리세린'),(103,'정제수, 향료')]:
                w.writerow(dict(product_id=i,name_clean=f'샴푸{i}',ingredients=ingredients))
        self.fake=FakeClient()
        self.service=AllergyService(db_path=self.db,products_path=self.csv,client=self.fake)
    def tearDown(self): self.temp.cleanup()

    def test_adds_flags_without_reordering(self):
        top3=[{'rank':i+1,'product_id':str(101+i),'reason':'기존설명'} for i in range(3)]
        attach_allergy_to_top3(top3,['리날룰'],self.service)
        self.assertEqual([r['rank'] for r in top3],[1,2,3])
        self.assertEqual([r['allergy_risk'] for r in top3],[True,False,False])
        self.assertEqual(self.fake.calls,1)
    def test_skip_when_no_allergies(self):
        top3=[{'product_id':'101'}]
        attach_allergy_to_top3(top3,[],self.service)
        self.assertIsNone(top3[0]['allergy_risk'])
        self.assertEqual(self.fake.calls,0)
    def test_unknown_allergy_returns_null(self):
        top3=[{'product_id':'101'}]
        attach_allergy_to_top3(top3,['미등록성분'],self.service)
        self.assertIsNone(top3[0]['allergy_risk'])
        self.assertEqual(self.fake.calls,0)
    def test_preserves_null_on_client_error(self):
        self.fake.predict=lambda *args,**kwargs: (_ for _ in ()).throw(RuntimeError('offline'))
        top3=[{'product_id':'101'}]
        attach_allergy_to_top3(top3,['리날룰'],self.service)
        self.assertIsNone(top3[0]['allergy_risk'])

if __name__=='__main__': unittest.main()
