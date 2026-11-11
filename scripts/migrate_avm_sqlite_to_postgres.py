from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from pathlib import Path

from scripts import offer_avm_store


def migrate(sqlite_path: Path) -> tuple[int, int]:
    database_url = os.environ.get("AVM_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("Defina DATABASE_URL ou AVM_DATABASE_URL para o PostgreSQL de destino.")
    if not sqlite_path.is_file():
        raise FileNotFoundError(f"Banco SQLite não encontrado: {sqlite_path}")

    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError as error:
        raise RuntimeError(
            "Driver PostgreSQL ausente. Execute: "
            "py -3.13 -m pip install -r requirements-api.txt"
        ) from error

    source = sqlite3.connect(sqlite_path)
    source.row_factory = sqlite3.Row
    try:
        imports = source.execute(
            """
            SELECT id, file_name, model, status, total_rows, processed_rows,
                   predicted_rows, error_rows, error_message, created_at, completed_at
            FROM avm_imports
            ORDER BY created_at, id
            """
        ).fetchall()
        row_count = source.execute(
            "SELECT COUNT(*) FROM avm_import_rows"
        ).fetchone()[0]

        offer_avm_store.initialize_store()
        with psycopg.connect(
            database_url,
            connect_timeout=5,
            row_factory=dict_row,
        ) as target:
            with target.transaction():
                existing = target.execute(
                    """
                    SELECT
                        EXISTS (SELECT 1 FROM avm_imports) AS has_imports,
                        EXISTS (SELECT 1 FROM avm_import_rows) AS has_rows
                    """
                ).fetchone()
                if existing["has_imports"] or existing["has_rows"]:
                    raise ValueError(
                        "O banco PostgreSQL de destino já contém importações. "
                        "A migração foi cancelada sem alterar os dados."
                    )

                with target.cursor() as cursor:
                    cursor.executemany(
                        """
                        INSERT INTO avm_imports (
                            id, file_name, model, status, total_rows, processed_rows,
                            predicted_rows, error_rows, error_message, created_at, completed_at
                        ) VALUES (
                            %(id)s, %(file_name)s, %(model)s, %(status)s, %(total_rows)s,
                            %(processed_rows)s, %(predicted_rows)s, %(error_rows)s,
                            %(error_message)s, %(created_at)s, %(completed_at)s
                        )
                        """,
                        [dict(row) for row in imports],
                    )

                cursor = source.execute(
                    """
                    SELECT import_id, source_row, source_data_json, prediction,
                           status, error_message
                    FROM avm_import_rows
                    ORDER BY import_id, source_row
                    """
                )
                while batch := cursor.fetchmany(500):
                    with target.cursor() as target_cursor:
                        target_cursor.executemany(
                            """
                            INSERT INTO avm_import_rows (
                                import_id, source_row, source_data_json, prediction,
                                status, error_message
                            ) VALUES (
                                %(import_id)s, %(source_row)s, %(source_data_json)s,
                                %(prediction)s, %(status)s, %(error_message)s
                            )
                            """,
                            [dict(row) for row in batch],
                        )
        return len(imports), row_count
    finally:
        source.close()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Copia o histórico SQLite do AVM para um PostgreSQL vazio."
    )
    parser.add_argument(
        "--sqlite-path",
        type=Path,
        default=offer_avm_store.DATABASE_PATH,
        help="Banco SQLite de origem (padrão: dados/avm_uploads.sqlite3).",
    )
    args = parser.parse_args()
    try:
        import_count, row_count = migrate(args.sqlite_path)
    except (OSError, RuntimeError, ValueError) as error:
        print(f"Erro: {error}", file=sys.stderr)
        return 1
    print(
        f"Migração concluída: {import_count} importação(ões) e "
        f"{row_count} linha(s) copiadas para PostgreSQL."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
