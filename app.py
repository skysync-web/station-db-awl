#!/usr/bin/env python3
"""
Siemens Step7 - Global DB AWL Generator  v5.0
20 DB pages (DB11-DB30), station-name builder, robot config, valve island config,
auto-generates: O_I, A_I, AB, RQT, Aux_Cycle, Mem_Cycle, TIO_D sections.
All auto-generated sections default to RESERVE first, then overwrite specific fields.
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import json
import re
import os
import sys
import copy

# ============================================================================
# CONSTANTS
# ============================================================================

DB_FIRST, DB_LAST = 11, 30
DB_RANGE = range(DB_FIRST, DB_LAST + 1)

REGULAR_PART2 = ["T", "TT", "LIFT"]
ROBOT_PART2 = ["R"]
MAX_ISLANDS = 2
MAX_VALVES = 10
MAX_UNITS = 8

ACTUATOR_TYPES = ["Clamp", "Shift Pin", "Swivel Unit", "Linear Unit"]

ACTUATOR_PLURAL = {
    "Clamp": "Clamps",
    "Shift Pin": "Shift Pins",
    "Swivel Unit": "Swivel Unit",
    "Linear Unit": "Linear Unit",
}
ACTUATOR_CMD = {
    "Clamp": "CLAMP ",
    "Shift Pin": "PIN   ",
    "Swivel Unit": "SWIVEL",
    "Linear Unit": "LINEAR",
}
ACTUATOR_RQT = {
    "Clamp": "Clamp",
    "Shift Pin": "Pin  ",
    "Swivel Unit": "Swvl ",
    "Linear Unit": "Lin  ",
}
ACTUATOR_AUX = {
    "Clamp": "Clamps",
    "Shift Pin": "Shift Pins",
    "Swivel Unit": "Swivel Unit",
    "Linear Unit": "Linear Unit",
}

TEMPLATE_NAME = "db11.AWL"

SECTION_NAMES = [
    "Header", "F_Gen", "Cycle", "F_Prim",
    "O_I", "AB", "A_I", "RQM", "RQT",
    "Aux_Cycle", "Mem_Cycle", "PICS", "MG",
    "TIO_D", "Type_Element_Code",
]

AUTO_GEN_SECTIONS = [
    "O_I", "AB", "A_I", "RQM", "RQT",
    "Aux_Cycle", "Mem_Cycle", "MG", "TIO_D",
]

# ============================================================================
# AWL TEMPLATE PARSER
# ============================================================================

def find_template():
    """Find the db11.AWL template file."""
    candidates = [
        os.path.join(os.path.dirname(os.path.abspath(__file__)), TEMPLATE_NAME),
        os.path.join(os.getcwd(), TEMPLATE_NAME),
    ]
    for p in candidates:
        if os.path.isfile(p):
            return p
    return None


def parse_awl_template(path):
    """
    Parse the AWL template file.
    Returns:
        sections: dict of section_name -> list of (field_name, field_type, comment)
        begin_values: dict of dotted_path -> value_string
        raw_lines: list of all lines
    """
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        raw_lines = f.readlines()

    sections = {}
    begin_values = {}
    current_section = []
    section_stack = []
    in_struct = False
    in_begin = False
    header_lines = []

    for line in raw_lines:
        stripped = line.strip()

        if stripped.startswith("BEGIN"):
            in_begin = True
            continue

        if stripped.startswith("END_DATA_BLOCK"):
            break

        if in_begin:
            # Parse BEGIN assignments: path := value;
            m = re.match(r'\s*(\S+)\s*:=\s*(.+?)\s*;\s*$', line)
            if m:
                begin_values[m.group(1).strip()] = m.group(2).strip()
            continue

        # Before BEGIN: parse STRUCT definitions
        if not in_struct and not section_stack:
            # Look for first STRUCT
            if "STRUCT" in stripped and "END_STRUCT" not in stripped:
                in_struct = True
                section_stack.append("root")
                current_section = []
            else:
                header_lines.append(line)
            continue

        # Inside struct definitions
        if "END_STRUCT" in stripped:
            if section_stack:
                sec_name = section_stack.pop()
                if sec_name != "root" and sec_name not in sections:
                    sections[sec_name] = current_section
                current_section = []
            continue

        # Check for nested STRUCT field
        m = re.match(r'\s*(\w+)\s*:\s*STRUCT\s*(;)?\s*(//(.*))?', stripped)
        if m:
            sec_name = m.group(1)
            comment = m.group(4).strip() if m.group(4) else ""
            section_stack.append(sec_name)
            sections[sec_name] = []
            current_section = sections[sec_name]
            continue

        # Check for ARRAY field
        m_arr = re.match(r'\s*(\w+)\s*:\s*ARRAY\s*\[\s*(\d+)\s*\.\.\s*(\d+)\s*\]\s*OF\s*(//(.*))?', stripped)
        if m_arr:
            fname = m_arr.group(1)
            comment = m_arr.group(5).strip() if m_arr.group(5) else ""
            if section_stack:
                sections.setdefault(section_stack[-1], [])
                sections[section_stack[-1]].append((fname, "ARRAY", comment))
            continue

        # Regular field
        m_field = re.match(r'\s*(\w+)\s*:\s*(\w+)\s*;?\s*(//(.*))?', stripped)
        if m_field:
            fname = m_field.group(1)
            ftype = m_field.group(2)
            comment = m_field.group(4).strip() if m_field.group(4) else ""
            if section_stack:
                sections.setdefault(section_stack[-1], [])
                sections[section_stack[-1]].append((fname, ftype, comment))

    return sections, begin_values, raw_lines, header_lines


# ============================================================================
# AWL GENERATION
# ============================================================================

def generate_awl(db_number, station_name, db_name, sections_data, template_path):
    """
    Generate a complete AWL file from template, replacing comments in
    specified sections with values from sections_data.

    sections_data: dict of section_name -> dict of field_index -> comment_string
    """
    with open(template_path, "r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()

    # Replace DATA_BLOCK name
    new_lines = []
    current_section = None
    section_stack = []
    in_begin = False

    for line in lines:
        stripped = line.strip()

        # Replace DB name on first line
        if stripped.startswith('DATA_BLOCK'):
            new_lines.append(f'DATA_BLOCK "{db_name}"\n')
            continue

        # Track section context for STRUCT
        if "END_STRUCT" in stripped:
            if section_stack:
                section_stack.pop()
            current_section = section_stack[-1] if section_stack else None
            new_lines.append(line)
            continue

        m = re.match(r'\s*(\w+)\s*:\s*STRUCT\s*', stripped)
        if m and "END_STRUCT" not in stripped:
            sec_name = m.group(1)
            section_stack.append(sec_name)
            current_section = sec_name
            new_lines.append(line)
            continue

        if stripped.startswith("BEGIN"):
            in_begin = True
            new_lines.append(line)
            continue

        if stripped.startswith("END_DATA_BLOCK"):
            new_lines.append(line)
            continue

        # If we are in a section that has replacement data
        if current_section and current_section in sections_data and not in_begin:
            # Match field line like: _XX : BOOL ; //comment
            m_field = re.match(r'(\s*_(\d+)\s*:\s*\w+\s*;\s*)//(.*)', line)
            if m_field:
                prefix = m_field.group(1)
                field_idx = int(m_field.group(2))
                if field_idx in sections_data[current_section]:
                    new_comment = sections_data[current_section][field_idx]
                    new_lines.append(f"{prefix}//{new_comment}\n")
                    continue

        new_lines.append(line)

    return new_lines


# ============================================================================
# AUTO-GENERATION FUNCTIONS
# ============================================================================

def make_reserve_dict(start, end):
    """Create a dict mapping field indices to 'RESERVE'."""
    return {i: "RESERVE" for i in range(start, end + 1)}


def auto_gen_oi(station, islands_config):
    """
    Generate O_I section comments.
    Fields _00 to _95, all default RESERVE first.
    For each island, for each valve, 2 entries (work + rest).
    """
    comments = make_reserve_dict(0, 95)
    idx = 0
    for isl_idx, island in enumerate(islands_config, start=1):
        for v_idx, valve in enumerate(island, start=1):
            act_type = valve["type"]
            plural = ACTUATOR_PLURAL.get(act_type, act_type)
            work = f"O/I {idx:02d} Order Input {plural} at Work position {station}_{isl_idx:02d}V{v_idx:02d}A"
            rest = f"O/I {idx+1:02d} Order Input {plural} at Rest position {station}_{isl_idx:02d}V{v_idx:02d}B"
            comments[idx] = work
            comments[idx + 1] = rest
            idx += 2
    return comments


def auto_gen_ai(station, islands_config):
    """
    Generate A_I section comments. Same layout as O_I but with 'A/I' and 'Update Input'.
    """
    comments = make_reserve_dict(0, 95)
    idx = 0
    for isl_idx, island in enumerate(islands_config, start=1):
        for v_idx, valve in enumerate(island, start=1):
            act_type = valve["type"]
            plural = ACTUATOR_PLURAL.get(act_type, act_type)
            work = f"A/I {idx:02d} Update Input {plural} at Work position {station}_{isl_idx:02d}V{v_idx:02d}A"
            rest = f"A/I {idx+1:02d} Update Input {plural} at Rest position {station}_{isl_idx:02d}V{v_idx:02d}B"
            comments[idx] = work
            comments[idx + 1] = rest
            idx += 2
    return comments


def auto_gen_ab(station, islands_config, robot_names):
    """
    Generate AB section comments.
    All fields _00 to _95 default RESERVE first.
    Robot entries at _24+, valve fwd at _51/_61, valve bwd at _71/_81.
    """
    comments = make_reserve_dict(0, 95)

    # Robot-related entries starting at _24
    n_robots = len(robot_names)
    slot = 24
    for rname in robot_names:
        comments[slot] = f"START ROBOT {rname}"
        slot += 1

    if n_robots >= 2:
        all_names_space = " ".join(robot_names)
        all_names_dash = "-".join(robot_names)
        comments[slot] = f"CONSENT TO WELD {all_names_space} (JOB1)"
        slot += 1
        comments[slot] = f"WAITING END OF WELDING {all_names_space} (JOB1)"
        slot += 1
        comments[slot] = f"CONSENT TO EXIT {all_names_dash} (ACK JOB1)"
        slot += 1

    # Valve forward commands
    base_fwd = [51, 61]
    base_bwd = [71, 81]
    for isl_idx, island in enumerate(islands_config):
        if isl_idx >= 2:
            break
        fwd_base = base_fwd[isl_idx]
        bwd_base = base_bwd[isl_idx]
        for v_idx, valve in enumerate(island):
            act_type = valve["type"]
            cmd = ACTUATOR_CMD.get(act_type, "CLAMP ")
            vv = v_idx + 1
            isl_num = isl_idx + 1
            fwd_comment = f"{station}_{isl_num:02d}V{vv:02d}A {cmd} COMMAND FORWARD"
            bwd_comment = f"{station}_{isl_num:02d}V{vv:02d}B {cmd} COMMAND BACKWARD"
            comments[fwd_base + v_idx] = fwd_comment
            comments[bwd_base + v_idx] = bwd_comment

    return comments


def auto_gen_rqt(station, islands_config, robot_names):
    """
    Generate RQT section comments.
    Fields _00 to _95, all default RESERVE first.
    Robot entries at _22+, valve entries at _51/_61/_71/_81.
    """
    comments = make_reserve_dict(0, 95)

    n_robots = len(robot_names)

    # Robot START entries starting at _22
    for i, rname in enumerate(robot_names):
        comments[22 + i] = f"RQT {22+i:02d} [ST{station}] Wait robot {rname} START"

    # Robot detail entries: for each robot, 3 entries
    base_detail = 22 + n_robots
    for i, rname in enumerate(robot_names):
        offset = base_detail + i * 3
        comments[offset] = f"RQT {offset:02d} [ST{station}] Wait inside of station {rname}"
        comments[offset + 1] = f"RQT {offset+1:02d} [ST{station}] Wait robot {rname} end of welding"
        comments[offset + 2] = f"RQT {offset+2:02d} [ST{station}] Wait Out of interference {rname}"

    # Valve entries
    base_work = [51, 61]
    base_rest = [71, 81]
    for isl_idx, island in enumerate(islands_config):
        if isl_idx >= 2:
            break
        for v_idx, valve in enumerate(island):
            act_type = valve["type"]
            rqt_type = ACTUATOR_RQT.get(act_type, "Clamp")
            units = valve.get("units", [])
            unit_list = "-".join(units) if units else ""
            vv = v_idx + 1
            isl_num = isl_idx + 1

            w_slot = base_work[isl_idx] + v_idx
            r_slot = base_rest[isl_idx] + v_idx
            comments[w_slot] = f"RQT {w_slot:02d} [ST{station}] Wait {rqt_type} {unit_list} at work {isl_num:02d}V{vv:02d}A"
            comments[r_slot] = f"RQT {r_slot:02d} [ST{station}] Wait {rqt_type} {unit_list} at rest {isl_num:02d}V{vv:02d}B"

    return comments


def auto_gen_aux_cycle(station, islands_config, robot_names):
    """
    Generate Aux_Cycle section comments.
    Fields _01 to _95, all default RESERVE first.
    """
    comments = make_reserve_dict(1, 95)

    n_robots = len(robot_names)

    # No fault robot entries starting at _02
    for i, rname in enumerate(robot_names):
        comments[2 + i] = f"No fault robot {rname}"

    # Robot out of interference starting at _46
    for i, rname in enumerate(robot_names):
        comments[46 + i] = f"Aux. Robot {rname} out of interference from {station}"

    # Consent to weld / exit (if 2+ robots)
    if n_robots >= 2:
        all_names_dash = "-".join(robot_names)
        comments[61] = f"Aux. Consent To Weld {all_names_dash}"
        comments[62] = f"Aux. Consent Exit {all_names_dash}"

    # Valve interlocks starting at _17
    slot = 17
    for isl_idx, island in enumerate(islands_config):
        isl_num = isl_idx + 1
        for v_idx, valve in enumerate(island):
            act_type = valve["type"]
            aux_type = ACTUATOR_AUX.get(act_type, act_type)
            units = valve.get("units", [])
            # Extract 3-digit codes from unit names (e.g., "050C01" -> "C050")
            c_codes = []
            for u in units:
                m = re.match(r'(\d{3})C\d+', u)
                if m:
                    c_codes.append(f"C{m.group(1)}")
            c_str = "-".join(c_codes) if c_codes else ""
            vv = v_idx + 1
            yv = f"{isl_num:02d}YV{vv:02d}"
            comments[slot] = f"Aux {slot} Interlock Fwd {aux_type} {yv} {c_str}"
            comments[slot + 1] = f"Aux {slot+1} Interlock Bwd {aux_type} {yv} {c_str}"
            slot += 2

    return comments


def auto_gen_mem_cycle(station, robot_names):
    """
    Generate Mem_Cycle section comments.
    Fields _01 to _95, all default RESERVE first.
    For each robot i (0-indexed), base = 17 + i*8:
      base: MEMORY END JOB 1  ROBOT {short_name} End of welding {station}
      base+4: MEMORY CHANGE TIPS OK {robot_name}
    short_name = last 5 chars of robot name (e.g., '40R01' from '040R01')
    """
    comments = make_reserve_dict(1, 95)

    for i, rname in enumerate(robot_names):
        base = 17 + i * 8
        short_name = rname[1:] if len(rname) == 6 else rname[-5:]
        comments[base] = f"MEMORY END JOB 1  ROBOT {short_name} End of welding {station}"
        comments[base + 4] = f"MEMORY CHANGE TIPS OK {rname}"

    return comments


def auto_gen_tio_d(station, islands_config, robot_names):
    """
    Generate TIO_D section comments.
    Fields _00 to _383, all default RESERVE first.
    Robot fault entries at _11+, valve alarms at _32+.
    """
    comments = make_reserve_dict(0, 383)

    # station prefix for TIO_D: e.g., "040T01" -> "ST40_T01"
    st3 = station[:3]  # "040"
    suffix = station[3:]  # "T01"
    tio_prefix = f"ST{station[1:3]}_{suffix}"  # "ST40_T01"

    # Robot fault entries starting at _11
    for i, rname in enumerate(robot_names):
        comments[11 + i] = f"M/A  [ST{st3}] ROBOT FAULT {rname}"

    # Valve alarms starting at _32
    slot = 32
    for isl_idx, island in enumerate(islands_config):
        isl_num = isl_idx + 1
        for v_idx, valve in enumerate(island):
            vv = v_idx + 1
            units = valve.get("units", [])
            valve_ref = f"{tio_prefix}_{isl_num:02d}V{vv:02d}"

            # 3 header entries
            comments[slot] = f"M/A {valve_ref} Group message"
            comments[slot + 1] = f"M/A {valve_ref} Interlock error for Fwd."
            comments[slot + 2] = f"M/A {valve_ref} Interlock error for Bwd."
            slot += 3

            # Per-unit entries (5 per unit: 4 limit messages + 1 RESERVE separator)
            for unit in units:
                unit_ref = f"{valve_ref}_{unit}"
                comments[slot] = f"M/A {unit_ref} Limit pos. Fwd. has been left (without control)"
                comments[slot + 1] = f"M/A {unit_ref} Limit pos. Bwd. has been left (without control)"
                comments[slot + 2] = f"M/A {unit_ref} Limit pos. fwd. has not been left (control act.)"
                comments[slot + 3] = f"M/A {unit_ref} Limit pos. bwd. has not been left (control act.)"
                comments[slot + 4] = "RESERVE"
                slot += 5

    return comments


# ============================================================================
# PROJECT DATA MODEL
# ============================================================================

def default_db_page():
    """Create default data for one DB page."""
    return {
        "sections": {},  # section_name -> {field_idx: comment}
    }


def default_project():
    """Create a new empty project."""
    return {
        "station_type": "Regular",
        "part1": "",
        "part2": "T",
        "part3": "",
        "robot_count": 0,
        "robot_names": [],
        "hmi_loc": "1",
        "operator_load": False,
        "operator_load_count": "1",
        "drop_part_with_robot": False,
        "drop_part_robot_count": "1",
        "drop_part_robot_names": ["", ""],
        "pick_part_with_robot": False,
        "pick_part_robot_count": "1",
        "pick_part_robot_names": ["", ""],
        "islands": [
            {
                "enabled": True,
                "valve_count": 1,
                "valves": [{"type": "Clamp", "units": ""}
                           for _ in range(MAX_VALVES)],
            },
            {
                "enabled": False,
                "valve_count": 0,
                "valves": [{"type": "Clamp", "units": ""}
                           for _ in range(MAX_VALVES)],
            },
        ],
        "db_pages": {str(db): default_db_page() for db in DB_RANGE},
    }


# ============================================================================
# GUI APPLICATION
# ============================================================================

class AWLGeneratorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Siemens Step7 - DB AWL Generator v5.0")
        self.root.geometry("1280x820")
        self.root.minsize(1000, 700)

        self.project = default_project()
        self.template_path = find_template()
        self.template_sections = {}
        self.template_begin = {}
        self.template_lines = []
        self.template_header = []
        self.loaded_db_pages = set()

        if self.template_path:
            self._load_template()

        self._build_ui()
        self._bind_shortcuts()

    def _load_template(self):
        try:
            self.template_sections, self.template_begin, self.template_lines, self.template_header = \
                parse_awl_template(self.template_path)
        except Exception as e:
            messagebox.showerror("Template Error", f"Failed to parse template:\n{e}")

    def _bind_shortcuts(self):
        self.root.bind("<Control-o>", lambda e: self.load_project())
        self.root.bind("<Control-s>", lambda e: self.save_project())
        self.root.bind("<Control-g>", lambda e: self.generate_current_db())

    # ---- UI BUILDING -------------------------------------------------------

    def _build_ui(self):
        # Menu bar
        menubar = tk.Menu(self.root)
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Open Project  Ctrl+O", command=self.load_project)
        file_menu.add_command(label="Save Project  Ctrl+S", command=self.save_project)
        file_menu.add_separator()
        file_menu.add_command(label="Generate Current DB  Ctrl+G", command=self.generate_current_db)
        file_menu.add_command(label="Generate All DBs", command=self.generate_all_dbs)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.root.quit)
        menubar.add_cascade(label="File", menu=file_menu)
        self.root.config(menu=menubar)

        # Main paned window
        main_pw = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        main_pw.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Left panel: configuration
        left_frame = ttk.Frame(main_pw, width=380)
        main_pw.add(left_frame, weight=0)

        # Right panel: DB pages
        right_frame = ttk.Frame(main_pw)
        main_pw.add(right_frame, weight=1)

        self._build_config_panel(left_frame)
        self._build_db_notebook(right_frame)

    def _build_config_panel(self, parent):
        canvas = tk.Canvas(parent, borderwidth=0, highlightthickness=0)
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        scroll_frame = ttk.Frame(canvas)

        scroll_frame.bind("<Configure>",
                          lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scroll_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Enable mouse wheel scrolling
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        canvas.bind_all("<MouseWheel>", _on_mousewheel, add="+")

        self._build_station_config(scroll_frame)
        self._build_robot_config(scroll_frame)
        self._build_valve_config(scroll_frame)
        self._build_extra_config(scroll_frame)
        self._build_action_buttons(scroll_frame)

    def _build_station_config(self, parent):
        frame = ttk.LabelFrame(parent, text="Station Configuration", padding=8)
        frame.pack(fill=tk.X, padx=5, pady=5)

        # Station type
        type_frame = ttk.Frame(frame)
        type_frame.pack(fill=tk.X, pady=2)
        ttk.Label(type_frame, text="Type:").pack(side=tk.LEFT)
        self.station_type_var = tk.StringVar(value=self.project["station_type"])
        ttk.Radiobutton(type_frame, text="Regular", variable=self.station_type_var,
                        value="Regular", command=self._on_station_type_change).pack(side=tk.LEFT, padx=5)
        ttk.Radiobutton(type_frame, text="Robot", variable=self.station_type_var,
                        value="Robot", command=self._on_station_type_change).pack(side=tk.LEFT, padx=5)

        # Station name builder
        name_frame = ttk.Frame(frame)
        name_frame.pack(fill=tk.X, pady=2)

        ttk.Label(name_frame, text="Name:").pack(side=tk.LEFT)

        self.part1_var = tk.StringVar(value=self.project["part1"])
        self.part1_entry = ttk.Entry(name_frame, textvariable=self.part1_var, width=5)
        self.part1_entry.pack(side=tk.LEFT, padx=2)

        self.part2_var = tk.StringVar(value=self.project["part2"])
        self.part2_combo = ttk.Combobox(name_frame, textvariable=self.part2_var,
                                         values=REGULAR_PART2, width=5, state="readonly")
        self.part2_combo.pack(side=tk.LEFT, padx=2)

        self.part3_var = tk.StringVar(value=self.project["part3"])
        self.part3_entry = ttk.Entry(name_frame, textvariable=self.part3_var, width=4)
        self.part3_entry.pack(side=tk.LEFT, padx=2)

        self.valid_label = ttk.Label(name_frame, text="", foreground="red", font=("TkDefaultFont", 12))
        self.valid_label.pack(side=tk.LEFT, padx=5)

        # DB name display
        db_frame = ttk.Frame(frame)
        db_frame.pack(fill=tk.X, pady=2)
        ttk.Label(db_frame, text="DB Name:").pack(side=tk.LEFT)
        self.db_name_var = tk.StringVar(value="")
        ttk.Label(db_frame, textvariable=self.db_name_var, font=("Consolas", 10, "bold")).pack(side=tk.LEFT, padx=5)

        # Trace changes
        for var in (self.part1_var, self.part2_var, self.part3_var, self.station_type_var):
            var.trace_add("write", self._update_station_name)

        self._update_station_name()

    def _on_station_type_change(self):
        stype = self.station_type_var.get()
        if stype == "Regular":
            self.part2_combo.configure(values=REGULAR_PART2)
            if self.part2_var.get() not in REGULAR_PART2:
                self.part2_var.set(REGULAR_PART2[0])
        else:
            self.part2_combo.configure(values=ROBOT_PART2)
            self.part2_var.set(ROBOT_PART2[0])
        self._update_station_name()

    def _update_station_name(self, *args):
        p1 = self.part1_var.get().strip()
        p2 = self.part2_var.get().strip()
        p3 = self.part3_var.get().strip()
        name = f"{p1}{p2}{p3}"

        valid = bool(re.match(r'^\d{3}(T|TT|LIFT|R)\d{2}$', name))
        if valid:
            self.valid_label.configure(text="OK", foreground="green")
            self.db_name_var.set(f"G-DB_{name}")
        else:
            self.valid_label.configure(text="X", foreground="red")
            self.db_name_var.set("")

        self.project["station_type"] = self.station_type_var.get()
        self.project["part1"] = p1
        self.project["part2"] = p2
        self.project["part3"] = p3

        # Re-validate robot names when station prefix changes
        if hasattr(self, 'robot_name_vars'):
            for i in range(len(self.robot_name_vars)):
                self._validate_robot_name(i)

    def _build_robot_config(self, parent):
        frame = ttk.LabelFrame(parent, text="Robot Configuration", padding=8)
        frame.pack(fill=tk.X, padx=5, pady=5)

        count_frame = ttk.Frame(frame)
        count_frame.pack(fill=tk.X, pady=2)
        ttk.Label(count_frame, text="Number of station robots:").pack(side=tk.LEFT)
        self.robot_count_var = tk.StringVar(value=str(self.project["robot_count"]))
        self.robot_count_combo = ttk.Combobox(count_frame, textvariable=self.robot_count_var,
                                               values=["0", "1", "2", "3", "4"],
                                               width=3, state="readonly")
        self.robot_count_combo.pack(side=tk.LEFT, padx=5)
        self.robot_count_var.trace_add("write", self._on_robot_count_change)

        self.robot_entries_frame = ttk.Frame(frame)
        self.robot_entries_frame.pack(fill=tk.X, pady=2)
        self.robot_name_vars = []
        self.robot_valid_labels = []
        self._rebuild_robot_entries()

    def _on_robot_count_change(self, *args):
        try:
            count = int(self.robot_count_var.get())
        except ValueError:
            count = 0
        self.project["robot_count"] = count
        self._rebuild_robot_entries()

    def _rebuild_robot_entries(self):
        for w in self.robot_entries_frame.winfo_children():
            w.destroy()

        count = self.project["robot_count"]
        self.robot_name_vars = []
        self.robot_valid_labels = []

        # Pad existing robot_names list
        while len(self.project["robot_names"]) < count:
            self.project["robot_names"].append("")

        for i in range(count):
            row = ttk.Frame(self.robot_entries_frame)
            row.pack(fill=tk.X, pady=1)
            ttk.Label(row, text=f"Robot {i+1}:").pack(side=tk.LEFT)
            var = tk.StringVar(value=self.project["robot_names"][i] if i < len(self.project["robot_names"]) else "")
            entry = ttk.Entry(row, textvariable=var, width=10)
            entry.pack(side=tk.LEFT, padx=2)
            valid_lbl = ttk.Label(row, text="", foreground="red")
            valid_lbl.pack(side=tk.LEFT, padx=2)
            self.robot_name_vars.append(var)
            self.robot_valid_labels.append(valid_lbl)

            var.trace_add("write", lambda *a, idx=i: self._validate_robot_name(idx))
            self._validate_robot_name(i)

    def _validate_robot_name(self, idx):
        if idx >= len(self.robot_name_vars):
            return
        name = self.robot_name_vars[idx].get().strip()
        station_prefix = self.project.get("part1", "")
        valid = bool(re.match(r'^\d{3}R\d{2}$', name))
        # First 3 digits must match station first 3 digits
        if valid and station_prefix and name[:3] != station_prefix:
            valid = False
        if valid:
            self.robot_valid_labels[idx].configure(text="OK", foreground="green")
        elif name and station_prefix and re.match(r'^\d{3}R\d{2}$', name) and name[:3] != station_prefix:
            self.robot_valid_labels[idx].configure(text=f"Must start with {station_prefix}", foreground="red")
        else:
            self.robot_valid_labels[idx].configure(text="X", foreground="red")

        # Update project
        while len(self.project["robot_names"]) <= idx:
            self.project["robot_names"].append("")
        self.project["robot_names"][idx] = name

    def _get_robot_names(self):
        """Get validated robot names from current UI state."""
        station_prefix = self.project.get("part1", "")
        names = []
        for var in self.robot_name_vars:
            name = var.get().strip()
            if re.match(r'^\d{3}R\d{2}$', name) and (not station_prefix or name[:3] == station_prefix):
                names.append(name)
        return names

    def _build_valve_config(self, parent):
        frame = ttk.LabelFrame(parent, text="Valve Island Configuration", padding=8)
        frame.pack(fill=tk.X, padx=5, pady=5)

        self.island_frames = []
        self.island_enabled_vars = []
        self.island_valve_count_vars = []
        self.valve_type_vars = []
        self.valve_unit_vars = []
        self.valve_widgets = []

        for isl in range(MAX_ISLANDS):
            isl_frame = ttk.LabelFrame(frame, text=f"BM{isl+1:02d}", padding=5)
            isl_frame.pack(fill=tk.X, pady=3)

            top_row = ttk.Frame(isl_frame)
            top_row.pack(fill=tk.X)

            en_var = tk.BooleanVar(value=self.project["islands"][isl]["enabled"])
            en_cb = ttk.Checkbutton(top_row, text="Enabled", variable=en_var,
                                     command=lambda i=isl: self._on_island_toggle(i))
            en_cb.pack(side=tk.LEFT)
            self.island_enabled_vars.append(en_var)

            ttk.Label(top_row, text="Valves:").pack(side=tk.LEFT, padx=(10, 2))
            vc_var = tk.StringVar(value=str(self.project["islands"][isl]["valve_count"]))
            vc_combo = ttk.Combobox(top_row, textvariable=vc_var,
                                     values=[str(x) for x in range(1, MAX_VALVES + 1)],
                                     width=3, state="readonly")
            vc_combo.pack(side=tk.LEFT)
            self.island_valve_count_vars.append(vc_var)
            vc_var.trace_add("write", lambda *a, i=isl: self._rebuild_valve_rows(i))

            valves_frame = ttk.Frame(isl_frame)
            valves_frame.pack(fill=tk.X, pady=2)

            self.island_frames.append(valves_frame)
            self.valve_type_vars.append([])
            self.valve_unit_vars.append([])
            self.valve_widgets.append([])

            self._rebuild_valve_rows(isl)

    def _on_island_toggle(self, isl_idx):
        enabled = self.island_enabled_vars[isl_idx].get()
        self.project["islands"][isl_idx]["enabled"] = enabled
        self._rebuild_valve_rows(isl_idx)

    def _rebuild_valve_rows(self, isl_idx):
        frame = self.island_frames[isl_idx]
        for w in frame.winfo_children():
            w.destroy()

        self.valve_type_vars[isl_idx] = []
        self.valve_unit_vars[isl_idx] = []
        self.valve_widgets[isl_idx] = []

        enabled = self.island_enabled_vars[isl_idx].get()
        if not enabled:
            return

        try:
            count = int(self.island_valve_count_vars[isl_idx].get())
        except ValueError:
            count = 1

        self.project["islands"][isl_idx]["valve_count"] = count
        self.project["islands"][isl_idx]["enabled"] = True

        for v in range(count):
            row = ttk.Frame(frame)
            row.pack(fill=tk.X, pady=1)

            ttk.Label(row, text=f"V{v+1:02d}:").pack(side=tk.LEFT)

            proj_valve = self.project["islands"][isl_idx]["valves"][v]
            t_var = tk.StringVar(value=proj_valve.get("type", "Clamp"))
            t_combo = ttk.Combobox(row, textvariable=t_var, values=ACTUATOR_TYPES,
                                    width=12, state="readonly")
            t_combo.pack(side=tk.LEFT, padx=2)
            self.valve_type_vars[isl_idx].append(t_var)

            ttk.Label(row, text="Units:").pack(side=tk.LEFT, padx=(5, 2))
            u_var = tk.StringVar(value=proj_valve.get("units", ""))
            u_entry = ttk.Entry(row, textvariable=u_var, width=30)
            u_entry.pack(side=tk.LEFT, padx=2, fill=tk.X, expand=True)
            self.valve_unit_vars[isl_idx].append(u_var)

            # Trace to update project
            t_var.trace_add("write", lambda *a, ii=isl_idx, vi=v: self._on_valve_change(ii, vi))
            u_var.trace_add("write", lambda *a, ii=isl_idx, vi=v: self._on_valve_change(ii, vi))

    def _on_valve_change(self, isl_idx, v_idx):
        if v_idx < len(self.valve_type_vars[isl_idx]):
            self.project["islands"][isl_idx]["valves"][v_idx]["type"] = \
                self.valve_type_vars[isl_idx][v_idx].get()
        if v_idx < len(self.valve_unit_vars[isl_idx]):
            self.project["islands"][isl_idx]["valves"][v_idx]["units"] = \
                self.valve_unit_vars[isl_idx][v_idx].get()

    def _build_extra_config(self, parent):
        frame = ttk.LabelFrame(parent, text="Additional Configuration", padding=8)
        frame.pack(fill=tk.X, padx=5, pady=5)

        # --- HMI loc ---
        hmi_row = ttk.Frame(frame)
        hmi_row.pack(fill=tk.X, pady=2)
        ttk.Label(hmi_row, text="HMI loc:").pack(side=tk.LEFT)
        self.hmi_loc_var = tk.StringVar(value=self.project.get("hmi_loc", "1"))
        ttk.Combobox(hmi_row, textvariable=self.hmi_loc_var,
                     values=[str(i) for i in range(1, 9)],
                     width=4, state="readonly").pack(side=tk.LEFT, padx=5)

        # --- Operator Load ---
        op_outer = ttk.LabelFrame(frame, text="Operator Load", padding=4)
        op_outer.pack(fill=tk.X, pady=3)
        op_top = ttk.Frame(op_outer)
        op_top.pack(fill=tk.X)
        self.operator_load_var = tk.BooleanVar(value=self.project.get("operator_load", False))
        ttk.Radiobutton(op_top, text="No", variable=self.operator_load_var, value=False,
                        command=self._on_operator_load_change).pack(side=tk.LEFT)
        ttk.Radiobutton(op_top, text="Yes", variable=self.operator_load_var, value=True,
                        command=self._on_operator_load_change).pack(side=tk.LEFT, padx=5)
        self.operator_load_detail = ttk.Frame(op_outer)
        ttk.Label(self.operator_load_detail, text="Count:").pack(side=tk.LEFT)
        self.operator_load_count_var = tk.StringVar(value=self.project.get("operator_load_count", "1"))
        ttk.Combobox(self.operator_load_detail, textvariable=self.operator_load_count_var,
                     values=["1", "2"], width=3, state="readonly").pack(side=tk.LEFT, padx=5)
        if self.operator_load_var.get():
            self.operator_load_detail.pack(fill=tk.X, pady=2)

        # --- Drop Part With Robot ---
        drop_outer = ttk.LabelFrame(frame, text="Drop Part With Robot", padding=4)
        drop_outer.pack(fill=tk.X, pady=3)
        drop_top = ttk.Frame(drop_outer)
        drop_top.pack(fill=tk.X)
        self.drop_part_var = tk.BooleanVar(value=self.project.get("drop_part_with_robot", False))
        ttk.Radiobutton(drop_top, text="No", variable=self.drop_part_var, value=False,
                        command=self._on_drop_part_change).pack(side=tk.LEFT)
        ttk.Radiobutton(drop_top, text="Yes", variable=self.drop_part_var, value=True,
                        command=self._on_drop_part_change).pack(side=tk.LEFT, padx=5)
        self.drop_part_detail = ttk.Frame(drop_outer)
        drop_count_row = ttk.Frame(self.drop_part_detail)
        drop_count_row.pack(fill=tk.X)
        ttk.Label(drop_count_row, text="Count:").pack(side=tk.LEFT)
        self.drop_part_count_var = tk.StringVar(value=self.project.get("drop_part_robot_count", "1"))
        ttk.Combobox(drop_count_row, textvariable=self.drop_part_count_var,
                     values=["1", "2"], width=3, state="readonly").pack(side=tk.LEFT, padx=5)
        self.drop_part_count_var.trace_add("write", lambda *a: self._rebuild_drop_robot_entries())
        self.drop_robot_entries_frame = ttk.Frame(self.drop_part_detail)
        self.drop_robot_entries_frame.pack(fill=tk.X)
        self.drop_robot_name_vars = []
        self.drop_robot_valid_labels = []
        self._rebuild_drop_robot_entries()
        if self.drop_part_var.get():
            self.drop_part_detail.pack(fill=tk.X, pady=2)

        # --- Pick Part With Robot ---
        pick_outer = ttk.LabelFrame(frame, text="Pick Part With Robot", padding=4)
        pick_outer.pack(fill=tk.X, pady=3)
        pick_top = ttk.Frame(pick_outer)
        pick_top.pack(fill=tk.X)
        self.pick_part_var = tk.BooleanVar(value=self.project.get("pick_part_with_robot", False))
        ttk.Radiobutton(pick_top, text="No", variable=self.pick_part_var, value=False,
                        command=self._on_pick_part_change).pack(side=tk.LEFT)
        ttk.Radiobutton(pick_top, text="Yes", variable=self.pick_part_var, value=True,
                        command=self._on_pick_part_change).pack(side=tk.LEFT, padx=5)
        self.pick_part_detail = ttk.Frame(pick_outer)
        pick_count_row = ttk.Frame(self.pick_part_detail)
        pick_count_row.pack(fill=tk.X)
        ttk.Label(pick_count_row, text="Count:").pack(side=tk.LEFT)
        self.pick_part_count_var = tk.StringVar(value=self.project.get("pick_part_robot_count", "1"))
        ttk.Combobox(pick_count_row, textvariable=self.pick_part_count_var,
                     values=["1", "2"], width=3, state="readonly").pack(side=tk.LEFT, padx=5)
        self.pick_part_count_var.trace_add("write", lambda *a: self._rebuild_pick_robot_entries())
        self.pick_robot_entries_frame = ttk.Frame(self.pick_part_detail)
        self.pick_robot_entries_frame.pack(fill=tk.X)
        self.pick_robot_name_vars = []
        self.pick_robot_valid_labels = []
        self._rebuild_pick_robot_entries()
        if self.pick_part_var.get():
            self.pick_part_detail.pack(fill=tk.X, pady=2)

    def _on_operator_load_change(self):
        self.project["operator_load"] = self.operator_load_var.get()
        if self.operator_load_var.get():
            self.operator_load_detail.pack(fill=tk.X, pady=2)
        else:
            self.operator_load_detail.pack_forget()

    def _on_drop_part_change(self):
        self.project["drop_part_with_robot"] = self.drop_part_var.get()
        if self.drop_part_var.get():
            self.drop_part_detail.pack(fill=tk.X, pady=2)
        else:
            self.drop_part_detail.pack_forget()

    def _on_pick_part_change(self):
        self.project["pick_part_with_robot"] = self.pick_part_var.get()
        if self.pick_part_var.get():
            self.pick_part_detail.pack(fill=tk.X, pady=2)
        else:
            self.pick_part_detail.pack_forget()

    def _rebuild_drop_robot_entries(self):
        for w in self.drop_robot_entries_frame.winfo_children():
            w.destroy()
        self.drop_robot_name_vars = []
        self.drop_robot_valid_labels = []
        try:
            count = int(self.drop_part_count_var.get())
        except ValueError:
            count = 1
        saved = self.project.get("drop_part_robot_names", ["", ""])
        for i in range(count):
            row = ttk.Frame(self.drop_robot_entries_frame)
            row.pack(fill=tk.X, pady=1)
            ttk.Label(row, text=f"Robot {i+1}:").pack(side=tk.LEFT)
            var = tk.StringVar(value=saved[i] if i < len(saved) else "")
            ttk.Entry(row, textvariable=var, width=10).pack(side=tk.LEFT, padx=2)
            lbl = ttk.Label(row, text="", foreground="red")
            lbl.pack(side=tk.LEFT, padx=2)
            self.drop_robot_name_vars.append(var)
            self.drop_robot_valid_labels.append(lbl)
            var.trace_add("write", lambda *a, idx=i: self._validate_ext_robot(
                idx, self.drop_robot_name_vars, self.drop_robot_valid_labels, "drop_part_robot_names"))
            self._validate_ext_robot(i, self.drop_robot_name_vars, self.drop_robot_valid_labels, "drop_part_robot_names")

    def _rebuild_pick_robot_entries(self):
        for w in self.pick_robot_entries_frame.winfo_children():
            w.destroy()
        self.pick_robot_name_vars = []
        self.pick_robot_valid_labels = []
        try:
            count = int(self.pick_part_count_var.get())
        except ValueError:
            count = 1
        saved = self.project.get("pick_part_robot_names", ["", ""])
        for i in range(count):
            row = ttk.Frame(self.pick_robot_entries_frame)
            row.pack(fill=tk.X, pady=1)
            ttk.Label(row, text=f"Robot {i+1}:").pack(side=tk.LEFT)
            var = tk.StringVar(value=saved[i] if i < len(saved) else "")
            ttk.Entry(row, textvariable=var, width=10).pack(side=tk.LEFT, padx=2)
            lbl = ttk.Label(row, text="", foreground="red")
            lbl.pack(side=tk.LEFT, padx=2)
            self.pick_robot_name_vars.append(var)
            self.pick_robot_valid_labels.append(lbl)
            var.trace_add("write", lambda *a, idx=i: self._validate_ext_robot(
                idx, self.pick_robot_name_vars, self.pick_robot_valid_labels, "pick_part_robot_names"))
            self._validate_ext_robot(i, self.pick_robot_name_vars, self.pick_robot_valid_labels, "pick_part_robot_names")

    def _validate_ext_robot(self, idx, name_vars, valid_labels, project_key):
        if idx >= len(name_vars):
            return
        name = name_vars[idx].get().strip()
        valid = bool(re.match(r'^\d{3}R\d{2}$', name))
        if valid:
            valid_labels[idx].configure(text="OK", foreground="green")
        else:
            valid_labels[idx].configure(text="X" if name else "", foreground="red")
        names = self.project.setdefault(project_key, ["", ""])
        while len(names) <= idx:
            names.append("")
        names[idx] = name

    def _build_action_buttons(self, parent):
        frame = ttk.Frame(parent, padding=8)
        frame.pack(fill=tk.X, padx=5, pady=5)

        ttk.Button(frame, text="Auto-Generate All Sections",
                   command=self.auto_generate_all).pack(fill=tk.X, pady=2)
        ttk.Button(frame, text="Generate Current DB (Ctrl+G)",
                   command=self.generate_current_db).pack(fill=tk.X, pady=2)
        ttk.Button(frame, text="Generate All DBs",
                   command=self.generate_all_dbs).pack(fill=tk.X, pady=2)

    # ---- DB NOTEBOOK -------------------------------------------------------

    def _build_db_notebook(self, parent):
        self.db_notebook = ttk.Notebook(parent)
        self.db_notebook.pack(fill=tk.BOTH, expand=True)

        self.db_tab_frames = {}
        self.db_section_notebooks = {}
        self.db_section_widgets = {}

        for db_num in DB_RANGE:
            tab_frame = ttk.Frame(self.db_notebook)
            self.db_notebook.add(tab_frame, text=f"DB{db_num}")
            self.db_tab_frames[db_num] = tab_frame

        # Lazy load on tab change
        self.db_notebook.bind("<<NotebookTabChanged>>", self._on_db_tab_changed)

        # Load first tab
        self.root.after(100, lambda: self._load_db_page(DB_FIRST))

    def _on_db_tab_changed(self, event):
        idx = self.db_notebook.index("current")
        db_num = DB_FIRST + idx
        if db_num not in self.loaded_db_pages:
            self._load_db_page(db_num)

    def _load_db_page(self, db_num):
        if db_num in self.loaded_db_pages:
            return
        self.loaded_db_pages.add(db_num)

        parent = self.db_tab_frames[db_num]
        section_nb = ttk.Notebook(parent)
        section_nb.pack(fill=tk.BOTH, expand=True)
        self.db_section_notebooks[db_num] = section_nb
        self.db_section_widgets[db_num] = {}

        for sec_name in SECTION_NAMES:
            sec_frame = ttk.Frame(section_nb)
            section_nb.add(sec_frame, text=sec_name)
            self._build_section_tab(db_num, sec_name, sec_frame)

    def _build_section_tab(self, db_num, sec_name, parent):
        """Build a section tab with editable comment fields."""
        # Scrollable frame
        canvas = tk.Canvas(parent, borderwidth=0, highlightthickness=0)
        scrollbar_v = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        scrollbar_h = ttk.Scrollbar(parent, orient="horizontal", command=canvas.xview)
        inner = ttk.Frame(canvas)

        inner.bind("<Configure>",
                    lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar_v.set, xscrollcommand=scrollbar_h.set)

        scrollbar_v.pack(side=tk.RIGHT, fill=tk.Y)
        scrollbar_h.pack(side=tk.BOTTOM, fill=tk.X)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        canvas.bind("<Enter>", lambda e: canvas.bind_all("<MouseWheel>", _on_mousewheel))
        canvas.bind("<Leave>", lambda e: canvas.unbind_all("<MouseWheel>"))

        widgets = {}

        if sec_name == "Header":
            self._build_header_section(db_num, inner, widgets)
        elif sec_name in self.template_sections:
            fields = self.template_sections[sec_name]
            db_key = str(db_num)
            saved = self.project["db_pages"].get(db_key, {}).get("sections", {}).get(sec_name, {})

            for row_idx, (fname, ftype, default_comment) in enumerate(fields):
                ttk.Label(inner, text=fname, width=8, anchor="e").grid(
                    row=row_idx, column=0, padx=(5, 2), pady=1, sticky="e")
                ttk.Label(inner, text=ftype, width=6).grid(
                    row=row_idx, column=1, padx=2, pady=1)

                # Get field index from name
                m = re.match(r'_(\d+)', fname)
                field_idx = int(m.group(1)) if m else None
                key = str(field_idx) if field_idx is not None else fname

                comment_val = saved.get(key, default_comment)
                var = tk.StringVar(value=comment_val)
                entry = ttk.Entry(inner, textvariable=var, width=80)
                entry.grid(row=row_idx, column=2, padx=2, pady=1, sticky="ew")
                widgets[key] = var

            inner.columnconfigure(2, weight=1)
        else:
            ttk.Label(inner, text=f"Section '{sec_name}' not found in template.").pack(padx=10, pady=10)

        self.db_section_widgets[db_num][sec_name] = widgets

    def _build_header_section(self, db_num, parent, widgets):
        """Build the header section with DB name info."""
        ttk.Label(parent, text="Header / General Info", font=("TkDefaultFont", 11, "bold")).pack(padx=10, pady=10)

        info_frame = ttk.Frame(parent)
        info_frame.pack(fill=tk.X, padx=10, pady=5)

        ttk.Label(info_frame, text="DB Number:").grid(row=0, column=0, sticky="e", padx=5, pady=2)
        ttk.Label(info_frame, text=str(db_num), font=("Consolas", 10)).grid(row=0, column=1, sticky="w", padx=5, pady=2)

        ttk.Label(info_frame, text="Station Name:").grid(row=1, column=0, sticky="e", padx=5, pady=2)
        sn_label = ttk.Label(info_frame, textvariable=self.db_name_var, font=("Consolas", 10))
        sn_label.grid(row=1, column=1, sticky="w", padx=5, pady=2)

    # ---- COLLECT UI DATA ---------------------------------------------------

    def _get_station_name(self):
        p1 = self.part1_var.get().strip()
        p2 = self.part2_var.get().strip()
        p3 = self.part3_var.get().strip()
        return f"{p1}{p2}{p3}"

    def _get_islands_config(self):
        """
        Build a list of island configs from the UI.
        Each island is a list of valve dicts: [{"type": ..., "units": [...]}, ...]
        """
        islands = []
        for isl_idx in range(MAX_ISLANDS):
            if not self.island_enabled_vars[isl_idx].get():
                continue
            try:
                count = int(self.island_valve_count_vars[isl_idx].get())
            except ValueError:
                count = 0
            valves = []
            for v in range(count):
                vtype = "Clamp"
                units_str = ""
                if v < len(self.valve_type_vars[isl_idx]):
                    vtype = self.valve_type_vars[isl_idx][v].get()
                if v < len(self.valve_unit_vars[isl_idx]):
                    units_str = self.valve_unit_vars[isl_idx][v].get()
                units = [u.strip() for u in units_str.split(",") if u.strip()]
                valves.append({"type": vtype, "units": units})
            islands.append(valves)
        return islands

    def _save_section_widgets_to_project(self, db_num):
        """Save current widget values back to project data."""
        db_key = str(db_num)
        if db_key not in self.project["db_pages"]:
            self.project["db_pages"][db_key] = default_db_page()

        if db_num not in self.db_section_widgets:
            return

        for sec_name, widgets in self.db_section_widgets[db_num].items():
            sec_data = {}
            for key, var in widgets.items():
                sec_data[key] = var.get()
            self.project["db_pages"][db_key]["sections"][sec_name] = sec_data

    # ---- AUTO-GENERATION ---------------------------------------------------

    def auto_generate_all(self):
        """Auto-generate all sections for the current DB page."""
        station = self._get_station_name()
        if not re.match(r'^\d{3}(T|TT|LIFT|R)\d{2}$', station):
            messagebox.showwarning("Invalid Station", "Please enter a valid station name first.")
            return

        islands_config = self._get_islands_config()
        robot_names = self._get_robot_names()

        idx = self.db_notebook.index("current")
        db_num = DB_FIRST + idx

        # Make sure page is loaded
        if db_num not in self.loaded_db_pages:
            self._load_db_page(db_num)

        # Generate all auto sections
        gen_funcs = {
            "O_I": lambda: auto_gen_oi(station, islands_config),
            "A_I": lambda: auto_gen_ai(station, islands_config),
            "AB": lambda: auto_gen_ab(station, islands_config, robot_names),
            "RQT": lambda: auto_gen_rqt(station, islands_config, robot_names),
            "Aux_Cycle": lambda: auto_gen_aux_cycle(station, islands_config, robot_names),
            "Mem_Cycle": lambda: auto_gen_mem_cycle(station, robot_names),
            "TIO_D": lambda: auto_gen_tio_d(station, islands_config, robot_names),
        }

        # For sections that also need RESERVE default: RQM, MG
        # These are auto-gen sections but we only set them to RESERVE (no specific logic beyond that)
        reserve_only_sections = {
            "RQM": (0, 95),
            "MG": (0, 95),
        }

        for sec_name, func in gen_funcs.items():
            comments = func()
            self._apply_section_comments(db_num, sec_name, comments)

        for sec_name, (start, end) in reserve_only_sections.items():
            comments = make_reserve_dict(start, end)
            self._apply_section_comments(db_num, sec_name, comments)

        messagebox.showinfo("Auto-Generate",
                            f"Auto-generated sections for DB{db_num}.\n"
                            f"Station: {station}\n"
                            f"Robots: {len(robot_names)}\n"
                            f"Islands: {len(islands_config)}")

    def _apply_section_comments(self, db_num, sec_name, comments):
        """Apply generated comments to the section widgets."""
        if db_num not in self.db_section_widgets:
            return
        if sec_name not in self.db_section_widgets[db_num]:
            return

        widgets = self.db_section_widgets[db_num][sec_name]
        for field_idx, comment in comments.items():
            key = str(field_idx)
            if key in widgets:
                widgets[key].set(comment)

    # ---- GENERATION --------------------------------------------------------

    def generate_current_db(self):
        """Generate AWL file for the currently selected DB."""
        idx = self.db_notebook.index("current")
        db_num = DB_FIRST + idx
        self._generate_db(db_num)

    def generate_all_dbs(self):
        """Generate AWL files for all 20 DBs."""
        out_dir = filedialog.askdirectory(title="Select Output Directory")
        if not out_dir:
            return

        station = self._get_station_name()
        if not re.match(r'^\d{3}(T|TT|LIFT|R)\d{2}$', station):
            messagebox.showwarning("Invalid Station", "Please enter a valid station name first.")
            return

        count = 0
        for db_num in DB_RANGE:
            try:
                self._generate_db(db_num, output_dir=out_dir, silent=True)
                count += 1
            except Exception as e:
                messagebox.showerror("Error", f"Failed to generate DB{db_num}: {e}")

        messagebox.showinfo("Done", f"Generated {count} AWL files in:\n{out_dir}")

    def _generate_db(self, db_num, output_dir=None, silent=False):
        """Generate a single DB AWL file."""
        if not self.template_path:
            messagebox.showerror("Error", "Template file not found!")
            return

        station = self._get_station_name()
        if not re.match(r'^\d{3}(T|TT|LIFT|R)\d{2}$', station):
            messagebox.showwarning("Invalid Station", "Please enter a valid station name first.")
            return

        db_name = f"G-DB_{station}"

        # Save current widget state to project
        if db_num in self.loaded_db_pages:
            self._save_section_widgets_to_project(db_num)

        # Collect sections data for generation
        db_key = str(db_num)
        sections_data = {}
        saved_sections = self.project["db_pages"].get(db_key, {}).get("sections", {})

        for sec_name, sec_comments in saved_sections.items():
            int_comments = {}
            for k, v in sec_comments.items():
                try:
                    int_comments[int(k)] = v
                except (ValueError, TypeError):
                    pass
            if int_comments:
                sections_data[sec_name] = int_comments

        # Generate AWL lines
        awl_lines = generate_awl(db_num, station, db_name, sections_data, self.template_path)

        if output_dir is None:
            output_dir = filedialog.askdirectory(title="Select Output Directory")
            if not output_dir:
                return

        filename = f"db{db_num}.AWL"
        filepath = os.path.join(output_dir, filename)

        with open(filepath, "w", encoding="utf-8") as f:
            f.writelines(awl_lines)

        if not silent:
            messagebox.showinfo("Generated", f"Saved: {filepath}")

    # ---- SAVE / LOAD PROJECT -----------------------------------------------

    def save_project(self):
        """Save project to JSON file."""
        # First save all loaded DB page widgets
        for db_num in self.loaded_db_pages:
            self._save_section_widgets_to_project(db_num)

        # Update project from UI
        self.project["station_type"] = self.station_type_var.get()
        self.project["part1"] = self.part1_var.get().strip()
        self.project["part2"] = self.part2_var.get().strip()
        self.project["part3"] = self.part3_var.get().strip()
        self.project["robot_count"] = int(self.robot_count_var.get())
        self.project["robot_names"] = [v.get().strip() for v in self.robot_name_vars]
        self.project["hmi_loc"] = self.hmi_loc_var.get()
        self.project["operator_load"] = self.operator_load_var.get()
        self.project["operator_load_count"] = self.operator_load_count_var.get()
        self.project["drop_part_with_robot"] = self.drop_part_var.get()
        self.project["drop_part_robot_count"] = self.drop_part_count_var.get()
        self.project["drop_part_robot_names"] = [v.get().strip() for v in self.drop_robot_name_vars]
        self.project["pick_part_with_robot"] = self.pick_part_var.get()
        self.project["pick_part_robot_count"] = self.pick_part_count_var.get()
        self.project["pick_part_robot_names"] = [v.get().strip() for v in self.pick_robot_name_vars]

        # Save island config
        for isl_idx in range(MAX_ISLANDS):
            self.project["islands"][isl_idx]["enabled"] = self.island_enabled_vars[isl_idx].get()
            try:
                self.project["islands"][isl_idx]["valve_count"] = \
                    int(self.island_valve_count_vars[isl_idx].get())
            except ValueError:
                pass
            for v in range(MAX_VALVES):
                if v < len(self.valve_type_vars[isl_idx]):
                    self.project["islands"][isl_idx]["valves"][v]["type"] = \
                        self.valve_type_vars[isl_idx][v].get()
                if v < len(self.valve_unit_vars[isl_idx]):
                    self.project["islands"][isl_idx]["valves"][v]["units"] = \
                        self.valve_unit_vars[isl_idx][v].get()

        path = filedialog.asksaveasfilename(
            title="Save Project",
            defaultextension=".json",
            filetypes=[("JSON Files", "*.json"), ("All Files", "*.*")],
        )
        if not path:
            return

        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.project, f, indent=2, ensure_ascii=False)

        messagebox.showinfo("Saved", f"Project saved to:\n{path}")

    def load_project(self):
        """Load project from JSON file."""
        path = filedialog.askopenfilename(
            title="Open Project",
            filetypes=[("JSON Files", "*.json"), ("All Files", "*.*")],
        )
        if not path:
            return

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load project:\n{e}")
            return

        self.project = data

        # Ensure all keys exist
        self.project.setdefault("station_type", "Regular")
        self.project.setdefault("part1", "")
        self.project.setdefault("part2", "T")
        self.project.setdefault("part3", "")
        self.project.setdefault("robot_count", 0)
        self.project.setdefault("robot_names", [])
        self.project.setdefault("hmi_loc", "1")
        self.project.setdefault("operator_load", False)
        self.project.setdefault("operator_load_count", "1")
        self.project.setdefault("drop_part_with_robot", False)
        self.project.setdefault("drop_part_robot_count", "1")
        self.project.setdefault("drop_part_robot_names", ["", ""])
        self.project.setdefault("pick_part_with_robot", False)
        self.project.setdefault("pick_part_robot_count", "1")
        self.project.setdefault("pick_part_robot_names", ["", ""])
        self.project.setdefault("islands", [
            {"enabled": True, "valve_count": 1,
             "valves": [{"type": "Clamp", "units": ""} for _ in range(MAX_VALVES)]},
            {"enabled": False, "valve_count": 0,
             "valves": [{"type": "Clamp", "units": ""} for _ in range(MAX_VALVES)]},
        ])
        self.project.setdefault("db_pages", {str(db): default_db_page() for db in DB_RANGE})

        # Ensure islands have enough valves
        for isl in self.project["islands"]:
            while len(isl.get("valves", [])) < MAX_VALVES:
                isl["valves"].append({"type": "Clamp", "units": ""})

        self._apply_project_to_ui()
        messagebox.showinfo("Loaded", f"Project loaded from:\n{path}")

    def _apply_project_to_ui(self):
        """Push project data to the UI widgets."""
        # Station config
        self.station_type_var.set(self.project.get("station_type", "Regular"))
        self._on_station_type_change()
        self.part1_var.set(self.project.get("part1", ""))
        self.part2_var.set(self.project.get("part2", "T"))
        self.part3_var.set(self.project.get("part3", ""))

        # Robot config
        self.robot_count_var.set(str(self.project.get("robot_count", 0)))
        self._rebuild_robot_entries()
        for i, var in enumerate(self.robot_name_vars):
            if i < len(self.project.get("robot_names", [])):
                var.set(self.project["robot_names"][i])

        # Island config
        for isl_idx in range(MAX_ISLANDS):
            isl = self.project["islands"][isl_idx]
            self.island_enabled_vars[isl_idx].set(isl.get("enabled", False))
            self.island_valve_count_vars[isl_idx].set(str(isl.get("valve_count", 1)))
            self._rebuild_valve_rows(isl_idx)
            for v in range(len(self.valve_type_vars[isl_idx])):
                if v < len(isl.get("valves", [])):
                    self.valve_type_vars[isl_idx][v].set(isl["valves"][v].get("type", "Clamp"))
                    self.valve_unit_vars[isl_idx][v].set(isl["valves"][v].get("units", ""))

        # Extra config
        self.hmi_loc_var.set(self.project.get("hmi_loc", "1"))
        self.operator_load_var.set(self.project.get("operator_load", False))
        self._on_operator_load_change()
        self.operator_load_count_var.set(self.project.get("operator_load_count", "1"))
        self.drop_part_var.set(self.project.get("drop_part_with_robot", False))
        self.drop_part_count_var.set(self.project.get("drop_part_robot_count", "1"))
        self._rebuild_drop_robot_entries()
        self._on_drop_part_change()
        self.pick_part_var.set(self.project.get("pick_part_with_robot", False))
        self.pick_part_count_var.set(self.project.get("pick_part_robot_count", "1"))
        self._rebuild_pick_robot_entries()
        self._on_pick_part_change()

        # Reload all DB pages that were previously loaded
        old_loaded = set(self.loaded_db_pages)
        self.loaded_db_pages.clear()

        # Clear and rebuild all loaded DB tabs
        for db_num in old_loaded:
            parent = self.db_tab_frames[db_num]
            for w in parent.winfo_children():
                w.destroy()
            if db_num in self.db_section_notebooks:
                del self.db_section_notebooks[db_num]
            if db_num in self.db_section_widgets:
                del self.db_section_widgets[db_num]

        # Reload currently visible tab
        idx = self.db_notebook.index("current")
        db_num = DB_FIRST + idx
        self._load_db_page(db_num)


# ============================================================================
# MAIN
# ============================================================================

def main():
    root = tk.Tk()
    app = AWLGeneratorApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
