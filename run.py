from __future__ import annotations

from app import create_app

app = create_app()


def main() -> None:
    from config import settings

    if settings.IS_PRODUCTION or settings.ENVIRONMENT == "staging":
        from gunicorn.app.wsgiapp import WSGIApplication
        import sys
        sys.argv = ["gunicorn", "run:app", "-c", "gunicorn.conf.py"]
        WSGIApplication().run()
    else:
        from app.socketio import socketio
        socketio.run(
            app,
            host=settings.FLASK_HOST,
            port=settings.FLASK_PORT,
            debug=True,
            allow_unsafe_werkzeug=True,
        )


if __name__ == "__main__":
    main()
