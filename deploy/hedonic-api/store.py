from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any


def database_url() -> str | None:
    return os.environ.get("DATABASE_URL") or os.environ.get("AVM_DATABASE_URL")


def initialize_store() -> bool:
    url = database_url()
    if not url:
        if os.environ.get("REQUIRE_DATABASE", "false").lower() == "true":
            raise RuntimeError("DATABASE_URL é obrigatório neste ambiente.")
        return False
    import psycopg

    with psycopg.connect(url, connect_timeout=8) as connection:
        connection.execute(
            """CREATE TABLE IF NOT EXISTS hedonic_avm_predictions (
                id UUID PRIMARY KEY,
                model_id TEXT NOT NULL,
                input_json JSONB NOT NULL,
                prediction_brl DOUBLE PRECISION NOT NULL CHECK (prediction_brl > 0),
                created_at TIMESTAMPTZ NOT NULL
            )"""
        )
        connection.execute("ALTER TABLE hedonic_avm_predictions ENABLE ROW LEVEL SECURITY")
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_hedonic_predictions_created_at "
            "ON hedonic_avm_predictions (created_at DESC)"
        )
    return True


def save_predictions(
    properties: list[dict[str, Any]],
    predictions: list[float],
    model_id: str = "hedonic_spline_ridge_v4_offer_calibrated",
) -> list[str | None]:
    if len(properties) != len(predictions):
        raise ValueError("A quantidade de entradas e previsões não corresponde.")
    url = database_url()
    if not url:
        return [None] * len(properties)
    import psycopg

    now = datetime.now(timezone.utc)
    entries = [(uuid.uuid4(), p, v, now) for p, v in zip(properties, predictions)]
    with psycopg.connect(url, connect_timeout=8) as connection:
        with connection.cursor() as cursor:
            cursor.executemany(
                """INSERT INTO hedonic_avm_predictions
                    (id, model_id, input_json, prediction_brl, created_at)
                    VALUES (%s, %s, %s::jsonb, %s, %s)""",
                [
                    (record_id, model_id,
                     json.dumps(item, ensure_ascii=False, allow_nan=False), value, created)
                    for record_id, item, value, created in entries
                ],
            )
    return [str(record_id) for record_id, _, _, _ in entries]


def list_predictions(limit: int = 50) -> list[dict[str, Any]]:
    url = database_url()
    if not url:
        return []
    import psycopg
    from psycopg.rows import dict_row

    with psycopg.connect(url, connect_timeout=8, row_factory=dict_row) as connection:
        rows = connection.execute(
            """SELECT id, model_id, prediction_brl, created_at
               FROM hedonic_avm_predictions
               ORDER BY created_at DESC LIMIT %s""",
            (limit,),
        ).fetchall()
    return [
        {
            "id": str(row["id"]),
            "model_id": row["model_id"],
            "prediction_brl": row["prediction_brl"],
            "created_at": row["created_at"].isoformat(),
        }
        for row in rows
    ]
