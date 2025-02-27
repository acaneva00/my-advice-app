# backend/cashflow.py
def calculate_income_net_of_super(income, super_included, employer_contribution_rate):
    """
    Calculate income excluding super contributions
    
    Args:
        income: Total income provided by user
        super_included: Boolean indicating if super is included in income
        employer_contribution_rate: Employer super contribution rate (percentage)
        
    Returns:
        Income excluding super contributions
    """
    if super_included:
        # If income includes super, we need to back-calculate the base income
        return income / (1 + employer_contribution_rate/100)
    else:
        # If super is on top, income net of super is the same as provided income
        return income

def calculate_after_tax_income(income, age):
    """
    Calculate after-tax income based on Australian tax rates
    
    Args:
        income: Annual income excluding super
        age: Age of the individual
        
    Returns:
        After-tax annual income
    """
    # Australian 2024-2025 tax brackets
    tax_brackets = [
        (0, 18200, 0, 0),
        (18201, 45000, 0.16, 0),
        (45001, 135000, 0.30, 4288),
        (135001, 190000, 0.37, 31288),
        (190001, float('inf'), 0.45, 51638)
    ]
    
    # Calculate base tax
    tax = 0
    for min_income, max_income, rate, base in tax_brackets:
        if income > min_income:
            taxable_in_bracket = min(income, max_income) - min_income
            tax += taxable_in_bracket * rate + (base if income >= max_income else 0)
    
    # Apply Medicare levy (2%)
    medicare_levy = income * 0.02
    
    # Apply Low Income Tax Offset (LITO)
    lito = 0
    if income <= 37500:
        lito = 700
    elif income <= 45000:
        lito = 700 - ((income - 37500) * 0.05)
    elif income <= 66667:
        lito = 325 - ((income - 45000) * 0.015)
    
    # Apply Low and Middle Income Tax Offset (LMITO) if applicable
    # Note: LMITO was discontinued after 2021-2022, but included here as example
    lmito = 0
    
    # Apply Senior and Pensioner Tax Offset (SAPTO) if eligible
    sapto = 0
    if age >= 67:  # Pension age
        if income <= 32279:
            sapto = 2230
        elif income <= 50119:
            sapto = 2230 - ((income - 32279) * 0.125)
    
    # Calculate final tax
    total_tax = tax + medicare_levy - lito - lmito - sapto
    total_tax = max(0, total_tax)  # Tax cannot be negative
    
    # After-tax income
    after_tax_income = income - total_tax
    
    return after_tax_income