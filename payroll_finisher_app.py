#!/usr/bin/env python3
"""
Star Security Payroll Finisher - Web Application
Processes biweekly payroll with overtime calculations
"""

import streamlit as st
import pandas as pd
from io import BytesIO
from datetime import datetime

# Page configuration
st.set_page_config(
    page_title="Star Security - Payroll Finisher",
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

def to_excel(df):
    """Convert dataframe to Excel file in memory"""
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Payroll')
    output.seek(0)
    return output

# Main UI
st.title("⭐ Star Security - Payroll Finisher")
st.markdown("### Biweekly Payroll Processor with Overtime Calculations")

# Sidebar with instructions
with st.sidebar:
    st.header("📋 Instructions")
    st.markdown("""
    1. **Upload** your biweekly payroll Excel file
    2. **Preview** the data to verify it's correct
    3. **Process** the payroll with one click
    4. **Download** the finished file for QuickBooks
    
    ---
    
    ### Key Features
    - ✓ Calculates overtime at 88 hours
    - ✓ Handles multiple pay rates
    - ✓ Splits shifts at OT threshold
    - ✓ Excludes PHP (Holiday) from OT
    - ✓ Consolidates by rate code
    
    ---
    
    ### Requirements
    Your Excel file must have these columns:
    - Name
    - Transaction Date
    - Customer
    - Service Item
    - Payroll Item
    - Duration
    - Class
    - Billable
    - Notes
    """)
    
    st.markdown("---")
    st.caption("Star Security Inc. | Payroll Finisher v1.0")

# Main content area
col1, col2 = st.columns([2, 1])

with col1:
    st.subheader("Upload Payroll File")
    uploaded_file = st.file_uploader(
        "Choose your Excel file (.xlsx)",
        type=['xlsx'],
        help="Upload the raw biweekly payroll export"
    )

with col2:
    st.subheader("Status")
    if uploaded_file is None:
        st.info("👆 Upload a file to begin")
    else:
        st.success("✓ File uploaded")

# Process the file if uploaded
if uploaded_file is not None:
    try:
        # Read the uploaded file
        input_df = pd.read_excel(uploaded_file)
        
        # Show input preview
        st.subheader("📄 Input Data Preview")
        st.dataframe(input_df, use_container_width=True, height=300)
        
        col1, col2, col3 = st.columns([1, 1, 2])
        
        with col1:
            st.metric("Total Shifts", len(input_df))
        with col2:
            st.metric("Employees", input_df['Name'].nunique())
        with col3:
            st.metric("Total Hours", f"{input_df['Duration'].sum():.1f}")
        
        # Process button
        st.markdown("---")
        if st.button("🚀 Process Payroll", type="primary", use_container_width=True):
            with st.spinner("Processing payroll data..."):
                # Process the data
                output_df, stats = process_payroll_data(input_df)
                
                # Store in session state
                st.session_state['output_df'] = output_df
                st.session_state['stats'] = stats
                st.session_state['processed'] = True
        
        # Show results if processed
        if st.session_state.get('processed', False):
            st.success("✅ Processing Complete!")
            
            # Stats
            st.subheader("📊 Summary Statistics")
            col1, col2, col3, col4 = st.columns(4)
            
            stats = st.session_state['stats']
            with col1:
                st.metric("Employees Processed", stats['employees_processed'])
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
                st.metric("PHP (Holiday) Hours", f"{stats['total_php_hours']:.1f}")
            
            # Show output preview
            st.subheader("✨ Processed Output")
            st.dataframe(st.session_state['output_df'], use_container_width=True, height=400)
            
            # Download button
            excel_data = to_excel(st.session_state['output_df'])
            
            st.download_button(
                label="📥 Download Processed Payroll",
                data=excel_data,
                file_name=f"payroll_processed_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                type="primary",
                use_container_width=True
            )
            
            st.info("💡 Tip: The downloaded file is ready to import into QuickBooks")
            
    except Exception as e:
        st.error(f"❌ Error processing file: {str(e)}")
        st.exception(e)

else:
    # Show help when no file is uploaded
    st.markdown("---")
    st.subheader("🎯 How It Works")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("""
        **Overtime Calculation**
        - Processes shifts chronologically
        - Tracks cumulative hours per employee
        - Splits shifts at exactly 88 hours
        - Everything after 88 becomes OT
        - Adds " OT/ STAT" to rate codes
        """)
    
    with col2:
        st.markdown("""
        **PHP (Holiday) Handling**
        - ESA public holiday entitlement
        - NOT counted toward 88-hour threshold
        - Appears separately in output
        - Paid at $30/hour for all staff
        - Only appears after statutory holidays
        """)
    
    st.markdown("---")
    st.subheader("📝 Example")
    
    st.markdown("""
    **Employee works 107.5 hours with multiple rates:**
    - 59 hours @ 23.50 Rate (regular)
    - 12.5 hours @ 18 Rate (regular)
    - 16.5 hours @ 23.50 Rate (regular)
    - *(88 hours reached)*
    - 7.5 hours @ 23.50 Rate → **becomes OT**
    - 12 hours @ 18 Rate → **becomes OT**
    
    **Output:**
    - 23.50 Rate: 75.5 hours
    - 18 Rate: 12.5 hours
    - 23.50 Rate OT/ STAT: 7.5 hours
    - 18 Rate OT/ STAT: 12 hours
    """)
