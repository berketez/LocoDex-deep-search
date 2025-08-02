import os

import gradio as gr

from libs.utils.generation import generate_html
from libs.utils.llms import generate_toc_image
from libs.utils.podcast import full_podcast_generation
from together_open_deep_research import DeepResearcher


def wrap_in_iframe(html_content, width="100%", height="600px"):
    iframe_html = f"""
    <iframe 
        srcdoc="{html_content.replace('"', '&quot;')}" 
        width="{width}" 
        height="{height}" 
        frameborder="0" 
        style="border: 1px solid #eee; border-radius: 8px;"
    ></iframe>
    """
    return iframe_html

def func(query, budget, max_queries, max_sources, 
         planning_model, summarization_model, json_model, answer_model, 
         generate_podcast=True, progress=gr.Progress()):
    
    if not os.environ.get("TOGETHER_API_KEY") or not os.environ.get("TAVILY_API_KEY"):
        missing_keys = []
        if not os.environ.get("TOGETHER_API_KEY"):
            missing_keys.append("TOGETHER_API_KEY")
        if not os.environ.get("TAVILY_API_KEY"):
            missing_keys.append("TAVILY_API_KEY")
            
        error_message = f"Missing API keys in environment variables: {', '.join(missing_keys)}."
        return gr.Warning(error_message)
    
    try:
        researcher = DeepResearcher(
            budget=budget,
            max_queries=max_queries if max_queries > 0 else -1,
            max_sources=max_sources if max_sources > 0 else -1,
            planning_model=planning_model,
            summarization_model=summarization_model,
            json_model=json_model,
            answer_model=answer_model,
            observer=progress
        )
        
        answer = researcher(query)

        progress(0.98, "Generating Cover Image")

        toc_image_url = generate_toc_image(
                researcher.prompts["data_visualization_prompt"], answer_model, query
            )
        
        base64_audio = None
        if generate_podcast:
            progress(0.99, "Generating Podcast")
            base64_audio = full_podcast_generation(system_prompt=researcher.prompts["create_podcast_script_prompt"], text=answer)

        html_content = generate_html(answer, toc_image_url, base64_audio=base64_audio)
        
        iframe_content = wrap_in_iframe(html_content)

        return iframe_content
    
    # this is a catch ALL for the gradio app
    except Exception as e:
        error_message = f"An error occurred: {str(e)}"
        return gr.Warning(error_message)

with gr.Blocks(title="Together Open Deep Research") as demo:
    gr.Markdown("# Together Open Deep Research")

    with gr.Accordion("⚠️ DISCLAIMER ⚠️", open=False):
        gr.Markdown(
            """**Please be aware:**
            
- AI research tools may produce content with bias, stereotypes, or hallucinations
- Results may contain inaccurate or misleading information
- Always verify and fact-check the information provided
- Do not make important decisions based solely on these results without independent verification"""
        )
    
    with gr.Row():
        query_input = gr.Textbox(placeholder="Enter your research topic-..", label="Search Topic", scale=3)
    
    with gr.Accordion("Environment Variables Requirements", open=True):
        gr.Markdown("""**Required Environment Variables:**
- TOGETHER_API_KEY: Get from [Together AI](https://together.ai/)
- TAVILY_API_KEY: Get from [Tavily](https://tavily.com/)

These must be set in your environment before running the application.""")
    
    with gr.Accordion("Advanced Settings", open=False):
        with gr.Row():
            with gr.Column(scale=1):
                budget = gr.Slider(minimum=1, maximum=10, value=2, step=1, label="Research Budget (iterations)")
            
            with gr.Column(scale=1):
                max_queries = gr.Slider(minimum=-1, maximum=5, value=3, step=1, label="Max Queries (-1 for unlimited)")
                max_sources = gr.Slider(minimum=-1, maximum=10, value=10, step=1, label="Max Sources (-1 for unlimited)")
        
        with gr.Row():
            planning_model = gr.Dropdown(
                choices=[
                    "together_ai/Qwen/Qwen2.5-72B-Instruct-Turbo",
                    "together_ai/meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo",
                ],
                value="together_ai/Qwen/Qwen2.5-72B-Instruct-Turbo",
                label="Planning Model"
            )
            
            summarization_model = gr.Dropdown(
                choices=[
                    "together_ai/meta-llama/Llama-3.3-70B-Instruct-Turbo",
                    "together_ai/meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo",
                ],
                value="together_ai/meta-llama/Llama-3.3-70B-Instruct-Turbo",
                label="Summarization Model"
            )
            
        with gr.Row():
            json_model = gr.Dropdown(
                choices=[
                    "together_ai/meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo",
                ],
                value="together_ai/meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo",
                label="JSON Model"
            )
            
            answer_model = gr.Dropdown(
                choices=[
                    "together_ai/deepseek-ai/DeepSeek-V3",
                    "together_ai/deepseek-ai/DeepSeek-R1-Distill-Llama-70B",
                ],
                value="together_ai/deepseek-ai/DeepSeek-V3",
                label="Answer Generation Model"
            )
        
        with gr.Row():
            generate_podcast = gr.Checkbox(value=True, label="Generate Podcast")
    

    
    with gr.Row():
        submit_btn = gr.Button("Submit", variant="primary")
    
    with gr.Row():
        output = gr.HTML(value="<div style='padding: 20px; border: 1px solid #eee; min-height: 600px; border-radius: 8px;'><p style='color: #888;'>Enter a search query and click Submit to see results here</p></div>")
    
    submit_btn.click(
        fn=func, 
        inputs=[
            query_input, budget, max_queries, max_sources, 
            planning_model, summarization_model, json_model, answer_model,
            generate_podcast
        ], 
        outputs=output
    , concurrency_limit=10)

demo.launch()   