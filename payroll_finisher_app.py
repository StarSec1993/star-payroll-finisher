#!/usr/bin/env python3
"""
Star Security Payroll Tools - Web Application with Stat Holiday & PHP
Tab 1: Payroll Finisher (Overtime + Stat Holidays + PHP)
Tab 2: Union Benefits Calculator
"""

import streamlit as st
import pandas as pd
from io import BytesIO
from datetime import datetime, timedelta
import re

# Page configuration
st.set_page_config(
    page_title="Star Security - Payroll Tools",
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
    match = re.search(r'(\d+)%', notes_str)
    if match:
        return float(match.group(1)) / 100
    
    match = re.search(r'(\d+)\s*percent', notes_str, re.IGNORECASE)
    if match:
        return float(match.group(1)) / 100
    
    return 0.04  # Default 4%

def split_shift_at_midnight(shift_date, shift_hours, stat_dates):
    """
    Split a shift if it crosses midnight on a stat holiday
    Returns list of (date, hours, is_stat) tuples
    """
    shift_segments = []
    
    # Assume shift starts at beginning of date
    current_time = shift_date
    remaining_hours = shift_hours
    
    while remaining_hours > 0:
        current_date = current_time.date()
        
        # Hours until midnight (or end of shift)
        hours_in_current_day = min(remaining_hours, 24)
        
        # Check if current date is a stat
        is_stat = any(current_date == stat_date.date() for stat_date in stat_dates)
        
        shift_segments.append((current_date, hours_in_current_day, is_stat))
        
        remaining_hours -= hours_in_current_day
        current_time += timedelta(days=1)
    
    return shift_segments

def process_payroll_data_with_stats(df, period_start, period_end, stat_dates=None):
    """
    Process payroll data with stat holiday handling and PHP calculation
    """
    if stat_dates is None:
        stat_dates = []
    
    # Convert stat dates to datetime
    stat_dates = [pd.to_datetime(d) for d in stat_dates]
    
    # Ensure Transaction Date is datetime
    df['Transaction Date'] = pd.to_datetime(df['Transaction Date'])
    
    # Filter to payroll period
    period_df = df[
        (df['Transaction Date'] >= period_start) & 
        (df['Transaction Date'] <= period_end)
    ].copy()
    
    # Get lookback data for PHP (4 weeks before each stat)
    lookback_data = {}
    for stat_date in stat_dates:
        lookback_start = stat_date - timedelta(days=28)
        lookback_end = stat_date - timedelta(days=1)
        
        lookback_df = df[
            (df['Transaction Date'] >= lookback_start) & 
            (df['Transaction Date'] <= lookback_end)
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
            
            # Split shift if it crosses stat dates
            shift_segments = split_shift_at_midnight(shift_date, shift_hours, stat_dates)
            
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
        
        # Calculate PHP for this employee
        php_total_hours = 0
        
        for stat_date in stat_dates:
            if stat_date not in lookback_data:
                continue
            
            lookback_df = lookback_data[stat_date]
            employee_lookback = lookback_df[lookback_df['Name'] == employee_name].copy()
            
            if len(employee_lookback) == 0:
                continue
            
            # Calculate regular wages (exclude stat/OT hours from lookback)
            total_wages = 0
            vacation_pct = 0.04  # Default
            
            for _, lb_shift in employee_lookback.iterrows():
                lb_hours = lb_shift['Duration']
                lb_rate_code = lb_shift['Payroll Item']
                lb_notes = lb_shift.get('Notes', '')
                
                if pd.isna(lb_hours) or lb_hours == 0:
                    continue
                
                # Skip stat/OT hours in lookback
                if 'OT' in str(lb_rate_code) or 'STAT' in str(lb_rate_code):
                    continue
                
                # Get rate and vacation %
                rate = extract_rate_from_code(lb_rate_code)
                vacation_pct = max(vacation_pct, extract_vacation_percent(lb_notes))
                
                total_wages += lb_hours * rate
            
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
    output_df = output_df.sort_values(['Name', 'Payroll Item']).reset_index(drop=True)
    
    return output_df, stats

def process_payroll_data(df):
    """
    Original process_payroll_data for non-stat periods
    """
    # Ensure Transaction Date is datetime
    df['Transaction Date'] = pd.to_datetime(df['Transaction Date'])
    
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
            
            # Check if this is PHP (Holiday) - ESA entitlement, not worked hours
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
    output_df = output_df.sort_values(['Name', 'Payroll Item']).reset_index(drop=True)
    
    return output_df, stats

def calculate_union_benefits(df):
    """
    Calculate union benefits with 44-hour weekly cap
    $0.80 per hour, max 44 hours per week
    """
    # Ensure Transaction Date is datetime
    df['Transaction Date'] = pd.to_datetime(df['Transaction Date'])
    
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

st.title("⭐ Star Security - Payroll Tools")
st.markdown("**Professional Payroll Processing & Union Benefits Calculator**")

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
            help="Upload the raw payroll export (may include extra weeks for PHP lookback)",
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
            input_df = pd.read_excel(uploaded_file_tab1)
            
            st.subheader("📄 Input Data Preview")
            st.dataframe(input_df, use_container_width=True, height=250)
            
            # Stat Holiday Configuration
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
            
            stat_dates = []
            if has_stat:
                st.markdown("**Enter Stat Holiday Dates (12am-11:59pm each day):**")
                
                num_stats = st.number_input(
                    "Number of stat holidays in this period",
                    min_value=1,
                    max_value=5,
                    value=1,
                    help="How many stats are in this period?",
                    key="num_stats"
                )
                
                cols = st.columns(min(num_stats, 3))
                for i in range(num_stats):
                    with cols[i % 3]:
                        stat_date = st.date_input(
                            f"Stat #{i+1}",
                            value=datetime.now().date(),
                            key=f"stat_date_{i}"
                        )
                        stat_dates.append(stat_date)
                
                st.info(f"💡 For PHP calculation, upload data starting {(min(stat_dates) - timedelta(days=28)).strftime('%B %d, %Y')} (4 weeks before first stat)")
            
            st.markdown("---")
            
            col1, col2, col3 = st.columns([1, 1, 2])
            with col1:
                st.metric("Total Shifts", len(input_df))
            with col2:
                st.metric("Employees", input_df['Name'].nunique())
            with col3:
                st.metric("Total Hours", f"{input_df['Duration'].sum():.1f}")
            
            if st.button("🚀 Process Payroll", type="primary", use_container_width=True, key="process_payroll"):
                with st.spinner("Processing payroll data..."):
                    if has_stat:
                        # Process with stat holidays and PHP
                        output_df, stats = process_payroll_data_with_stats(
                            input_df,
                            pd.to_datetime(period_start),
                            pd.to_datetime(period_end),
                            stat_dates=[pd.to_datetime(d) for d in stat_dates]
                        )
                    else:
                        # Regular processing
                        # Filter to period
                        period_df = input_df[
                            (pd.to_datetime(input_df['Transaction Date']) >= pd.to_datetime(period_start)) &
                            (pd.to_datetime(input_df['Transaction Date']) <= pd.to_datetime(period_end))
                        ].copy()
                        output_df, stats = process_payroll_data(period_df)
                    
                    st.session_state['payroll_output_df'] = output_df
                    st.session_state['payroll_stats'] = stats
                    st.session_state['payroll_processed'] = True
            
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
                    st.metric("Reduction", f"{100 - (stats['output_lines']/stats['input_shifts']*100):.0f}%")
                
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
            input_df_union = pd.read_excel(uploaded_file_tab2)
            
            st.subheader("📄 Input Data Preview")
            st.dataframe(input_df_union, use_container_width=True, height=250)
            
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

# Sidebar info
with st.sidebar:
    st.header("📋 About")
    st.markdown("""
    **Star Security Payroll Tools v3.0**
    
    **Tab 1: Payroll Finisher**
    - Processes overtime at 88 hours
    - Stat holiday premium pay (1.5x)
    - PHP (Public Holiday Pay) calculation
    - Stat hours excluded from OT
    - Handles multiple pay rates
    - QuickBooks ready
    
    **Tab 2: Union Benefits**
    - Calculates union contributions
    - $0.80 per hour worked
    - Max 44 hours per week
    - Split by Week 1 & Week 2
    
    ---
    
    **Stat Holiday Features:**
    - 12am-11:59pm premium pay
    - Automatic shift splitting
    - 4-week PHP lookback
    - Custom vacation % support
    
    ---
    
    Star Security Inc. | Enhanced
    """)
