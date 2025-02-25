import plotly.express as px
import base64
import io

def generate_fee_bar_chart(fees: list) -> str:
    """
    Generate a bar chart as a base64-encoded PNG image (embedded in markdown)
    from a list of tuples (fund_name, fee_value).
    """
    print("DEBUG charts.py: Generating fee bar chart with fees:", fees)
    # Extract fund names and fee values.
    fund_names = [f[0] for f in fees]
    fee_values = [f[1] for f in fees]
    
    # Create the bar chart.
    fig = px.bar(
        x=fund_names,
        y=fee_values,
        labels={'x': 'Fund Name', 'y': 'Total Fee ($)'},
        title='Total Superannuation Fees by Fund'
    )
    fig.update_layout(xaxis_title="Fund Name", yaxis_title="Total Fee ($)")
    
    # Convert the figure to an image (specify engine "kaleido")
    try:
        img_bytes = fig.to_image(format="png", engine="kaleido")
        print("DEBUG charts.py: Generated image bytes, length:", len(img_bytes))
    except Exception as e:
        print("DEBUG charts.py: Error generating image:", e)
        return "Chart generation failed."
    
    # Encode the image to base64.
    try:
        encoded = base64.b64encode(img_bytes).decode("utf-8")
        print("DEBUG charts.py: Encoded image length:", len(encoded))
    except Exception as e:
        print("DEBUG charts.py: Error encoding image:", e)
        return "Chart encoding failed."
    
    # Return markdown code embedding the image.
    markdown_img = f"![Fee Comparison](data:image/png;base64,{encoded})"
    print("DEBUG charts.py: Returning markdown image.")
    return markdown_img
