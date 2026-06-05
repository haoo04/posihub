"""Historical position / order backfill from exchange APIs.

Pulls closed orders (and closed-position summaries for validation) from an
exchange, normalises them into a neutral structure, classifies each record
against existing local data for idempotency, and simulates FIFO open/close
matching for a preview-then-commit workflow.

See ``docs/order-level-position.md`` and the project plan
``历史仓位 API 回填`` for the full specification.
"""
