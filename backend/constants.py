# backend/constants.py

# Default assumptions
economic_assumptions = {
    "WAGE_GROWTH": 3.0,               # Annual wage growth as percentage
    "EMPLOYER_CONTRIBUTION_RATE": 12.0,  # Employer super contribution percentage
    "INVESTMENT_RETURN": 8.0,         # Gross annual investment return percentage
    "INFLATION_RATE": 2.5,            # Annual inflation rate percentage
    "RETIREMENT_INVESTMENT_RETURN": 6.0  # Gross annual investment return percentage in retirement (more conservative)
}

# Age Pension parameters (as of 2025)
age_pension_params = {
    "MAX_PENSION_SINGLE": 30558.00,  # Maximum annual pension for singles
    "MAX_PENSION_COUPLE": 46065.00,  # Maximum annual pension for couples (combined)
    "ASSETS_THRESHOLD_HOMEOWNER_SINGLE": 294500,  # Assets threshold for single homeowners
    "ASSETS_THRESHOLD_HOMEOWNER_COUPLE": 443500,  # Assets threshold for couple homeowners
    "ASSETS_THRESHOLD_NON_HOMEOWNER_SINGLE": 505500,  # Assets threshold for single non-homeowners
    "ASSETS_THRESHOLD_NON_HOMEOWNER_COUPLE": 654500,  # Assets threshold for couple non-homeowners
    "ASSETS_TAPER_RATE": 0.00375,  # Assets test taper rate (fortnightly reduction per dollar over threshold)
    "INCOME_THRESHOLD_SINGLE": 198.00,  # Fortnightly income threshold for singles
    "INCOME_THRESHOLD_COUPLE": 352.00,  # Fortnightly income threshold for couples (combined)
    "INCOME_TAPER_RATE": 0.50,  # Income test taper rate (reduction per dollar over threshold)
    "DEEMING_THRESHOLD_SINGLE": 60400,  # Deeming threshold for single
    "DEEMING_THRESHOLD_COUPLE": 100800,  # Deeming threshold for couple
    "DEEMING_RATE_LOWER": 0.020,  # Lower deeming rate
    "DEEMING_RATE_HIGHER": 0.035,  # Higher deeming rate
}