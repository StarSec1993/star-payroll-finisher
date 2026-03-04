#!/usr/bin/env python3
"""
Payroll Finisher - Processes biweekly payroll data with overtime calculations

This script:
1. Groups shifts by employee
2. Sorts chronologically by transaction date
3. Tracks cumulative hours to identify when 88-hour threshold is hit
4. Splits shifts at the 88-hour mark
5. Converts hours after 88 to overtime rate codes (adds " OT/ STAT")
6. Consolidates hours by rate code
7. Outputs processed payroll data
"""

import pandas as pd
from datetime import datetime
import sys

def process_payroll(input_file, output_file):
    """
    Process payroll data with overtime calculations
    
    Args:
        input_file: Path to input Excel file
        output_file: Path to output Excel file
    """
    # Read the Excel file
    print(f"Reading {input_file}...")
    df = pd.read_excel(input_file)
    
    # Ensure Transaction Date is datetime
    df['Transaction Date'] = pd.to_datetime(df['Transaction Date'])
    
    # Sort by Name and Transaction Date to process chronologically
    df = df.sort_values(['Name', 'Transaction Date']).reset_index(drop=True)
    
    # Process each employee
    processed_rows = []
    
    for employee_name in df['Name'].unique():
        print(f"Processing {employee_name}...")
        
        # Get all shifts for this employee
        employee_shifts = df[df['Name'] == employee_name].copy()
        employee_shifts = employee_shifts.sort_values('Transaction Date').reset_index(drop=True)
        
        # Track cumulative hours and process shifts
        cumulative_hours = 0
        regular_hours = {}  # dict to track hours by rate code
        overtime_hours = {}  # dict to track OT hours by rate code
        php_hours = {}  # dict to track PHP (Holiday) hours separately - NOT counted toward OT
        first_date = employee_shifts['Transaction Date'].iloc[0]
        
        for idx, shift in employee_shifts.iterrows():
            shift_hours = shift['Duration']
            rate_code = shift['Payroll Item']
            
            # Check if this is PHP (Holiday) - ESA entitlement, not worked hours
            if rate_code == 'PHP (Holiday)' or rate_code == 'PHP(Holiday)':
                # PHP hours do NOT count toward overtime threshold
                if rate_code not in php_hours:
                    php_hours[rate_code] = 0
                php_hours[rate_code] += shift_hours
                # Do NOT add to cumulative_hours - continue to next shift
                continue
            
            # Calculate where this shift falls relative to 88-hour threshold
            hours_before_threshold = cumulative_hours
            hours_after_adding_shift = cumulative_hours + shift_hours
            
            if hours_after_adding_shift <= 88:
                # Entire shift is regular time
                if rate_code not in regular_hours:
                    regular_hours[rate_code] = 0
                regular_hours[rate_code] += shift_hours
                
            elif hours_before_threshold >= 88:
                # Entire shift is overtime
                ot_rate_code = f"{rate_code} OT/ STAT"
                if ot_rate_code not in overtime_hours:
                    overtime_hours[ot_rate_code] = 0
                overtime_hours[ot_rate_code] += shift_hours
                
            else:
                # Shift spans the 88-hour threshold - need to split
                regular_portion = 88 - hours_before_threshold
                overtime_portion = shift_hours - regular_portion
                
                # Add regular portion
                if rate_code not in regular_hours:
                    regular_hours[rate_code] = 0
                regular_hours[rate_code] += regular_portion
                
                # Add overtime portion
                ot_rate_code = f"{rate_code} OT/ STAT"
                if ot_rate_code not in overtime_hours:
                    overtime_hours[ot_rate_code] = 0
                overtime_hours[ot_rate_code] += overtime_portion
            
            # Update cumulative hours
            cumulative_hours += shift_hours
        
        # Create consolidated rows for this employee
        # First add all regular time entries
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
        
        # Then add all overtime entries
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
        
        # Finally add PHP (Holiday) entries - ESA entitlement, not worked hours
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
    
    # Create output dataframe
    output_df = pd.DataFrame(processed_rows)
    
    # Sort by Name and Payroll Item (to keep regular before OT)
    output_df = output_df.sort_values(['Name', 'Payroll Item']).reset_index(drop=True)
    
    # Write to Excel
    print(f"Writing to {output_file}...")
    output_df.to_excel(output_file, index=False)
    
    print(f"✓ Processing complete!")
    print(f"  Processed {len(df['Name'].unique())} employees")
    print(f"  Input: {len(df)} shift lines")
    print(f"  Output: {len(output_df)} consolidated lines")
    
    return output_df

def main():
    if len(sys.argv) < 2:
        print("Usage: python payroll_finisher.py <input_file.xlsx> [output_file.xlsx]")
        print("\nExample:")
        print("  python payroll_finisher.py payroll_input.xlsx")
        print("  python payroll_finisher.py payroll_input.xlsx processed_payroll.xlsx")
        sys.exit(1)
    
    input_file = sys.argv[1]
    
    # Generate output filename if not provided
    if len(sys.argv) >= 3:
        output_file = sys.argv[2]
    else:
        # Default: add "_processed" before the extension
        if input_file.endswith('.xlsx'):
            output_file = input_file.replace('.xlsx', '_processed.xlsx')
        elif input_file.endswith('.xls'):
            output_file = input_file.replace('.xls', '_processed.xlsx')
        else:
            output_file = input_file + '_processed.xlsx'
    
    try:
        process_payroll(input_file, output_file)
    except FileNotFoundError:
        print(f"Error: Could not find file '{input_file}'")
        sys.exit(1)
    except Exception as e:
        print(f"Error processing payroll: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
