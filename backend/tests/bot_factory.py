"""Object builders for the bot tests. Not a `test_*` module — see `pine_corpus`."""

from __future__ import annotations

from decimal import Decimal

from apps.bots.models import Bot, BotRun, BotState, Strategy, StrategyVersion
from tests import pine_corpus

DEFAULT_SOURCE = (pine_corpus.ACCEPT / "01_sma_cross.pine").read_text()


def make_version(source: str = DEFAULT_SOURCE, *, name: str = "test strategy") -> StrategyVersion:
    strategy, _ = Strategy.objects.get_or_create(name=name)
    version = strategy.versions.count() + 1
    return StrategyVersion.objects.create(
        strategy=strategy, version=version, source=source, parsed_ok=True
    )


def make_bot(
    *,
    source: str = DEFAULT_SOURCE,
    name: str = "bot",
    state: str = BotState.DRAFT,
    symbol: str = "BTCUSDT",
    interval: str = "15m",
    leverage: int = 1,
    sl_pct: str | None = None,
    tp_pct: str | None = None,
    risk_config: dict | None = None,
    inputs: dict | None = None,
) -> Bot:
    return Bot.objects.create(
        strategy_version=make_version(source, name=f"{name} strategy"),
        name=name,
        symbol=symbol,
        interval=interval,
        leverage=leverage,
        sl_pct=Decimal(sl_pct) if sl_pct else None,
        tp_pct=Decimal(tp_pct) if tp_pct else None,
        input_values=inputs or {},
        risk_config=risk_config or {},
        state=state,
        dry_run=state != BotState.LIVE,
    )


def make_run(bot: Bot, **kwargs) -> BotRun:
    return BotRun.objects.create(bot=bot, **kwargs)
