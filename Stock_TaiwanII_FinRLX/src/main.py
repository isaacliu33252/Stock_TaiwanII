#!/usr/bin/env python3
"""
Stock_TaiwanII_FinRLX — Main Entry Point
==========================================

Usage:
    python -m src.main dashboard     # Web dashboard
    python -m src.main backtest      # Run backtest
    python -m src.main trade          # Execute live trading (Alpaca)
    python -m src.main config         # Show current config
"""
import argparse
import logging
import sys
from pathlib import Path

# Add project root to path
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from src.config.settings import get_config


def setup_parser():
    parser = argparse.ArgumentParser(
        description="Stock_TaiwanII_FinRLX — AI-Native Modular Quantitative Trading",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Commands:
  dashboard   Start web dashboard (FinRL-X web tool)
  backtest    Run backtest using RL strategy
  trade       Execute live/paper trading via Alpaca
  config      Print current configuration

Examples:
  python -m src.main config
  python -m src.main backtest --config ./config/portfolio.yaml
  python -m src.main trade --live
        """
    )
    parser.add_argument(
        "command",
        choices=["dashboard", "backtest", "trade", "config"],
        help="Command to execute"
    )
    parser.add_argument("--config", type=str, help="Path to config file")
    parser.add_argument("--live", action="store_true", help="Use live trading (default: paper)")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")
    return parser


def main():
    parser = setup_parser()
    args = parser.parse_args()

    # Load config
    config = get_config()

    # Setup logging
    level = logging.DEBUG if args.verbose else getattr(logging, config.logging.level)
    logging.basicConfig(
        level=level,
        format=config.logging.format,
    )
    logger = logging.getLogger(__name__)

    logger.info(f"Stock_TaiwanII_FinRLX v{config.version}")
    logger.info(f"Environment: {config.environment} | Data: {config.get_data_dir()}")

    try:
        if args.command == "dashboard":
            logger.info("Starting dashboard...")
            from src.web.app import main as dashboard_main
            dashboard_main()

        elif args.command == "backtest":
            logger.info("Running backtest...")
            # Lazy import to avoid heavy deps at startup
            from src.backtest.backtest_engine import BacktestEngine
            from src.strategies.rl_portfolio_strategy import RLPortfolioStrategy, RLPortfolioConfig
            from src.config.settings import get_config

            cfg = get_config()
            # TODO: load from args.config yaml when ready
            # For now, run a quick demo
            print("Backtest ready. Provide --config yaml to run specific strategy.")
            print(f"Data dir: {cfg.get_data_dir()}")

        elif args.command == "trade":
            logger.info("Starting trade executor...")
            if not config.alpaca.api_key:
                print("ERROR: Alpaca API key not configured.")
                print("  Set APCA_API_KEY and APCA_API_SECRET in .env file.")
                print("  Then run: python -m src.main trade --live")
                sys.exit(1)
            if args.live:
                config.environment = "live"
            from src.trading.trade_executor import TradeExecutor
            from src.trading.alpaca_manager import AlpacaManager, AlpacaAccount
            from src.config.settings import get_config

            account = AlpacaAccount(
                name="default",
                api_key=config.alpaca.api_key,
                api_secret=config.alpaca.api_secret,
                base_url=config.alpaca.base_url,
            )
            alpaca = AlpacaManager(accounts=[account])
            executor = TradeExecutor(alpaca)
            print(f"Trade executor initialized (paper={config.is_paper()})")
            print("Ready to execute. TODO: hook up strategy.generate_weights() next.")

        elif args.command == "config":
            print("Current Configuration:")
            print(f"  Version:     {config.version}")
            print(f"  Environment: {config.environment}")
            print(f"  Data dir:    {config.get_data_dir()}")
            print(f"  Model dir:   {config.get_model_dir()}")
            print(f"  Alpaca key:  {'✓ set' if config.alpaca.api_key else '✗ NOT SET'}")
            print(f"  Log level:   {config.logging.level}")

    except KeyboardInterrupt:
        logger.info("Cancelled by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Error: {e}")
        if args.verbose:
            import traceback; traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()