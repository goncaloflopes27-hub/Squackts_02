from __future__ import annotations

import argparse
import logging
import os
import sqlite3
import sys
from contextlib import ExitStack
from logging.handlers import RotatingFileHandler
from pathlib import Path
from tempfile import TemporaryDirectory

from config import APP_DISPLAY_VERSION, APP_NAME, AppPaths


def _arguments(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Gestão desktop de operações Print-on-Demand")
    parser.add_argument("--version", action="version", version=f"%(prog)s {APP_DISPLAY_VERSION}")
    parser.add_argument("--data-dir", type=Path, help="Diretório dos dados deste perfil")
    parser.add_argument("--demo", action="store_true", help="Abrir dados fictícios num perfil separado")
    parser.add_argument("--smoke-test", action="store_true", help="Verificar arranque e páginas e terminar")
    parser.add_argument("--screenshots", type=Path, help="Guardar capturas das seis páginas durante --smoke-test")
    parser.add_argument("--expect-platform", help="Falhar a verificação se o plugin Qt carregado for diferente")
    parser.add_argument("--smoke-default-profile", action="store_true", help="Usar o perfil configurado explicitamente no ensaio, em vez de dados temporários")
    return parser.parse_args(argv)


def _logging(paths: AppPaths) -> RotatingFileHandler:
    paths.logs_dir.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(paths.log_file_path, maxBytes=2_000_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logging.getLogger("squackts").setLevel(logging.INFO)
    logging.getLogger("squackts").addHandler(handler)
    return handler


def _close_logging(handler: RotatingFileHandler) -> None:
    logging.getLogger("squackts").removeHandler(handler)
    handler.close()


def main(argv: list[str] | None = None) -> int:
    args = _arguments(argv)
    with ExitStack() as resources:
        if args.smoke_test and args.data_dir is None and not args.smoke_default_profile:
            home = Path(resources.enter_context(TemporaryDirectory(prefix="squackts-smoke-")))
        elif args.data_dir is not None:
            home = args.data_dir.expanduser().resolve()
        else:
            import config
            home = config.PATHS.data_dir.parent
        if args.demo:
            if args.data_dir is None and not args.smoke_test:
                home = home.with_name(home.name + "-demo")
            from scripts.demo import seed_demo
            seed_demo(home)
        paths = AppPaths.from_home(home)
        if args.smoke_test and sys.platform not in {"win32", "darwin"} and not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
            os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtCore import QLocale, QLockFile
        from PySide6.QtGui import QIcon
        from PySide6.QtWidgets import QApplication, QMessageBox

        from service_container import bootstrap_infrastructure
        from ui.main_window import MainWindow

        instance = QApplication.instance()
        if instance is not None and not isinstance(instance, QApplication):
            raise RuntimeError("A interface requer QApplication")
        qt = instance if isinstance(instance, QApplication) else QApplication([sys.argv[0]])
        if args.expect_platform and qt.platformName() != args.expect_platform:
            raise RuntimeError(f"Plugin Qt incorreto: {qt.platformName()}; esperado: {args.expect_platform}")
        qt.setApplicationName(APP_NAME)
        qt.setOrganizationName("Squack TS")
        qt.setApplicationVersion(APP_DISPLAY_VERSION)
        QLocale.setDefault(QLocale(QLocale.Language.Portuguese, QLocale.Country.Portugal))
        source_root = Path(__file__).resolve().parent
        bundle_root = Path(getattr(sys, "_MEIPASS", source_root))
        for icon in (bundle_root / "assets" / "squackts.svg", source_root / "packaging" / "assets" / "squackts.svg"):
            if icon.is_file():
                qt.setWindowIcon(QIcon(str(icon)))
                break
        from ui.theme import initialize_theme
        initialize_theme(qt)
        splash = None
        if not args.smoke_test:
            from ui.splash import StartupSplash
            splash = StartupSplash()
            splash.show()
            splash.advance(15, "A abrir o teu espaço de trabalho…")
        try:
            paths.data_dir.mkdir(parents=True, exist_ok=True)
            lock = QLockFile(str(home / ".squackts.lock"))
            if not lock.tryLock(100):
                raise ValueError("Este perfil já está aberto noutra instância do SquackTS.")
            resources.callback(lock.unlock)
            resources.callback(_close_logging, _logging(paths))
            from ui.error_reporting import install_exception_handler
            resources.callback(install_exception_handler(qt, paths.log_file_path))
            container = bootstrap_infrastructure(paths, migrate_legacy=not args.demo and not args.smoke_test)
            resources.callback(container.close)
            if splash is not None:
                splash.advance(75, "A organizar o painel…")
            window = MainWindow(container)
            window.show()
            if splash is not None:
                splash.advance(100, "Tudo pronto.")
                splash.close()
            if args.smoke_test:
                from ui.smoke import SmokeProbe
                probe = SmokeProbe(window, qt, args.screenshots)
                probe.start()
            status = qt.exec()
            if args.smoke_test:
                return status or int(bool(probe.failures))
            return status
        except (OSError, ValueError, RuntimeError, sqlite3.Error) as error:
            if splash is not None:
                splash.close()
            logging.getLogger("squackts").exception("Falha no arranque")
            if qt.platformName() == "offscreen" or args.smoke_test:
                print(f"SquackTS: {error}", file=sys.stderr)
            else:
                QMessageBox.critical(None, APP_NAME, str(error))
            return 1


if __name__ == "__main__":
    raise SystemExit(main())
