#!/usr/bin/env python3
"""
Star Security Payroll Tools - Web Application
Tab 1: Payroll Finisher (Overtime Calculations)
Tab 2: Union Benefits Calculator
"""

import streamlit as st
import pandas as pd
from io import BytesIO
from datetime import datetime, timedelta

# Page configuration
st.set_page_config(
    page_title="Star Security - Payroll Tools",
    page_icon="⭐",
    layout="wide"
)

def process_payroll_data(df):
    """
    Process payroll data with overtime calculations
    Returns processed dataframe and summary statistics
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
                ot_rate_code = f"{rate_code} OT/ STAT"
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
                ot_rate_code = f"{rate_code} OT/ STAT"
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
    
    output_df = pd.DataFrame(results)
    output_df = output_df.sort_values('Name').reset_index(drop=True)
    
    return output_df

def to_excel(df):
    """Convert dataframe to Excel file in memory"""
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Data')
    output.seek(0)
    return output

# Main UI
st.title("⭐ Star Security - Payroll Tools")

# Create tabs
tab1, tab2 = st.tabs(["📊 Payroll Finisher", "💰 Union Benefits Calculator"])

# ============================================================================
# TAB 1: PAYROLL FINISHER (Original functionality)
# ============================================================================
with tab1:
    st.markdown("### Biweekly Payroll Processor with Overtime Calculations")
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.subheader("Upload Payroll File")
        uploaded_file_tab1 = st.file_uploader(
            "Choose your Excel file (.xlsx)",
            type=['xlsx'],
            help="Upload the raw biweekly payroll export",
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
            st.dataframe(input_df, use_container_width=True, height=300)
            
            col1, col2, col3 = st.columns([1, 1, 2])
            with col1:
                st.metric("Total Shifts", len(input_df))
            with col2:
                st.metric("Employees", input_df['Name'].nunique())
            with col3:
                st.metric("Total Hours", f"{input_df['Duration'].sum():.1f}")
            
            st.markdown("---")
            if st.button("🚀 Process Payroll", type="primary", use_container_width=True, key="process_payroll"):
                with st.spinner("Processing payroll data..."):
                    output_df, stats = process_payroll_data(input_df)
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
                
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Regular Hours", f"{stats['total_regular_hours']:.1f}")
                with col2:
                    st.metric("Overtime Hours", f"{stats['total_ot_hours']:.1f}")
                with col3:
                    st.metric("PHP (Holiday)", f"{stats['total_php_hours']:.1f}")
                
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
    **Star Security Payroll Tools**
    
    **Tab 1: Payroll Finisher**
    - Processes overtime at 88 hours
    - Handles multiple pay rates
    - Excludes PHP (Holiday) from OT
    - QuickBooks ready
    
    **Tab 2: Union Benefits**
    - Calculates union contributions
    - $0.80 per hour worked
    - Max 44 hours per week
    - Split by Week 1 & Week 2
    
    ---
    
    Star Security Inc. | v2.0
    """)
