import re
from dataclasses import dataclass
@dataclass(frozen=True)
class Normalized:
    key:str; brand:str|None; model:str|None; flags:set[str]
def normalize(title:str, description:str="")->Normalized:
    text=f"{title} {description}".lower()
    flags={x for x,p in {"LOT":r"\blot\b","PARTS":r"pi[eè]ces?","BROKEN":r"\bhs\b|hors service","SEALED":r"scell[ée]"}.items() if re.search(p,text)}
    lego=re.search(r"\b(?:lego\s*)?(\d{4,6})\b",text)
    if lego:return Normalized(f"lego:{lego.group(1)}","LEGO",lego.group(1),flags)
    iphone=re.search(r"\biphone\s*(\d{1,2}(?:\s*(?:pro|max|plus)){0,2})\b",text)
    if iphone:return Normalized("apple:iphone:"+re.sub(r"\s+","-",iphone.group(1).strip()),"Apple","iPhone "+iphone.group(1).strip(),flags)
    key=re.sub(r"[^a-z0-9]+","-",title.lower()).strip("-")[:120]
    return Normalized(key,None,None,flags)
