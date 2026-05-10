# Base Attackers

A 2D arcade game built with Python and
[Arcade](https://api.arcade.academy/) using the
[arcade-game-framework](https://github.com/darthwilliam1118/arcade-game-framework).

## Running

Download the latest release exe from the Releases page, or run from source:

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
python main.py        # use "python", not "py" — py bypasses the venv on Windows
```

## Development

```bash
pip install -e ".[dev]"
pytest --cov=src
black .
ruff check .
```

## License

MIT — see LICENSE.
