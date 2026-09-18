from app.normalizer import normalize
from app.pricing import robust_score
from app.worker import allowed
class A: include_terms=["technic","concorde"];exclude_terms=["lot"]
def test_lego_normalization():
    n=normalize("LEGO Technic 42146 neuf scellé");assert n.key=="lego:42146" and "SEALED" in n.flags
def test_scoring():
    s=robust_score(10,[10,20,30,40,50,60,1000]);assert s and s.label=="DEAL" and s.median<100
def test_filters():
    assert allowed({"title":"LEGO Concorde"},A());assert not allowed({"title":"lot LEGO Concorde"},A())
