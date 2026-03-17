import logging
import sys

logging.basicConfig(
    stream=sys.stdout,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

from app import create_app

app = create_app()

if __name__ == "__main__":
    app.run(debug=True, port=5000)
