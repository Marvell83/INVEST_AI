import unittest
from moduller_v02 import vergi_defteri,marj_yolu,roiic_tanisi,tum_kokler

class TestV02(unittest.TestCase):
    def test_tangent(self): self.assertAlmostEqual(tum_kokler(lambda x:(x-2)**2,0,4)[0],2,6)
    def test_nearby(self):
        roots=tum_kokler(lambda x:(x-1)*(x-1.001),.9,1.1)
        self.assertEqual(len(roots),2)
        self.assertAlmostEqual(roots[0],1,5);self.assertAlmostEqual(roots[1],1.001,5)
    def test_multiple(self): self.assertEqual(len(tum_kokler(lambda x:x*x-4,-3,3)),2)
    def test_no_root(self): self.assertEqual(tum_kokler(lambda x:x*x+1,-3,3),[])
    def test_nol(self):
        x=vergi_defteri([-100,60,80],.25)
        self.assertEqual([r['nakit_vergi'] for r in x],[0,0,10])
        self.assertEqual(x[-1]['kalan_zarar'],0)
    def test_margin(self): self.assertAlmostEqual(marj_yolu(.1,.2,.5,2),.175)
    def test_roiic(self): self.assertEqual(roiic_tanisi([10,20,30],[50,0]),[.2,None])
if __name__=='__main__': unittest.main()
