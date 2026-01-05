#!/usr/bin/env python3
"""
Star Security Payroll Tools v4.0 - Two-Tab Excel with Time-Based Stat Splitting
Tab 1: Payroll Finisher (Overtime + Stat Holidays + PHP with 176-hour cap)
Tab 2: Union Benefits Calculator
"""

import streamlit as st
import pandas as pd
from io import BytesIO
from datetime import datetime, timedelta, time as dt_time
import re

# Page configuration
st.set_page_config(
    page_title="Star Security - Payroll Tools v4.0",
    page_icon="⭐",
    layout="wide"
)

def extract_rate_from_code(rate_code):
    """Extract hourly rate from rate code string"""
    if pd.isna(rate_code):
        return 0
    
    rate_str = str(rate_code).strip()
    
    # Handle "Regular" special case
    if rate_str.lower() == 'regular':
        return 17.60
    
    # Extract number from codes like "20 Rate" or "21.75 Rate"
    match = re.match(r'(\d+\.?\d*)\s*Rate', rate_str)
    if match:
        return float(match.group(1))
    
    return 0

def get_ot_stat_code(rate_code):
    """Convert regular rate code to OT/STAT code with proper spacing"""
    if pd.isna(rate_code):
        return rate_code
    
    rate_str = str(rate_code).strip()
    
    # Handle "Regular" special case
    if rate_str.lower() == 'regular':
        return "Hourly Overtime /STAT"
    
    # Handle special case for 21.75 (no space after /)
    if "21.75" in rate_str and "OT" not in rate_str:
        return "21.75 Rate OT/STAT"
    
    # All other codes have space after /
    # Remove existing OT/STAT if present
    base_code = rate_str.replace(" OT/STAT", "").replace(" OT/ STAT", "").strip()
    
    return f"{base_code} OT/ STAT"

def extract_vacation_percent(notes):
    """Extract vacation percentage from Notes column, default 4%"""
    if pd.isna(notes):
        return 0.04
    
    notes_str = str(notes).strip()
    
    # Look for patterns like "6%" or "6 percent"
    match = re.search(r'(\d+\.?\d*)%', notes_str)
    if match:
        return float(match.group(1)) / 100
    
    match = re.search(r'(\d+\.?\d*)\s*percent', notes_str, re.IGNORECASE)
    if match:
        return float(match.group(1)) / 100
    
    return 0.04  # Default 4%

def split_shift_with_times(shift_date, start_time, end_time, total_hours, stat_dates, times_dict=None):
    """
    Split a shift using actual start/end times to properly handle midnight crossings
    
    Args:
        shift_date: Date shift started (pandas datetime)
        start_time: Start time (datetime.time object or from times_dict)
        end_time: End time (datetime.time object or from times_dict)
        total_hours: Total hours worked
        stat_dates: List of stat dates to check against
        times_dict: Optional dict with times by (name, date)
    
    Returns:
        List of (date, hours, is_stat) tuples
    """
    shift_segments = []
    
    # Handle missing start/end times - fall back to simple split
    if pd.isna(start_time) or pd.isna(end_time):
        # Simple assumption: treat all hours as on shift_date
        is_stat = any(shift_date.date() == stat_date.date() for stat_date in stat_dates)
        return [(shift_date.date(), total_hours, is_stat)]
    
    # Convert time objects to time if needed
    if isinstance(start_time, dt_time):
        start_t = start_time
    else:
        # Parse from string
        try:
            start_str = str(start_time)
            start_hour, start_min, start_sec = map(int, start_str.split(':'))
            start_t = dt_time(start_hour, start_min, start_sec)
        except:
            # Failed to parse - fall back
            is_stat = any(shift_date.date() == stat_date.date() for stat_date in stat_dates)
            return [(shift_date.date(), total_hours, is_stat)]
    
    if isinstance(end_time, dt_time):
        end_t = end_time
    else:
        # Parse from string
        try:
            end_str = str(end_time)
            end_hour, end_min, end_sec = map(int, end_str.split(':'))
            end_t = dt_time(end_hour, end_min, end_sec)
        except:
            # Failed to parse - fall back
            is_stat = any(shift_date.date() == stat_date.date() for stat_date in stat_dates)
            return [(shift_date.date(), total_hours, is_stat)]
    
    # Create full datetime objects
    shift_start = datetime.combine(shift_date.date(), start_t)
    
    # If end time is before start time, shift crosses midnight
    if end_t < start_t:
        # Shift ends next day
        shift_end = datetime.combine(shift_date.date() + timedelta(days=1), end_t)
    else:
        # Shift ends same day
        shift_end = datetime.combine(shift_date.date(), end_t)
    
    # Split at midnight if needed
    current_datetime = shift_start
    
    while current_datetime < shift_end:
        current_date = current_datetime.date()
        
        # Find midnight of next day
        next_midnight = datetime.combine(current_date + timedelta(days=1), dt_time(0, 0, 0))
        
        # Hours until midnight or end of shift
        if next_midnight <= shift_end:
            segment_end = next_midnight
        else:
            segment_end = shift_end
        
        # Calculate hours in this segment
        segment_hours = (segment_end - current_datetime).total_seconds() / 3600
        
        # Check if this date is a stat
        is_stat = any(current_date == stat_date.date() for stat_date in stat_dates)
        
        if segment_hours > 0:
            shift_segments.append((current_date, segment_hours, is_stat))
        
        # Move to next segment
        current_datetime = segment_end
    
    return shift_segments

def load_two_tab_excel(uploaded_file):
    """
    Load Excel file with two tabs:
    - Tab 1: Payroll data (main data with rate codes)
    - Tab 2: Times (time breakdown for splitting)
    
    Returns: (payroll_df, times_df)
    """
    try:
        # Read all sheets
        excel_file = pd.ExcelFile(uploaded_file)
        
        # Get sheet names
        sheet_names = excel_file.sheet_names
        
        if len(sheet_names) >= 2:
            # Two-tab format
            payroll_df = pd.read_excel(uploaded_file, sheet_name=0)
            times_df = pd.read_excel(uploaded_file, sheet_name=1)
            return payroll_df, times_df
        else:
            # Single tab - old format
            payroll_df = pd.read_excel(uploaded_file, sheet_name=0)
            return payroll_df, None
            
    except Exception as e:
        st.error(f"Error reading Excel file: {str(e)}")
        return None, None

def normalize_payroll_dataframe(df):
    """Normalize column names to standard format"""
    # Column mapping for different export formats
    column_mapping = {
        'Date': 'Transaction Date',
        'Staff_Last_First': 'Name',
        'Actual_Total_calc': 'Duration',
        'Project': 'Customer'
    }
    
    # Rename columns if they exist
    for old_col, new_col in column_mapping.items():
        if old_col in df.columns and new_col not in df.columns:
            df = df.rename(columns={old_col: new_col})
    
    # Add missing columns with defaults
    if 'Service Item' not in df.columns:
        df['Service Item'] = 'Labor'
    if 'Class' not in df.columns:
        df['Class'] = ''
    if 'Billable' not in df.columns:
        df['Billable'] = 'N'
    if 'Notes' not in df.columns:
        df['Notes'] = ''
    
    # Ensure Transaction Date is datetime
    df['Transaction Date'] = pd.to_datetime(df['Transaction Date'])
    
    return df

def create_times_lookup(times_df):
    """Create lookup dict from times dataframe"""
    if times_df is None:
        return {}
    
    times_dict = {}
    
    # Normalize times_df columns
    if 'Date' in times_df.columns:
        times_df = times_df.rename(columns={'Date': 'Transaction Date'})
    if 'Staff_Last_First' in times_df.columns:
        times_df = times_df.rename(columns={'Staff_Last_First': 'Name'})
    
    times_df['Transaction Date'] = pd.to_datetime(times_df['Transaction Date'])
    
    for _, row in times_df.iterrows():
        name = row.get('Name', '')
        date = row.get('Transaction Date')
        start = row.get('Actual_Start')
        end = row.get('Actual_End')
        
        if pd.notna(name) and pd.notna(date):
            key = (str(name), date.date())
            times_dict[key] = {
                'start': start,
                'end': end
            }
    
    return times_dict

def process_payroll_data_with_stats(df, times_df, period_start, period_end, stat_configs):
    """
    Process payroll data with stat holiday handling and PHP calculation
    
    Args:
        df: Main payroll dataframe (Tab 1)
        times_df: Times dataframe (Tab 2)
        period_start: Payroll period start date
        period_end: Payroll period end date
        stat_configs: List of dicts with {stat_date, php_start, php_end}
    """
    # Normalize the dataframe
    df = normalize_payroll_dataframe(df)
    
    # Create times lookup
    times_dict = create_times_lookup(times_df)
    
    # Extract stat dates
    stat_dates = [pd.to_datetime(config['stat_date']) for config in stat_configs]
    
    # Filter to payroll period
    period_df = df[
        (df['Transaction Date'] >= period_start) & 
        (df['Transaction Date'] <= period_end)
    ].copy()
    
    # Get lookback data for PHP for each stat
    lookback_data = {}
    for config in stat_configs:
        stat_date = pd.to_datetime(config['stat_date'])
        php_start = pd.to_datetime(config['php_start'])
        php_end = pd.to_datetime(config['php_end'])
        
        lookback_df = df[
            (df['Transaction Date'] >= php_start) & 
            (df['Transaction Date'] <= php_end)
        ].copy()
        
        lookback_data[stat_date] = lookback_df
    
    # Sort by Name and Transaction Date
    period_df = period_df.sort_values(['Name', 'Transaction Date']).reset_index(drop=True)
    
    # Process each employee
    processed_rows = []
    stats = {
        'employees_processed': 0,
        'input_shifts': len(period_df),
        'output_lines': 0,
        'total_regular_hours': 0,
        'total_ot_hours': 0,
        'total_stat_hours': 0,
        'total_php_hours': 0
    }
    
    for employee_name in period_df['Name'].unique():
        stats['employees_processed'] += 1
        
        # Get all shifts for this employee in the period
        employee_shifts = period_df[period_df['Name'] == employee_name].copy()
        employee_shifts = employee_shifts.sort_values('Transaction Date').reset_index(drop=True)
        
        # Track hours by type
        cumulative_regular_hours = 0  # Only non-stat hours count toward OT
        regular_hours = {}
        overtime_hours = {}
        stat_hours = {}
        first_date = employee_shifts['Transaction Date'].iloc[0]
        
        for idx, shift in employee_shifts.iterrows():
            shift_hours = shift['Duration']
            rate_code = shift['Payroll Item']
            shift_date = shift['Transaction Date']
            
            # Skip NaN/0 duration
            if pd.isna(shift_hours) or shift_hours == 0:
                continue
            
            # Skip if already marked as OT/STAT or PHP
            if 'OT' in str(rate_code) or 'STAT' in str(rate_code) or 'PHP' in str(rate_code):
                continue
            
            # Get start/end times from times_dict
            lookup_key = (str(employee_name), shift_date.date())
            start_time = None
            end_time = None
            
            if lookup_key in times_dict:
                start_time = times_dict[lookup_key]['start']
                end_time = times_dict[lookup_key]['end']
            
            # Split shift using start/end times if available
            shift_segments = split_shift_with_times(
                shift_date, start_time, end_time, shift_hours, stat_dates, times_dict
            )
            
            for seg_date, seg_hours, is_stat in shift_segments:
                if is_stat:
                    # Stat premium hours - already 1.5x, don't count toward OT
                    ot_stat_code = get_ot_stat_code(rate_code)
                    if ot_stat_code not in stat_hours:
                        stat_hours[ot_stat_code] = 0
                    stat_hours[ot_stat_code] += seg_hours
                    stats['total_stat_hours'] += seg_hours
                    
                else:
                    # Regular hours - check against 88-hour threshold
                    hours_before = cumulative_regular_hours
                    hours_after = cumulative_regular_hours + seg_hours
                    
                    if hours_after <= 88:
                        # All regular
                        if rate_code not in regular_hours:
                            regular_hours[rate_code] = 0
                        regular_hours[rate_code] += seg_hours
                        stats['total_regular_hours'] += seg_hours
                        
                    elif hours_before >= 88:
                        # All overtime
                        ot_code = get_ot_stat_code(rate_code)
                        if ot_code not in overtime_hours:
                            overtime_hours[ot_code] = 0
                        overtime_hours[ot_code] += seg_hours
                        stats['total_ot_hours'] += seg_hours
                        
                    else:
                        # Split at 88-hour threshold
                        regular_portion = 88 - hours_before
                        ot_portion = seg_hours - regular_portion
                        
                        # Regular portion
                        if rate_code not in regular_hours:
                            regular_hours[rate_code] = 0
                        regular_hours[rate_code] += regular_portion
                        stats['total_regular_hours'] += regular_portion
                        
                        # OT portion
                        ot_code = get_ot_stat_code(rate_code)
                        if ot_code not in overtime_hours:
                            overtime_hours[ot_code] = 0
                        overtime_hours[ot_code] += ot_portion
                        stats['total_ot_hours'] += ot_portion
                    
                    # Update cumulative (only non-stat hours)
                    cumulative_regular_hours += seg_hours
        
        # Calculate PHP for this employee with 176-hour cap
        php_total_hours = 0
        
        for stat_date in stat_dates:
            if stat_date not in lookback_data:
                continue
            
            lookback_df = lookback_data[stat_date]
            employee_lookback = lookback_df[lookback_df['Name'] == employee_name].copy()
            
            if len(employee_lookback) == 0:
                continue
            
            # Calculate regular wages with 176-hour cap
            total_hours = 0
            total_wages = 0
            vacation_pct = 0.04  # Default
            
            for _, lb_shift in employee_lookback.iterrows():
                lb_hours = lb_shift['Duration']
                lb_rate_code = lb_shift['Payroll Item']
                lb_notes = lb_shift.get('Notes', '')
                
                if pd.isna(lb_hours) or lb_hours == 0:
                    continue
                
                # Skip stat/OT hours in lookback (only count regular hours)
                if 'OT' in str(lb_rate_code) or 'STAT' in str(lb_rate_code):
                    continue
                
                # Get rate and vacation %
                rate = extract_rate_from_code(lb_rate_code)
                vacation_pct = max(vacation_pct, extract_vacation_percent(lb_notes))
                
                total_hours += lb_hours
            
            # Cap at 176 hours (88 × 2 pay periods)
            capped_hours = min(total_hours, 176)
            
            # Calculate wages based on capped hours
            # Use weighted average or primary rate
            if capped_hours > 0:
                # Get primary rate from most common rate code in lookback
                rate_codes = employee_lookback[
                    ~employee_lookback['Payroll Item'].str.contains('OT|STAT', na=False)
                ]['Payroll Item'].mode()
                
                if len(rate_codes) > 0:
                    primary_rate = extract_rate_from_code(rate_codes.iloc[0])
                    total_wages = capped_hours * primary_rate
                
                # Calculate PHP: (wages + vacation) / 20 / 30 (to get hours)
                if total_wages > 0:
                    php_dollars = (total_wages * (1 + vacation_pct)) / 20
                    php_hours = php_dollars / 30  # Convert to hours at $30/hr
                    php_total_hours += php_hours
        
        # Create consolidated rows for this employee
        for rate_code, hours in regular_hours.items():
            processed_rows.append({
                'Name': employee_name,
                'Transaction Date': first_date,
                'Customer': 'STAR TOTAL',
                'Service Item': 'Labor',
                'Payroll Item': rate_code,
                'Duration': round(hours, 2),
                'Class': '',
                'Billable': 'N',
                'Notes': ''
            })
            stats['output_lines'] += 1
        
        for rate_code, hours in overtime_hours.items():
            processed_rows.append({
                'Name': employee_name,
                'Transaction Date': first_date,
                'Customer': 'STAR TOTAL',
                'Service Item': 'Labor',
                'Payroll Item': rate_code,
                'Duration': round(hours, 2),
                'Class': '',
                'Billable': 'N',
                'Notes': ''
            })
            stats['output_lines'] += 1
        
        for rate_code, hours in stat_hours.items():
            processed_rows.append({
                'Name': employee_name,
                'Transaction Date': first_date,
                'Customer': 'STAR TOTAL',
                'Service Item': 'Labor',
                'Payroll Item': rate_code,
                'Duration': round(hours, 2),
                'Class': '',
                'Billable': 'N',
                'Notes': ''
            })
            stats['output_lines'] += 1
        
        # Add PHP if applicable
        if php_total_hours > 0:
            # Use first stat date in period for PHP line
            php_date = min([sd for sd in stat_dates if period_start <= sd <= period_end])
            
            processed_rows.append({
                'Name': employee_name,
                'Transaction Date': php_date,
                'Customer': 'STAR TOTAL',
                'Service Item': 'Labor',
                'Payroll Item': 'PHP (Holiday)',
                'Duration': round(php_total_hours, 2),
                'Class': '',
                'Billable': 'N',
                'Notes': ''
            })
            stats['output_lines'] += 1
            stats['total_php_hours'] += php_total_hours
    
    # Create output dataframe
    output_df = pd.DataFrame(processed_rows)
    if len(output_df) > 0:
        output_df = output_df.sort_values(['Name', 'Payroll Item']).reset_index(drop=True)
    
    return output_df, stats

def process_payroll_data(df):
    """
    Original process_payroll_data for non-stat periods
    """
    # Normalize the dataframe
    df = normalize_payroll_dataframe(df)
    
    # Sort by Name and Transaction Date
    df = df.sort_values(['Name', 'Transaction Date']).reset_index(drop=True)
    
    # Process each employee
    processed_rows = []
    stats = {
        'employees_processed': 0,
        'input_shifts': len(df),
        'output_lines': 0,
        'total_regular_hours': 0,
        'total_ot_hours': 0,
        'total_php_hours': 0
    }
    
    for employee_name in df['Name'].unique():
        stats['employees_processed'] += 1
        
        # Get all shifts for this employee
        employee_shifts = df[df['Name'] == employee_name].copy()
        employee_shifts = employee_shifts.sort_values('Transaction Date').reset_index(drop=True)
        
        # Track cumulative hours and process shifts
        cumulative_hours = 0
        regular_hours = {}
        overtime_hours = {}
        php_hours = {}
        first_date = employee_shifts['Transaction Date'].iloc[0]
        
        for idx, shift in employee_shifts.iterrows():
            shift_hours = shift['Duration']
            rate_code = shift['Payroll Item']
            
            # Skip rows with missing/NaN duration values
            if pd.isna(shift_hours) or shift_hours == 0:
                continue
            
            # Check if this is PHP (Holiday)
            if rate_code == 'PHP (Holiday)' or rate_code == 'PHP(Holiday)':
                if rate_code not in php_hours:
                    php_hours[rate_code] = 0
                php_hours[rate_code] += shift_hours
                stats['total_php_hours'] += shift_hours
                continue
            
            # Calculate where this shift falls relative to 88-hour threshold
            hours_before_threshold = cumulative_hours
            hours_after_adding_shift = cumulative_hours + shift_hours
            
            if hours_after_adding_shift <= 88:
                # Entire shift is regular time
                if rate_code not in regular_hours:
                    regular_hours[rate_code] = 0
                regular_hours[rate_code] += shift_hours
                stats['total_regular_hours'] += shift_hours
                
            elif hours_before_threshold >= 88:
                # Entire shift is overtime
                ot_rate_code = get_ot_stat_code(rate_code)
                if ot_rate_code not in overtime_hours:
                    overtime_hours[ot_rate_code] = 0
                overtime_hours[ot_rate_code] += shift_hours
                stats['total_ot_hours'] += shift_hours
                
            else:
                # Shift spans the 88-hour threshold - need to split
                regular_portion = 88 - hours_before_threshold
                overtime_portion = shift_hours - regular_portion
                
                # Add regular portion
                if rate_code not in regular_hours:
                    regular_hours[rate_code] = 0
                regular_hours[rate_code] += regular_portion
                stats['total_regular_hours'] += regular_portion
                
                # Add overtime portion
                ot_rate_code = get_ot_stat_code(rate_code)
                if ot_rate_code not in overtime_hours:
                    overtime_hours[ot_rate_code] = 0
                overtime_hours[ot_rate_code] += overtime_portion
                stats['total_ot_hours'] += overtime_portion
            
            # Update cumulative hours
            cumulative_hours += shift_hours
        
        # Create consolidated rows for this employee
        for rate_code, hours in regular_hours.items():
            processed_rows.append({
                'Name': employee_name,
                'Transaction Date': first_date,
                'Customer': 'STAR TOTAL',
                'Service Item': 'Labor',
                'Payroll Item': rate_code,
                'Duration': hours,
                'Class': '',
                'Billable': 'N',
                'Notes': ''
            })
            stats['output_lines'] += 1
        
        for rate_code, hours in overtime_hours.items():
            processed_rows.append({
                'Name': employee_name,
                'Transaction Date': first_date,
                'Customer': 'STAR TOTAL',
                'Service Item': 'Labor',
                'Payroll Item': rate_code,
                'Duration': hours,
                'Class': '',
                'Billable': 'N',
                'Notes': ''
            })
            stats['output_lines'] += 1
        
        for rate_code, hours in php_hours.items():
            processed_rows.append({
                'Name': employee_name,
                'Transaction Date': first_date,
                'Customer': 'STAR TOTAL',
                'Service Item': 'Labor',
                'Payroll Item': rate_code,
                'Duration': hours,
                'Class': '',
                'Billable': 'N',
                'Notes': ''
            })
            stats['output_lines'] += 1
    
    # Create output dataframe
    output_df = pd.DataFrame(processed_rows)
    if len(output_df) > 0:
        output_df = output_df.sort_values(['Name', 'Payroll Item']).reset_index(drop=True)
    
    return output_df, stats

def calculate_union_benefits(df):
    """
    Calculate union benefits with 44-hour weekly cap
    $0.80 per hour, max 44 hours per week
    """
    # Normalize dataframe
    df = normalize_payroll_dataframe(df)
    
    # Sort by Name and Date
    df = df.sort_values(['Name', 'Transaction Date']).reset_index(drop=True)
    
    # Find the date range
    min_date = df['Transaction Date'].min()
    week1_end = min_date + timedelta(days=6)
    
    results = []
    
    for employee_name in df['Name'].unique():
        # Get all shifts for this employee
        employee_shifts = df[df['Name'] == employee_name].copy()
        
        # Skip rows with NaN/0 duration
        employee_shifts = employee_shifts[
            employee_shifts['Duration'].notna() & 
            (employee_shifts['Duration'] > 0)
        ]
        
        if len(employee_shifts) == 0:
            continue
        
        # Split into weeks
        week1_shifts = employee_shifts[employee_shifts['Transaction Date'] <= week1_end]
        week2_shifts = employee_shifts[employee_shifts['Transaction Date'] > week1_end]
        
        # Calculate actual hours
        week1_actual = week1_shifts['Duration'].sum() if len(week1_shifts) > 0 else 0
        week2_actual = week2_shifts['Duration'].sum() if len(week2_shifts) > 0 else 0
        
        # Cap at 44 hours per week
        week1_payable = min(week1_actual, 44)
        week2_payable = min(week2_actual, 44)
        
        # Calculate total
        total_payable = week1_payable + week2_payable
        total_cost = total_payable * 0.80
        
        results.append({
            'Name': employee_name,
            'Week 1 Actual Hours': round(week1_actual, 2),
            'Week 1 Payable Hours': round(week1_payable, 2),
            'Week 2 Actual Hours': round(week2_actual, 2),
            'Week 2 Payable Hours': round(week2_payable, 2),
            'Total Payable Hours': round(total_payable, 2),
            'Total Cost ($0.80/hr)': round(total_cost, 2)
        })
    
    return pd.DataFrame(results)

def to_excel(df):
    """Convert dataframe to Excel bytes"""
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Sheet1')
    return output.getvalue()

# ============================================================================
# MAIN APP
# ============================================================================

st.title("⭐ Star Security - Payroll Tools v4.0")
st.markdown("**Professional Payroll Processing with Time-Based Stat Splitting**")

# Create tabs
tab1, tab2 = st.tabs(["📊 Payroll Finisher", "💰 Union Benefits"])

# ============================================================================
# TAB 1: PAYROLL FINISHER
# ============================================================================
with tab1:
    st.markdown("### Biweekly Payroll Processor with Overtime & Stat Holidays")
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.subheader("Upload Payroll File")
        uploaded_file_tab1 = st.file_uploader(
            "Choose your Excel file (.xlsx)",
            type=['xlsx'],
            help="Single tab (old format) or Two tabs: Tab 1 = Payroll, Tab 2 = Times",
            key="payroll_uploader"
        )
    
    with col2:
        st.subheader("Status")
        if uploaded_file_tab1 is None:
            st.info("👆 Upload a file to begin")
        else:
            st.success("✓ File uploaded")
    
    if uploaded_file_tab1 is not None:
        try:
            # Load Excel file (one or two tabs)
            payroll_df, times_df = load_two_tab_excel(uploaded_file_tab1)
            
            if payroll_df is None:
                st.error("Failed to load Excel file")
            else:
                # Normalize for preview
                preview_df = normalize_payroll_dataframe(payroll_df.copy())
                
                st.subheader("📄 Input Data Preview (Tab 1)")
                st.dataframe(preview_df.head(20), use_container_width=True, height=250)
                
                if times_df is not None:
                    with st.expander("📋 View Times Data (Tab 2)"):
                        st.dataframe(times_df.head(20), use_container_width=True, height=200)
                        st.success("✓ Time-based splitting enabled")
                else:
                    st.info("ℹ️ Single-tab format detected (no time splitting)")
                
                # Configuration
                st.markdown("---")
                st.subheader("⚙️ Payroll Configuration")
                
                col1, col2 = st.columns(2)
                
                with col1:
                    period_start = st.date_input(
                        "Payroll Period START Date",
                        value=datetime.now().date(),
                        help="First day of the payroll period",
                        key="period_start"
                    )
                
                with col2:
                    period_end = st.date_input(
                        "Payroll Period END Date",
                        value=(datetime.now() + timedelta(days=13)).date(),
                        help="Last day of the payroll period",
                        key="period_end"
                    )
                
                has_stat = st.checkbox(
                    "📅 This period contains Stat Holiday(s)",
                    value=False,
                    help="Check this if there are statutory holidays in this payroll period",
                    key="has_stat"
                )
                
                stat_configs = []
                
                if has_stat:
                    st.markdown("**Stat Holiday Configuration:**")
                    
                    if times_df is None:
                        st.warning("⚠️ For accurate stat calculations at midnight, your file should have two tabs with start/end times.")
                    
                    num_stats = st.number_input(
                        "Number of stat holidays in this period",
                        min_value=1,
                        max_value=5,
                        value=1,
                        help="How many stats are in this period?",
                        key="num_stats"
                    )
                    
                    for i in range(num_stats):
                        st.markdown(f"**Stat #{i+1}:**")
                        col1, col2, col3 = st.columns(3)
                        
                        with col1:
                            stat_date = st.date_input(
                                f"Stat Date",
                                value=datetime.now().date(),
                                key=f"stat_date_{i}",
                                help="The statutory holiday date"
                            )
                        
                        with col2:
                            php_start = st.date_input(
                                f"PHP Lookback START",
                                value=datetime.now().date() - timedelta(days=28),
                                key=f"php_start_{i}",
                                help="Start of 4-week lookback period"
                            )
                        
                        with col3:
                            php_end = st.date_input(
                                f"PHP Lookback END",
                                value=datetime.now().date() - timedelta(days=1),
                                key=f"php_end_{i}",
                                help="End of 4-week lookback period"
                            )
                        
                        stat_configs.append({
                            'stat_date': stat_date,
                            'php_start': php_start,
                            'php_end': php_end
                        })
                        
                        st.markdown("---")
                
                col1, col2, col3 = st.columns([1, 1, 2])
                with col1:
                    st.metric("Total Shifts", len(preview_df))
                with col2:
                    st.metric("Employees", preview_df['Name'].nunique())
                with col3:
                    st.metric("Total Hours", f"{preview_df['Duration'].sum():.1f}")
                
                if st.button("🚀 Process Payroll", type="primary", use_container_width=True, key="process_payroll"):
                    with st.spinner("Processing payroll data..."):
                        try:
                            if has_stat:
                                # Process with stat holidays and PHP
                                output_df, stats = process_payroll_data_with_stats(
                                    payroll_df,
                                    times_df,
                                    pd.to_datetime(period_start),
                                    pd.to_datetime(period_end),
                                    stat_configs
                                )
                            else:
                                # Regular processing
                                # Filter to period
                                period_df = payroll_df.copy()
                                period_df = normalize_payroll_dataframe(period_df)
                                period_df = period_df[
                                    (period_df['Transaction Date'] >= pd.to_datetime(period_start)) &
                                    (period_df['Transaction Date'] <= pd.to_datetime(period_end))
                                ].copy()
                                output_df, stats = process_payroll_data(period_df)
                            
                            st.session_state['payroll_output_df'] = output_df
                            st.session_state['payroll_stats'] = stats
                            st.session_state['payroll_processed'] = True
                        
                        except Exception as e:
                            st.error(f"❌ Error during processing: {str(e)}")
                            import traceback
                            st.code(traceback.format_exc())
                
                if st.session_state.get('payroll_processed', False):
                    st.success("✅ Processing Complete!")
                    
                    st.subheader("📊 Summary Statistics")
                    col1, col2, col3, col4 = st.columns(4)
                    
                    stats = st.session_state['payroll_stats']
                    with col1:
                        st.metric("Employees", stats['employees_processed'])
                    with col2:
                        st.metric("Input Shifts", stats['input_shifts'])
                    with col3:
                        st.metric("Output Lines", stats['output_lines'])
                    with col4:
                        reduction = 100 - (stats['output_lines']/max(stats['input_shifts'], 1)*100)
                        st.metric("Reduction", f"{reduction:.0f}%")
                    
                    cols = st.columns(4)
                    with cols[0]:
                        st.metric("Regular Hours", f"{stats['total_regular_hours']:.1f}")
                    with cols[1]:
                        st.metric("Overtime Hours", f"{stats['total_ot_hours']:.1f}")
                    with cols[2]:
                        if 'total_stat_hours' in stats:
                            st.metric("Stat Hours", f"{stats['total_stat_hours']:.1f}")
                    with cols[3]:
                        st.metric("PHP Hours", f"{stats['total_php_hours']:.1f}")
                    
                    st.subheader("✨ Processed Output")
                    st.dataframe(st.session_state['payroll_output_df'], use_container_width=True, height=400)
                    
                    excel_data = to_excel(st.session_state['payroll_output_df'])
                    st.download_button(
                        label="📥 Download Processed Payroll",
                        data=excel_data,
                        file_name=f"payroll_processed_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        type="primary",
                        use_container_width=True,
                        key="download_payroll"
                    )
                    
                    st.info("💡 Tip: The downloaded file is ready to import into QuickBooks")
        
        except Exception as e:
            st.error(f"❌ Error processing file: {str(e)}")
            import traceback
            st.code(traceback.format_exc())

# ============================================================================
# TAB 2: UNION BENEFITS CALCULATOR
# ============================================================================
with tab2:
    st.markdown("### Union Benefits Calculator (44-Hour Weekly Cap)")
    st.markdown("**Rate:** $0.80 per hour | **Max:** 44 hours per week")
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.subheader("Upload Payroll File")
        uploaded_file_tab2 = st.file_uploader(
            "Choose your Excel file (.xlsx)",
            type=['xlsx'],
            help="Upload the same biweekly payroll file",
            key="union_uploader"
        )
    
    with col2:
        st.subheader("Status")
        if uploaded_file_tab2 is None:
            st.info("👆 Upload a file to begin")
        else:
            st.success("✓ File uploaded")
    
    if uploaded_file_tab2 is not None:
        try:
            # Load first tab only
            payroll_df, _ = load_two_tab_excel(uploaded_file_tab2)
            input_df_union = normalize_payroll_dataframe(payroll_df)
            
            st.subheader("📄 Input Data Preview")
            st.dataframe(input_df_union.head(20), use_container_width=True, height=250)
            
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Total Shifts", len(input_df_union))
            with col2:
                st.metric("Employees", input_df_union['Name'].nunique())
            with col3:
                st.metric("Total Hours", f"{input_df_union['Duration'].sum():.1f}")
            
            st.markdown("---")
            if st.button("💰 Calculate Union Benefits", type="primary", use_container_width=True, key="process_union"):
                with st.spinner("Calculating union benefits..."):
                    union_df = calculate_union_benefits(input_df_union)
                    st.session_state['union_output_df'] = union_df
                    st.session_state['union_processed'] = True
            
            if st.session_state.get('union_processed', False):
                st.success("✅ Calculation Complete!")
                
                union_df = st.session_state['union_output_df']
                
                st.subheader("📊 Summary")
                col1, col2, col3, col4 = st.columns(4)
                
                with col1:
                    st.metric("Employees", len(union_df))
                with col2:
                    total_actual = union_df['Week 1 Actual Hours'].sum() + union_df['Week 2 Actual Hours'].sum()
                    st.metric("Actual Hours", f"{total_actual:.1f}")
                with col3:
                    st.metric("Payable Hours", f"{union_df['Total Payable Hours'].sum():.1f}")
                with col4:
                    st.metric("Total Cost", f"${union_df['Total Cost ($0.80/hr)'].sum():.2f}")
                
                st.subheader("💰 Union Benefits by Employee")
                st.markdown("*Hours capped at 44 per week. Compare Actual vs Payable to see savings.*")
                st.dataframe(union_df, use_container_width=True, height=400)
                
                # Show examples of capping
                capped = union_df[
                    (union_df['Week 1 Actual Hours'] > 44) | 
                    (union_df['Week 2 Actual Hours'] > 44)
                ]
                
                if len(capped) > 0:
                    with st.expander(f"📌 {len(capped)} Employees with Hours Over 44 (Capping Applied)"):
                        st.dataframe(capped, use_container_width=True)
                
                excel_data_union = to_excel(union_df)
                st.download_button(
                    label="📥 Download Union Benefits Report",
                    data=excel_data_union,
                    file_name=f"union_benefits_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    type="primary",
                    use_container_width=True,
                    key="download_union"
                )
        
        except Exception as e:
            st.error(f"❌ Error processing file: {str(e)}")
            import traceback
            st.code(traceback.format_exc())

# Sidebar info
with st.sidebar:
    st.header("📋 About")
    st.markdown("""
    **Star Security Payroll Tools v4.0**
    
    **Tab 1: Payroll Finisher**
    - Two-tab Excel support
    - Time-based midnight splitting
    - Stat holiday premium pay (1.5x)
    - PHP with 176-hour cap
    - Manual PHP date entry
    - Handles consecutive stats
    - QuickBooks ready
    
    **Tab 2: Union Benefits**
    - $0.80 per hour worked
    - Max 44 hours per week
    - Split by Week 1 & Week 2
    
    ---
    
    **New in v4.0:**
    - ✨ Two-tab Excel format
    - ✨ Precise time-based splitting
    - ✨ 176-hour PHP cap (ESA compliant)
    - ✨ Manual PHP lookback dates
    - ✨ Handles any shift crossing midnight
    
    ---
    
    Star Security Inc. | v4.0
    """)
