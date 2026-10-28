# insurance-land

A toy multi-agent housing and insurance market with seeded initial distributions and disaster exposure.

```bash
uv sync --locked
uv run python main.py
```

`main.py` is the runner. Application packages (`agents`, `domain`, `factories`, and `utils`) live alongside it. See [the documentation](docs/README.md) and [initial-distribution setup](docs/initial-distributions.md).
