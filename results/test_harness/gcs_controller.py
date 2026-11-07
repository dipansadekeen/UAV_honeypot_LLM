#!/usr/bin/env python3
"""Local MAVLink Ground Control dashboard for UAV_honeypot_LLM.

Dependencies:
    pip install pymavlink matplotlib

Examples:
    python gcs_controller.py
    python gcs_controller.py --listen-port 14550 --target-port 14551

Run the honeypot separately with: python module_main.py

The dashboard binds 127.0.0.1:14550 and sends MAVLink COMMAND_LONG packets
from system/component 255/190 to the honeypot at 127.0.0.1:14551.
It never connects to a physical flight controller by default.
"""
from __future__ import annotations

import argparse
import math
import queue
import socket
import threading
import time
import tkinter as tk
from collections import defaultdict, deque
from datetime import datetime
from tkinter import messagebox, ttk

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
from pymavlink import mavutil

MAV = mavutil.mavlink

COMMAND_NAMES = {
    400: "ARM / DISARM",
    22: "TAKEOFF",
    16: "WAYPOINT",
    21: "LAND",
    20: "RTL",
    512: "REQUEST HEARTBEAT",
}

PX4_MAIN_MODES = {
    0: "UNSET", 1: "MANUAL", 2: "ALTCTL", 3: "POSCTL",
    4: "AUTO", 5: "ACRO", 6: "OFFBOARD", 7: "STABILIZED",
    8: "RATTITUDE", 9: "SIMPLE",
}
PX4_AUTO_SUBMODES = {
    0: "UNSET", 1: "READY", 2: "TAKEOFF", 3: "LOITER", 4: "MISSION",
    5: "RTL", 6: "LAND", 7: "RTGS", 8: "FOLLOW_TARGET",
    9: "PRECLAND", 10: "VTOL_TAKEOFF",
}


def decode_px4_mode(custom_mode: int, autopilot: int) -> str:
    """Decode PX4 custom_mode if the heartbeat advertises PX4; always keep raw integer."""
    if int(autopilot) != int(MAV.MAV_AUTOPILOT_PX4):
        return f"Non-PX4 autopilot ({autopilot}) — raw only"
    main = (int(custom_mode) >> 16) & 0xFF
    sub = (int(custom_mode) >> 24) & 0xFF
    mode = PX4_MAIN_MODES.get(main, f"MAIN {main}")
    if main == 4:
        mode += " / " + PX4_AUTO_SUBMODES.get(sub, f"SUB {sub}")
    return f"{mode}    [main={main}, sub={sub}]"


class MavlinkUDP:
    """Single socket: sends to the honeypot, listens for replies on the GCS port."""

    def __init__(self, listen_ip: str, listen_port: int, target_ip: str,
                 target_port: int, events: queue.Queue):
        self.events = events
        self.target = (target_ip, target_port)
        self.stop = threading.Event()
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind((listen_ip, listen_port))
        self.sock.settimeout(0.25)
        self.out = MAV.MAVLink(None)
        self.out.srcSystem = 255
        self.out.srcComponent = 190
        self.parser = MAV.MAVLink(None)
        self.send_lock = threading.Lock()
        self.thread = threading.Thread(target=self._receive, name="MAVLink RX", daemon=True)
        self.thread.start()

    def _put(self, item: dict) -> None:
        try:
            self.events.put_nowait(item)
        except queue.Full:
            pass

    def _receive(self) -> None:
        while not self.stop.is_set():
            try:
                datagram, address = self.sock.recvfrom(65535)
            except socket.timeout:
                continue
            except OSError:
                break
            if address != self.target:
                continue  # Dashboard is dedicated to this local honeypot endpoint.
            for byte in datagram:
                try:
                    msg = self.parser.parse_char(bytes([byte]))
                except Exception as ex:
                    self._put({"kind": "error", "message": f"MAVLink parse error: {ex}"})
                    continue
                if msg is not None and msg.get_type() != "BAD_DATA":
                    self._put({"kind": "rx", "message": msg, "at": time.monotonic()})

    def command(self, target_system: int, target_component: int,
                command_id: int, params: list[float] | tuple[float, ...]):
        if len(params) != 7:
            raise ValueError("Exactly seven MAVLink parameters required")
        if not all(math.isfinite(float(p)) for p in params):
            raise ValueError("All command parameters must be finite")
        with self.send_lock:
            msg = self.out.command_long_encode(
                int(target_system), int(target_component), int(command_id), 0,
                *[float(p) for p in params]
            )
            data = msg.pack(self.out)
            self.sock.sendto(data, self.target)

    def close(self):
        self.stop.set()
        self.sock.close()


class GroundStation(tk.Tk):
    def __init__(self, args):
        super().__init__()
        self.title("UAV Honeypot  |  MAVLink Ground Control Dashboard")
        self.geometry("1300x1000")
        self.minsize(1080, 740)
        self.configure(bg="#f4f7fb")
        self.configure_style()
        self.started = time.monotonic()
        self.last_hb = 0.0
        self.hb_count = 0
        self.last_hb_interval = None
        self.target_system = 1
        self.target_component = 1
        self.events = queue.Queue(maxsize=5000)
        self.pending = defaultdict(deque)
        self.hb_history = deque(maxlen=220)
        self.alt_history = deque(maxlen=1500)
        self.vars = {name: tk.StringVar(value="—") for name in (
            "link", "heartbeat", "src", "armed", "base", "custom",
            "decoded", "status", "alt", "latlon", "battery", "ack", "landed"
        )}
        self.vars["link"].set("Waiting for heartbeat")
        self.vars["heartbeat"].set("No heartbeat received")
        self.takeoff_alt = tk.StringVar(value="10.0")
        self.wp_lat = tk.StringVar(value="47.3979709")
        self.wp_lon = tk.StringVar(value="8.5461637")
        self.wp_alt = tk.StringVar(value="10.0")
        self._build(args)
        try:
            self.link = MavlinkUDP(args.listen_ip, args.listen_port,
                                   args.target_ip, args.target_port, self.events)
            self.log(f"LISTEN {args.listen_ip}:{args.listen_port} | SEND {args.target_ip}:{args.target_port}")
            self.log("Waiting for honeypot heartbeat; default target system/component = 1/1")
        except OSError as ex:
            messagebox.showerror("UDP port unavailable", f"Cannot bind GCS socket: {ex}\n\n"
                                 "Close QGroundControl or change the listen port.")
            self.destroy()
            return
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.after(150, self._process_events)
        self.after(1000, self._refresh_plot)

    def configure_style(self):
        s = ttk.Style(self)
        if "clam" in s.theme_names():
            s.theme_use("clam")
        s.configure("Root.TFrame", background="#f4f7fb")
        s.configure("Panel.TFrame", background="#ffffff")
        s.configure("Panel.TLabelframe", background="#ffffff", bordercolor="#d7e0e8")
        s.configure("Panel.TLabelframe.Label", background="#ffffff", foreground="#263953", font=("Segoe UI", 11, "bold"))
        s.configure("Metric.TLabel", background="#ffffff", foreground="#63758a", font=("Segoe UI", 9))
        s.configure("Value.TLabel", background="#ffffff", foreground="#15263d", font=("Segoe UI", 12, "bold"))
        s.configure("Title.TLabel", background="#f4f7fb", foreground="#172941", font=("Segoe UI", 19, "bold"))
        s.configure("Info.TLabel", background="#f4f7fb", foreground="#65788d", font=("Segoe UI", 9))
        s.configure("Action.TButton", padding=(10, 5), font=("Segoe UI", 10, "bold"))
        s.configure("Danger.TButton", padding=(10, 5), font=("Segoe UI", 10, "bold"))

    def _metric(self, parent, name: str, caption: str, row: int, col: int,
                col_span: int = 1):
        cell = ttk.Frame(parent, style="Panel.TFrame")
        cell.grid(row=row, column=col, columnspan=col_span, sticky="nsew", padx=9, pady=4)
        ttk.Label(cell, text=caption, style="Metric.TLabel").pack(anchor="w")
        ttk.Label(cell, textvariable=self.vars[name], style="Value.TLabel",
                  wraplength=330).pack(anchor="w")

    def _build(self, args):
        outer = ttk.Frame(self, style="Root.TFrame", padding=(18, 12))
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(3, weight=1, minsize=500)
        outer.rowconfigure(4, minsize=152)
        ttk.Label(outer, text="UAV Honeypot • MAVLink GCS", style="Title.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(outer, text=f"Receive  {args.listen_ip}:{args.listen_port}     →     Honeypot  {args.target_ip}:{args.target_port}     |     Local test dashboard",
                  style="Info.TLabel").grid(row=1, column=0, sticky="w", pady=(1, 10))

        metrics = ttk.LabelFrame(outer, text="LIVE HEARTBEAT / VEHICLE STATE", style="Panel.TLabelframe", padding=10)
        metrics.grid(row=2, column=0, sticky="ew", pady=(0, 12))
        for c in range(4):
            metrics.columnconfigure(c, weight=1)
        self._metric(metrics, "link", "CONNECTION", 0, 0)
        self._metric(metrics, "heartbeat", "HEARTBEAT RATE / AGE", 0, 1)
        self._metric(metrics, "armed", "ARM STATE", 0, 2)
        self._metric(metrics, "src", "HEARTBEAT SYSTEM / COMPONENT", 0, 3)
        self._metric(metrics, "custom", "CUSTOM_MODE (RAW UINT32)", 1, 0)
        self._metric(metrics, "decoded", "PX4 CUSTOM MODE / SUBMODE", 1, 1)
        self._metric(metrics, "base", "BASE_MODE (BITMASK)", 1, 2)
        self._metric(metrics, "status", "SYSTEM_STATUS", 1, 3)

        center = ttk.Frame(outer, style="Root.TFrame")
        center.grid(row=3, column=0, sticky="nsew")
        center.columnconfigure(0, weight=0)
        center.columnconfigure(1, weight=1)
        center.rowconfigure(0, weight=1)

        commands = ttk.LabelFrame(center, text="SEND MAVLINK COMMANDS", style="Panel.TLabelframe", padding=12)
        commands.grid(row=0, column=0, sticky="nsw", padx=(0, 11))
        ttk.Label(commands, text="COMMAND_LONG → honeypot", style="Metric.TLabel").pack(anchor="w", pady=(0, 7))
        row = ttk.Frame(commands, style="Panel.TFrame")
        row.pack(fill="x", pady=(0, 5))
        ttk.Button(row, text="ARM", style="Action.TButton", width=14,
                   command=lambda: self._send("ARM", 400, [1, 0, 0, 0, 0, 0, 0])).pack(side="left", padx=(0, 5))
        ttk.Button(row, text="DISARM", style="Danger.TButton", width=14,
                   command=lambda: self._send("DISARM", 400, [0, 0, 0, 0, 0, 0, 0])).pack(side="left")

        ttk.Separator(commands).pack(fill="x", pady=7)
        ttk.Label(commands, text="TAKEOFF  •  Altitude in meters", style="Value.TLabel").pack(anchor="w", pady=(0, 4))
        row = ttk.Frame(commands, style="Panel.TFrame")
        row.pack(fill="x")
        ttk.Entry(row, textvariable=self.takeoff_alt, width=12).pack(side="left", padx=(0, 8))
        ttk.Button(row, text="TAKEOFF", style="Action.TButton", width=15,
                   command=self.takeoff).pack(side="left")

        ttk.Separator(commands).pack(fill="x", pady=9)
        ttk.Label(commands, text="GO TO WAYPOINT", style="Value.TLabel").pack(anchor="w", pady=(0, 5))
        for label, var in (("Latitude", self.wp_lat),
                           ("Longitude", self.wp_lon),
                           ("Altitude (m)", self.wp_alt)):
            row = ttk.Frame(commands, style="Panel.TFrame")
            row.pack(fill="x", pady=3)
            ttk.Label(row, text=label, style="Metric.TLabel", width=14).pack(side="left")
            ttk.Entry(row, textvariable=var, width=21).pack(side="left")
        ttk.Button(commands, text="GO TO WAYPOINT", style="Action.TButton", width=29,
                   command=self.waypoint).pack(anchor="w", pady=(5, 0))

        ttk.Separator(commands).pack(fill="x", pady=10)
        row = ttk.Frame(commands, style="Panel.TFrame")
        row.pack(fill="x", pady=2)
        ttk.Button(row, text="LAND", style="Action.TButton", width=14,
                   command=lambda: self._send("LAND", 21, [0] * 7)).pack(side="left", padx=(0, 5))
        ttk.Button(row, text="RTL", style="Action.TButton", width=14,
                   command=lambda: self._send("RTL", 20, [0] * 7)).pack(side="left")
        ttk.Button(commands, text="REQUEST HEARTBEAT", width=29,
                   command=lambda: self._send("REQUEST HEARTBEAT", 512, [0] * 7)).pack(anchor="w", pady=(11, 3))
        ttk.Label(commands, text="ACK confirms receipt/admission, not physical\ncompletion of a flight maneuver.",
                  style="Metric.TLabel").pack(anchor="w", pady=(7, 0))

        right = ttk.Frame(center, style="Root.TFrame")
        right.grid(row=0, column=1, sticky="nsew")
        right.rowconfigure(1, weight=1)
        right.columnconfigure(0, weight=1)
        telem = ttk.LabelFrame(right, text="LIVE TELEMETRY", style="Panel.TLabelframe", padding=9)
        telem.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        for c in range(4):
            telem.columnconfigure(c, weight=1)
        self._metric(telem, "alt", "RELATIVE ALTITUDE", 0, 0)
        self._metric(telem, "latlon", "LATITUDE / LONGITUDE", 0, 1)
        self._metric(telem, "battery", "BATTERY", 0, 2)
        self._metric(telem, "landed", "LANDED STATE", 0, 3)
        self._metric(telem, "ack", "LAST COMMAND ACK", 1, 0, 4)

        graphframe = ttk.LabelFrame(right, text="HEARTBEAT CUSTOM_MODE / ALTITUDE HISTORY", style="Panel.TLabelframe", padding=5)
        graphframe.grid(row=1, column=0, sticky="nsew")
        self.fig = Figure(figsize=(8.1, 4), dpi=100, facecolor="white")
        self.ax_mode = self.fig.add_subplot(211)
        self.ax_alt = self.fig.add_subplot(212)
        self.fig.subplots_adjust(left=0.11, right=0.97, top=0.94, bottom=0.13, hspace=0.43)
        self.canvas = FigureCanvasTkAgg(self.fig, master=graphframe)
        self.canvas.get_tk_widget().pack(fill="both", expand=True)
        self._draw_chart()

        bottom = ttk.Frame(outer, style="Root.TFrame")
        bottom.grid(row=4, column=0, sticky="nsew", pady=(12, 0))
        pan = ttk.Panedwindow(bottom, orient=tk.HORIZONTAL)
        pan.pack(fill="both", expand=True)
        history = ttk.LabelFrame(pan, text="RECENT HEARTBEATS", style="Panel.TLabelframe", padding=6)
        self.hb_tree = ttk.Treeview(history, show="headings", height=7,
                                    columns=("time", "base", "custom", "mode", "arm"))
        widths = (78, 70, 120, 170, 85)
        labels = ("Time", "Base", "Custom mode", "PX4 mode", "Armed")
        for key, label, width in zip(self.hb_tree["columns"], labels, widths):
            self.hb_tree.heading(key, text=label)
            self.hb_tree.column(key, width=width, minwidth=50)
        self.hb_tree.pack(fill="both", expand=True)
        pan.add(history, weight=2)
        logs = ttk.LabelFrame(pan, text="COMMAND / ACK EVENTS", style="Panel.TLabelframe", padding=6)
        self.console = tk.Text(logs, height=8, wrap="word", bg="#132035", fg="#e0eafa",
                               insertbackground="white", font=("Consolas", 9), relief="flat")
        self.console.pack(fill="both", expand=True)
        self.console.config(state="disabled")
        pan.add(logs, weight=3)

    def _send(self, label: str, command_id: int, params):
        if not hasattr(self, "link"):
            return
        try:
            self.link.command(self.target_system, self.target_component, command_id, params)
            self.pending[command_id].append(label)
            self.log(f"TX  {label:<20} cmd={command_id}  params={list(params)}")
            if not self.last_hb:
                self.log("WARN No heartbeat yet; UDP delivery is unconfirmed.")
        except (OSError, ValueError) as ex:
            messagebox.showerror("Send failed", str(ex))
            self.log(f"ERROR Cannot send {label}: {ex}")

    @staticmethod
    def _validated_number(value, label, lower=None, upper=None):
        try:
            v = float(value)
        except ValueError as ex:
            raise ValueError(f"{label} must be a number") from ex
        if not math.isfinite(v):
            raise ValueError(f"{label} must be finite")
        if (lower is not None and v < lower) or (upper is not None and v > upper):
            raise ValueError(f"{label} must be between {lower} and {upper}")
        return v

    def takeoff(self):
        try:
            alt = self._validated_number(self.takeoff_alt.get(), "Takeoff altitude", 0.01, 10000)
        except ValueError as ex:
            messagebox.showwarning("Invalid takeoff", str(ex))
            return
        self._send("TAKEOFF", 22, [0, 0, 0, 0, 0, 0, alt])

    def waypoint(self):
        try:
            lat = self._validated_number(self.wp_lat.get(), "Latitude", -90, 90)
            lon = self._validated_number(self.wp_lon.get(), "Longitude", -180, 180)
            alt = self._validated_number(self.wp_alt.get(), "Waypoint altitude", 0.01, 10000)
        except ValueError as ex:
            messagebox.showwarning("Invalid waypoint", str(ex))
            return
        # The honeypot converts COMMAND_LONG p5/p6 degrees to int(degrees*1e7).
        self._send("WAYPOINT", 16, [0, 0, 0, 0, lat, lon, alt])

    def log(self, message: str):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.console.config(state="normal")
        self.console.insert("end", f"[{timestamp}] {message}\n")
        if int(self.console.index("end-1c").split(".")[0]) > 350:
            self.console.delete("1.0", "50.0")
        self.console.see("end")
        self.console.config(state="disabled")

    def _process_events(self):
        try:
            for _ in range(600):
                try:
                    item = self.events.get_nowait()
                except queue.Empty:
                    break
                if item["kind"] == "error":
                    self.log("WARN " + item["message"])
                else:
                    self._on_mav(item["message"], item["at"])
            if self.last_hb:
                age = time.monotonic() - self.last_hb
                self.vars["link"].set("● CONNECTED" if age < 3.5 else "● HEARTBEAT LOST")
                interval = "—" if self.last_hb_interval is None else f"{1/self.last_hb_interval:.2f} Hz"
                self.vars["heartbeat"].set(f"{interval}  |  age {age:.1f} s  |  count {self.hb_count}")
            self.after(150, self._process_events)
        except tk.TclError:
            pass

    def _on_mav(self, msg, at: float):
        t = msg.get_type()
        if t == "HEARTBEAT":
            if self.last_hb:
                self.last_hb_interval = at - self.last_hb
            self.last_hb = at
            self.hb_count += 1
            self.target_system = msg.get_srcSystem()
            self.target_component = msg.get_srcComponent()
            base = int(msg.base_mode)
            custom = int(msg.custom_mode)
            armed = bool(base & MAV.MAV_MODE_FLAG_SAFETY_ARMED)
            mode = decode_px4_mode(custom, int(msg.autopilot))
            self.vars["src"].set(f"{self.target_system} / {self.target_component}")
            self.vars["armed"].set("ARMED" if armed else "DISARMED")
            self.vars["base"].set(f"{base}  (0x{base:02X})")
            self.vars["custom"].set(str(custom))
            self.vars["decoded"].set(mode)
            try:
                status = MAV.enums["MAV_STATE"][int(msg.system_status)].name.replace("MAV_STATE_", "")
            except (KeyError, AttributeError):
                status = str(msg.system_status)
            self.vars["status"].set(status)
            self.hb_history.append((at - self.started, custom))
            vals = (datetime.now().strftime("%H:%M:%S"), base, custom,
                    mode.split("    ")[0], "YES" if armed else "NO")
            self.hb_tree.insert("", 0, values=vals)
            children = self.hb_tree.get_children()
            if len(children) > 24:
                self.hb_tree.delete(*children[24:])
        elif t == "COMMAND_ACK":
            cmd = int(msg.command)
            result = int(msg.result)
            try:
                result_name = MAV.enums["MAV_RESULT"][result].name.replace("MAV_RESULT_", "")
            except (KeyError, AttributeError):
                result_name = f"RESULT_{result}"
            label = self.pending[cmd].popleft() if self.pending[cmd] else COMMAND_NAMES.get(cmd, str(cmd))
            self.vars["ack"].set(f"{label} ({cmd}): {result_name}")
            self.log(f"ACK {label:<20} cmd={cmd}  {result_name}")
        elif t == "GLOBAL_POSITION_INT":
            lat = int(msg.lat) / 1e7
            lon = int(msg.lon) / 1e7
            alt = int(msg.relative_alt) / 1000
            self.vars["latlon"].set(f"{lat:.6f}, {lon:.6f}")
            self.vars["alt"].set(f"{alt:.2f} m")
            self.alt_history.append((at - self.started, alt))
        elif t == "VFR_HUD":
            if self.vars["alt"].get() == "—":
                self.vars["alt"].set(f"{float(msg.alt):.2f} m (VFR)")
        elif t == "SYS_STATUS":
            rem = int(msg.battery_remaining)
            volts = int(msg.voltage_battery) / 1000
            self.vars["battery"].set(f"{rem}%  |  {volts:.2f} V")
        elif t == "EXTENDED_SYS_STATE":
            landed_states = {0: "UNDEFINED", 1: "ON GROUND", 2: "IN AIR",
                             3: "TAKEOFF", 4: "LANDING"}
            value = int(msg.landed_state)
            self.vars["landed"].set(landed_states.get(value, str(value)))

    def _draw_chart(self):
        for axis in (self.ax_mode, self.ax_alt):
            axis.clear()
            axis.grid(alpha=0.2)
            axis.tick_params(labelsize=8)
        if self.hb_history:
            t, v = zip(*self.hb_history)
            self.ax_mode.step(t, v, where="post", color="#2667bc", lw=2, marker=".", ms=3)
            self.ax_mode.set_xlim(max(0, t[-1] - 120), max(12, t[-1] + 2))
            self.ax_mode.ticklabel_format(style="plain", axis="y", useOffset=False)
        else:
            self.ax_mode.text(0.5, 0.52, "Waiting for HEARTBEAT...", ha="center",
                              va="center", transform=self.ax_mode.transAxes, color="#708095")
        self.ax_mode.set_ylabel("custom_mode", fontsize=9)
        self.ax_mode.set_title("HEARTBEAT.custom_mode (raw value)", fontsize=10, loc="left")
        if self.alt_history:
            t, v = zip(*self.alt_history)
            self.ax_alt.plot(t, v, color="#1a9679", lw=1.8)
            self.ax_alt.set_xlim(max(0, t[-1] - 120), max(12, t[-1] + 2))
        else:
            self.ax_alt.text(0.5, 0.5, "Waiting for GLOBAL_POSITION_INT...", ha="center",
                             va="center", transform=self.ax_alt.transAxes, color="#708095")
        self.ax_alt.set_ylabel("altitude (m)", fontsize=9)
        self.ax_alt.set_xlabel("Elapsed time (seconds)", fontsize=9)
        self.ax_alt.set_title("GLOBAL_POSITION_INT.relative_alt", fontsize=10, loc="left")
        self.canvas.draw_idle()

    def _refresh_plot(self):
        self._draw_chart()
        try:
            self.after(1000, self._refresh_plot)
        except tk.TclError:
            pass

    def _close(self):
        if hasattr(self, "link"):
            self.link.close()
        self.destroy()


def main():
    parser = argparse.ArgumentParser(description="Local UAV honeypot MAVLink command + heartbeat GUI")
    parser.add_argument("--listen-ip", default="127.0.0.1")
    parser.add_argument("--listen-port", type=int, default=14550)
    parser.add_argument("--target-ip", default="127.0.0.1")
    parser.add_argument("--target-port", type=int, default=14551)
    args = parser.parse_args()
    GroundStation(args).mainloop()


if __name__ == "__main__":
    main()
