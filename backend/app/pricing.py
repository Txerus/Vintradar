from dataclasses import dataclass
from statistics import median
@dataclass(frozen=True)
class Score:
    label:str; percentile:float; median:float; count:int; confidence:str
def robust_score(price:float, values:list[float])->Score|None:
    xs=sorted(v for v in values if v>0)
    if len(xs)<3:return None
    q1=xs[len(xs)//4]; q3=xs[(3*len(xs))//4]; iqr=q3-q1
    clean=[v for v in xs if q1-1.5*iqr<=v<=q3+1.5*iqr] or xs
    pct=sum(v<=price for v in clean)/len(clean)
    label="DEAL" if pct<=.20 else "GOOD" if pct<.50 else "NORMAL" if pct<=.75 else "EXPENSIVE"
    confidence="HIGH" if len(clean)>=30 else "MEDIUM" if len(clean)>=10 else "LOW"
    return Score(label,pct,median(clean),len(clean),confidence)
