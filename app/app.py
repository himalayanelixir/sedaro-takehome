# HTTP SERVER

import json

from flask import Flask, request, Response
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from simulator import Simulator
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from store import QRangeStore
import logging
from datetime import datetime
import time
class Base(DeclarativeBase):
    pass


############################## Application Configuration ##############################

app = Flask(__name__)
CORS(app, origins=["http://localhost:3030"])

db = SQLAlchemy(model_class=Base)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///database.db"
app.config["LAST_BUILD_DURATION"] = None
app.config["LAST_SIM_DURATION"] = None
db.init_app(app)

logging.basicConfig(level=logging.INFO)


############################## Metrics ##############################

app_start_time = datetime.now()
last_simulation_duration = None

############################## Database Models ##############################


class Simulation(db.Model):
    id: Mapped[int] = mapped_column(primary_key=True)
    data: Mapped[str]


with app.app_context():
    db.create_all()


############################## API Endpoints ##############################


@app.get("/")
def health():
    return "<p>Sedaro Nano API - running!</p>"


@app.get("/simulation")
def get_data():
    # Get most recent simulation from database
    simulation: Simulation = Simulation.query.order_by(Simulation.id.desc()).first()
    return simulation.data if simulation else []


@app.post("/simulation")
def simulate():
    # Get data from request in this form
    # init = {
    #     "Body1": {"x": 0, "y": 0.1, "vx": 0.1, "vy": 0},
    #     "Body2": {"x": 0, "y": 1, "vx": 1, "vy": 0},
    # }

    # Define time and timeStep for each agent
    init: dict = request.json
    for key in init:
        init[key]["time"] = 0
        init[key]["timeStep"] = 0.01

    # Create store and simulator
    t = datetime.now()
    store = QRangeStore()
    simulator = Simulator(store=store, init=init)
    app.config["LAST_BUILD_DURATION"] = (datetime.now() - t).total_seconds()
    logging.info(f"Time to Build: {app.config['LAST_BUILD_DURATION']}")

    # Run simulation
    t = datetime.now()
    simulator.simulate()
    app.config["LAST_SIM_DURATION"] = (datetime.now() - t).total_seconds()
    logging.info(f"Time to Simulate: {app.config['LAST_SIM_DURATION']}")

    # Save data to database
    simulation = Simulation(data=json.dumps(store.store))
    db.session.add(simulation)
    db.session.commit()

    return store.store

@app.get("/metrics")
def metrics():
    # Calculate server uptime in seconds
    uptime = (datetime.now() - app_start_time).total_seconds()

    # Count how many simulations have been stored
    count = Simulation.query.count()
    
    # Report the build duration of the most recent simulation
    build_duration = app.config.get("LAST_BUILD_DURATION") or 0.0

    # Report the duration of the most recent simulation
    sim_duration = app.config.get("LAST_SIM_DURATION") or 0.0

    # Prometheus-compatible plain text output
    prometheus_metrics = f"""
# HELP app_uptime_seconds Uptime of the Flask app in seconds.
# TYPE app_uptime_seconds gauge
app_uptime_seconds {round(uptime, 2)}

# HELP simulation_count Total number of simulations run.
# TYPE simulation_count counter
simulation_count {count}

# HELP last_simulation_build_duration_seconds Time to build the simulation in seconds.
# TYPE last_simulation_build_duration_seconds gauge
last_simulation_build_duration_seconds {round(build_duration, 4)}

# HELP last_simulation_duration_seconds Time to run the last simulation in seconds.
# TYPE last_simulation_duration_seconds gauge
last_simulation_duration_seconds {round(sim_duration, 4)}
""".strip()

    return Response(prometheus_metrics, mimetype="text/plain")

@app.get("/metrics/json")
def metrics_json():
    # Calculate server uptime in seconds
    uptime = (datetime.now() - app_start_time).total_seconds()

    # Count how many simulations have been stored
    count = Simulation.query.count()

    # Report durations, with defaults if unset
    build_duration = app.config.get("LAST_BUILD_DURATION") or 0.0
    sim_duration = app.config.get("LAST_SIM_DURATION") or 0.0

    # Return metrics as JSON
    return {
        "uptime_seconds": round(uptime, 2),
        "simulation_count": count,
        "last_simulation_build_duration_seconds": round(build_duration, 4),
        "last_simulation_duration_seconds": round(sim_duration, 4),
    }

@app.get("/healthz")
def health_check():
    try:
        # Try a trivial DB query to verify DB connectivity
        Simulation.query.first()

        # If successful, return OK status
        return {
            "status": "ok",
            "db": True,
            "sim_ready": True
        }

    except Exception as e:
        # On failure, return diagnostic error message
        return {
            "status": "fail",
            "db": False,
            "sim_ready": False,
            "error": str(e)
        }, 500