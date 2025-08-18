from gevent import monkey; monkey.patch_all()

from dotenv import load_dotenv
from themybuttsite import create_app

load_dotenv()
app = create_app()