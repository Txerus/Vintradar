from abc import ABC, abstractmethod
from dataclasses import dataclass
@dataclass(frozen=True)
class ExternalQuote:
    source:str; value:float; currency:str; meta:dict
class PriceSource(ABC):
    @abstractmethod
    async def quote(self, canonical_key:str, condition:str)->ExternalQuote|None: ...
class VintedInternalSource(PriceSource):
    async def quote(self, canonical_key:str, condition:str)->ExternalQuote|None:return None
class BrickLinkSource(PriceSource):
    def __init__(self, enabled:bool):self.enabled=enabled
    async def quote(self, canonical_key:str, condition:str)->ExternalQuote|None:
        if not self.enabled or not canonical_key.startswith("lego:"):return None
        return None
class PriceChartingSource(PriceSource):
    async def quote(self, canonical_key:str, condition:str)->ExternalQuote|None:return None
class EbaySource(PriceSource):
    async def quote(self, canonical_key:str, condition:str)->ExternalQuote|None:return None
class KeepaSource(PriceSource):
    async def quote(self, canonical_key:str, condition:str)->ExternalQuote|None:return None
class BackMarketSource(PriceSource):
    async def quote(self, canonical_key:str, condition:str)->ExternalQuote|None:return None
