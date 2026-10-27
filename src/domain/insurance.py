"""Explicit toy contracts, opening purchases, and capital-limited claim settlement.

Premiums are paid once up front. Building loss uses the pre-disaster home value;
renters loss uses the contents amount explicitly declared in the offer. No debt,
renewal, rebuilding, or automatic cover is inferred.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from decimal import Decimal
from enum import StrEnum
from types import MappingProxyType

from src.domain.housing import HousingMarket
from src.domain.models import Entity, Home
from src.utils.validation.collections import index_by_id
from src.utils.validation.money import validate_money


class Product(StrEnum):
    HOMEOWNERS = "homeowners"
    LANDLORD = "landlord"
    RENTERS = "renters"


@dataclass(frozen=True, slots=True)
class Insurer:
    id: int
    name: str
    capital: Decimal

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("Insurer name cannot be empty")
        validate_money(self.capital, field="capital")


@dataclass(frozen=True, slots=True)
class Offer:
    id: int
    insurer_id: int
    product: Product
    premium: Decimal
    limit: Decimal
    deductible: Decimal = Decimal(0)
    term_periods: int = 12
    contents_value: Decimal = Decimal(0)

    def __post_init__(self) -> None:
        if not isinstance(self.product, Product):
            raise ValueError("product must be a Product")
        for name in ("premium", "limit", "deductible", "contents_value"):
            validate_money(getattr(self, name), field=name)
        if type(self.term_periods) is not int or self.term_periods <= 0:
            raise ValueError("term_periods must be a positive integer")
        if self.product != Product.RENTERS and self.contents_value != 0:
            raise ValueError("contents_value is only used for renters coverage")


@dataclass(frozen=True, slots=True)
class CoverageChoice:
    offer_id: int
    home_id: int


@dataclass(frozen=True, slots=True)
class Contract:
    id: int
    person_id: int
    home_id: int
    offer: Offer
    starts_at: int
    ends_at: int


@dataclass(frozen=True, slots=True)
class Claim:
    contract_id: int
    period: int
    home_id: int
    due: Decimal
    paid: Decimal


@dataclass(frozen=True, slots=True)
class InsuranceObservation:
    person: Entity
    homes: tuple[Home, ...]
    offers: tuple[Offer, ...]


@dataclass(frozen=True, slots=True)
class InsurerObservation:
    firm: Insurer
    people: tuple[Entity, ...]
    homes: tuple[Home, ...]
    period: int


def eligible_product(person_id: int, home: Home) -> Product | None:
    if home.destroyed:
        return None
    if home.owner_id == person_id:
        return Product.HOMEOWNERS if home.occupant_id == person_id else Product.LANDLORD
    if home.occupant_id == person_id:
        return Product.RENTERS
    return None


class InsuranceMarket:
    def __init__(self, firms: Sequence[Insurer]) -> None:
        self._firms = index_by_id(firms)
        self._contracts: list[Contract] = []
        self._claims: list[Claim] = []
        self._claimed: set[int] = set()
        self._opened = False

    @property
    def firms(self) -> Mapping[int, Insurer]:
        return MappingProxyType(self._firms)

    @property
    def contracts(self) -> tuple[Contract, ...]:
        return tuple(self._contracts)

    @property
    def claims(self) -> tuple[Claim, ...]:
        return tuple(self._claims)

    @property
    def opened(self) -> bool:
        return self._opened

    def copy(self) -> InsuranceMarket:
        result = InsuranceMarket(tuple(self._firms.values()))
        result._contracts = self._contracts.copy()
        result._claims = self._claims.copy()
        result._claimed = self._claimed.copy()
        result._opened = self._opened
        return result

    def open(
        self,
        market: HousingMarket,
        offers: Sequence[Offer],
        choices: Mapping[int, tuple[CoverageChoice, ...]],
        *,
        starts_at: int,
    ) -> None:
        """Called on working copies by Environment; rejected purchases commit nothing."""
        if self._opened:
            raise ValueError("The opening insurance round has already completed")
        indexed = index_by_id(offers)
        if any(o.insurer_id not in self._firms for o in offers):
            raise ValueError("Unknown insurer in offer")
        if choices.keys() != market.entities.keys():
            raise ValueError("Insurance choices must cover every person")
        purchased: set[tuple[int, int, Product]] = set()
        for person_id in sorted(choices):
            for choice in choices[person_id]:
                if choice.offer_id not in indexed or choice.home_id not in market.homes:
                    raise ValueError("Unknown offer or home")
                offer = indexed[choice.offer_id]
                home = market.homes[choice.home_id]
                if eligible_product(person_id, home) != offer.product:
                    raise ValueError("Person is not eligible for this coverage")
                key = (person_id, home.id, offer.product)
                if key in purchased:
                    raise ValueError("Duplicate coverage for the same interest")
                purchased.add(key)
                market.adjust_cash(person_id, -offer.premium)
                firm = self._firms[offer.insurer_id]
                self._firms[firm.id] = replace(firm, capital=firm.capital + offer.premium)
                self._contracts.append(
                    Contract(
                        len(self._contracts) + 1,
                        person_id,
                        home.id,
                        offer,
                        starts_at,
                        starts_at + offer.term_periods - 1,
                    )
                )
        self._opened = True

    def settle(
        self, market: HousingMarket, losses: Sequence[Home], period: int
    ) -> tuple[Claim, ...]:
        """Settle in contract-ID order, capped by available capital; record unpaid loss.

        This is an explicit toy insolvency rule, not a promise of guaranteed coverage.
        """
        indexed = {home.id: home for home in losses}
        results = []
        for contract in self._contracts:
            if (
                contract.id in self._claimed
                or contract.home_id not in indexed
                or not contract.starts_at <= period <= contract.ends_at
            ):
                continue
            home = indexed[contract.home_id]
            offer = contract.offer
            if eligible_product(contract.person_id, home) != offer.product:
                continue
            loss = offer.contents_value if offer.product == Product.RENTERS else home.market_value
            due = min(offer.limit, max(Decimal(0), loss - offer.deductible))
            firm = self._firms[offer.insurer_id]
            paid = min(due, firm.capital)
            self._firms[firm.id] = replace(firm, capital=firm.capital - paid)
            market.adjust_cash(contract.person_id, paid)
            claim = Claim(contract.id, period, home.id, due, paid)
            results.append(claim)
            self._claims.append(claim)
            self._claimed.add(contract.id)
        return tuple(results)
