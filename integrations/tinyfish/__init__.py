"""TinyFish supplier research (optional stage).

Public surface:

* :class:`TinyFishClient` — thin REST client for the free Search and Fetch APIs
* :func:`extract_facts` — deterministic extraction of supplier facts from text
* :mod:`source_validation` — decide whether a page is worth fetching/parsing

Deliberately excludes the metered Agent and Browser APIs: supplier research must
stay inside TinyFish's free daily allowance.
"""

from __future__ import annotations

from integrations.tinyfish.client import PROVIDER, TinyFishClient
from integrations.tinyfish.parser import extract_facts
from integrations.tinyfish.schemas import CandidateFact, FetchedPage, SearchHit

__all__ = [
    "PROVIDER",
    "CandidateFact",
    "FetchedPage",
    "SearchHit",
    "TinyFishClient",
    "extract_facts",
]