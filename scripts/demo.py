"""Create synthetic, separate demonstration data, optionally opening the app."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

MARKER = ".squackts-demo.json"
ROOT = Path(__file__).resolve().parents[1]


def seed_demo(home: Path) -> dict[str, object]:
    home = home.expanduser().resolve()
    marker = home / MARKER
    if marker.is_file():
        metadata: dict[str, object] = json.loads(marker.read_text(encoding="utf-8"))
        if metadata.get("kind") != "squackts-demo" or not (home / "data" / "pod_manager.db").is_file():
            raise ValueError("A demonstração está incompleta. Escolha outra pasta vazia.")
        return metadata
    if home.exists() and any(home.iterdir()):
        raise ValueError("A pasta de demonstração tem ficheiros. Escolha uma pasta nova ou vazia.")
    home.mkdir(parents=True, exist_ok=True)
    from config import AppPaths
    from service_container import bootstrap_infrastructure

    container = bootstrap_infrastructure(AppPaths.from_home(home), migrate_legacy=False)
    try:
        clients = [
            container.clients.create_client({"nome": name, "email": email, "ativo": 1})
            for name, email in [("Atelier Aurora", "aurora@example.test"), ("Clube do Bairro", "clube@example.test")]
        ]
        products = [
            container.products.create_product({
                "nome": name, "sku": sku, "descricao": "Produto fictício de demonstração",
                "preco": price, "custo": cost, "stock": stock, "stock_minimo": 3,
                "tipo_producao": kind, "ativo": 1,
            })
            for name, sku, price, cost, stock, kind in [
                ("T-shirt Aurora", "DEMO-TS", "22.50", "8.00", 0, "print_on_demand"),
                ("Saco de algodão", "DEMO-SC", "12.00", "4.00", 30, "stock_fisico"),
                ("Hoodie Clube", "DEMO-HD", "39.00", "16.00", 6, "misto"),
            ]
        ]
        for number in range(8):
            container.orders.create_order({
                "client_id": clients[number % len(clients)],
                "estado": "rascunho" if number < 2 else "confirmada",
                "pago": number % 2 if number >= 2 else 0,
                "tracking": "", "metodo_pagamento": "manual", "portes": "3.50",
                "data_prevista": "", "notas": "DADOS FICTÍCIOS — demonstração",
                "items": [{"product_id": products[number % len(products)], "quantidade": number % 3 + 1}],
            })
        metadata = {"kind": "squackts-demo", "home": str(home), "clients": len(clients), "products": len(products), "orders": 8}
        marker.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        return metadata
    finally:
        container.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--home", type=Path, default=ROOT / ".demo", help="Pasta nova/vazia para os dados fictícios")
    parser.add_argument("--launch", action="store_true", help="Abrir a aplicação com estes dados")
    args = parser.parse_args()
    try:
        metadata = seed_demo(args.home)
    except ValueError as error:
        parser.error(str(error))
    print(json.dumps(metadata, ensure_ascii=False, indent=2))
    if args.launch:
        environment = os.environ.copy()
        environment["SQUACKTS_DATA_HOME"] = str(args.home.expanduser().resolve())
        return subprocess.call([sys.executable, str(ROOT / "app.py")], cwd=ROOT, env=environment)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
