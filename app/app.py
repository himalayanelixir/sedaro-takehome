# HTTP SERVER

import json

from collections import deque
from flask import Flask, request, Response
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from simulator import Simulator
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from store import QRangeStore
import logging
import sys
from datetime import datetime
import time
class Base(DeclarativeBase):
    pass


############################## Format logs ##############################

class JsonFormatter(logging.Formatter):
    def format(self, record):
        log_record = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "message": record.getMessage(),
            "module": record.module,
            "file": record.pathname,
            "line": record.lineno,
            "function": record.funcName,
        }
        return json.dumps(log_record)

# Attach formatter to stream handler
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(JsonFormatter())

# Set global logging config
logging.basicConfig(
    level=logging.INFO,
    handlers=[handler]
)


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
recent_average_sim_durations = deque(maxlen=10)


############################## Database Models ##############################

class Simulation(db.Model):
    id: Mapped[int] = mapped_column(primary_key=True)
    data: Mapped[str]


with app.app_context():
    db.create_all()


############################## Helper Functions ##############################

def collect_metrics():
    uptime = (datetime.now() - app_start_time).total_seconds()
    count = Simulation.query.count()
    build_duration = app.config.get("LAST_BUILD_DURATION") or 0.0
    sim_duration = app.config.get("LAST_SIM_DURATION") or 0.0

    avg_duration = sum(recent_average_sim_durations) / len(recent_average_sim_durations) if recent_average_sim_durations else 0.0

    return {
        "uptime_seconds": round(uptime, 2),
        "simulation_count": count,
        "last_simulation_build_duration_seconds": round(build_duration, 4),
        "last_simulation_duration_seconds": round(sim_duration, 4),
        "recent_avg_simulation_duration_seconds": round(avg_duration, 4),
    }


############################## API Endpoints ##############################

@app.get("/")
def health():
    return "<p>Sedaro Nano API - running!</p>"


@app.get("/simulation")
def get_data():
    simulation: Simulation = Simulation.query.order_by(Simulation.id.desc()).first()
    if simulation:
        return simulation.data, 200
    return [], 404


@app.post("/simulation")
def simulate():
    # Get data from request in this form
    # init = {
    #     "Body1": {"x": 0, "y": 0.1, "vx": 0.1, "vy": 0},
    #     "Body2": {"x": 0, "y": 1, "vx": 1, "vy": 0},
    # }

    # Define time and timeStep for each agent
    init: dict = request.json
    if not init or not isinstance(init, dict):
        return {"error": "Invalid simulation input"}, 400

    try:
        for key in init:
            init[key]["time"] = 0
            init[key]["timeStep"] = 0.01
    except Exception:
        return {"error": "Malformed body structure"}, 422

    # Create store and simulator
    t = datetime.now()
    store = QRangeStore()
    simulator = Simulator(store=store, init=init)
    app.config["LAST_BUILD_DURATION"] = (datetime.now() - t).total_seconds()
    logging.info(f"Time to Build: {app.config['LAST_BUILD_DURATION']}")

    # Run simulation
    t = datetime.now()
    simulator.simulate()
    duration = (datetime.now() - t).total_seconds()
    app.config["LAST_SIM_DURATION"] = duration
    recent_average_sim_durations.append(duration)
    logging.info(f"Time to Simulate: {duration}")

    # Save data to database
    simulation = Simulation(data=json.dumps(store.store))
    db.session.add(simulation)
    db.session.commit()

    return store.store

@app.get("/metrics")
def metrics():
    metrics_data = collect_metrics()
    return (
        "\n".join([
            "# HELP sedaro_uptime_seconds Time since the app started in seconds",
            "# TYPE sedaro_uptime_seconds gauge",
            f"sedaro_uptime_seconds {metrics_data['uptime_seconds']}",

            "# HELP sedaro_simulation_count Total number of simulations run",
            "# TYPE sedaro_simulation_count counter",
            f"sedaro_simulation_count {metrics_data['simulation_count']}",

            "# HELP sedaro_last_simulation_build_duration_seconds Duration of the last simulator build",
            "# TYPE sedaro_last_simulation_build_duration_seconds gauge",
            f"sedaro_last_simulation_build_duration_seconds {metrics_data['last_simulation_build_duration_seconds']}",

            "# HELP sedaro_last_simulation_duration_seconds Duration of the last simulation run",
            "# TYPE sedaro_last_simulation_duration_seconds gauge",
            f"sedaro_last_simulation_duration_seconds {metrics_data['last_simulation_duration_seconds']}",

            "# HELP sedaro_recent_avg_simulation_duration_seconds Rolling average simulation duration (last 10)",
            "# TYPE sedaro_recent_avg_simulation_duration_seconds gauge",
            f"sedaro_recent_avg_simulation_duration_seconds {metrics_data['recent_avg_simulation_duration_seconds']}",
        ]),
        200,
        {"Content-Type": "text/plain"},
    )


@app.get("/metrics/json")
def metrics_json():
    return collect_metrics()

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

@app.get("/debug")
def debug():
    return {
        "start_time": app_start_time.isoformat(),
        "last_build_duration": app.config.get("LAST_BUILD_DURATION"),
        "last_sim_duration": app.config.get("LAST_SIM_DURATION"),
        "recent_durations": list(recent_average_sim_durations),
        "db_entries": Simulation.query.count()
    }

#  Log request IPs and timestamps
@app.before_request
def log_request_info():
    logging.info(f"[{datetime.now().isoformat()}] {request.method} {request.path} from {request.remote_addr}")
