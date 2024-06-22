from mangum import Mangum

from ticker_info import app

handler = Mangum(app, lifespan="off")
