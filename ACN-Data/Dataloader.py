from datetime import datetime, timedelta
import pytz
import json
import math
import random


class DataLoader:
    def __init__(
        self,
        filepath,
        delta_minutes=15,
        instance_length_hours=24,
        L=1,
        U=10,
        ev_multiplier=20,
        num_stations=3,
        value_mode="fixed",
        fav_alpha=0.3,
        seed=42,
    ):
        self.delta = timedelta(minutes=delta_minutes)
        self.delta_minutes = self.delta.total_seconds() / 60.0
        self.instance_length = timedelta(hours=instance_length_hours)
        self.L, self.U = float(L), float(U)
        self.ev_multiplier = int(ev_multiplier)
        self.value_delta = (self.U - self.L) / self.ev_multiplier
        self.num_stations = int(num_stations)
        self.value_mode = value_mode
        self.fav_alpha = float(fav_alpha)

        self.X = self.fav_alpha * (self.U - self.L)

        self.fav_L = self.L + self.X * 1
        self.fav_delta = (self.U - self.fav_L) / self.ev_multiplier

        self.meta = {}
        self.instances = []
        self.time_window = 0
        self.total_evs = 0
        self.theta = self.U
        self.D_max = 0
        self.D_min = float("inf")
        random.seed(seed)

        self._load(filepath)

    def _reset(self):
        self.meta = {}
        self.instances = []
        self.time_window = 0
        self.total_evs = 0
        self.theta = self.U
        self.D_max = 0
        self.D_min = float("inf")

    def __iter__(self):
        """Iterate over instances"""
        for inst in self.instances:
            yield inst

    # --------------------------------------------------
    # Helpers
    # --------------------------------------------------

    def _parse_gmt_to_ca(self, time_str):
        dt_naive = datetime.strptime(
            time_str.replace(" GMT", ""), "%a, %d %b %Y %H:%M:%S"
        )
        dt_gmt = pytz.timezone("GMT").localize(dt_naive)
        return dt_gmt.astimezone(pytz.timezone("America/Los_Angeles"))

    def _time_to_index(self, dt, start_time):
        return int((dt - start_time).total_seconds() // self.delta.total_seconds())

    def get_value(self, total_req, batch_idx):

        low = self.L + batch_idx * self.value_delta
        high = self.L + (batch_idx + 1) * self.value_delta

        # safety (floating point)
        high = min(high, self.U)

        # Pick uniformly in this batch
        v = random.uniform(low, high)

        return [v * total_req for _ in range(self.num_stations)]

    def get_value_favorite(self, total_req, batch_idx, favorite_station):

        # create value list for all stations
        values = []

        for s in range(self.num_stations):

            if s == favorite_station:
                # favorite station density (batched in [L+X , U])
                low = self.fav_L + batch_idx * self.fav_delta
                high = self.fav_L + (batch_idx + 1) * self.fav_delta
                high = min(high, self.U)

                v = random.uniform(low, high)

            else:
                # non-favorite stations density
                v = random.uniform(self.L, min(self.L + self.X, self.L + (batch_idx + 1) * self.value_delta))

            values.append(v * total_req)

        return values

    # --------------------------------------------------
    # Main loader
    # --------------------------------------------------

    def _load(self, filepath):
        self._reset()

        with open(filepath, "r") as f:
            data = json.load(f)

        # ---- Meta ----
        meta = data.get("_meta", {})
        global_start = self._parse_gmt_to_ca(meta["start"])
        global_end = self._parse_gmt_to_ca(meta["end"])

        self.meta = {
            "site": meta.get("site"),
            "start": global_start,
            "end": global_end,
            "min_kWh": meta.get("min_kWh"),
        }

        # ---- Instance windows (HOURS-based) ----
        total_seconds = (global_end - global_start).total_seconds()
        num_instances = math.ceil(total_seconds / self.instance_length.total_seconds())

        instance_windows = []
        for i in range(num_instances):
            inst_start = global_start + i * self.instance_length
            inst_end = min(inst_start + self.instance_length, global_end)
            instance_windows.append((inst_start, inst_end))

        self.instances = [[] for _ in range(num_instances)]

        # ---- Assign EVs ----
        for item in data.get("_items", []):
            arrival = self._parse_gmt_to_ca(item["connectionTime"])
            departure = self._parse_gmt_to_ca(item["disconnectTime"])

            if arrival < global_start or arrival >= global_end:
                continue

            inst_idx = int(
                (arrival - global_start).total_seconds()
                // self.instance_length.total_seconds()
            )

            inst_start, inst_end = instance_windows[inst_idx]

            arrival = max(arrival, inst_start)
            departure = min(departure, inst_end)

            arrival_idx = self._time_to_index(arrival, inst_start)
            departure_idx = self._time_to_index(departure, inst_start)
            if departure_idx > arrival_idx + 15:
                departure_idx = arrival_idx + 15
            self.D_max = max(self.D_max, departure_idx - arrival_idx + 1)
            self.D_min = min(self.D_min, departure_idx - arrival_idx + 1)
            self.time_window = max(self.time_window, arrival_idx + 1, departure_idx + 1)

            energy = item.get("kWhDelivered", 5)

            energy /= 5

            rateLimit = 0
            if "userInputs" in item and item["userInputs"] is not None:
                for ui in item["userInputs"]:
                    if "kWhRequested" in ui and "minutesAvailable" in ui:
                        rate = (
                            max(ui["kWhRequested"], energy)
                            * self.delta_minutes
                            / ui["minutesAvailable"]
                        )
                        rateLimit = max(rateLimit, rate)

            if rateLimit == 0:
                rateLimit = 3

            ev = {
                "arrival": arrival_idx,
                "departure": departure_idx,
                "demand": energy,
                "rateLimit": rateLimit,
                "id": item.get("_id"),
                "batch": 0,
            }
            fav_station = random.randrange(self.num_stations)
            for i in range(self.ev_multiplier):
                ev_i = dict(ev)
                ev_i["batch"] = i + 1

                if self.value_mode == "stationwise":
                    ev_i["favorite_station"] = fav_station
                    ev_i["value"] = self.get_value_favorite(
                        energy, batch_idx=i, favorite_station=fav_station
                    )
                else:
                    ev_i["value"] = self.get_value(energy, batch_idx=i)

                self.instances[inst_idx].append(ev_i)
                self.total_evs += 1
        for inst_idx in range(len(self.instances)):
            self.instances[inst_idx] = sorted(
                self.instances[inst_idx],
                key=lambda x: (x["batch"], x["arrival"], x["departure"]),
            )

        print(
            f"[EVDataLoader] Data loading completed.\n"
            f"  • Number of instances      : {len(self.instances)}\n"
            f"  • Total EVs loaded          : {self.total_evs}\n"
            f"  • Instance length (hours)   : {self.instance_length.total_seconds() / 3600}\n"
            f"  • Time discretization (min) : {self.delta_minutes}\n"
            f"  • Time window (# of slots per instance)        : {self.time_window}\n"
        )
