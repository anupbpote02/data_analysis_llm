import streamlit as st
import pandas as pd
import openai
import matplotlib.pyplot as plt
import seaborn as sns
import warnings
import datetime
import base64
from io import BytesIO


st.set_page_config(
    page_title="Ask Your CSV",
    page_icon="📊",
    layout="wide"
)

# Initialize OpenAI client
client = openai.OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

# Helper function for export
def export_conversation():
    """Export conversation history as HTML (works like PDF when printed)"""
    if not st.session_state.messages:
        return None
    
    # Create HTML content with embedded styles
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 40px; }}
            h1 {{ color: #333; }}
            h2 {{ color: #666; margin-top: 30px; }}
            h3 {{ color: #888; margin-top: 20px; }}
            .question {{ background-color: #f0f0f0; padding: 10px; border-radius: 5px; margin: 10px 0; }}
            .answer {{ padding: 10px; margin: 10px 0; }}
            .metadata {{ color: #999; font-size: 14px; }}
            code {{ background-color: #f5f5f5; padding: 2px 4px; border-radius: 3px; }}
            pre {{ background-color: #f5f5f5; padding: 10px; border-radius: 5px; overflow-x: auto; }}
        </style>
    </head>
    <body>
        <h1>Data Analysis Report</h1>
        <p class="metadata">Generated on: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}</p>
    """
    
    # Add data summary
    if st.session_state.df is not None:
        html_content += f"""
        <h2>Dataset Information</h2>
        <ul>
            <li>Total Rows: {st.session_state.df.shape[0]}</li>
            <li>Total Columns: {st.session_state.df.shape[1]}</li>
            <li>Column Names: {', '.join(st.session_state.df.columns)}</li>
        </ul>
        """
    
    # Add conversation
    html_content += "<h2>Analysis Conversation</h2>"
    for msg in st.session_state.messages:
        if msg["role"] == "user":
            html_content += f'<div class="question"><strong>Question:</strong> {msg["content"]}</div>'
        else:
            # Convert markdown code blocks to HTML
            content = msg["content"].replace("```python", "<pre><code>").replace("```", "</code></pre>")
            html_content += f'<div class="answer"><strong>Analysis:</strong><br>{content}</div>'
            if "figure" in msg:
                html_content += '<p><em>[Visualization generated - see application for details]</em></p>'
    
    html_content += """
    </body>
    </html>
    """
    
    return html_content

# Session state initialization
if "messages" not in st.session_state:
    st.session_state.messages = []
if "df" not in st.session_state:
    st.session_state.df = None
if "data_summary" not in st.session_state:
    st.session_state.data_summary = None

st.title("📊 Ask Your CSV")
st.markdown("Upload your data and ask questions in plain English!")

# Sidebar for file upload
with st.sidebar:
    st.header("📁 Data Upload")
    uploaded_file = st.file_uploader("Upload a CSV file", type=["csv"])
    
    if uploaded_file:
        try:
            df = pd.read_csv(uploaded_file)
            st.session_state.df = df
            
            # Create data summary for token optimization
            st.session_state.data_summary = {
                "shape": df.shape,
                "columns": df.columns.tolist(),
                "dtypes": df.dtypes.to_dict(),
                "sample": df.head(3).to_dict(),
                "stats": df.describe().to_dict() if not df.empty else {}
            }
            
            st.success(f"✅ Loaded {df.shape[0]} rows × {df.shape[1]} columns")
            
            # Data preview
            with st.expander("Preview Data"):
                st.dataframe(df.head())
                
            # Basic stats
            with st.expander("Data Summary"):
                col1, col2 = st.columns(2)
                with col1:
                    st.metric("Total Rows", df.shape[0])
                    st.metric("Total Columns", df.shape[1])
                with col2:
                    st.metric("Memory Usage", f"{df.memory_usage().sum() / 1024:.1f} KB")
                    st.metric("Missing Values", df.isnull().sum().sum())
                    
        except Exception as e:
            st.error(f"Error reading file: {str(e)}")
            st.info("Please make sure your file is a valid CSV format.")
    else:
        st.info("👆 Upload a CSV file to start analyzing!")
    
    # Export options (only show if there are messages)
    if st.session_state.messages:
        st.sidebar.markdown("---")
        st.sidebar.header("💾 Export Options")
        if st.sidebar.button("Generate Report"):
            export_html = export_conversation()
            st.sidebar.download_button(
                label="📥 Download Report (HTML)",
                data=export_html,
                file_name=f"data_analysis_{datetime.datetime.now().strftime('%Y%m%d_%H%M')}.html",
                mime="text/html"
            )
            st.sidebar.info("💡 Tip: Open the HTML file and print to PDF for best results")


# Main chat interface
if st.session_state.df is not None:
    # Display chat history
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            # Re-display any saved figures
            if "figure" in msg:
                st.pyplot(msg["figure"])
    
    # Chat input
    user_input = st.chat_input("Ask a question about your data")
    
    if user_input:
        # Add user message to history
        st.session_state.messages.append({"role": "user", "content": user_input})
        
        # Display user message
        with st.chat_message("user"):
            st.markdown(user_input)
        
        # Prepare data context with token optimization
        df = st.session_state.df
        if len(df) > 100:
            data_context = f"""
            Dataset shape: {st.session_state.data_summary['shape']}
            Columns: {', '.join(st.session_state.data_summary['columns'])}
            Data types: {st.session_state.data_summary['dtypes']}
            Sample rows: {st.session_state.data_summary['sample']}
            Basic statistics: {st.session_state.data_summary['stats']}
            """
        else:
            data_context = f"""
            Full dataset:
            {df.to_string()}
            """
        
        # Enhanced system prompt
        system_prompt = f"""You are a helpful data analyst assistant. 
        
        The user has uploaded a CSV file with the following information:
        {data_context}
        
        The data is loaded in a pandas DataFrame called `df`.
        
        Guidelines:
        - Answer the user's question clearly and concisely
        - If the question requires analysis, write Python code using pandas, matplotlib, or seaborn
        - For visualizations, always use plt.figure() before plotting and include plt.tight_layout()
        - Always validate data before operations (check for nulls, data types, etc.)
        - If you can't answer due to data limitations, explain why
        - Keep responses focused on the data and question asked
        - Summarize your findings, insights, and any relevant statistics or visual trends.
        - Focus on delivering the results and what they mean, not on how to get them.
        - If a chart or visualization would help, display the chart in the response using matplotlib or seaborn.
        - If a user asks for a specific visualization, display the chart in the response using matplotlib or seaborn.
        
        When writing code:
        - Import statements are already done (pandas as pd, matplotlib.pyplot as plt, seaborn as sns)
        - The dataframe is available as 'df'
        - For plots, use plt.figure(figsize=(10, 6)) for better display
        - Always add titles and labels to plots
        """
        
        # Generate response
        with st.chat_message("assistant"):
            message_placeholder = st.empty()
            with st.spinner("Analyzing your data..."):
                try:
                    # Get conversation history for context
                    messages = [{"role": "system", "content": system_prompt}]
                    
                    # Include last 3 exchanges for context
                    for msg in st.session_state.messages[-6:]:
                        content = msg["content"]
                        # Truncate long messages in history to save tokens
                        if len(content) > 500:
                            content = content[:500] + "..."
                        messages.append({"role": msg["role"], "content": content})
                    
                    messages.append({"role": "user", "content": user_input})
                    
                    response = client.chat.completions.create(
                        model="gpt-4.1",
                        messages=messages,
                        temperature=0.1,
                        max_tokens=1500
                    )
                    
                    reply = response.choices[0].message.content
                    message_placeholder.markdown(reply)
                    
                    # Try to execute any code in the response
                    if "```python" in reply:
                        code_blocks = reply.split("```python")
                        for i in range(1, len(code_blocks)):
                            code = code_blocks[i].split("```")[0]
                            
                            try:
                                # Capture warnings
                                with warnings.catch_warnings(record=True) as w:
                                    warnings.simplefilter("always")
                                    
                                    # Create figure for potential plots
                                    plt.figure(figsize=(10, 6))
                                    
                                    # Execute code in controlled environment
                                    exec_globals = {
                                        "df": df,
                                        "pd": pd,
                                        "plt": plt,
                                        "sns": sns,
                                        "st": st
                                    }
                                    
                                    exec(code.strip(), exec_globals)
                                    
                                    # Display any warnings
                                    if w:
                                        for warning in w:
                                            st.info(f"Note: {warning.message}")
                                    
                                    # Display plot if created
                                    fig = plt.gcf()
                                    if fig.get_axes():
                                        st.pyplot(fig)
                                        # Save figure in message for persistence
                                        st.session_state.messages.append({
                                            "role": "assistant",
                                            "content": reply,
                                            "figure": fig
                                        })
                                    else:
                                        st.session_state.messages.append({
                                            "role": "assistant",
                                            "content": reply
                                        })
                                    
                                    plt.close()
                                
                            except Exception as e:
                                error_type = type(e).__name__
                                st.error(f"Code execution failed: {error_type}")
                                
                                # Provide helpful context based on error type
                                if "NameError" in str(e):
                                    st.info("This might mean a column name is misspelled or doesn't exist.")
                                elif "TypeError" in str(e):
                                    st.info("This often happens when trying to plot non-numeric data.")
                                elif "KeyError" in str(e):
                                    st.info("The specified column might not exist in your dataset.")
                                else:
                                    st.info("Try rephrasing your question or check your data format.")
                                
                                st.code(code, language="python")
                    else:
                        # No code in response
                        st.session_state.messages.append({
                            "role": "assistant",
                            "content": reply
                        })
                    
                except openai.APIError as e:
                    st.error(f"OpenAI API Error: {str(e)}")
                    st.info("Please check your API key and try again.")
                except Exception as e:
                    st.error(f"Error generating response: {str(e)}")
                    st.info("Please try again or rephrase your question.")
else:
    # No data uploaded state
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.info("👈 Please upload a CSV file to start")
        
        # Example questions
        st.markdown("### 💡 Example questions you can ask:")
        st.markdown("""
        - What are the main trends in my data?
        - Show me a correlation matrix
        - Create a bar chart of the top 10 categories
        - What's the average value by month?
        - Are there any outliers in the price column?
        """)

# Footer with tips
st.markdown("---")
st.markdown("""
<div style='text-align: center; color: gray; font-size: 12px;'>
💡 Tip: Be specific with your questions for better results | 
🔒 Your data stays private and is not stored
</div>
""", unsafe_allow_html=True)