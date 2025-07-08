# wsgi.py
from rms import create_app   # or however you currently build the Flask app

app = create_app()

# If you need env-file support on the server:
from dotenv import load_dotenv;
load_dotenv()