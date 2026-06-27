# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 1.x     | :white_check_mark: |

## Reporting a Vulnerability

We take the security of eSIM E-Go seriously. If you discover a security vulnerability, please **do not** open a public issue.

Instead, send a private report to **oj33593@gmail.com** with the subject line `[SECURITY] eSIM E-Go Server`.

Please include:
- A description of the vulnerability
- Steps to reproduce
- Potential impact
- Any suggested fix (if known)

You should receive a response within **48 hours**. If the issue is confirmed, a fix will be released as soon as possible, typically within 7 days.

## Responsible Disclosure

We kindly ask that you allow us time to fix and release a patch before disclosing the vulnerability publicly.

## Scope

This security policy covers the main repository `omermask/esim-ego-server` and its companion dashboard (admin panel). It does **not** cover third-party dependencies — please report those to their respective maintainers.

## Best Practices for Deployment

1. **Change all secrets** in `.env` before going to production — `SECRET_KEY`, `API_KEYS_ENCRYPTION_KEY`, database passwords, API keys
2. **Enable HTTPS** behind a reverse proxy (Nginx/Caddy)
3. **Restrict admin access** using the IP whitelist (`ADMIN_IP_WHITELIST`)
4. **Enable 2FA** for all admin accounts (`/admin/security/enable-2fa`)
5. **Keep Redis firewalled** — it should not be exposed to the public internet
6. **Regularly update dependencies** — use `pip-audit` or Dependabot
