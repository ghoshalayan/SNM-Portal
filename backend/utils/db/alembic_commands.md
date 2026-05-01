# Alembic Quick Reference

> All commands run from `backend/` directory with venv activated.

## Status
```bash
alembic current                    # Show current DB revision
alembic history --verbose          # Full migration history
alembic heads                      # Show latest available revision
```

## Apply Migrations
```bash
alembic upgrade head               # Apply ALL pending migrations
alembic upgrade +1                 # Apply next 1 migration
alembic upgrade <revision_id>      # Apply up to specific revision
```

## Rollback
```bash
alembic downgrade -1               # Undo last 1 migration
alembic downgrade <revision_id>    # Rollback to specific revision
alembic downgrade base             # Undo ALL migrations (empty DB)
```

## Create Migrations
```bash
# Auto-generate from model changes (ALWAYS review the output)
alembic revision --autogenerate -m "Description of change"

# Create empty migration (for data seeds, manual DDL)
alembic revision -m "Description of change"
```

## Stamp (Mark DB state without running migrations)
```bash
alembic stamp head                 # Mark DB as fully migrated
alembic stamp base                 # Mark DB as empty
alembic stamp <revision_id>        # Mark DB at specific point
```

## Current Migration Chain
```
base
 └── 9eaf9699f05f  "Initial schema - all 25 tables"
      └── e88c297e3e9d  "Seed superadmin, test user, company, menus, permissions"
           └── f3a1b2c4d5e6  "Fix menu URLs singular → plural"  ← HEAD
```

## Tips
- **Always review** auto-generated migrations before applying
- **Never edit** a migration that has already been applied to production
- **Create new migrations** to fix issues, don't modify old ones
- Alembic uses `alembic_version` table to track state
- Connection string comes from `.env` → `DB_CONNECTION_STRING`
