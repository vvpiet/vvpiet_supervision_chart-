import datetime
from typing import List, Dict
import pandas as pd

def generate_exam_dates(start_date: datetime.date, end_date: datetime.date, exclude_weekends: bool, holidays: List[datetime.date]) -> List[datetime.date]:
    dates = []
    cur = start_date
    while cur <= end_date:
        # When exclude_weekends is True we skip Sundays only (weekday()==6).
        # Historically we skipped Sat/Sun; updated to skip only Sundays (weekday()==6)
        if exclude_weekends and cur.weekday() == 6:
            cur += datetime.timedelta(days=1)
            continue
        if cur in holidays:
            cur += datetime.timedelta(days=1)
            continue
        dates.append(cur)
        cur += datetime.timedelta(days=1)
    return dates

def generate_schedule(dates: List[datetime.date], default_blocks: int, special_blocks: Dict[datetime.date,int], staff_df: pd.DataFrame, session_blocks: Dict[str, int] = None, day_blocks: Dict[str, Dict[str, int]] = None, date_session_blocks: Dict[datetime.date, Dict[str, int]] = None) -> pd.DataFrame:
    """Generates a schedule DataFrame with columns: date, session (Morning/Evening), assigned (list of supervisors)
    Rules: For each session we assign supervisors such that morning and evening duties are equally distributed.
    Supervisors are assigned in round-robin order, alternating between morning and evening to balance load.
    
    Args:
        dates: List of exam dates
        default_blocks: Default number of blocks per day (used if no per-date or per-session override)
        special_blocks: Dict mapping date -> blocks count (overrides default_blocks for that date, both sessions)
        staff_df: DataFrame with supervisor names
        session_blocks: Dict mapping "morning" or "evening" -> blocks count (per-session default override)
        day_blocks: Dict mapping day name (e.g., "Monday") -> {"morning": blocks, "evening": blocks} (per-day override)
        date_session_blocks: Dict mapping date -> {"morning": blocks, "evening": blocks} (per-date per-session override, highest priority)
    """
    names = staff_df.iloc[:,1].fillna("Unnamed").tolist()
    if len(names) == 0:
        raise ValueError("No supervisors available")
    
    if session_blocks is None:
        session_blocks = {}
    if day_blocks is None:
        day_blocks = {}
    if date_session_blocks is None:
        date_session_blocks = {}
    
    schedule_rows = []
    
    # Map weekday integers to day names
    day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    
    # First pass: calculate total supervisors needed for morning and evening
    morning_total = 0
    evening_total = 0
    
    for d in dates:
        day_name = day_names[d.weekday()]
        iso_year, iso_week, iso_weekday = d.isocalendar()
        
        for session in ["Morning", "Evening"]:
            blocks = default_blocks
            
            # Apply week+day override if present (format: "week_1_Monday")
            week_day_key = f"week_{iso_week}_{day_name}"
            if week_day_key in day_blocks and isinstance(day_blocks[week_day_key], dict) and session.lower() in day_blocks[week_day_key]:
                blocks = day_blocks[week_day_key][session.lower()]
            elif day_name in day_blocks and isinstance(day_blocks[day_name], dict) and session.lower() in day_blocks[day_name]:
                blocks = day_blocks[day_name][session.lower()]
            
            if blocks == default_blocks and session_blocks and session.lower() in session_blocks:
                blocks = session_blocks[session.lower()]
            
            if d in special_blocks:
                blocks = special_blocks[d]
            
            if d in date_session_blocks and session.lower() in date_session_blocks[d]:
                blocks = date_session_blocks[d][session.lower()]
            
            extras = 1 if blocks == 1 else 2
            count = blocks + extras
            
            if session == "Morning":
                morning_total += count
            else:
                evening_total += count
    
    # Second pass: assign supervisors with balanced morning/evening distribution
    # Track how many times each supervisor is assigned to morning/evening
    supervisor_morning_count = {name: 0 for name in names}
    supervisor_evening_count = {name: 0 for name in names}
    
    # Create list of (date, session, blocks_needed) tuples
    assignments = []
    for d in dates:
        day_name = day_names[d.weekday()]
        iso_year, iso_week, iso_weekday = d.isocalendar()
        
        for session in ["Morning", "Evening"]:
            blocks = default_blocks
            
            week_day_key = f"week_{iso_week}_{day_name}"
            if week_day_key in day_blocks and isinstance(day_blocks[week_day_key], dict) and session.lower() in day_blocks[week_day_key]:
                blocks = day_blocks[week_day_key][session.lower()]
            elif day_name in day_blocks and isinstance(day_blocks[day_name], dict) and session.lower() in day_blocks[day_name]:
                blocks = day_blocks[day_name][session.lower()]
            
            if blocks == default_blocks and session_blocks and session.lower() in session_blocks:
                blocks = session_blocks[session.lower()]
            
            if d in special_blocks:
                blocks = special_blocks[d]
            
            if d in date_session_blocks and session.lower() in date_session_blocks[d]:
                blocks = date_session_blocks[d][session.lower()]
            
            extras = 1 if blocks == 1 else 2
            count = blocks + extras
            
            assignments.append((d, session, count))
    
    # Assign supervisors using balanced allocation
    # For each assignment, pick the supervisor with the least assignments in that session
    for d, session, count in assignments:
        assigned = []
        for i in range(count):
            # Find supervisor with least assignments in this session
            if session == "Morning":
                # Sort by morning count, then by evening count (to balance overall)
                best_supervisor = min(names, key=lambda name: (supervisor_morning_count[name], supervisor_morning_count[name] + supervisor_evening_count[name]))
                supervisor_morning_count[best_supervisor] += 1
            else:  # Evening
                # Sort by evening count, then by morning count (to balance overall)
                best_supervisor = min(names, key=lambda name: (supervisor_evening_count[name], supervisor_morning_count[name] + supervisor_evening_count[name]))
                supervisor_evening_count[best_supervisor] += 1
            
            assigned.append(best_supervisor)
        
        schedule_rows.append({"date": d, "session": session, "assigned": assigned})
    
    return pd.DataFrame(schedule_rows)

def build_supervisor_table(supervisor_name: str, schedule_df: pd.DataFrame) -> pd.DataFrame:
    """Build per-supervisor table with Sr. No., Date, Morning, Evening (ticks)"""
    rows = []
    # Get unique dates
    dates = sorted(schedule_df["date"].unique())
    sr = 1
    for d in dates:
        morning = schedule_df[(schedule_df["date"]==d) & (schedule_df["session"]=="Morning")]
        evening = schedule_df[(schedule_df["date"]==d) & (schedule_df["session"]=="Evening")]
        m_tick = "✓" if supervisor_name in (morning.iloc[0]["assigned"] if not morning.empty else []) else ""
        e_tick = "✓" if supervisor_name in (evening.iloc[0]["assigned"] if not evening.empty else []) else ""
        if m_tick or e_tick:
            rows.append({"Sr. No.": sr, "Date": d.strftime('%Y-%m-%d'), "Morning": m_tick, "Evening": e_tick})
            sr += 1
    return pd.DataFrame(rows)
