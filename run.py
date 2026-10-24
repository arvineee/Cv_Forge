import os

from app import create_app

app = create_app()

if __name__ == "__main__":
    # The Werkzeug debugger allows arbitrary code execution, so it is opt-in
    # for local development only. Production runs under gunicorn.
    debug = os.environ.get("DEBUG", "false").lower() == "true"
    app.run(debug=debug)
