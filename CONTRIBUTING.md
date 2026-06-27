# Contributing to eSIM E-Go

First off, thank you for considering contributing! We welcome contributions from everyone, whether it's a bug report, a new feature, a translation improvement, or a payment provider integration.

## Language

- Issues and PRs should be written in **English** or **Arabic** (العربية)
- Code comments and docstrings should be in **English**
- Translation files are in `app/translations/` — feel free to fix or improve any of the 12 supported languages

## Getting Started

1. Fork the repository
2. Clone your fork:
   ```bash
   git clone https://github.com/your-username/esim-ego-server.git
   cd esim-ego-server
   ```
3. Run the development environment:
   ```bash
   docker compose up -d
   cp .env.example .env
   python -m venv venv && source venv/bin/activate
   pip install -r requirements.txt
   python run.py
   ```

## Development Workflow

1. Create a branch: `git checkout -b feat/your-feature` or `fix/your-fix`
2. Make your changes
3. Test your changes:
   ```bash
   # Start the server
   python run.py
   # In another terminal, run tests
   python -m pytest tests/ -v
   ```
4. Format your code (we follow PEP 8):
   ```bash
   pip install black flake8
   black app/ run.py config.py
   flake8 app/ run.py config.py
   ```
5. Commit using clear commit messages:
   ```
   feat: add support for [provider name] payment gateway
   fix: resolve [issue] in order service
   i18n: add [language] translation
   docs: update API.md with [endpoint]
   ```
6. Push and open a Pull Request

## Pull Request Guidelines

- Keep PRs focused — one feature/fix per PR
- Update `API.md` if you add or change an endpoint
- Update translation files if you add new user-facing messages
- Add yourself to the list of contributors if you'd like
- Ensure your PR passes the CI checks

## Adding a New Provider

The plugin system makes adding providers straightforward:

1. Create a file in `app/providers/<category>/<your_provider>.py`
2. Implement the abstract base class from `app/providers/base.py`
3. Decorate with the registry decorator (see existing providers for examples)
4. If it's a payment gateway, add the necessary fields to `config.py`
5. Add environment variables to `.env.example`

See `app/providers/` for examples (ZainCash, FIB, SuperQI for payments; BulkSMSIraq, OTPIQ for SMS; eSIMGo for eSIM activation).

## Translation Guidelines

1. Each language has its own JSON file in `app/translations/`
2. Keys are hierarchical and follow the pattern: `module.section.key`
3. When adding a new key, add it to **all** translation files (copy from `en.json`)
4. Use the helper script to find missing keys:
   ```bash
   python scripts/fill_translations.py
   ```

## Reporting Issues

- Use the [Bug Report](https://github.com/omermask/esim-ego-server/issues/new?template=bug_report.md) template
- Include server logs, environment details, and reproduction steps
- For security vulnerabilities, see `SECURITY.md`

## Code of Conduct

All contributors must adhere to our [Code of Conduct](CODE_OF_CONDUCT.md).

---

**Questions?** Open a [Discussion](https://github.com/omermask/esim-ego-server/discussions) or email oj33593@gmail.com.
