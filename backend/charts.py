# Updated charts.py for older Gradio compatibility
import plotly.express as px
import base64

def generate_fee_bar_chart(fees: list) -> str:
    """
    Generate a simple HTML table for fee comparison - compatible with older Gradio
    """
    # Sort fees by amount (ascending)
    sorted_fees = sorted(fees, key=lambda x: x[1])
    
    # Generate an HTML table
    rows = ""
    for fund_name, fee in sorted_fees:
        rows += f"""
            <tr>
                <td style="padding: 8px; border-bottom: 1px solid #ddd;">{fund_name}</td>
                <td style="padding: 8px; border-bottom: 1px solid #ddd; text-align: right;">${fee:,.2f}</td>
            </tr>
        """
    
    html = f"""
    <div style="border: 1px solid #ddd; border-radius: 8px; padding: 15px; margin: 10px 0; background-color: white;">
        <h3 style="margin-top: 0;">Total Superannuation Fees by Fund</h3>
        <table style="width: 100%; border-collapse: collapse;">
            <tr>
                <th style="text-align: left; padding: 8px; border-bottom: 2px solid #ddd;">Fund Name</th>
                <th style="text-align: right; padding: 8px; border-bottom: 2px solid #ddd;">Annual Fee</th>
            </tr>
            {rows}
        </table>
    </div>
    """
    
    return html