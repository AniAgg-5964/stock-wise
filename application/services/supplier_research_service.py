"""StockWise — supplier research service (optional TinyFish stage).

Orchestrates web research for suppliers. It is the *only* place that may call
TinyFish: UI event handlers never talk to the network.

Two jobs, in priority order:

1. **Find suppliers.** A search result is a page, not a company, so the useful
   output is a candidate the user can turn into a real supplier record. This does
   not depend on the page being fetchable, which matters because most Indian B2B
   marketplaces refuse automated fetches outright.
2. **Extract facts** where possible. Every fact is stored as a *candidate*;
   nothing reaches ``product_suppliers`` until the user verifies and applies it.

Safety rules enforced here:

* research is **opt-in** (a stored setting, off by default)
* a missing API key is reported, never crashes the app
* blocked/thin pages are reported and skipped, never guessed at
* every fetch is capped, so a stray loop cannot burn the free daily allowance
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Optional, Sequence

from app.config import Config
from domain.entities import ExternalSource, ProductSupplier, Supplier, SupplierObservation
from domain.exceptions import (
    DuplicateSupplierError,
    NotFoundError,
    ResearchNotConfiguredError,
    TinyFishError,
    ValidationError,
)
from domain.money import to_money
from integrations.tinyfish import parser as fact_parser
from integrations.tinyfish.client import PROVIDER
from integrations.tinyfish.source_validation import (
    FAILED_HOST_LOOKBACK_DAYS,
    host_of,
    is_known_bot_hostile,
    screen_text,
    validate_url,
)

logger = logging.getLogger(__name__)

SETTING_ENABLED = "supplier_research_enabled"

#: Hard ceiling on pages fetched by a single research action.
MAX_FETCHES_PER_ACTION = 5

#: observation field -> product_suppliers attribute
_APPLICABLE_FIELDS = {
    fact_parser.FIELD_UNIT_COST: "unit_cost",
    fact_parser.FIELD_MOQ: "minimum_order_qty",
    fact_parser.FIELD_PACK_SIZE: "pack_size",
    fact_parser.FIELD_LEAD_TIME: "lead_time_days",
}

FIELD_LABELS = {
    fact_parser.FIELD_UNIT_COST: "Unit cost",
    fact_parser.FIELD_MOQ: "Minimum order qty",
    fact_parser.FIELD_PACK_SIZE: "Pack size",
    fact_parser.FIELD_LEAD_TIME: "Lead time (days)",
}


@dataclass(frozen=True)
class ResearchStatus:
    """Whether research can run, and if not, exactly why."""

    enabled: bool
    configured: bool
    reason: str | None = None

    @property
    def can_run(self) -> bool:
        return self.enabled and self.configured


@dataclass
class SourceCandidate:
    """A search result worth looking at.

    ``block_reason`` is advisory: it says a fetch probably will not work, but the
    user can always try anyway. It exists so a batch action does not waste its
    budget and so the user is not surprised.
    """

    url: str
    title: str = ""
    snippet: str = ""
    site_name: str = ""
    source_id: int | None = None
    cached: bool = False
    host: str = ""
    block_reason: str | None = None
    #: Set when this candidate's website is already a saved supplier.
    supplier_id: int | None = None

    @property
    def likely_blocked(self) -> bool:
        return self.block_reason is not None

    @property
    def already_saved(self) -> bool:
        return self.supplier_id is not None


@dataclass
class ResearchResult:
    """Outcome of fetching and parsing one or more sources."""

    sources: list[ExternalSource] = field(default_factory=list)
    observations: list[SupplierObservation] = field(default_factory=list)
    cached: bool = False
    skipped: list[str] = field(default_factory=list)


@dataclass
class SupplierDraft:
    """A proposed supplier record, not yet saved.

    ``name`` is a *guess* from the website domain. A search result's title
    describes a product rather than a company, so this must always be presented
    as an editable suggestion.
    """

    name: str
    website_url: str
    notes: str
    existing_supplier: Optional[Supplier] = None

    @property
    def already_saved(self) -> bool:
        return self.existing_supplier is not None


def _now() -> str:
    """SQLite's datetime('now') format, so timestamps compare consistently."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class SupplierResearchService:
    def __init__(
        self,
        sources,
        observations,
        suppliers,
        products,
        audit,
        settings,
        client,
        *,
        supplier_service=None,
        cache_minutes: int | None = None,
        max_fetches_per_action: int | None = None,
    ) -> None:
        self.sources = sources
        self.observations = observations
        self.suppliers = suppliers
        self.products = products
        self.audit = audit
        self.settings = settings
        self.client = client
        self.supplier_service = supplier_service
        self.cache_minutes = (
            Config.TINYFISH_CACHE_MINUTES if cache_minutes is None else int(cache_minutes)
        )
        self.max_fetches_per_action = max(
            1,
            int(Config.TINYFISH_MAX_FETCHES_PER_ACTION
                if max_fetches_per_action is None else max_fetches_per_action),
        )

    # ------------------------------------------------------------- lifecycle
    def status(self) -> ResearchStatus:
        enabled = self.is_enabled()
        configured = bool(getattr(self.client, "is_configured", False))
        if not configured:
            reason = "No API key. Add TINYFISH_API_KEY to your .env file and restart."
        elif not enabled:
            reason = "Live research is switched off. Turn it on to use the web."
        else:
            reason = None
        return ResearchStatus(enabled=enabled, configured=configured, reason=reason)

    def is_enabled(self) -> bool:
        raw = str(self.settings.get(SETTING_ENABLED, "") or "").strip().lower()
        if not raw:
            return Config.DEFAULT_SUPPLIER_RESEARCH_ENABLED
        return raw in ("1", "true", "yes", "on")

    def set_enabled(self, enabled: bool, actor: str = "user") -> None:
        self.settings.set(SETTING_ENABLED, "1" if enabled else "0")
        self.audit.record_event(
            "supplier_research_toggled", "settings", None, {"enabled": bool(enabled)}, actor
        )

    # ---------------------------------------------------------------- search
    def search(
        self,
        *,
        product_id: int | None = None,
        query: str | None = None,
        limit: int = 10,
    ) -> list[SourceCandidate]:
        """Find candidate supplier pages for a product (or a free-text query).

        Candidates are annotated with whether their site is likely to refuse a
        fetch and whether they are already a saved supplier, so the UI can warn
        and offer the right action without spending a fetch to find out.
        """
        self._guard()
        query = (query or self.build_query(product_id)).strip()
        if not query:
            raise ValidationError("query", "Enter something to search for")

        hits = self.client.search(query, limit=limit)
        failed_hosts = self._hosts_that_failed_before()
        candidates: list[SourceCandidate] = []
        for hit in hits:
            url = validate_url(hit.url)
            if not url:
                logger.info("Skipping unfetchable research URL: %s", hit.url)
                continue
            source = self.sources.create(ExternalSource(
                provider=PROVIDER, url=url, query=query, parse_status="discovered",
            ))
            host = host_of(url)
            existing = self.find_supplier_for_url(url)
            candidates.append(SourceCandidate(
                url=url, title=hit.title, snippet=hit.snippet,
                site_name=hit.site_name or host, source_id=source.id, host=host,
                block_reason=_block_reason(host, failed_hosts),
                supplier_id=existing.id if existing else None,
            ))
        return candidates

    def build_query(self, product_id: int | None) -> str:
        """Compose a search query from real product data (no fabrication)."""
        if product_id is None:
            return ""
        product = self.products.get_by_id(product_id)
        if product is None:
            raise NotFoundError("Product", product_id)
        parts = [product.name]
        if product.brand:
            parts.insert(0, product.brand)
        query = " ".join(p for p in parts if p).strip()
        return f"{query} wholesale supplier price MOQ India"

    # ------------------------------------------------------- supplier records
    def find_supplier_for_url(self, url: str | None) -> Optional[Supplier]:
        """An existing supplier on the same website, matched by host.

        Matching on host rather than exact URL because supplier websites are
        hand-typed: they arrive as ``indiamart.com`` as often as
        ``https://www.indiamart.com/``. Scanning the (small) supplier list keeps
        the comparison tolerant of every such variation.
        """
        host = host_of(url)
        if not host or self.supplier_service is None:
            return None
        for supplier in self.supplier_service.list_suppliers(active_only=False):
            if host_of(supplier.website_url) == host:
                return supplier
        return None

    def draft_supplier(self, candidate: SourceCandidate, *, query: str | None = None) -> SupplierDraft:
        """Build — but do not save — a supplier record from a search candidate."""
        return SupplierDraft(
            name=_name_guess_from_host(candidate.host or host_of(candidate.url)),
            website_url=candidate.url,
            notes=_provenance_notes(candidate, query),
            existing_supplier=self.find_supplier_for_url(candidate.url),
        )

    def add_supplier_from_candidate(
        self,
        draft: SupplierDraft,
        *,
        actor: str = "user",
        force: bool = False,
    ) -> Supplier:
        """Save a researched candidate as a supplier record.

        A duplicate website is refused so the supplier list stays trustworthy.
        ``force`` exists for a genuine second branch of the same company.
        """
        if self.supplier_service is None:
            raise TinyFishError("Supplier records are not available in this context")

        name = (draft.name or "").strip()
        if not name:
            raise ValidationError("name", "Give the supplier a name")

        existing = self.find_supplier_for_url(draft.website_url)
        if existing is not None and not force:
            raise DuplicateSupplierError(
                "website_url",
                f"'{existing.name}' is already saved with this website",
                existing_id=existing.id,
                existing_name=existing.name,
            )

        supplier = self.supplier_service.create_supplier(
            Supplier(
                name=name,
                website_url=(draft.website_url or "").strip() or None,
                notes=draft.notes,
            ),
            actor=actor,
        )
        self.audit.record_event(
            "supplier_added_from_research", "supplier", supplier.id,
            {"name": supplier.name, "website": supplier.website_url}, actor,
        )
        return supplier

    # --------------------------------------------------------------- research
    def research(
        self,
        *,
        url: str,
        product_id: int | None = None,
        supplier_id: int | None = None,
        query: str | None = None,
    ) -> ResearchResult:
        """Fetch one page and extract candidate facts. Cached within the window."""
        return self.research_many(
            [url], product_id=product_id, supplier_id=supplier_id, query=query
        )

    def research_candidates(
        self,
        candidates: Sequence[SourceCandidate],
        *,
        product_id: int | None = None,
        query: str | None = None,
        skip_blocked: bool = True,
    ) -> ResearchResult:
        """Research a batch of candidates in one capped action.

        With ``skip_blocked`` the sites flagged as likely to refuse are passed
        over rather than burning fetch budget on them, and the reason is reported
        back so the user still knows they were skipped.
        """
        self._guard()
        result = ResearchResult()

        urls: list[str] = []
        supplier_by_url: dict[str, int] = {}
        for candidate in candidates:
            label = candidate.site_name or candidate.host or _short(candidate.url)
            if skip_blocked and candidate.likely_blocked:
                result.skipped.append(f"{label}: {candidate.block_reason}")
                continue
            urls.append(candidate.url)
            if candidate.supplier_id:
                supplier_by_url[candidate.url] = candidate.supplier_id

        if not urls:
            result.skipped.append("Nothing left to research.")
            return result

        outcome = self.research_many(
            urls, product_id=product_id, query=query, supplier_by_url=supplier_by_url
        )
        result.sources = outcome.sources
        result.observations = outcome.observations
        result.cached = outcome.cached
        result.skipped.extend(outcome.skipped)
        return result

    def research_many(
        self,
        urls: Sequence[str],
        *,
        product_id: int | None = None,
        supplier_id: int | None = None,
        query: str | None = None,
        supplier_by_url: dict[str, int] | None = None,
    ) -> ResearchResult:
        """Fetch up to ``max_fetches_per_action`` pages and extract facts."""
        self._guard()

        validated: list[str] = []
        result = ResearchResult()
        for raw_url in urls:
            url = validate_url(raw_url)
            if url:
                validated.append(url)
            else:
                result.skipped.append(f"{_short(raw_url)} (unsupported or blocked URL)")

        # Serve from cache when this page was already parsed recently.
        fresh: list[str] = []
        for url in validated:
            cached_source = self.sources.find_recent_by_url(url, self.cache_minutes)
            if cached_source is not None:
                cached_observations = list(self.observations.list_for_source(cached_source.id))
                if cached_observations:
                    logger.info("Reusing cached research for %s", url)
                    result.sources.append(cached_source)
                    result.observations.extend(cached_observations)
                    result.cached = True
                    continue
            fresh.append(url)

        budget = self.max_fetches_per_action
        if len(fresh) > budget:
            result.skipped.append(
                f"Capped at {budget} page(s) per action; {len(fresh) - budget} not fetched."
            )
            fresh = fresh[:budget]

        if fresh:
            pages = self.client.fetch(fresh)
            for page in pages:
                page_url = page.url or page.final_url
                result.sources.append(self._absorb_page(
                    page,
                    product_id=product_id,
                    supplier_id=(supplier_by_url or {}).get(page_url, supplier_id),
                    query=query,
                    result=result,
                ))
        return result

    def _mark(self, source: ExternalSource, parse_status: str,
              content_hash: str | None = None) -> None:
        """Persist the outcome *and* reflect it on the returned object.

        Callers render the source they were handed, so an in-memory source left at
        ``pending`` would misreport a page that was actually parsed or rejected.
        """
        self.sources.set_parse_status(source.id, parse_status, content_hash)
        source.parse_status = parse_status
        if content_hash:
            source.content_hash = content_hash

    def _absorb_page(
        self, page, *, product_id: int | None, supplier_id: int | None,
        query: str | None, result: ResearchResult,
    ) -> ExternalSource:
        """Record one fetched page and persist whatever facts it yields."""
        source = self.sources.create(ExternalSource(
            provider=PROVIDER, url=page.url or page.final_url, query=query, parse_status="pending",
        ))
        url = page.url or page.final_url

        if not page.ok:
            reason = _friendly_fetch_error(page.error)
            self._mark(source, f"fetch_error:{reason}"[:120])
            result.skipped.append(f"{_short(url)}: {reason}")
            return source

        screen = screen_text(page.text)
        if not screen.usable:
            self._mark(source, screen.reason)
            result.skipped.append(f"{_short(url)}: page {screen.reason.replace('_', ' ')}")
            return source

        facts = fact_parser.extract_facts(page.text)
        observations = [
            SupplierObservation(
                field_name=f.field_name, field_value=f.field_value, currency=f.currency,
                confidence=round(f.confidence, 3), source_id=source.id,
                product_id=product_id, supplier_id=supplier_id,
            )
            for f in facts
        ]
        saved = self.observations.create_many(observations)
        result.observations.extend(saved)
        self._mark(source, "ok", screen.content_hash)
        logger.info("Researched %s -> %d candidate fact(s)", page.url, len(saved))
        return source

    # ---------------------------------------------------------- observations
    def observations_for_product(
        self, product_id: int, *, only_unverified: bool = False,
    ) -> Sequence[SupplierObservation]:
        return self.observations.list_for_product(product_id, only_unverified=only_unverified)

    def verify(self, observation_id: int, actor: str = "user") -> SupplierObservation:
        observation = self._require_observation(observation_id)
        self.observations.mark_verified(observation_id, True)
        self.audit.record_event(
            "supplier_observation_verified", "supplier_observation", observation_id,
            {"field": observation.field_name, "value": observation.field_value}, actor,
        )
        return self.observations.get_by_id(observation_id)  # type: ignore[return-value]

    def reject(self, observation_id: int, actor: str = "user") -> None:
        """Discard a candidate. The audit trail keeps the rejection on record."""
        observation = self._require_observation(observation_id)
        self.observations.delete(observation_id)
        self.audit.record_event(
            "supplier_observation_rejected", "supplier_observation", observation_id,
            {"field": observation.field_name, "value": observation.field_value}, actor,
        )

    def apply(self, observation_id: int, supplier_id: int, actor: str = "user") -> ProductSupplier:
        """Write a verified candidate onto a product↔supplier link.

        This is the only path from the web to ``product_suppliers``, and it always
        requires an explicit ``supplier_id`` chosen by the user.
        """
        observation = self._require_observation(observation_id)

        if observation.product_id is None:
            raise ValidationError("product_id", "This observation is not tied to a product")
        if self.suppliers.get_by_id(supplier_id) is None:
            raise NotFoundError("Supplier", supplier_id)

        attribute = _APPLICABLE_FIELDS.get(observation.field_name)
        if attribute is None:
            raise ValidationError("field_name", f"'{observation.field_name}' cannot be applied")

        value = _coerce_observation_value(observation)

        existing = next(
            (
                link for link, _supplier
                in self.suppliers.get_product_suppliers(observation.product_id)
                if link.supplier_id == supplier_id
            ),
            None,
        )
        link = ProductSupplier(
            id=existing.id if existing else None,
            product_id=observation.product_id,
            supplier_id=supplier_id,
            supplier_sku=existing.supplier_sku if existing else None,
            lead_time_days=existing.lead_time_days if existing else Config.DEFAULT_LEAD_TIME_DAYS,
            minimum_order_qty=(
                existing.minimum_order_qty if existing else Config.DEFAULT_MINIMUM_ORDER_QTY
            ),
            pack_size=existing.pack_size if existing else Config.DEFAULT_PACK_SIZE,
            unit_cost=existing.unit_cost if existing else None,
            is_preferred=existing.is_preferred if existing else False,
        )
        if observation.field_name == fact_parser.FIELD_UNIT_COST:
            link.unit_cost = to_money(value)
        else:
            setattr(link, attribute, value)
        link.last_verified_at = _now()

        saved = self.suppliers.link_product_supplier(link)
        self.observations.mark_verified(observation_id, True)
        self.audit.record_event(
            "supplier_observation_applied", "product", observation.product_id,
            {
                "observation_id": observation_id,
                "field": observation.field_name,
                "value": str(value),
                "supplier_id": supplier_id,
            },
            actor,
        )
        return saved

    # --------------------------------------------------------------- helpers
    def _guard(self) -> None:
        status = self.status()
        if not status.configured:
            raise ResearchNotConfiguredError(status.reason or "TinyFish is not configured.")
        if not status.enabled:
            raise TinyFishError(status.reason or "Live research is switched off.")

    def _require_observation(self, observation_id: int) -> SupplierObservation:
        observation = self.observations.get_by_id(observation_id)
        if observation is None:
            raise NotFoundError("Supplier observation", observation_id)
        return observation

    def _hosts_that_failed_before(self) -> set[str]:
        """Hosts that have already refused us, learned from our own history."""
        try:
            failed = self.sources.list_failed_sources(within_days=FAILED_HOST_LOOKBACK_DAYS)
        except Exception:  # pragma: no cover - a hint must never break a search
            logger.warning("Could not read past fetch failures", exc_info=True)
            return set()
        return {host_of(source.url) for source in failed if host_of(source.url)}


def _block_reason(host: str, failed_hosts: set[str]) -> str | None:
    """Why a fetch may not work, or ``None`` when there is no reason to doubt it.

    A host that actually refused us outranks the curated list, because it is
    evidence rather than a guess.
    """
    if host and host in failed_hosts:
        return "refused us before — likely blocks automated access"
    if is_known_bot_hostile(host):
        return "often blocks automated access"
    return None


def _name_guess_from_host(host: str) -> str:
    """A plausible company name from a domain root.

    Explicitly a guess — the caller shows it as an editable suggestion. Trying to
    be cleverer here would be worse: search titles describe products, not firms.
    """
    root = (host or "").split(".")[0]
    words = [word for word in re.split(r"[^a-z0-9]+", root.lower()) if word]
    return " ".join(words).title()


def _provenance_notes(candidate: SourceCandidate, query: str | None) -> str:
    """Notes recording where this supplier came from, so it can be re-checked.

    Always names the tool, even without a query: a record that says a supplier
    came off the web should say so regardless of how it was found.
    """
    origin = "Discovered via TinyFish search"
    if query:
        origin += f' for "{query}"'
    lines: list[str] = [origin + "."]
    if candidate.title:
        lines.append(f"Page title: {candidate.title}")
    if candidate.snippet:
        lines.append(candidate.snippet[:280])
    lines.append(f"Source: {candidate.url}")
    return "\n".join(lines)


def _coerce_observation_value(observation: SupplierObservation):
    """Validate a scraped string before it can touch a typed column.

    Guards against a page smuggling junk into money or quantity fields, and
    refuses foreign currency rather than silently guessing a rate.
    """
    raw = (observation.field_value or "").strip()
    if not raw:
        raise ValidationError("field_value", "That observation has no value")

    if observation.field_name == fact_parser.FIELD_UNIT_COST:
        currency = (observation.currency or "INR").upper()
        if currency not in ("INR", "RS", "RUPEE", "RUPEES"):
            raise ValidationError(
                "currency",
                f"Found {currency} pricing. StockWise records INR only — no rate "
                "conversion is attempted, so convert it yourself first.",
            )
        try:
            return to_money(Decimal(raw))
        except (InvalidOperation, ValueError) as exc:
            raise ValidationError("field_value", f"'{raw}' is not a usable price") from exc

    try:
        number = int(float(raw))
    except (TypeError, ValueError) as exc:
        raise ValidationError("field_value", f"'{raw}' is not a whole number") from exc

    if observation.field_name == fact_parser.FIELD_LEAD_TIME and number < 0:
        raise ValidationError("field_value", "Lead time cannot be negative")
    if observation.field_name in (fact_parser.FIELD_MOQ, fact_parser.FIELD_PACK_SIZE) and number < 1:
        raise ValidationError("field_value", "Order quantity and pack size must be at least 1")
    return number


def _friendly_fetch_error(error: str | None) -> str:
    """Turn a raw TinyFish fetch error into something a shop owner can read."""
    text = (error or "").strip()
    lowered = text.lower()
    if "target_http_error" in lowered or "403" in lowered:
        return "the site refused the request (it likely blocks automated access)"
    if "empty_content" in lowered or lowered == "empty":
        return "the page came back empty (usually a JavaScript-only site)"
    if "404" in lowered or "not_found" in lowered:
        return "the page no longer exists"
    if "timeout" in lowered:
        return "the page took too long to load"
    if "dns" in lowered or "resolve" in lowered:
        return "the site's address could not be resolved"
    if "ssl" in lowered or "certificate" in lowered:
        return "the site's security certificate could not be read"
    return text[:120] or "the page could not be fetched"


def _short(url: str, limit: int = 68) -> str:
    """Trim a long URL so skip messages stay on one readable line."""
    return url if len(url) <= limit else url[: limit - 3] + "\u2026"