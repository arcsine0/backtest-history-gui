"""PyTauri entry point for the local backtesting backend."""

from anyio.from_thread import start_blocking_portal
from pytauri import Commands, builder_factory, context_factory

commands: Commands = Commands()


@commands.command()
def backend_status() -> str:
    """TODO: Return richer application state once services are implemented."""
    return "Backtesting.py backend scaffold ready"


# TODO: Register typed PyTauri commands here, for example:
# @commands.command()
# async def run_backtest(body: BacktestRequest) -> BacktestResult: ...


def main() -> int:
    with start_blocking_portal("asyncio") as portal:
        app = builder_factory().build(
            context=context_factory(),
            invoke_handler=commands.generate_handler(portal),
        )
        return app.run_return()
